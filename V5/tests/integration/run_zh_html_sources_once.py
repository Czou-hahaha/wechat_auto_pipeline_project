#!/usr/bin/env python3
"""仅跑新增中文 html_list 源 + FCC 固定 URL，再走 run_once 全流程（含推微信）。"""
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

from src.config import Settings
from src.main import setup_logging
from src.pipeline import PipelineRunner

# cn_36kr_001=RSS（稳定）；其余 html_list 为 SPA 栏目页，解析不到链接时仍保留配置供后续改版
DEFAULT_ZH_SOURCE_IDS = (
    "cn_36kr_001,cn_36kr_list_002,cn_tmtpost_001,cn_huxiu_001,cn_jiemian_001,cn_yicai_001"
)
DEFAULT_PIN_URLS = (
    "https://dronedj.com/2026/05/18/dji-autel-fcc-drone-firmware/,"
    "https://dronedj.com/2026/05/19/autel-drone-ban-us-fcc/"
)


async def main() -> None:
    os.environ.setdefault("INGEST_ZH_HTML_ONLY", "true")
    os.environ.setdefault("INGEST_ZH_HTML_SOURCE_IDS", DEFAULT_ZH_SOURCE_IDS)
    os.environ.setdefault("INGEST_PIN_URLS", DEFAULT_PIN_URLS)
    os.environ.setdefault("CLUSTER_SUMMARY_MAX_SOURCES", "5")
    os.environ.setdefault("CLUSTER_SUMMARY_EXCERPT_CHARS", "1500")
    os.environ.setdefault("RUN_ONCE_PUSH_TO_WECHAT", "true")
    # 中文源验收：先放宽 RSS 标题词表，产业门在抓正文后由 editorial/scope 过滤
    os.environ.setdefault("RSS_RELEVANCE_FILTER_ENABLED", "false")

    s = Settings()
    setup_logging(s.log_level)
    logging.info(
        "zh_html_sources_once: ids=%s pin_urls=%d push=%s",
        s.ingest_zh_html_source_ids,
        len(s.parsed_ingest_pin_urls()),
        s.run_once_push_to_wechat,
    )
    stats = await PipelineRunner(s).run_once()
    logging.info("zh_html_sources_once done: %s", stats)


if __name__ == "__main__":
    asyncio.run(main())
