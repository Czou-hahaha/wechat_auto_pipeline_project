"""Dispatch expansion candidate retrieval (GDELT DOC vs DDGS)."""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from event_enhancement.gdelt.query import strip_gdelt_query_lang_suffix
from event_enhancement.gdelt.types import GdeltHit

if TYPE_CHECKING:
    from event_enhancement.config_expansion import ExpansionConfig
    from event_enhancement.gdelt.client import GdeltAsyncClient

logger = logging.getLogger(__name__)


async def collect_expansion_hits(
    *,
    queries: list[str],
    backend: str,
    gdelt_client: "GdeltAsyncClient | None",
    exp: "ExpansionConfig",
) -> list[GdeltHit]:
    """Run each query string against GDELT or DDGS (plain query = GDELT string without ``sourcelang``)."""
    b = (backend or "gdelt").strip().lower()
    out: list[GdeltHit] = []
    if b == "ddgs":
        from event_enhancement.search.ddgs_hits import ddgs_text_search_sync

        mx = max(1, min(int(exp.gdelt.max_records), 50))
        for q in queries:
            plain = strip_gdelt_query_lang_suffix(q)
            if not plain:
                continue
            part = await asyncio.to_thread(ddgs_text_search_sync, plain, mx)
            out.extend(part)
        return out

    if gdelt_client is None:
        logger.warning("collect_expansion_hits: gdelt backend but client is None")
        return []
    for q in queries:
        out.extend(await gdelt_client.search(query=q))
    return out
