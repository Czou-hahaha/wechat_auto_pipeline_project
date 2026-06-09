#!/usr/bin/env python3
"""将 articles.wechat_draft_pushed_at 同步到 events.event_wechat_draft_pushed_at。"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.config import Settings
from src.storage import JsonStore


def main() -> None:
    store = JsonStore(Path(Settings().data_dir))
    n = store.sync_event_draft_pushed_flags()
    pushed_articles = sum(
        1
        for r in store.list_all()
        if isinstance(r, dict) and str(r.get("wechat_draft_pushed_at") or "").strip()
    )
    print(f"synced_events={n} articles_with_draft_pushed_at={pushed_articles}")


if __name__ == "__main__":
    main()
