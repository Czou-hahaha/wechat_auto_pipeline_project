from __future__ import annotations

import asyncio
import html
import logging
import re
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Awaitable, Callable
from urllib.parse import urlparse

import httpx
from ddgs import DDGS
from googlenewsdecoder import gnewsdecoder

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


ENCYCLOPEDIA_BLOCKLIST = (
    "baike.baidu.com",
    "wikipedia.org",
    "zh.wikipedia.org",
    "en.wikipedia.org",
    "hudong.com",
    "baike.com",
)


def _is_blocked_url(url: str) -> bool:
    raw = (url or "").strip()
    if not raw:
        return True
    try:
        host = (urlparse(raw).hostname or "").lower()
    except Exception:
        host = raw.lower()
    return any(dom in host for dom in ENCYCLOPEDIA_BLOCKLIST)


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


def normalize_title(raw_title: str) -> str:
    title = " ".join((raw_title or "").strip().split())
    if not title:
        return "未命名"
    # Repeatedly trim tail source marker: "标题 - 新浪网" / "标题 | 21财经".
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
    # RSS snippets may include markdown artifacts like "**427支**".
    snippet = snippet.replace("**", "")
    snippet = re.sub(r"\s+", " ", snippet).strip()
    return snippet


async def google_news_search(query: str, max_results: int, timeout_seconds: float = 12.0) -> list[SearchHit]:
    q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?hl=zh-CN&gl=CN&ceid=CN:zh-Hans&q={q}"
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    return _dedupe_hits(_parse_news_rss(resp.text, max_results=max_results), max_results=max_results)


def _parse_news_rss(text: str, *, max_results: int) -> list[SearchHit]:
    root = ET.fromstring(text)
    rows: list[SearchHit] = []
    for node in root.findall(".//item"):
        t = (node.findtext("title") or "").strip()
        u = (node.findtext("link") or "").strip()
        s = (node.findtext("description") or "").strip()
        p = (node.findtext("pubDate") or "").strip()
        if not t or not u:
            continue
        t = _normalize_google_rss_title(t, s)
        s = normalize_snippet(s)
        u = _decode_google_news_url(u)
        try:
            dt = parsedate_to_datetime(p)
            p_iso = dt.astimezone(timezone.utc).isoformat() if dt else ""
        except Exception:
            p_iso = ""
        rows.append(SearchHit(title=t, url=u, snippet=s, published_at=p_iso))
        if len(rows) >= max_results:
            break
    return rows


