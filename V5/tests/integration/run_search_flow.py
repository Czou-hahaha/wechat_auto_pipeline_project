"""
搜索流程端到端测试：RSS 聚合 + GDELT 主题检索，获取近 12 小时新闻。
直接输出到 stdout，方便查看结果。

若某条 ``published_at`` 仍为空，则 GET 原文 HTML，用与主链路一致的 ``PipelineRunner._extract_published_at``
补全时间，并在 JSON 中写入 DOM 探测（所有 ``<time datetime>``、常见 ``meta`` 发布时间）。
Phase 2 在 ``filter_by_age`` **之前**对缺 ``published_at`` 的条目抓落地页补全（与 ``run_once`` 主链路一致）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from time import perf_counter
from pathlib import Path

_V3_ROOT = Path(__file__).resolve().parents[2]
if str(_V3_ROOT) not in sys.path:
    sys.path.insert(0, str(_V3_ROOT))

os.environ.setdefault("MAX_ARTICLE_AGE_HOURS", "12")
os.environ.setdefault("RSS_AGGREGATE_ENABLED", "true")
os.environ.setdefault("SEARCH_LOAD_HIS_DATA_SOURCES", "true")
os.environ.setdefault("HIS_DATA_SOURCES_PATH", "config/data_sources.json")
os.environ.setdefault("SEARCH_KEYWORDS_PATH", "config/search_keywords.json")
os.environ.setdefault("GDELT_TIMEOUT_SEC", "45")
os.environ.setdefault("GDELT_MAX_RECORDS", "50")
os.environ.setdefault("LOG_LEVEL", "INFO")
os.environ.setdefault("SEARCH_TEST_ARTICLE_PAGE_BACKFILL", "true")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(name)s - %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)

from src.config import Settings
from src.html_list_monitor import _iso_from_time_datetime_attr
from src.rss_aggregate import aggregate_rss_from_data_sources
from src.search import SearchHit, filter_by_age, merge_search_hits, search_gdelt_topics_bilingual
from src.utils.search_published_at_backfill import backfill_missing_published_at

def _fmt_hit(i: int, h: SearchHit) -> str:
    pub = h.published_at or "(无时间)"
    source = "RSS" if h.from_rss else "GDELT"
    snippet_preview = (h.snippet or "")[:120].replace("\n", " ")
    return (
        f"  [{i:>3}] [{source:>5}] {h.title}\n"
        f"        URL: {h.url}\n"
        f"        Published: {pub}\n"
        f"        Snippet: {snippet_preview}..."
    )


async def main() -> None:
    s = Settings()
    zh = s.parsed_chinese_keywords()
    en = s.parsed_english_keywords()
    max_hours = s.max_article_age_hours

    print("=" * 80)
    print(f"搜索流程测试 — 获取近 {max_hours} 小时新闻")
    print(f"当前 UTC 时间: {datetime.now(timezone.utc).isoformat()}")
    print(f"chinese_keywords: {zh}")
    print(f"english_keywords: {en}")
    print(f"RSS_RELEVANCE_FILTER_ENABLED: {s.rss_relevance_filter_enabled}")
    print("=" * 80)

    print("\n>>> Phase 0: RSS 聚合 <<<")
    t0 = perf_counter()
    rss_hits = await aggregate_rss_from_data_sources(s)
    print(f"    RSS 原始结果: {len(rss_hits)} 条  耗时: {perf_counter() - t0:.2f}s")
    rss_aged = filter_by_age(rss_hits, max_hours)
    print(f"    RSS {max_hours}h 窗口过滤后: {len(rss_aged)} 条")

    print("\n>>> Phase 1: GDELT 主题检索（仅英文，一词一请求串行） <<<")
    t1 = perf_counter()
    gdelt_hits, http_n = await search_gdelt_topics_bilingual(s)
    print(f"    GDELT 合并结果: {len(gdelt_hits)} 条  HTTP 请求次数: {http_n}  耗时: {perf_counter() - t1:.2f}s")

    merge_cap = 1500
    all_hits = merge_search_hits(rss_hits, gdelt_hits, max_total=merge_cap)
    print(f"\n合并去重后: {len(all_hits)} 条")

    missing_before = sum(1 for h in all_hits if not (h.published_at or "").strip())
    print(f"\n>>> Phase 2: 原文页补全 published_at（缺时间 {missing_before}/{len(all_hits)} 条）<<<")
    t2 = perf_counter()
    all_hits, probes = await backfill_missing_published_at(all_hits, s)
    aged = filter_by_age(all_hits, max_hours)
    print(f"{max_hours}h 时间窗过滤后: {len(aged)} 条")
    filled_from_page = sum(1 for p in probes if p.get("published_at_source") == "article_page_pipeline")
    still_missing = sum(1 for h in aged if not (h.published_at or "").strip())
    print(f"    从原文 HTML 解析补全: {filled_from_page} 条  仍缺: {still_missing} 条  耗时: {perf_counter() - t2:.2f}s")

    print("\n" + "=" * 80)
    print(f"最终结果 ({len(aged)} 条，含原文补全后)")
    print("=" * 80)

    if not aged:
        print("  (无结果)")
    else:
        for i, h in enumerate(aged, 1):
            print(_fmt_hit(i, h))

    rss_count = sum(1 for h in aged if h.from_rss)
    gdelt_count = len(aged) - rss_count
    print("\n" + "-" * 80)
    print(f"统计: RSS={rss_count}  GDELT={gdelt_count}  总计={len(aged)}")
    print("-" * 80)

    if aged:
        out_path = str(_V3_ROOT / "tests/data/search/test_search_results.json")
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        records: list[dict[str, Any]] = []
        for h, pr in zip(aged, probes):
            records.append(
                {
                    "title": h.title,
                    "url": h.url,
                    "snippet": h.snippet[:500],
                    "published_at": h.published_at,
                    "from_rss": h.from_rss,
                    "published_at_probe": pr,
                }
            )
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        print(f"\n详细结果已写入: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
