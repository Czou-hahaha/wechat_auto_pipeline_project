#!/usr/bin/env python3
"""合并 ACSL–Draganfly 重复事件：保留 e7809b13，并入 a9e30739 主稿。"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.config import Settings
from src.storage import JsonStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KEEP = "e7809b13-dfc8-447e-9f51-807d421813ff"
DROP = "a9e30739-ed0e-45b5-b9e1-2c48c7c3cefb"
SUAS = "https://www.suasnews.com/2026/05/drone-makers-acsl-and-draganfly-partner-to-bring-ndaa-compliant-japanese-drones-to-canadian-market-signs-exclusive-distributor-agreement-and-launches-technology-integration/"


def main() -> None:
    settings = Settings()
    store = JsonStore(Path(settings.data_dir))
    moved = 0
    for row in store._read():
        if not isinstance(row, dict):
            continue
        url = str(row.get("resolved_url") or row.get("source_url") or "")
        if str(row.get("event_id") or "") == DROP or url.rstrip("/") == SUAS.rstrip("/"):
            aid = str(row.get("id") or "")
            if aid:
                store.patch_article(aid, {"event_id": KEEP})
                moved += 1
    maps = store._read_event_map()
    new_maps = []
    for m in maps:
        if str(m.get("event_id") or "") == DROP:
            new_maps.append(
                {
                    **m,
                    "event_id": KEEP,
                    "role": "support",
                }
            )
        elif str(m.get("event_id") or "") != DROP:
            new_maps.append(m)
    store._write_event_map(new_maps)
    events = [e for e in store.list_events() if str(e.get("id") or "") != DROP]
    store._write_events(events)
    logger.info("merged duplicate ACSL: moved_articles=%d dropped_event=%s", moved, DROP[:13])


if __name__ == "__main__":
    main()
