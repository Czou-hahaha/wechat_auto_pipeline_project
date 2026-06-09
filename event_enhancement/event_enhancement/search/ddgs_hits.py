"""Synchronous DuckDuckGo text search → ``GdeltHit`` rows (optional expansion backend)."""
from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

from event_enhancement.gdelt.types import GdeltHit

logger = logging.getLogger(__name__)


def ddgs_text_search_sync(query: str, max_results: int) -> list[GdeltHit]:
    """Run ``ddgs`` text search in a worker thread; returns hits compatible with GDELT downstream."""
    q = (query or "").strip()
    if not q:
        return []
    try:
        from ddgs import DDGS
    except ImportError:
        logger.error("web_search_backend=ddgs requires the ddgs package (pip install ddgs)")
        return []

    verify = os.environ.get("DDGS_VERIFY_SSL", "false").strip().lower() in ("1", "true", "yes")
    mx = max(1, min(int(max_results), 50))
    hits: list[GdeltHit] = []
    seen: set[str] = set()
    try:
        with DDGS(verify=verify) as ddgs:
            for item in ddgs.text(q, max_results=mx):
                if not isinstance(item, dict):
                    continue
                url = str(item.get("href") or item.get("url") or "").strip()
                if not url or url in seen:
                    continue
                seen.add(url)
                title = str(item.get("title") or "").strip() or "未命名"
                body = str(item.get("body") or "").strip()
                dom = (urlparse(url).netloc or "").lower()
                hits.append(
                    GdeltHit(title=title, url=url, snippet=body[:2000], published_at="", domain=dom),
                )
    except Exception as e:
        logger.warning("ddgs search failed query_prefix=%s err=%s", q[:80], type(e).__name__)
    return hits
