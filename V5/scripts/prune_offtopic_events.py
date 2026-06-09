#!/usr/bin/env python3
"""移除战争/非产业叙事(治安·灾难·选举·体育)/离题事件；有正文时按全文规则清理。"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.config import Settings
from src.utils.topic_prefilter import should_keep_editorial_content, should_keep_stored_record

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    settings = Settings()
    data_dir = Path(settings.data_dir)
    events_path = data_dir / "events.json"
    articles_path = data_dir / "articles.json"
    map_path = data_dir / "event_article_map.json"

    events = json.loads(events_path.read_text(encoding="utf-8"))
    articles = json.loads(articles_path.read_text(encoding="utf-8"))
    event_map = json.loads(map_path.read_text(encoding="utf-8")) if map_path.is_file() else []

    remove_event_ids: set[str] = set()
    remove_article_ids: set[str] = set()

    for ev in events:
        if not isinstance(ev, dict):
            continue
        eid = str(ev.get("id") or "").strip()
        if not eid:
            continue
        title = str(ev.get("title_zh") or ev.get("title") or "").strip()
        press = str(ev.get("event_press_zh") or ev.get("summary_zh") or ev.get("summary") or "")
        if should_keep_editorial_content(title=title, snippet=press[:800], text=press):
            continue
        remove_event_ids.add(eid)
        logger.info("prune event=%s title=%s", eid[:13], title[:70])

    for row in articles:
        if not isinstance(row, dict):
            continue
        aid = str(row.get("id") or "").strip()
        eid = str(row.get("event_id") or "").strip()
        if not aid:
            continue
        if eid in remove_event_ids:
            remove_article_ids.add(aid)
            continue
        title = str(row.get("title") or "").strip()
        body = str(row.get("extracted_text") or row.get("summary") or "")
        if len(body.strip()) < 200:
            continue
        if should_keep_stored_record(title=title, snippet=body[:800], text=body):
            continue
        remove_article_ids.add(aid)
        if eid:
            remove_event_ids.add(eid)
        logger.info("prune article(fulltext)=%s title=%s", aid[:13], title[:70])

    if not remove_event_ids and not remove_article_ids:
        logger.info("prune_offtopic_events: nothing to remove")
        return

    kept_events = [e for e in events if str(e.get("id") or "").strip() not in remove_event_ids]
    kept_articles = [
        a
        for a in articles
        if str(a.get("id") or "").strip() not in remove_article_ids
        and str(a.get("event_id") or "").strip() not in remove_event_ids
    ]
    kept_map = [m for m in event_map if str(m.get("event_id") or "").strip() not in remove_event_ids]
    events_path.write_text(json.dumps(kept_events, ensure_ascii=False, indent=2), encoding="utf-8")
    articles_path.write_text(json.dumps(kept_articles, ensure_ascii=False, indent=2), encoding="utf-8")
    map_path.write_text(json.dumps(kept_map, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(
        "prune_offtopic_events done removed_events=%d removed_articles=%d articles=%d->%d",
        len(remove_event_ids),
        len(remove_article_ids),
        len(articles),
        len(kept_articles),
    )


if __name__ == "__main__":
    main()
