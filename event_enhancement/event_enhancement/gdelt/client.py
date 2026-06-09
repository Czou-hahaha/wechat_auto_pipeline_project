"""Async GDELT DOC client — delegates to global ``http_core`` rate limit + retry."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx

from event_enhancement.config_expansion import ExpansionConfig
from event_enhancement.gdelt.http_core import (
    DEFAULT_BACKOFF_SEC,
    GdeltHttpConfig,
    fetch_gdelt_doc_json,
)
from event_enhancement.gdelt.types import GdeltHit
from event_enhancement.settings import Settings

logger = logging.getLogger(__name__)


def _seendate_to_iso(seen: str) -> str:
    raw = (seen or "").strip()
    if len(raw) >= 14 and raw[:14].isdigit():
        try:
            dt = datetime.strptime(raw[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            pass
    return ""


def _hits_from_payload(data: object, *, max_results: int) -> list[GdeltHit]:
    articles = data.get("articles") if isinstance(data, dict) else None
    if not isinstance(articles, list):
        logger.warning(
            "gdelt unexpected payload keys=%s",
            list(data.keys()) if isinstance(data, dict) else type(data),
        )
        return []
    rows: list[GdeltHit] = []
    seen_url: set[str] = set()
    for art in articles:
        if not isinstance(art, dict):
            continue
        u = str(art.get("url") or "").strip()
        if not u or u in seen_url:
            continue
        seen_url.add(u)
        title = str(art.get("title") or "").strip() or "未命名"
        excerpt = str(art.get("excerpt") or art.get("excerpt_highlighted") or "").strip()
        dom = str(art.get("domain") or "").strip()
        snippet = excerpt[:2000] if excerpt else dom[:500]
        seen = _seendate_to_iso(str(art.get("seendate") or ""))
        rows.append(GdeltHit(title=title, url=u, snippet=snippet, published_at=seen, domain=dom))
        if len(rows) >= max_results:
            break
    return rows


class GdeltAsyncClient:
    """Serial GDELT access via process-wide rate limiter in ``http_core``."""

    def __init__(
        self,
        *,
        settings: Settings,
        expansion: ExpansionConfig,
        http_client: httpx.AsyncClient,
        cache_dir: Path | None = None,
    ) -> None:
        self._settings = settings
        self._e = expansion
        self._client = http_client
        self._ua_idx = 0
        g = expansion.gdelt
        backoff = tuple(
            min(float(g.backoff_max_sec), float(g.backoff_base_sec) * (2**i))
            for i in range(max(1, int(g.max_retries)))
        )
        if len(backoff) < 3:
            backoff = DEFAULT_BACKOFF_SEC
        self._http_cfg = GdeltHttpConfig(
            base_url=(settings.gdelt_base_url or "").strip()
            or "https://api.gdeltproject.org/api/v2/doc/doc",
            timespan=str(g.timespan or "1h").strip(),
            max_records=int(g.max_records),
            timeout_sec=float(expansion.http_fetch_timeout_sec),
            retry_timeout_sec=float(g.retry_timeout_sec),
            min_interval_sec=max(5.0, float(g.min_interval_sec)),
            max_retries=max(1, int(g.max_retries)),
            backoff_sec=backoff[:3] if len(backoff) >= 3 else DEFAULT_BACKOFF_SEC,
            cache_dir=cache_dir,
        )

    def _next_ua(self) -> str:
        uas = self._e.user_agents
        if not uas:
            return "Mozilla/5.0 (compatible; EventEnhancement/1.0)"
        ua = uas[self._ua_idx % len(uas)]
        self._ua_idx += 1
        return ua

    async def search(
        self,
        *,
        query: str,
        timespan: str | None = None,
    ) -> list[GdeltHit]:
        q = (query or "").strip()
        if not q:
            return []
        cfg = self._http_cfg
        if timespan:
            cfg = GdeltHttpConfig(
                base_url=cfg.base_url,
                timespan=timespan.strip(),
                max_records=cfg.max_records,
                timeout_sec=cfg.timeout_sec,
                retry_timeout_sec=cfg.retry_timeout_sec,
                min_interval_sec=cfg.min_interval_sec,
                max_retries=cfg.max_retries,
                backoff_sec=cfg.backoff_sec,
                cache_dir=cfg.cache_dir,
                cache_ttl_sec=cfg.cache_ttl_sec,
                user_agent=self._next_ua(),
            )
        else:
            cfg = GdeltHttpConfig(
                base_url=cfg.base_url,
                timespan=cfg.timespan,
                max_records=cfg.max_records,
                timeout_sec=cfg.timeout_sec,
                retry_timeout_sec=cfg.retry_timeout_sec,
                min_interval_sec=cfg.min_interval_sec,
                max_retries=cfg.max_retries,
                backoff_sec=cfg.backoff_sec,
                cache_dir=cfg.cache_dir,
                cache_ttl_sec=cfg.cache_ttl_sec,
                user_agent=self._next_ua(),
            )
        result = await fetch_gdelt_doc_json(self._client, query=q, config=cfg)
        if result.data is None:
            return []
        return _hits_from_payload(result.data, max_results=cfg.max_records)
