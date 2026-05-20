#!/usr/bin/env python3
"""逐源探测中文 RSS/HTML：中文关键词 → 落地页 published_at。"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

_V3 = Path(__file__).resolve().parents[2]
_REPO = _V3.parent
sys.path.insert(0, str(_V3))
sys.path.insert(0, str(_REPO / "event_enhancement"))

os.environ.setdefault("HIS_DATA_SOURCES_PATH", "config/data_sources.json")
os.environ.setdefault("SEARCH_KEYWORDS_PATH", "config/search_keywords.json")
os.environ.setdefault("HTML_LIST_TIMEOUT_SEC", "25")
os.environ.setdefault("RSS_TIMEOUT_SEC", "25")

import httpx
from bs4 import BeautifulSoup

from src.config import Settings
from src.html_list_monitor import fetch_html_list_hits
from src.main import setup_logging
from src.pipeline import PipelineRunner
from src.rss_aggregate import _fetch_one_feed, _parse_iso_from_pubdate, _text_matches_any_keyword
from src.utils.search_published_at_backfill import _dom_time_probe

SOURCE_IDS = (
    "cn_36kr_001",
    "cn_36kr_list_002",
    "cn_tmtpost_001",
    "cn_huxiu_001",
    "cn_jiemian_001",
    "cn_yicai_001",
)


def _load_sources(settings: Settings) -> list[dict]:
    path = Path(settings.his_data_sources_path)
    if not path.is_absolute():
        path = _V3 / path
    rows = json.loads(path.read_text(encoding="utf-8"))
    allow = set(SOURCE_IDS)
    out: list[dict] = []
    for row in rows:
        if isinstance(row, dict) and str(row.get("id") or "") in allow:
            out.append(row)
    return out


async def _hits_for_source(
    client: httpx.AsyncClient,
    row: dict,
    *,
    keywords: list[str],
) -> list[dict]:
    sid = str(row.get("id") or "")
    hits: list[dict] = []
    rss = str(row.get("rss") or "").strip()
    if rss.startswith("http"):
        raw_hits = await _fetch_one_feed(
            client,
            rss,
            per_feed_max=12,
            keywords=keywords,
            relevance_filter=True,
        )
        for h in raw_hits:
            hits.append(
                {
                    "url": h.url,
                    "title": h.title,
                    "rss_published_at": h.published_at or "",
                    "via": "rss",
                }
            )
    if str(row.get("ingest_mode") or "").lower() == "html_list":
        lu = str(row.get("list_monitor_url") or "").strip()
        val = str(row.get("value") or "").strip()
        if lu.startswith("http") and val:
            list_hits = await fetch_html_list_hits(
                client,
                list_url=lu,
                site_value=val,
                per_feed_max=15,
                keywords=keywords,
                relevance_filter=True,
                source_name=str(row.get("name") or sid),
            )
            for h in list_hits:
                hits.append(
                    {
                        "url": h.url,
                        "title": h.title,
                        "rss_published_at": h.published_at or "",
                        "via": "html_list",
                    }
                )
    # 去重 URL
    seen: set[str] = set()
    deduped: list[dict] = []
    for h in hits:
        u = (h.get("url") or "").strip()
        if not u or u in seen:
            continue
        seen.add(u)
        deduped.append(h)
    return deduped[:5]


async def _probe_page(
    client: httpx.AsyncClient,
    runner: PipelineRunner,
    url: str,
) -> dict:
    out: dict = {"url": url, "ok": False, "published_at": "", "date_only": False, "error": ""}
    try:
        resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30.0)
        resp.raise_for_status()
        soup = BeautifulSoup(runner._decode_html(resp), "html.parser")
        iso, coarse = runner._extract_published_at(soup, page_url=str(resp.url))
        out["final_url"] = str(resp.url)
        out["dom_probe"] = _dom_time_probe(soup)
        if iso:
            out["ok"] = True
            out["published_at"] = iso
            out["date_only"] = coarse
        else:
            out["error"] = "extract_empty"
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"[:280]
    return out


async def main() -> None:
    setup_logging("INFO")
    s = Settings()
    zh = s.parsed_chinese_keywords()
    runner = PipelineRunner(s)
    sources = _load_sources(s)
    report: dict = {"at": datetime.now(timezone.utc).isoformat(), "chinese_keywords": zh, "sources": {}}

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), follow_redirects=True) as client:
        for row in sources:
            sid = str(row.get("id") or "")
            logging.info("probe source %s", sid)
            hits = await _hits_for_source(client, row, keywords=zh)
            entry = {"config": {"rss": row.get("rss"), "list": row.get("list_monitor_url")}, "hits": len(hits), "articles": []}
            for h in hits[:2]:
                probe = await _probe_page(client, runner, h["url"])
                probe["title"] = (h.get("title") or "")[:100]
                probe["rss_published_at"] = h.get("rss_published_at") or ""
                probe["via"] = h.get("via")
                entry["articles"].append(probe)
            if not hits:
                entry["note"] = "no_keyword_hits"
            report["sources"][sid] = entry

    out = _V3 / "data" / "probe_zh_published_at.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== 中文源 published_at 探测（中文关键词）===\n")
    for sid, entry in report["sources"].items():
        print(f"[{sid}] 命中={entry.get('hits', 0)}")
        if entry.get("note"):
            print(f"  {entry['note']}")
        for a in entry.get("articles", []):
            st = "OK" if a.get("ok") else "FAIL"
            print(f"  {st} page={a.get('published_at') or '-'} rss={a.get('rss_published_at') or '-'} via={a.get('via')}")
            print(f"      {(a.get('title') or '')[:70]}")
            if not a.get("ok"):
                dom = a.get("dom_probe") or {}
                print(f"      err={a.get('error')} meta={dom.get('meta_published_fields', [])[:1]} time={dom.get('time_datetime_attrs', [])[:2]}")
    print(f"\n报告: {out}")


if __name__ == "__main__":
    asyncio.run(main())
