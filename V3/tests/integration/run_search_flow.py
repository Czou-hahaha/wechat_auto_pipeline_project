"""
搜索流程端到端测试：RSS 聚合 + GDELT 主题检索，获取近 12 小时新闻。
直接输出到 stdout，方便查看结果。

若某条 ``published_at`` 仍为空，则 GET 原文 HTML，用与主链路一致的 ``PipelineRunner._extract_published_at``
补全时间，并在 JSON 中写入 DOM 探测（所有 ``<time datetime>``、常见 ``meta`` 发布时间）。
注意：候选集已先经 ``filter_by_age`` 剔除「无发布时间」条目；Phase 2 仅对仍留在列表中的 URL 有意义（通常为检索侧已有时间的复核/探测）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
from dataclasses import replace
from datetime import datetime, timezone
from time import perf_counter
from typing import Any
from pathlib import Path
from zoneinfo import ZoneInfo

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

from bs4 import BeautifulSoup
import httpx

from src.config import Settings
from src.html_list_monitor import _iso_from_time_datetime_attr
from src.pipeline import PipelineRunner
from src.rss_aggregate import aggregate_rss_from_data_sources
from src.search import SearchHit, filter_by_age, merge_search_hits, search_gdelt_topics_bilingual

_FETCH_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_ISO_DAY_RE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")


def _dom_time_probe(soup: BeautifulSoup) -> dict[str, Any]:
    """开发者工具可见的 DOM：``<time datetime>`` 与常见 ``meta`` 发布时间（仅探测，不解析择优）。"""
    time_attrs = [
        str(t.get("datetime")).strip()
        for t in soup.select("time[datetime]")
        if (t.get("datetime") or "").strip()
    ]
    meta_rows: list[dict[str, str]] = []
    for attr, key in (
        ("property", "article:published_time"),
        ("property", "og:published_time"),
        ("property", "article:modified_time"),
        ("itemprop", "datePublished"),
        ("itemprop", "dateCreated"),
        ("name", "pubdate"),
        ("name", "publishdate"),
    ):
        for node in soup.find_all("meta", attrs={attr: key}):
            c = (node.get("content") or node.get("datetime") or "").strip()
            if c:
                meta_rows.append({attr: key, "content": c[:200]})
    return {
        "time_datetime_attrs": time_attrs[:30],
        "meta_published_fields": meta_rows[:20],
    }


async def _backfill_one(
    client: Any,
    h: SearchHit,
    runner: PipelineRunner,
    sem: asyncio.Semaphore,
) -> tuple[SearchHit, dict[str, Any]]:
    """对单条：若缺 ``published_at`` 则抓原文并解析；返回 (可能更新后的 hit, probe 字典)。"""
    probe: dict[str, Any] = {
        "article_page_fetched": False,
        "article_page_final_url": "",
        "article_page_fetch_error": "",
        "published_at_source": "search_hit",
        "dom_probe": {},
        "pipeline_published_at": "",
        "pipeline_date_only": False,
    }
    if (h.published_at or "").strip():
        probe["published_at_source"] = "search_hit"
        return h, probe
    url = (h.url or "").strip()
    if not url.startswith("http"):
        probe["article_page_fetch_error"] = "invalid_url"
        return h, probe
    async with sem:
        try:
            resp = await client.get(url, headers={"User-Agent": _FETCH_UA})
            resp.raise_for_status()
        except Exception as exc:
            probe["article_page_fetch_error"] = f"{type(exc).__name__}: {exc}"[:500]
            return h, probe
    probe["article_page_fetched"] = True
    probe["article_page_final_url"] = str(resp.url)
    html_text = PipelineRunner._decode_html(resp)
    soup = BeautifulSoup(html_text, "html.parser")
    probe["dom_probe"] = _dom_time_probe(soup)
    page_iso, date_only = runner._extract_published_at(soup, page_url=str(resp.url))
    probe["pipeline_published_at"] = page_iso
    probe["pipeline_date_only"] = bool(date_only)
    if (page_iso or "").strip():
        probe["published_at_source"] = "article_page_pipeline"
        return replace(h, published_at=page_iso.strip()), probe
    for raw_td in probe["dom_probe"].get("time_datetime_attrs") or []:
        cand = _iso_from_time_datetime_attr(raw_td)
        if cand:
            probe["published_at_source"] = "article_page_dom_time_only"
            probe["pipeline_published_at"] = cand
            return replace(h, published_at=cand), probe
    for row in probe["dom_probe"].get("meta_published_fields") or []:
        raw_m = (row.get("content") or "").strip()
        if not raw_m:
            continue
        cand = _iso_from_time_datetime_attr(raw_m) if "T" in raw_m else ""
        if not cand:
            m = _ISO_DAY_RE.search(raw_m)
            if m:
                cand = (
                    datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), 12, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
                    .astimezone(timezone.utc)
                    .isoformat()
                )
        if cand:
            probe["published_at_source"] = "article_page_dom_meta_only"
            probe["pipeline_published_at"] = cand
            return replace(h, published_at=cand), probe
    probe["published_at_source"] = "missing_after_article_page"
    return h, probe


async def backfill_missing_published_at(
    hits: list[SearchHit],
    settings: Settings,
    *,
    max_concurrent: int = 4,
) -> tuple[list[SearchHit], list[dict[str, Any]]]:
    """对 ``published_at`` 为空的条目抓取原文并探测 DOM；返回新 hit 列表与每条 probe（与 hits 对齐）。"""
    if (os.environ.get("SEARCH_TEST_ARTICLE_PAGE_BACKFILL") or "true").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return hits, [{} for _ in hits]
    runner = PipelineRunner(settings)
    sem = asyncio.Semaphore(max(1, int(max_concurrent)))
    timeout = float(os.environ.get("SEARCH_TEST_ARTICLE_FETCH_TIMEOUT_SEC", "35") or "35")
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        tasks = [_backfill_one(client, h, runner, sem) for h in hits]
        pairs = await asyncio.gather(*tasks)
    new_hits = [p[0] for p in pairs]
    probes = [p[1] for p in pairs]
    return new_hits, probes


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

    print("\n>>> Phase 1: GDELT 主题检索（中/英 OR，少量 HTTP） <<<")
    t1 = perf_counter()
    gdelt_hits, http_n = await search_gdelt_topics_bilingual(s)
    print(f"    GDELT 合并结果: {len(gdelt_hits)} 条  HTTP 请求次数: {http_n}  耗时: {perf_counter() - t1:.2f}s")

    merge_cap = 1500
    all_hits = merge_search_hits(rss_hits, gdelt_hits, max_total=merge_cap)
    print(f"\n合并去重后: {len(all_hits)} 条")

    aged = filter_by_age(all_hits, max_hours)
    print(f"{max_hours}h 时间窗过滤后: {len(aged)} 条")

    missing_before = sum(1 for h in aged if not (h.published_at or "").strip())
    print(f"\n>>> Phase 2: 原文页补全 published_at + DOM 探测（检索阶段缺 {missing_before} 条）<<<")
    t2 = perf_counter()
    aged, probes = await backfill_missing_published_at(aged, s)
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