def _normalize_google_rss_title(title: str, description: str) -> str:
    t = (title or "").strip()
    if t and t.lower() != "google news":
        return normalize_title(t)
    # Some Google RSS items use "Google News" as title.
    # Fall back to anchor text in description if available.
    m = re.search(r"<a[^>]*>(.*?)</a>", description or "", flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return t or "未命名"
    anchor_text = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
    return normalize_title(anchor_text or (t or "未命名"))


def _decode_google_news_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return raw
    host = (urlparse(raw).hostname or "").lower()
    if "news.google.com" not in host:
        return raw
    try:
        decoded = gnewsdecoder(raw, interval=1)
        if decoded.get("status") and (decoded.get("decoded_url") or "").strip():
            return str(decoded["decoded_url"]).strip()
    except Exception:
        logger.warning("google news url decode failed: %s", raw, exc_info=True)
    return raw


def ddgs_fallback(query: str, max_results: int) -> list[SearchHit]:
    rows: list[SearchHit] = []
    now = datetime.now(timezone.utc).isoformat()
    with DDGS(verify=False) as ddgs:
        for item in ddgs.text(query, max_results=max_results, backend="bing"):
            title = normalize_title(str(item.get("title") or "").strip())
            url = str(item.get("href") or "").strip()
            snippet = normalize_snippet(str(item.get("body") or "").strip())
            if not title or not url:
                continue
            if _is_blocked_url(url):
                continue
            rows.append(SearchHit(title=title, url=url, snippet=snippet, published_at=now))
    return _dedupe_hits(rows, max_results=max_results)


def ddgs_primary_search(query: str, max_results: int) -> list[SearchHit]:
    """
    主 DDGS 工具：限定 backend=bing，减少默认多引擎导致的长阻塞。
    """
    rows: list[SearchHit] = []
    now = datetime.now(timezone.utc).isoformat()
    with DDGS(verify=False) as ddgs:
        for item in ddgs.text(query, max_results=max_results, backend="bing"):
            title = normalize_title(str(item.get("title") or "").strip())
            url = str(item.get("href") or "").strip()
            snippet = normalize_snippet(str(item.get("body") or "").strip())
            if not title or not url:
                continue
            if _is_blocked_url(url):
                continue
            rows.append(SearchHit(title=title, url=url, snippet=snippet, published_at=now))
    return _dedupe_hits(rows, max_results=max_results)


async def _search_site_then_global_async(
    *,
    query: str,
    max_results: int,
    target_sites: list[str],
    call: Callable[[str, int], Awaitable[list[SearchHit]]],
) -> list[SearchHit]:
    # 优先目标站点，然后再做全域检索补充。
    merged: list[SearchHit] = []
    per_call = max(3, min(max_results, 10))
    for site in target_sites:
        scoped_query = f"{query} site:{site}"
        try:
            merged.extend(await call(scoped_query, per_call))
        except Exception:
            logger.warning("site-scoped async search failed: site=%s query=%s", site, query, exc_info=True)
    try:
        merged.extend(await call(query, max_results))
    except Exception:
        logger.warning("global async search failed: query=%s", query, exc_info=True)
    return _dedupe_hits(merged, max_results=max_results)


async def _search_site_then_global_sync(
    *,
    query: str,
    max_results: int,
    target_sites: list[str],
    call: Callable[[str, int], list[SearchHit]],
) -> list[SearchHit]:
    merged: list[SearchHit] = []
    per_call = max(3, min(max_results, 10))
    for site in target_sites:
        scoped_query = f"{query} site:{site}"
        try:
            rows = await asyncio.to_thread(call, scoped_query, per_call)
            merged.extend(rows)
        except Exception:
            logger.warning("site-scoped sync search failed: site=%s query=%s", site, query, exc_info=True)
    try:
        rows = await asyncio.to_thread(call, query, max_results)
        merged.extend(rows)
    except Exception:
        logger.warning("global sync search failed: query=%s", query, exc_info=True)
    return _dedupe_hits(merged, max_results=max_results)


async def _with_retries(
    *,
    label: str,
    call: Callable[[], Awaitable[list[SearchHit]]],
    max_attempts: int = 3,
) -> list[SearchHit]:
    for attempt in range(1, max_attempts + 1):
        try:
            rows = await call()
            if rows:
                logger.info("search tool=%s success on attempt=%d rows=%d", label, attempt, len(rows))
                return rows
            logger.warning("search tool=%s empty result on attempt=%d", label, attempt)
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
) -> tuple[list[SearchHit], str]:
    """
    三段式搜索链路（两种主工具 + 一种兜底），每种工具最多重试 3 次。
    若三种工具均失败/空结果，返回空列表并标记 `paused`，由上游决定暂停任务。
    """
    # 工具1：Google News RSS（主）
    google_rows = await _with_retries(
        label="google_news_rss",
        call=lambda: _search_site_then_global_async(
            query=query,
            max_results=max_results,
            target_sites=target_sites,
            call=google_news_search,
        ),
        max_attempts=max_attempts_per_tool,
    )
    if google_rows:
        return google_rows, "google_news_rss"

    # 工具2：DDGS（主）
    ddgs_primary_rows = await _with_retries(
        label="ddgs_primary",
        call=lambda: _search_site_then_global_sync(
            query=query,
            max_results=max_results,
            target_sites=target_sites,
            call=ddgs_primary_search,
        ),
        max_attempts=max_attempts_per_tool,
    )
    if ddgs_primary_rows:
        return ddgs_primary_rows, "ddgs_primary"

    # 工具3：DDGS（兜底）
    ddgs_rows = await _with_retries(
        label="ddgs_fallback",
        call=lambda: _search_site_then_global_sync(
            query=query,
            max_results=max_results,
            target_sites=target_sites,
            call=ddgs_fallback,
        ),
        max_attempts=max_attempts_per_tool,
    )
    if ddgs_rows:
        return ddgs_rows, "ddgs_fallback"

    return [], "paused"


def filter_by_age(rows: list[SearchHit], max_hours: int) -> list[SearchHit]:
    if max_hours <= 0:
        return rows
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_hours)
    out: list[SearchHit] = []
    for row in rows:
        try:
            dt = datetime.fromisoformat(row.published_at.replace("Z", "+00:00"))
            if dt >= cutoff:
                out.append(row)
        except Exception:
            continue
    return out
