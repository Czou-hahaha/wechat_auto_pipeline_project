#!/usr/bin/env python3
"""合并库内已知重复 event（保留较早/较完整的一条）。"""
from __future__ import annotations

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

# (keep, drop)
PAIRS: list[tuple[str, str]] = [
    (
        "e06842b5-1147-4fb9-9b0c-b8ae6fc71a29",
        "26959401-c969-4d12-b268-b98457cdc187",
    ),
    (
        "7db0febe-5d39-4a5f-ae4d-a44b0c3a9956",
        "eb9489ef-283e-4d1a-995b-a405530ca36e",
    ),
]


def merge_pair(store: JsonStore, keep: str, drop: str) -> None:
    moved_articles = 0
    for row in store._read():
        if not isinstance(row, dict):
            continue
        if str(row.get("event_id") or "") == drop:
            aid = str(row.get("id") or "")
            if aid:
                store.patch_article(aid, {"event_id": keep})
                moved_articles += 1

    maps = store._read_event_map()
    seen: set[tuple[str, str]] = set()
    new_maps: list[dict] = []
    for m in maps:
        if not isinstance(m, dict):
            continue
        eid = str(m.get("event_id") or "")
        if eid == drop:
            m = {**m, "event_id": keep, "role": m.get("role") or "support"}
            eid = keep
        url = str(m.get("resolved_url") or m.get("source_url") or "")
        key = (eid, store.url_fingerprint(url))
        if key in seen:
            continue
        seen.add(key)
        new_maps.append(m)
    store._write_event_map(new_maps)

    events = [e for e in store.list_events() if str(e.get("id") or "") != drop]
    store._write_events(events)
    logger.info(
        "merged duplicate events keep=%s drop=%s moved_articles=%d",
        keep[:13],
        drop[:13],
        moved_articles,
    )


def main() -> None:
    settings = Settings()
    store = JsonStore(Path(settings.data_dir))
    for keep, drop in PAIRS:
        if not store.get_event(keep):
            logger.warning("skip missing keep=%s", keep[:13])
            continue
        if not store.get_event(drop):
            logger.warning("skip missing drop=%s", drop[:13])
            continue
        merge_pair(store, keep, drop)


if __name__ == "__main__":
    main()
