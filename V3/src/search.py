from __future__ import annotations

import asyncio
import html
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Awaitable, Callable
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_TITLE_SOURCE_TAIL_RE = re.compile(r"\s*[-|—_]+\s*")
_SOURCE_TOKEN_HINT_RE = re.compile(
    r"(网|报|社|台|频道|新闻|资讯|财经|日报|晚报|观察|客户端|之声|news|finance|cn|com)$",
    flags=re.IGNORECASE,
)


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str
    published_at: str
    from_rss: bool = False


ENCYCLOPEDIA_BLOCKLIST = (
    "baike.baidu.com",
    "wikipedia.org",
    "zh.wikipedia.org",
    "en.wikipedia.org",
    "hudong.com",
    "baike.com",
)

SEARCH_SOURCE_BLOCKLIST = (
    "rfi.fr",
    "radiofrance.fr",
)


def _is_blocked_url(url: str) -> bool:
    raw = (url or "").strip()
    if not raw:
        return True
    try:
        host = (urlparse(raw).hostname or "").lower()
    except Exception:
        host = raw.lower()
    if any(dom in host for dom in ENCYCLOPEDIA_BLOCKLIST):
        return True
    return any(dom in host for dom in SEARCH_SOURCE_BLOCKLIST)


def _dedupe_hits(rows: list[SearchHit], *, max_results: int) -> list[SearchHit]:
    seen: set[str] = set()
    out: list[SearchHit] = []
    for row in rows:
        key = row.url.strip().lower().rstrip("/")
        if not key or key in seen:
            continue
        if _is_blocked_url(row.url):
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= max_results:
            break
    return out


def merge_search_hits(*chunks: list[SearchHit], max_total: int) -> list[SearchHit]:
    merged: list[SearchHit] = []
    for c in chunks:
        merged.extend(c)
    return _dedupe_hits(merged, max_results=max_total)


def normalize_title(raw_title: str) -> str:
    title = " ".join((raw_title or "").strip().split())
    if not title:
        return "未命名"
    for _ in range(3):
        parts = _TITLE_SOURCE_TAIL_RE.split(title)
        if len(parts) < 2:
            break
        tail = (parts[-1] or "").strip()
        if not tail:
            title = " - ".join(parts[:-1]).strip()
            continue
        tail_compact = tail.replace(" ", "")
        if len(tail_compact) <= 16 or _SOURCE_TOKEN_HINT_RE.search(tail_compact):
            title = " - ".join(parts[:-1]).strip()
            continue
        break
    return title or "未命名"


def normalize_snippet(raw_snippet: str) -> str:
    snippet = raw_snippet or ""
    snippet = re.sub(r"<[^>]+>", " ", snippet)
    snippet = html.unescape(snippet)
    snippet = snippet.replace("**", "")
    snippet = re.sub(r"\s+", " ", snippet).strip()
    return snippet


async def _search_site_then_global_async(
    *,
    query: str,
    max_results: int,
    target_sites: list[str],
    call: Callable[[str, int], Awaitable[list[SearchHit]]],
    allow_global_fallback: bool = True,
) -> list[SearchHit]:
    """先按站点域名约束（GDELT ``domain:``），再全域同一 ``query``。"""
    started = perf_counter()
    merged: list[SearchHit] = []
    per_call = max(3, min(max_results, 10))
    for site in target_sites:
        scoped_query = f"({query}) domain:{site}"
        try:
            merged.extend(await call(scoped_query, per_call))
        except Exception:
            logger.warning("site-scoped gdelt failed: site=%s query=%s", site, query, exc_info=True)
    merged = _dedupe_hits(merged, max_results=max_results)
    if merged:
        logger.info(
            "site-scoped satisfied query=%s sites=%d rows=%d elapsed=%.2fs",
            query,
            len(target_sites),
            len(merged),
            perf_counter() - started,
        )
        return merged
    if not allow_global_fallback:
        logger.info("site-scoped empty, no global fallback query=%s sites=%d", query, len(target_sites))
        return []
    logger.info("site-scoped empty, fallback to global query=%s sites=%d", query, len(target_sites))
    try:
        merged = await call(query, max_results)
    except Exception:
        logger.warning("global gdelt failed: query=%s", query, exc_info=True)
        return []
    out = _dedupe_hits(merged, max_results=max_results)
    logger.info(
        "global fallback done query=%s rows=%d elapsed=%.2fs",
        query,
        len(out),
        perf_counter() - started,
    )
    return out


async def _with_retries(
    *,
    label: str,
    call: Callable[[], Awaitable[list[SearchHit]]],
    max_attempts: int = 3,
    call_timeout_sec: float = 90.0,
) -> list[SearchHit]:
    for attempt in range(1, max_attempts + 1):
        try:
            rows = await asyncio.wait_for(call(), timeout=call_timeout_sec)
            if rows:
                logger.info("search tool=%s success on attempt=%d rows=%d", label, attempt, len(rows))
                return rows
            logger.warning("search tool=%s empty result on attempt=%d", label, attempt)
        except asyncio.TimeoutError:
            logger.warning("search tool=%s timeout on attempt=%d timeout=%.1fs", label, attempt, call_timeout_sec)
        except Exception:
            logger.warning("search tool=%s failed on attempt=%d", label, attempt, exc_info=True)
        if attempt < max_attempts:
            await asyncio.sleep(min(2 * attempt, 5))
    return []


