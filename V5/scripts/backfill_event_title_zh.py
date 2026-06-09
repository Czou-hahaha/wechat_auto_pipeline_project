#!/usr/bin/env python3
"""为 events.json 生成短中文标题 headline_zh / title_zh（12–28 字）。"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.ai import SummaryService
from src.bff.event_mapper import _event_press_text
from src.config import Settings
from src.storage import JsonStore
from src.utils.headline_zh import (
    first_zh_sentence,
    is_overlong_zh_headline,
    trim_zh_headline_heuristic,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    settings = Settings()
    store = JsonStore(Path(settings.data_dir))
    svc = SummaryService(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
    )
    updated = 0
    for ev in store.list_events():
        if not isinstance(ev, dict):
            continue
        eid = str(ev.get("id") or "").strip()
        if not eid:
            continue
        headline = str(ev.get("headline_zh") or "").strip()
        if headline and not is_overlong_zh_headline(headline):
            continue
        title = str(ev.get("title") or "").strip()
        press = _event_press_text(ev)
        lede = first_zh_sentence(press) if press else ""
        new_headline = ""
        if svc._api_key:
            new_headline = await svc.generate_compact_headline_zh(
                context_title=title,
                press_lede=lede or str(ev.get("summary") or "")[:200],
            )
        if not new_headline:
            tzh = str(ev.get("title_zh") or "").strip()
            if tzh:
                new_headline = trim_zh_headline_heuristic(tzh)
            elif lede:
                new_headline = trim_zh_headline_heuristic(lede)
        if not new_headline or is_overlong_zh_headline(new_headline):
            continue
        store.patch_event(
            eid,
            {"headline_zh": new_headline, "title_zh": new_headline},
        )
        updated += 1
        logger.info("headline event=%s %s", eid[:13], new_headline)
    logger.info("backfill done updated=%d", updated)


if __name__ == "__main__":
    asyncio.run(main())
