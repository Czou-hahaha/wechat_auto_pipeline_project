"""GDELT 2.1 DOC API：程序化检索，输出 ``SearchHit``。"""
from __future__ import annotations

import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

from src.search import SearchHit, _dedupe_hits, _is_blocked_url

logger = logging.getLogger(__name__)

_EE_PATH_ENSURED = False


def _ensure_event_enhancement_path() -> None:
    global _EE_PATH_ENSURED
    if _EE_PATH_ENSURED:
        return
    root = Path(__file__).resolve().parents[2]
    ee = root / "event_enhancement"
    if ee.is_dir() and str(ee) not in sys.path:
        sys.path.insert(0, str(ee))
    _EE_PATH_ENSURED = True


def gdelt_timespan_for_hours(max_hours: int) -> str:
    """Map article-age window to GDELT ``timespan`` (capped at 24h; no 7d/30d)."""
    h = max(1, min(int(max_hours), 24))
    if h <= 1:
        return "1h"
    if h <= 6:
        return "6h"
    if h <= 12:
        return "12h"
    return "24h"


def resolve_gdelt_timespan(*, explicit: str, max_article_age_hours: int) -> str:
    """Prefer ``GDELT_TIMESPAN``; otherwise derive from age hours (max 24h)."""
    ts = (explicit or "").strip()
    if ts:
        return ts
    return gdelt_timespan_for_hours(max_article_age_hours)


def gdelt_format_or_term(raw: str) -> str:
    """Simple single-term query (no OR groups)."""
    t = str(raw or "").strip().replace('"', "")
    if not t:
        return ""
    if re.search(r"\s", t):
        return f'"{t}"'
    return t


def gdelt_build_or_query(terms: list[str]) -> str:
    """Legacy OR builder — prefer one-term-per-request in ``search_gdelt_topics_bilingual``."""
    parts: list[str] = []
    for term in terms:
        frag = gdelt_format_or_term(term)
        if frag:
            parts.append(f"({frag})" if " " not in frag or frag.startswith('"') else frag)
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return "(" + " OR ".join(parts) + ")"


def _hits_from_gdelt_payload(data: object, *, max_results: int) -> list[SearchHit]:
    articles = data.get("articles") if isinstance(data, dict) else None
    if not isinstance(articles, list):
        logger.warning(
            "gdelt unexpected payload keys=%s",
            list(data.keys()) if isinstance(data, dict) else type(data),
        )
        return []
    rows: list[SearchHit] = []
    for art in articles:
        if not isinstance(art, dict):
            continue
        u = str(art.get("url") or "").strip()
        if not u or _is_blocked_url(u):
            continue
        title = str(art.get("title") or "未命名").strip() or "未命名"
        excerpt = str(art.get("excerpt") or art.get("excerpt_highlighted") or "").strip()
        dom = str(art.get("domain") or "").strip()
        snippet = normalize_snippet_gdelt(excerpt, dom)
        seen = _seendate_to_iso(str(art.get("seendate") or ""))
        rows.append(SearchHit(title=title, url=u, snippet=snippet, published_at=seen))
    return _dedupe_hits(rows, max_results=max_results)


def _seendate_to_iso(seen: str) -> str:
    raw = (seen or "").strip()
    if len(raw) >= 14 and raw[:14].isdigit():
        try:
            dt = datetime.strptime(raw[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            pass
    return ""


def _http_config_from_settings(settings: object) -> "GdeltHttpConfig":
    _ensure_event_enhancement_path()
    from event_enhancement.gdelt.http_core import DEFAULT_BACKOFF_SEC, GdeltHttpConfig

    data_dir = Path(getattr(settings, "data_dir", Path("./data")))
    cache_dir = data_dir / "cache" / "gdelt"
    ts = resolve_gdelt_timespan(
        explicit=str(getattr(settings, "gdelt_timespan", "") or ""),
        max_article_age_hours=int(getattr(settings, "max_article_age_hours", 14)),
    )
    return GdeltHttpConfig(
        base_url=(getattr(settings, "gdelt_base_url", "") or "").strip()
        or "https://api.gdeltproject.org/api/v2/doc/doc",
        timespan=ts,
        max_records=max(1, min(int(getattr(settings, "gdelt_max_records", 50)), 75)),
        timeout_sec=float(getattr(settings, "gdelt_timeout_sec", 45.0)),
        retry_timeout_sec=float(getattr(settings, "gdelt_retry_timeout_sec", 15.0)),
        min_interval_sec=max(5.0, float(getattr(settings, "gdelt_min_interval_sec", 5.0))),
        max_retries=max(1, int(getattr(settings, "gdelt_max_retries", 3))),
        backoff_sec=DEFAULT_BACKOFF_SEC,
        cache_dir=cache_dir,
        cache_ttl_sec=max(60.0, float(getattr(settings, "gdelt_cache_ttl_min", 30)) * 60.0),
    )


async def gdelt_doc_search_with_client(
    client: httpx.AsyncClient,
    *,
    query: str,
    max_results: int,
    timespan: str,
    base_url: str = "https://api.gdeltproject.org/api/v2/doc/doc",
    request_timeout: float | None = None,
    http_config: "GdeltHttpConfig | None" = None,
) -> list[SearchHit]:
    """Call GDELT DOC via shared ``http_core`` (rate limit + retry + cache)."""
    _ensure_event_enhancement_path()
    from event_enhancement.gdelt.http_core import GdeltHttpConfig, fetch_gdelt_doc_json

    q = (query or "").strip()
    if not q:
        return []
    maxrec = max(1, min(int(max_results), 75))
    cfg = http_config or GdeltHttpConfig(
        base_url=(base_url or "https://api.gdeltproject.org/api/v2/doc/doc").strip(),
        timespan=(timespan or "1h").strip(),
        max_records=maxrec,
    )
    cfg = GdeltHttpConfig(
        base_url=cfg.base_url,
        timespan=(timespan or cfg.timespan or "1h").strip(),
        max_records=maxrec,
        timeout_sec=float(request_timeout) if request_timeout is not None else cfg.timeout_sec,
        retry_timeout_sec=cfg.retry_timeout_sec,
        min_interval_sec=cfg.min_interval_sec,
        max_retries=cfg.max_retries,
        backoff_sec=cfg.backoff_sec,
        cache_dir=cfg.cache_dir,
        cache_ttl_sec=cfg.cache_ttl_sec,
        user_agent=cfg.user_agent,
    )
    result = await fetch_gdelt_doc_json(client, query=q, config=cfg)
    if result.data is None:
        return []
    return _hits_from_gdelt_payload(result.data, max_results=maxrec)


async def gdelt_doc_search(
    *,
    query: str,
    max_results: int,
    timespan: str,
    timeout: float = 45.0,
    base_url: str = "https://api.gdeltproject.org/api/v2/doc/doc",
    settings: object | None = None,
) -> list[SearchHit]:
    """单次短连接调用（兼容旧代码路径）。"""
    cfg = _http_config_from_settings(settings) if settings is not None else None
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, trust_env=False) as client:
        return await gdelt_doc_search_with_client(
            client,
            query=query,
            max_results=max_results,
            timespan=timespan,
            base_url=base_url,
            request_timeout=timeout,
            http_config=cfg,
        )


def normalize_snippet_gdelt(excerpt: str, domain: str) -> str:
    if excerpt:
        return excerpt[:2000]
    return domain[:500]
