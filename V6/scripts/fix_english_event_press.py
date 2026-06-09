#!/usr/bin/env python3
"""将 events.json 中以外文为主的 event_press_zh / title 译为中文。"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.ai import SummaryService
from src.config import Settings
from src.storage import JsonStore
from src.utils.press_zh_guard import ensure_press_title_body_zh

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    settings = Settings()
    store = JsonStore(Path(settings.data_dir))
    summarizer = SummaryService(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
    )
    updated = 0
    for ev in store.list_events():
        if not isinstance(ev, dict):
            continue
        eid = str(ev.get("id") or "").strip()
        press = str(ev.get("event_press_zh") or "").strip()
        title = str(ev.get("title") or "").strip()
        if not eid or (not press and not title):
            continue
        if not (
            summarizer._text_is_mostly_non_cjk(press)
            or summarizer._text_is_mostly_non_cjk(title)
        ):
            continue
        title_zh, display_title, body_zh = await ensure_press_title_body_zh(
            summarizer, title=title, body=press or title
        )
        patch: dict[str, str] = {}
        if body_zh and body_zh != press:
            patch["event_press_zh"] = body_zh
        if title_zh:
            patch["title_zh"] = title_zh
        if display_title and display_title != title:
            patch["title"] = display_title
        if patch:
            store.patch_event(eid, patch)
            updated += 1
            logger.info("fixed event=%s keys=%s", eid[:13], list(patch.keys()))
    logger.info("fix_english_event_press done updated=%d", updated)


if __name__ == "__main__":
    asyncio.run(main())
