"""GDELT 2.1 DOC API：程序化检索，输出 ``SearchHit``。"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import httpx

from src.search import SearchHit, _dedupe_hits, _is_blocked_url

logger = logging.getLogger(__name__)


def gdelt_timespan_for_hours(max_hours: int) -> str:
    """GDELT ``timespan`` 近似映射。"""
    h = max(1, min(int(max_hours), 168))
    if h <= 6:
        return "6h"
    if h <= 12:
        return "12h"
    if h <= 24:
        return "24h"
    if h <= 48:
        return "2d"
    if h <= 72:
        return "3d"
    return "7d"


def _seendate_to_iso(seen: str) -> str:
    raw = (seen or "").strip()
    if len(raw) >= 14 and raw[:14].isdigit():
        try:
            dt = datetime.strptime(raw[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            pass
    return ""


def gdelt_format_or_term(raw: str) -> str:
    """将单个检索词格式化为 GDELT OR 子句（含空格短语加引号）。"""
    t = str(raw or "").strip().replace('"', "")
    if not t:
        return ""
    if re.search(r"\s", t):
        return f'"{t}"'
    return f"({t})"


def gdelt_build_or_query(terms: list[str]) -> str:
    """把词表拼成 ``(a OR b OR "phrase c")``。"""
    parts: list[str] = []
    for term in terms:
        frag = gdelt_format_or_term(term)
        if frag:
            parts.append(frag)
    if not parts:
        return ""
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


async def gdelt_doc_search_with_client(
    client: httpx.AsyncClient,
    *,
    query: str,
    max_results: int,
    timespan: str,
    base_url: str = "https://api.gdeltproject.org/api/v2/doc/doc",
) -> list[SearchHit]:
    """使用已有 ``AsyncClient`` 调用 GDELT DOC ``ArtList``。"""
    q = (query or "").strip()
    if not q:
        return []
    maxrec = max(1, min(int(max_results), 75))
    root = (base_url or "https://api.gdeltproject.org/api/v2/doc/doc").strip()
    params = {
        "query": q,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": str(maxrec),
        "timespan": (timespan or "24h").strip(),
        "sort": "datedesc",
    }
    resp = await client.get(root, params=params, headers={"User-Agent": "Mozilla/5.0 V3-pipeline"})
    resp.raise_for_status()
    data = resp.json()
    return _hits_from_gdelt_payload(data, max_results=maxrec)


async def gdelt_doc_search(
    *,
    query: str,
    max_results: int,
    timespan: str,
    timeout: float = 45.0,
    base_url: str = "https://api.gdeltproject.org/api/v2/doc/doc",
) -> list[SearchHit]:
    """单次短连接调用（兼容旧代码路径）。"""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        return await gdelt_doc_search_with_client(
            client,
            query=query,
            max_results=max_results,
            timespan=timespan,
            base_url=base_url,
        )


def normalize_snippet_gdelt(excerpt: str, domain: str) -> str:
    if excerpt:
        return excerpt[:2000]
    return domain[:500]
