"""Async GDELT DOC client with rate limit, backoff, UA rotation."""
from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from datetime import datetime, timezone

import httpx

from event_enhancement.config_expansion import ExpansionConfig
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
    """httpx + semaphore + min-interval + exponential backoff on 429/5xx."""

    def __init__(
        self,
        *,
        settings: Settings,
        expansion: ExpansionConfig,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._settings = settings
        self._e = expansion
        self._client = http_client
        self._sem = asyncio.Semaphore(expansion.gdelt.max_concurrent)
        self._interval_lock = asyncio.Lock()
        self._last_request_at: float = 0.0
        self._ua_idx = 0

    def _next_ua(self) -> str:
        uas = self._e.user_agents
        if not uas:
            return "Mozilla/5.0 (compatible; EventEnhancement/1.0)"
        ua = uas[self._ua_idx % len(uas)]
        self._ua_idx += 1
        return ua

    async def _respect_interval(self) -> None:
        gap = max(0.0, float(self._e.gdelt.min_interval_sec))
        if gap <= 0:
            return
        async with self._interval_lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            wait = gap - (now - self._last_request_at)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_at = loop.time()

    async def search(
        self,
        *,
        query: str,
        timespan: str | None = None,
    ) -> list[GdeltHit]:
        q = (query or "").strip()
        if not q:
            return []
        ts = (timespan or self._e.gdelt.timespan).strip()
        maxrec = max(1, min(int(self._e.gdelt.max_records), 75))
        root = (self._settings.gdelt_base_url or "").strip() or "https://api.gdeltproject.org/api/v2/doc/doc"
        params = {
            "query": q,
            "mode": "ArtList",
            "format": "json",
            "maxrecords": str(maxrec),
            "timespan": ts,
            "sort": "datedesc",
        }
        attempt = 0
        base = float(self._e.gdelt.backoff_base_sec)
        cap = float(self._e.gdelt.backoff_max_sec)
        jitter = float(self._e.gdelt.jitter_sec)
        max_retries = int(self._e.gdelt.max_retries)

        async with self._sem:
            while True:
                await self._respect_interval()
                headers = {"User-Agent": self._next_ua()}
                try:
                    resp = await self._client.get(root, params=params, headers=headers)
                except (httpx.HTTPError, OSError) as e:
                    logger.warning(
                        "gdelt transport error query_prefix=%s kind=%s",
                        q[:80],
                        type(e).__name__,
                    )
                    if attempt >= max_retries:
                        return []
                    attempt += 1
                    await self._sleep_backoff(attempt, base, cap, jitter)
                    continue

                if resp.status_code == 429 or (500 <= resp.status_code < 600):
                    logger.warning(
                        "gdelt retryable status=%s query_prefix=%s attempt=%s",
                        resp.status_code,
                        q[:80],
                        attempt,
                    )
                    if attempt >= max_retries:
                        return []
                    attempt += 1
                    await self._sleep_backoff(attempt, base, cap, jitter)
                    continue

                if resp.status_code != 200:
                    logger.warning("gdelt http status=%s query_prefix=%s", resp.status_code, q[:80])
                    return []

                text = (resp.text or "").strip()
                if not text:
                    logger.warning("gdelt empty body query_prefix=%s", q[:80])
                    if attempt >= max_retries:
                        return []
                    attempt += 1
                    await self._sleep_backoff(attempt, base, cap, jitter)
                    continue

                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    logger.warning("gdelt invalid json query_prefix=%s", q[:80])
                    if attempt >= max_retries:
                        return []
                    attempt += 1
                    await self._sleep_backoff(attempt, base, cap, jitter)
                    continue

                return _hits_from_payload(data, max_results=maxrec)

    async def _sleep_backoff(self, attempt: int, base: float, cap: float, jitter: float) -> None:
        exp = min(cap, base * (2 ** (attempt - 1)))
        exp += random.uniform(0.0, max(0.0, jitter))
        await asyncio.sleep(exp)
