#!/usr/bin/env python3
"""中文 RSS/HTML 源 + 中文关键词跑一轮入库（不固定 URL、默认不推微信）。"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

V3 = Path(__file__).resolve().parents[2]
ROOT = V3.parent
sys.path.insert(0, str(V3))
sys.path.insert(0, str(ROOT / "event_enhancement"))

DEFAULT_ZH_SOURCE_IDS = (
    "cn_36kr_001,cn_36kr_list_002,cn_tmtpost_001,cn_huxiu_001,cn_jiemian_001,cn_yicai_001"
)


async def main() -> None:
    os.environ.setdefault("INGEST_ZH_HTML_ONLY", "true")
    os.environ.setdefault("INGEST_ZH_HTML_SOURCE_IDS", DEFAULT_ZH_SOURCE_IDS)
    os.environ.setdefault("INGEST_PIN_URLS", "")
    os.environ.setdefault("RSS_RELEVANCE_FILTER_ENABLED", "true")
    os.environ.setdefault("RUN_ONCE_PUSH_TO_WECHAT", "false")
    os.environ.setdefault("MAX_ARTICLE_AGE_HOURS", "168")

    from src.config import Settings
    from src.main import setup_logging
    from src.pipeline import PipelineRunner

    s = Settings()
    setup_logging(s.log_level)
    logging.info(
        "zh_keywords_once: ids=%s keywords=%s push=%s",
        s.ingest_zh_html_source_ids,
        s.parsed_chinese_keywords(),
        s.run_once_push_to_wechat,
    )
    stats = await PipelineRunner(s).run_once()
    logging.info("zh_keywords_once done: %s", stats)


if __name__ == "__main__":
    asyncio.run(main())
