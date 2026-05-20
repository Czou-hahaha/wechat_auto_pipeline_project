"""Global GDELT DOC HTTP: rate limit, retry, cache, safe JSON parse."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Process-wide: at most one GDELT HTTP request per interval (default 5s).
_global_rate_lock = asyncio.Lock()
_global_last_request_at: float = 0.0

DEFAULT_BACKOFF_SEC = (5.0, 10.0, 20.0)
DEFAULT_MIN_INTERVAL_SEC = 5.0
DEFAULT_CACHE_TTL_SEC = 30 * 60


@dataclass(frozen=True)
class GdeltHttpConfig:
    base_url: str = "https://api.gdeltproject.org/api/v2/doc/doc"
    timespan: str = "1h"
    max_records: int = 50
    timeout_sec: float = 45.0
    retry_timeout_sec: float = 15.0
    min_interval_sec: float = DEFAULT_MIN_INTERVAL_SEC
    max_retries: int = 3
    backoff_sec: tuple[float, ...] = DEFAULT_BACKOFF_SEC
    cache_dir: Path | None = None
    cache_ttl_sec: float = DEFAULT_CACHE_TTL_SEC
    user_agent: str = "Mozilla/5.0 (compatible; V3-GDELT/1.0)"


@dataclass(frozen=True)
class GdeltHttpResult:
    data: dict[str, Any] | None
    status_code: int
    elapsed_sec: float
    retries: int
    from_cache: bool
    request_url: str


async def acquire_gdelt_rate_slot(min_interval_sec: float) -> None:
    """Enforce minimum gap between the *end* of one GDELT call and the start of the next."""
    gap = max(5.0, float(min_interval_sec))
    global _global_last_request_at
    async with _global_rate_lock:
        loop = asyncio.get_running_loop()
        now = loop.time()
        wait = gap - (now - _global_last_request_at)
        if wait > 0:
            logger.debug("gdelt rate limit sleep %.2fs", wait)
            await asyncio.sleep(wait)


async def mark_gdelt_request_finished(*, extra_cooldown_sec: float = 0.0) -> None:
    """Record request completion; optional extra pause after 429."""
    global _global_last_request_at
    async with _global_rate_lock:
        loop = asyncio.get_running_loop()
        _global_last_request_at = loop.time() + max(0.0, float(extra_cooldown_sec))


def _cache_key(query: str, timespan: str, max_records: int) -> str:
    raw = f"{query}|{timespan}|{max_records}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _read_cache(cache_dir: Path, key: str, ttl_sec: float) -> dict[str, Any] | None:
    path = cache_dir / f"{key}.json"
    if not path.is_file():
        return None
    try:
        age = time.time() - path.stat().st_mtime
        if age > ttl_sec:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
            return payload["data"]
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    return None


def _write_cache(cache_dir: Path, key: str, data: dict[str, Any], *, query: str) -> None:
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        body = {
            "query": query[:500],
            "cached_at": time.time(),
            "data": data,
        }
        path = cache_dir / f"{key}.json"
        path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        logger.warning("gdelt cache write failed key=%s err=%s", key[:12], e)


def _build_request_url(base_url: str, params: dict[str, str]) -> str:
    root = (base_url or "https://api.gdeltproject.org/api/v2/doc/doc").strip()
    q = httpx.QueryParams(params)
    return f"{root}?{q}"


async def fetch_gdelt_doc_json(
    client: httpx.AsyncClient,
    *,
    query: str,
    config: GdeltHttpConfig,
) -> GdeltHttpResult:
    """
    Fetch GDELT DOC ArtList JSON with global rate limit, retries, and optional disk cache.

    Empty body, non-JSON, 429, 5xx, and transport errors trigger retry with backoff.
    """
    q = (query or "").strip()
    if not q:
        return GdeltHttpResult(
            data=None,
            status_code=0,
            elapsed_sec=0.0,
            retries=0,
            from_cache=False,
            request_url="",
        )

    maxrec = max(1, min(int(config.max_records), 75))
    ts = (config.timespan or "1h").strip()
    params = {
        "query": q,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": str(maxrec),
        "timespan": ts,
        "sort": "datedesc",
    }
    request_url = _build_request_url(config.base_url, params)
    cache_key = _cache_key(q, ts, maxrec)

    if config.cache_dir is not None:
        cached = _read_cache(config.cache_dir, cache_key, config.cache_ttl_sec)
        if cached is not None:
            n = len(cached.get("articles") or [])
            logger.info(
                "gdelt cache hit query=%r timespan=%s maxrecords=%d records=%d url=%s",
                q[:120],
                ts,
                maxrec,
                n,
                request_url[:200],
            )
            return GdeltHttpResult(
                data=cached,
                status_code=200,
                elapsed_sec=0.0,
                retries=0,
                from_cache=True,
                request_url=request_url,
            )

    backoff = list(config.backoff_sec) or list(DEFAULT_BACKOFF_SEC)
    max_retries = max(1, int(config.max_retries))
    attempt = 0
    started = time.perf_counter()

    while True:
        await acquire_gdelt_rate_slot(config.min_interval_sec)
        req_timeout = config.timeout_sec if attempt == 0 else config.retry_timeout_sec
        t0 = time.perf_counter()
        status = 0
        text = ""
        try:
            resp = await client.get(
                config.base_url.strip(),
                params=params,
                headers={"User-Agent": config.user_agent},
                timeout=float(req_timeout),
            )
            status = resp.status_code
            text = (resp.text or "").strip()
        except (httpx.HTTPError, OSError) as e:
            elapsed = time.perf_counter() - t0
            await mark_gdelt_request_finished(extra_cooldown_sec=0.0)
            logger.warning(
                "gdelt transport error query=%r status=%s elapsed=%.2fs attempt=%d/%d "
                "retries=%d url=%s err=%s",
                q[:120],
                status,
                elapsed,
                attempt + 1,
                max_retries,
                attempt,
                request_url[:200],
                type(e).__name__,
            )
            if attempt >= max_retries - 1:
                return GdeltHttpResult(
                    data=None,
                    status_code=status,
                    elapsed_sec=time.perf_counter() - started,
                    retries=attempt,
                    from_cache=False,
                    request_url=request_url,
                )
            wait = backoff[min(attempt, len(backoff) - 1)]
            attempt += 1
            await asyncio.sleep(wait)
            continue

        elapsed = time.perf_counter() - t0
        retryable = status == 429 or (500 <= status < 600)
        if status != 200 or retryable:
            extra_cd = 5.0 if status == 429 else 0.0
            await mark_gdelt_request_finished(extra_cooldown_sec=extra_cd)
            logger.warning(
                "gdelt http query=%r status=%s elapsed=%.2fs attempt=%d/%d retries=%d "
                "body_prefix=%r url=%s",
                q[:120],
                status,
                elapsed,
                attempt + 1,
                max_retries,
                attempt,
                text[:200],
                request_url[:200],
            )
            if attempt >= max_retries - 1:
                return GdeltHttpResult(
                    data=None,
                    status_code=status,
                    elapsed_sec=time.perf_counter() - started,
                    retries=attempt,
                    from_cache=False,
                    request_url=request_url,
                )
            wait = backoff[min(attempt, len(backoff) - 1)]
            if status == 429:
                wait = max(wait, 6.0)
            attempt += 1
            await asyncio.sleep(wait)
            continue

        if not text:
            await mark_gdelt_request_finished()
            logger.warning(
                "gdelt empty body query=%r elapsed=%.2fs attempt=%d retries=%d url=%s",
                q[:120],
                elapsed,
                attempt + 1,
                attempt,
                request_url[:200],
            )
            if attempt >= max_retries - 1:
                return GdeltHttpResult(
                    data=None,
                    status_code=status,
                    elapsed_sec=time.perf_counter() - started,
                    retries=attempt,
                    from_cache=False,
                    request_url=request_url,
                )
            wait = backoff[min(attempt, len(backoff) - 1)]
            attempt += 1
            await asyncio.sleep(wait)
            continue

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            await mark_gdelt_request_finished()
            logger.warning(
                "gdelt invalid json query=%r elapsed=%.2fs attempt=%d retries=%d "
                "raw_prefix=%r url=%s",
                q[:120],
                elapsed,
                attempt + 1,
                attempt,
                text[:400],
                request_url[:200],
            )
            if attempt >= max_retries - 1:
                return GdeltHttpResult(
                    data=None,
                    status_code=status,
                    elapsed_sec=time.perf_counter() - started,
                    retries=attempt,
                    from_cache=False,
                    request_url=request_url,
                )
            wait = backoff[min(attempt, len(backoff) - 1)]
            attempt += 1
            await asyncio.sleep(wait)
            continue

        if not isinstance(data, dict):
            logger.warning(
                "gdelt unexpected json type=%s query=%r url=%s",
                type(data).__name__,
                q[:120],
                request_url[:200],
            )
            return GdeltHttpResult(
                data=None,
                status_code=status,
                elapsed_sec=time.perf_counter() - started,
                retries=attempt,
                from_cache=False,
                request_url=request_url,
            )

        articles = data.get("articles")
        n_records = len(articles) if isinstance(articles, list) else 0
        logger.info(
            "gdelt ok query=%r status=%s timespan=%s maxrecords=%d records=%d "
            "elapsed=%.2fs retries=%d cached=false url=%s",
            q[:120],
            status,
            ts,
            maxrec,
            n_records,
            time.perf_counter() - started,
            attempt,
            request_url[:200],
        )

        await mark_gdelt_request_finished()

        if config.cache_dir is not None:
            _write_cache(config.cache_dir, cache_key, data, query=q)

        return GdeltHttpResult(
            data=data,
            status_code=status,
            elapsed_sec=time.perf_counter() - started,
            retries=attempt,
            from_cache=False,
            request_url=request_url,
        )
