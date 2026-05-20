#!/usr/bin/env python3
"""五家中文源 + 关键词「低空经济」：每站最多抓 2 篇，输出预览 JSON（不写 articles.json）。"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

V3 = Path(__file__).resolve().parents[2]
ROOT = V3.parent
sys.path.insert(0, str(V3))
sys.path.insert(0, str(ROOT / "event_enhancement"))

SITE_HOSTS: dict[str, str] = {
    "36kr.com": "36氪",
    "tmtpost.com": "钛媒体",
    "huxiu.com": "虎嗅",
    "jiemian.com": "界面新闻-科技",
    "yicai.com": "第一财经",
}

ZH_SOURCE_IDS = (
    "cn_36kr_001,cn_36kr_list_002,cn_tmtpost_001,cn_huxiu_001,cn_jiemian_001,cn_yicai_001"
)
MAX_SCAN_PER_SITE = 50
KEYWORD = "低空经济"
OUT_PATH = V3 / "data/zh_dikong_preview.json"


def _site_key(url: str) -> str | None:
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    for domain, name in SITE_HOSTS.items():
        if host == domain or host.endswith("." + domain):
            return name
    return None


async def main() -> None:
    os.environ.setdefault("INGEST_ZH_HTML_ONLY", "true")
    os.environ.setdefault("INGEST_ZH_HTML_SOURCE_IDS", ZH_SOURCE_IDS)
    os.environ.setdefault("INGEST_PIN_URLS", "")
    os.environ.setdefault("RSS_RELEVANCE_FILTER_ENABLED", "false")
    os.environ.setdefault("RSS_PER_FEED_MAX", "30")
    os.environ.setdefault("RSS_TOTAL_MAX", "200")
    os.environ.setdefault("MAX_ARTICLE_AGE_HOURS", "168")
    os.environ.setdefault("RUN_ONCE_PUSH_TO_WECHAT", "false")

    from src.config import Settings
    from src.main import setup_logging
    from src.pipeline import PipelineRunner
    from src.rss_aggregate import aggregate_rss_from_data_sources
    from src.utils.topic_prefilter import should_fetch_zh_media_hit

    s = Settings()
    setup_logging(s.log_level)
    logging.info("preview dikong: sources=%s keyword=%s", s.ingest_zh_html_source_ids, KEYWORD)

    hits = await aggregate_rss_from_data_sources(s)
    kept = [h for h in hits if should_fetch_zh_media_hit(h)]
    logging.info("rss hits total=%d after_zh_prefilter=%d", len(hits), len(kept))

    by_site: dict[str, list] = defaultdict(list)
    for h in kept:
        site = _site_key(h.url)
        if site:
            by_site[site].append(h)

    runner = PipelineRunner(s)
    articles: list[dict] = []
    for site_name in SITE_HOSTS.values():
        matched: list[dict] = []
        scanned = 0
        for hit in by_site.get(site_name, [])[:MAX_SCAN_PER_SITE]:
            if len(matched) >= 2:
                break
            scanned += 1
            try:
                title, text, _, final_url, page_pub, _ = await runner._fetch_text(
                    hit.url, fallback_title=hit.title, fallback_snippet=hit.snippet
                )
                blob = f"{title}\n{hit.snippet or ''}\n{text or ''}"
                if KEYWORD not in blob:
                    continue
                pub, _ = runner._resolve_source_published_at(
                    page_published_at=page_pub, page_date_only_coarse=False
                )
                matched.append(
                    {
                        "site": site_name,
                        "status": "ok",
                        "title": title,
                        "source_url": hit.url,
                        "resolved_url": final_url or hit.url,
                        "source_published_at": pub or hit.published_at or "",
                        "rss_snippet": (hit.snippet or "")[:400],
                        "extracted_text_preview": (text or "")[:1200],
                        "extracted_chars": len(text or ""),
                    }
                )
            except Exception as exc:
                logging.warning("fetch failed %s: %s", hit.url, exc)
        if not matched:
            articles.append(
                {
                    "site": site_name,
                    "status": "no_keyword_match",
                    "rss_candidates": len(by_site.get(site_name, [])),
                    "pages_scanned": scanned,
                    "note": f"已扫 RSS 候选，正文/标题未出现「{KEYWORD}」",
                }
            )
        else:
            articles.extend(matched)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(articles, ensure_ascii=False, indent=2), encoding="utf-8")
    logging.info("wrote preview %s items=%d", OUT_PATH, len(articles))
    print(json.dumps(articles, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
