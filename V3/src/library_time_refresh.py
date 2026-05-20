"""刷新 ``articles.json`` 的 ``source_published_at``，并剔除超出时间窗的条目。"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup

from src.config import Settings
from src.html_list_monitor import _iso_from_time_datetime_attr
from src.pipeline import PipelineRunner

logger = logging.getLogger(__name__)

_FETCH_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


@dataclass
class RefreshLibraryTimesStats:
    total: int = 0
    refreshed: int = 0
    fetch_failed: int = 0
    kept: int = 0
    removed_missing_time: int = 0
    removed_time_window: int = 0


def _article_url(row: dict[str, Any]) -> str:
    return str(row.get("resolved_url") or row.get("source_url") or "").strip()


def _should_refetch(row: dict[str, Any]) -> bool:
    pub = str(row.get("source_published_at") or "").strip()
    if not pub:
        return True
    created = str(row.get("created_at") or "").strip()
    if created and pub == created:
        return True
    status = str(row.get("status") or "")
    if status in ("dedupe_test_stub", "event_enhancement", "fixture_hydrate"):
        return True
    return False


async def _fetch_published_at(
    client: httpx.AsyncClient,
    runner: PipelineRunner,
    url: str,
) -> tuple[str, bool]:
    resp = await client.get(url, headers={"User-Agent": _FETCH_UA})
    resp.raise_for_status()
    html_text = runner._decode_html(resp)
    soup = BeautifulSoup(html_text, "html.parser")
    page_iso, date_only = runner._extract_published_at(soup, page_url=str(resp.url))
    if (page_iso or "").strip():
        return page_iso.strip(), bool(date_only)
    for raw_td in soup.select("time[datetime]"):
        cand = _iso_from_time_datetime_attr(str(raw_td.get("datetime") or ""))
        if cand:
            return cand, False
    return "", False


async def refresh_library_published_at_and_prune(
    settings: Settings,
    *,
    max_age_days: int = 7,
    dry_run: bool = False,
) -> RefreshLibraryTimesStats:
    """
    对库内每篇文章重新抓取落地页发布时间，删除缺时间或超出 ``max_age_days`` 自然日窗的条目，
    并同步 ``event_article_map.json``。
    """
    runner = PipelineRunner(settings)
    store = runner.store
    rows = [r for r in store.list_all() if isinstance(r, dict)]
    stats = RefreshLibraryTimesStats(total=len(rows))
    max_hours = max(1, int(max_age_days)) * 24

    timeout = float(getattr(settings, "search_article_page_fetch_timeout_sec", 35.0) or 35.0)
    sem = asyncio.Semaphore(max(1, int(getattr(settings, "search_article_page_backfill_max_concurrent", 4))))

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:

        async def process_one(row: dict[str, Any]) -> dict[str, Any]:
            out = dict(row)
            if not _should_refetch(out):
                return out
            url = _article_url(out)
            if not url.startswith("http"):
                stats.fetch_failed += 1
                return out
            async with sem:
                try:
                    iso, date_only = await _fetch_published_at(client, runner, url)
                except Exception as exc:
                    logger.warning(
                        "refresh published_at fetch failed url=%s err=%s",
                        url[:80],
                        type(exc).__name__,
                    )
                    stats.fetch_failed += 1
                    out["source_published_at"] = ""
                    out["source_published_at_date_only"] = False
                    return out
            if iso:
                out["source_published_at"] = iso
                out["source_published_at_date_only"] = date_only
                stats.refreshed += 1
                logger.info(
                    "refreshed published_at: %s -> %s",
                    (out.get("title") or "")[:40],
                    iso[:25],
                )
            return out

        refreshed_rows = await asyncio.gather(*[process_one(r) for r in rows])

    kept: list[dict[str, Any]] = []
    kept_urls: set[str] = set()
    for row in refreshed_rows:
        pub = str(row.get("source_published_at") or "").strip()
        if not pub:
            stats.removed_missing_time += 1
            logger.info("remove (no time): %s", (row.get("title") or "")[:50])
            continue
        if not runner._published_at_within_window(
            source_published_at=pub,
            max_hours=max_hours,
            date_only_coarse=bool(row.get("source_published_at_date_only")),
        ):
            stats.removed_time_window += 1
            logger.info("remove (>%dd): %s pub=%s", max_age_days, (row.get("title") or "")[:50], pub[:25])
            continue
        kept.append(row)
        url = _article_url(row)
        if url:
            kept_urls.add(url)
        src = str(row.get("source_url") or "").strip()
        if src:
            kept_urls.add(src)
        stats.kept += 1

    if not dry_run:
        backup_dir = store.data_dir / f"backup_before_time_refresh_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
        backup_dir.mkdir(parents=True, exist_ok=True)
        for name in ("articles.json", "event_article_map.json", "events.json"):
            src_path = store.data_dir / name
            if src_path.exists():
                shutil.copy2(src_path, backup_dir / name)

        store._write(kept)

        map_rows = json.loads(store._event_map_path.read_text(encoding="utf-8"))
        if isinstance(map_rows, list):
            pruned = [
                m
                for m in map_rows
                if isinstance(m, dict)
                and (
                    str(m.get("resolved_url") or "").strip() in kept_urls
                    or str(m.get("source_url") or "").strip() in kept_urls
                )
            ]
            removed_maps = len(map_rows) - len(pruned)
            if removed_maps:
                logger.info("event_article_map pruned=%d kept=%d", removed_maps, len(pruned))
            store._event_map_path.write_text(
                json.dumps(pruned, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    return stats
