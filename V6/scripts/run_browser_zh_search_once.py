#!/usr/bin/env python3
"""单次跑中文站 Playwright 搜索，打印命中 URL（不入库）。"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.browser_zh_search import aggregate_browser_zh_search
from src.config import Settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


async def main() -> int:
    settings = Settings()
    if not settings.browser_zh_search_enabled:
        print("Set BROWSER_ZH_SEARCH_ENABLED=true in V4/.env first.")
        return 1
    hits = await aggregate_browser_zh_search(settings)
    print(f"\n=== browser_zh hits: {len(hits)} ===\n")
    for i, h in enumerate(hits[:50], 1):
        pub = h.published_at or "(no list time)"
        print(f"{i}. {h.title[:70]}")
        print(f"   {h.url}")
        print(f"   published_at={pub}\n")
    if len(hits) > 50:
        print(f"... and {len(hits) - 50} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
