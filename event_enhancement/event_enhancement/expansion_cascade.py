"""扩搜源联：英文 event 用 GDELT→RSS→DDGS（可关 GDELT）；中文 event 跳过 GDELT，仅 RSS→DDGS。"""
from __future__ import annotations

import asyncio
import functools
from typing import TYPE_CHECKING, Literal

from event_enhancement.gdelt.query import gdelt_query_from_plain
from event_enhancement.gdelt.types import GdeltHit
from event_enhancement.lang_detect import EventLang

if TYPE_CHECKING:
    from event_enhancement.config_expansion import ExpansionConfig
    from event_enhancement.gdelt.client import GdeltAsyncClient

ExpansionSource = Literal["gdelt", "google_rss", "ddgs"]


def expansion_sources_for_event_lang(lang: EventLang, exp: "ExpansionConfig") -> tuple[ExpansionSource, ...]:
    """zh：跳过 GDELT；en：完整三级联（若 ``expansion_search_cascade`` 关闭则单后端）。"""
    if not exp.expansion_search_cascade:
        if exp.web_search_backend == "ddgs":
            return ("ddgs",)
        return ("gdelt",)
    if lang == "zh":
        return ("google_rss", "ddgs")
    if getattr(exp, "expansion_gdelt_en_enabled", False):
        return ("gdelt", "google_rss", "ddgs")
    return ("google_rss", "ddgs")


async def _gather_gdelt_with_retries(
    *,
    gdelt_query: str,
    gdelt_client: "GdeltAsyncClient",
    attempts: int,
) -> tuple[list[GdeltHit], dict]:
    q = (gdelt_query or "").strip()
    if not q:
        return [], {"source": "gdelt", "query": "", "attempts": 0, "hits": 0}
    for i in range(max(1, attempts)):
        batch = await gdelt_client.search(query=q)
        if batch:
            return batch, {"source": "gdelt", "query": q, "attempts": i + 1, "hits": len(batch)}
        await asyncio.sleep(min(2.0 * (i + 1), 12.0))
    return [], {"source": "gdelt", "query": q, "attempts": attempts, "hits": 0}


async def _gather_rss_with_retries(
    *,
    plain: str,
    exp: "ExpansionConfig",
    attempts: int,
) -> tuple[list[GdeltHit], dict]:
    from event_enhancement.search.google_news_rss import google_news_rss_search_sync

    mx = max(1, min(int(exp.gdelt.max_records), 40))
    timeout = float(exp.http_fetch_timeout_sec)
    for i in range(max(1, attempts)):
        batch = await asyncio.to_thread(
            functools.partial(google_news_rss_search_sync, plain, mx, timeout_sec=timeout),
        )
        if batch:
            return batch, {"source": "google_rss", "query": plain, "attempts": i + 1, "hits": len(batch)}
        await asyncio.sleep(min(2.0 * (i + 1), 12.0))
    return [], {"source": "google_rss", "query": plain, "attempts": attempts, "hits": 0}


async def _gather_ddgs_with_retries(
    *,
    plain: str,
    exp: "ExpansionConfig",
    attempts: int,
) -> tuple[list[GdeltHit], dict]:
    from event_enhancement.search.ddgs_hits import ddgs_text_search_sync

    mx = max(1, min(int(exp.gdelt.max_records), 50))
    for i in range(max(1, attempts)):
        batch = await asyncio.to_thread(ddgs_text_search_sync, plain, mx)
        if batch:
            return batch, {"source": "ddgs", "query": plain, "attempts": i + 1, "hits": len(batch)}
        await asyncio.sleep(min(2.0 * (i + 1), 12.0))
    return [], {"source": "ddgs", "query": plain, "attempts": attempts, "hits": 0}


async def fetch_expansion_source_hits(
    source: ExpansionSource,
    *,
    plain_phrase: str,
    gdelt_client: "GdeltAsyncClient | None",
    exp: "ExpansionConfig",
    event_lang: EventLang = "en",
) -> tuple[list[GdeltHit], dict]:
    """对单一来源做多轮空结果重试；返回 (hits, meta)。"""
    plain = (plain_phrase or "").strip()
    n = max(1, min(10, int(exp.search_attempts_per_source)))
    src = source.strip().lower()
    if src == "gdelt":
        if gdelt_client is None:
            return [], {"source": "gdelt", "query": "", "attempts": 0, "hits": 0, "error": "no_client"}
        gq = gdelt_query_from_plain(plain, lang=event_lang)
        return await _gather_gdelt_with_retries(gdelt_query=gq, gdelt_client=gdelt_client, attempts=n)
    if src == "google_rss":
        return await _gather_rss_with_retries(plain=plain, exp=exp, attempts=n)
    if src == "ddgs":
        return await _gather_ddgs_with_retries(plain=plain, exp=exp, attempts=n)
    return [], {"source": src, "error": "unknown_source"}