async def search_with_toolchain(
    *,
    query: str,
    max_results: int,
    target_sites: list[str],
    max_attempts_per_tool: int = 3,
    allow_global_fallback: bool = True,
) -> tuple[list[SearchHit], str]:
    """
    GDELT DOC 检索：站点阶段 ``(query) domain:host``，失败或关闭回退时再跑全域 ``query``。
    """
    from src.config import Settings
    from src.gdelt_search import gdelt_doc_search, gdelt_timespan_for_hours

    s = Settings()
    ts = gdelt_timespan_for_hours(s.max_article_age_hours)
    to = float(s.gdelt_timeout_sec)
    bu = (s.gdelt_base_url or "https://api.gdeltproject.org/api/v2/doc/doc").strip()
    cap = max(1, min(int(s.gdelt_max_records), 75))

    async def gdelt_call(q: str, n: int) -> list[SearchHit]:
        return await gdelt_doc_search(
            query=q,
            max_results=min(int(n), cap),
            timespan=ts,
            timeout=to,
            base_url=bu,
        )

    rows = await _with_retries(
        label="gdelt_doc",
        call=lambda: _search_site_then_global_async(
            query=query,
            max_results=max_results,
            target_sites=target_sites,
            call=gdelt_call,
            allow_global_fallback=allow_global_fallback,
        ),
        max_attempts=max_attempts_per_tool,
        call_timeout_sec=max(to * 2, 60.0),
    )
    if rows:
        return rows, "gdelt_doc"
    return [], "paused"


def _chunk_terms(terms: list[str], size: int) -> list[list[str]]:
    if size <= 0:
        size = 10
    return [terms[i : i + size] for i in range(0, len(terms), size)]


async def search_gdelt_topics_bilingual(settings: "object") -> tuple[list[SearchHit], int]:
    """
    主题级 GDELT：按 ``search_keywords.json`` 的 ``chinese_keywords`` / ``english_keywords``
    各组 OR 查询（过长则分批），带并发上限与请求间隔，降低 429。

    Returns:
        (合并去重后的 hits, GDELT HTTP 请求次数)
    """
    from src.config import Settings
    from src.gdelt_search import gdelt_build_or_query, gdelt_doc_search_with_client, gdelt_timespan_for_hours

    if not isinstance(settings, Settings):
        raise TypeError("settings must be Settings")
    ts = gdelt_timespan_for_hours(settings.max_article_age_hours)
    cap = max(1, min(int(settings.gdelt_max_records), 75))
    to = float(settings.gdelt_timeout_sec)
    bu = (settings.gdelt_base_url or "").strip() or "https://api.gdeltproject.org/api/v2/doc/doc"
    per = max(3, int(settings.gdelt_or_max_terms_per_query))
    sem_n = max(1, int(settings.gdelt_max_concurrent))
    interval = max(0.0, float(settings.gdelt_min_interval_sec))

    zh = settings.parsed_chinese_keywords()
    en = settings.parsed_english_keywords()
    batches: list[tuple[str, str]] = []
    for i, chunk in enumerate(_chunk_terms(zh, per)):
        q = gdelt_build_or_query(chunk)
        if q:
            batches.append((f"zh_batch_{i}", q))
    for i, chunk in enumerate(_chunk_terms(en, per)):
        q = gdelt_build_or_query(chunk)
        if q:
            batches.append((f"en_batch_{i}", q))

    if not batches:
        return [], 0

    merged: list[SearchHit] = []
    http_requests = 0
    sem = asyncio.Semaphore(sem_n)

    async with httpx.AsyncClient(timeout=to, follow_redirects=True) as client:

        async def run_one(label: str, query: str) -> list[SearchHit]:
            nonlocal http_requests
            async with sem:
                await asyncio.sleep(interval)
                for attempt in range(1, 4):
                    try:
                        rows = await gdelt_doc_search_with_client(
                            client,
                            query=query,
                            max_results=cap,
                            timespan=ts,
                            base_url=bu,
                        )
                        http_requests += 1
                        if rows:
                            logger.info(
                                "gdelt topic batch ok label=%s rows=%d attempt=%d",
                                label,
                                len(rows),
                                attempt,
                            )
                            return rows
                        logger.warning("gdelt empty body label=%s (no retry)", label)
                        return []
                    except httpx.HTTPStatusError as exc:
                        http_requests += 1
                        code = exc.response.status_code if exc.response is not None else 0
                        if code == 429 and attempt < 3:
                            wait = min(8.0, 2.0 * attempt)
                            logger.warning("gdelt 429 label=%s attempt=%d sleep=%.1fs", label, attempt, wait)
                            await asyncio.sleep(wait)
                            continue
                        logger.warning("gdelt http label=%s code=%s", label, code, exc_info=True)
                        return []
                    except Exception:
                        http_requests += 1
                        logger.warning("gdelt batch failed label=%s attempt=%d", label, attempt, exc_info=True)
                    if attempt < 3:
                        await asyncio.sleep(min(2.0 * attempt, 6.0))
                return []

        parts = await asyncio.gather(*[run_one(lbl, q) for lbl, q in batches])
    for chunk in parts:
        merged.extend(chunk)
    merged = _dedupe_hits(merged, max_results=max(1500, int(settings.search_max_results) * 50))
    return merged, http_requests


def filter_by_age(rows: list[SearchHit], max_hours: int) -> list[SearchHit]:
    """仅保留「有可用 ``published_at``」且时间在 ``max_hours`` 小时窗内的条目。

    ``published_at`` 为空、仅空白、或无法解析为时间的条目一律剔除（不进入候选）。
    ``max_hours <= 0`` 时不做小时窗比较，但仍要求非空且可解析的 ``published_at``。
    """
    out: list[SearchHit] = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_hours)
    for row in rows:
        raw = (row.published_at or "").strip()
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            continue
        if max_hours <= 0:
            out.append(row)
            continue
        if dt >= cutoff:
            out.append(row)
    return out
