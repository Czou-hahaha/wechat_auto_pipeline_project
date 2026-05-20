"""检索阶段：对缺 ``published_at`` 的 ``SearchHit`` 抓取落地页并解析发布时间。"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from src.html_list_monitor import _iso_from_time_datetime_attr
from src.search import SearchHit

if TYPE_CHECKING:
    from src.config import Settings

logger = logging.getLogger(__name__)

_FETCH_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_ISO_DAY_RE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")


def _backfill_enabled(settings: "Settings") -> bool:
    if bool(getattr(settings, "search_article_page_backfill", True)):
        return True
    legacy = (os.environ.get("SEARCH_TEST_ARTICLE_PAGE_BACKFILL") or "").strip().lower()
    return legacy not in ("0", "false", "no", "off")


def _dom_time_probe(soup: BeautifulSoup) -> dict[str, Any]:
    time_attrs = [
        str(t.get("datetime")).strip()
        for t in soup.select("time[datetime]")
        if (t.get("datetime") or "").strip()
    ]
    meta_rows: list[dict[str, str]] = []
    for attr, key in (
        ("property", "article:published_time"),
        ("property", "og:published_time"),
        ("property", "article:modified_time"),
        ("itemprop", "datePublished"),
        ("itemprop", "dateCreated"),
        ("name", "pubdate"),
        ("name", "publishdate"),
    ):
        for node in soup.find_all("meta", attrs={attr: key}):
            c = (node.get("content") or node.get("datetime") or "").strip()
            if c:
                meta_rows.append({attr: key, "content": c[:200]})
    return {
        "time_datetime_attrs": time_attrs[:30],
        "meta_published_fields": meta_rows[:20],
    }


async def _backfill_one(
    client: httpx.AsyncClient,
    hit: SearchHit,
    runner: Any,
    sem: asyncio.Semaphore,
) -> tuple[SearchHit, dict[str, Any]]:
    probe: dict[str, Any] = {
        "article_page_fetched": False,
        "article_page_final_url": "",
        "article_page_fetch_error": "",
        "published_at_source": "search_hit",
        "dom_probe": {},
        "pipeline_published_at": "",
        "pipeline_date_only": False,
    }
    if (hit.published_at or "").strip():
        return hit, probe
    url = (hit.url or "").strip()
    if not url.startswith("http"):
        probe["article_page_fetch_error"] = "invalid_url"
        return hit, probe
    async with sem:
        try:
            resp = await client.get(url, headers={"User-Agent": _FETCH_UA})
            resp.raise_for_status()
        except Exception as exc:
            probe["article_page_fetch_error"] = f"{type(exc).__name__}: {exc}"[:500]
            return hit, probe
    probe["article_page_fetched"] = True
    probe["article_page_final_url"] = str(resp.url)
    html_text = runner._decode_html(resp)
    soup = BeautifulSoup(html_text, "html.parser")
    probe["dom_probe"] = _dom_time_probe(soup)
    page_iso, date_only = runner._extract_published_at(soup, page_url=str(resp.url))
    probe["pipeline_published_at"] = page_iso
    probe["pipeline_date_only"] = bool(date_only)
    if (page_iso or "").strip():
        probe["published_at_source"] = "article_page_pipeline"
        return replace(hit, published_at=page_iso.strip()), probe
    for raw_td in probe["dom_probe"].get("time_datetime_attrs") or []:
        cand = _iso_from_time_datetime_attr(raw_td)
        if cand:
            probe["published_at_source"] = "article_page_dom_time_only"
            probe["pipeline_published_at"] = cand
            return replace(hit, published_at=cand), probe
    for row in probe["dom_probe"].get("meta_published_fields") or []:
        raw_m = (row.get("content") or "").strip()
        if not raw_m:
            continue
        cand = _iso_from_time_datetime_attr(raw_m) if "T" in raw_m else ""
        if not cand:
            m = _ISO_DAY_RE.search(raw_m)
            if m:
                cand = (
                    datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), 12, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
                    .astimezone(timezone.utc)
                    .isoformat()
                )
        if cand:
            probe["published_at_source"] = "article_page_dom_meta_only"
            probe["pipeline_published_at"] = cand
            return replace(hit, published_at=cand), probe
    probe["published_at_source"] = "missing_after_article_page"
    return hit, probe


async def backfill_missing_published_at(
    hits: list[SearchHit],
    settings: "Settings",
    *,
    max_concurrent: int | None = None,
) -> tuple[list[SearchHit], list[dict[str, Any]]]:
    """对 ``published_at`` 为空的条目抓取原文并解析；返回新 hit 列表与每条 probe（与 hits 对齐）。"""
    if not _backfill_enabled(settings):
        return hits, [{} for _ in hits]
    missing = sum(1 for h in hits if not (h.published_at or "").strip())
    if missing == 0:
        return hits, [{} for _ in hits]
    from src.pipeline import PipelineRunner

    runner = PipelineRunner(settings)
    cap = max_concurrent
    if cap is None:
        cap = int(getattr(settings, "search_article_page_backfill_max_concurrent", 4) or 4)
    sem = asyncio.Semaphore(max(1, int(cap)))
    timeout = float(getattr(settings, "search_article_page_fetch_timeout_sec", 35.0) or 35.0)
    legacy_timeout = os.environ.get("SEARCH_TEST_ARTICLE_FETCH_TIMEOUT_SEC")
    if legacy_timeout:
        timeout = float(legacy_timeout)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        pairs = await asyncio.gather(*[_backfill_one(client, h, runner, sem) for h in hits])
    new_hits = [p[0] for p in pairs]
    probes = [p[1] for p in pairs]
    filled = sum(1 for p in probes if p.get("published_at_source", "").startswith("article_page"))
    logger.info(
        "search published_at backfill: missing_before=%d filled_from_page=%d still_missing=%d",
        missing,
        filled,
        sum(1 for h in new_hits if not (h.published_at or "").strip()),
    )
    return new_hits, probes
