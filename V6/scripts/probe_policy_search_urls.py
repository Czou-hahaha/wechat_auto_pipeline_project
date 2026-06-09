#!/usr/bin/env python3
"""探测政务站 browser_zh search_url 是否返回可解析政策/新闻链接。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

POLICY_SITES = [
    {
        "source_id": "cn_gov_001",
        "url": "https://sousuo.www.gov.cn/sousuo/search.shtml?code=17dbd896757b40679c54f6070455767&dataTypeId=107&searchWord={query}",
        "needle": "gov.cn",
    },
    {
        "source_id": "cn_ndrc_001",
        "url": "https://so.ndrc.gov.cn/s?siteCode=bm04000007&tab=all&qt={query}",
        "needle": "ndrc.gov.cn",
    },
    {
        "source_id": "cn_miit_001",
        "url": "https://www.miit.gov.cn/search/index.html?websiteid=1100000001&word={query}",
        "needle": "miit.gov.cn",
    },
    {
        "source_id": "cn_most_001",
        "url": "https://www.most.gov.cn/search/kj.html?searchword={query}",
        "needle": "most.gov.cn",
    },
    {
        "source_id": "cn_caac_001",
        "url": "https://www.caac.gov.cn/was5/web/search?channelid=203956&searchword={query}",
        "needle": "caac.gov.cn",
    },
    {
        "source_id": "cn_shenzhen_001",
        "url": "https://www.sz.gov.cn/search/gq/?keywords={query}",
        "needle": "sz.gov.cn",
    },
]


def probe_with_playwright(query: str, headless: bool = True) -> list[dict]:
    from playwright.sync_api import sync_playwright

    from src.browser_zh_search import _EXTRACT_LINKS_JS

    out: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page(locale="zh-CN")
        for site in POLICY_SITES:
            url = site["url"].replace("{query}", quote(query))
            needle = site["needle"]
            links = 0
            err = ""
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(4000)
                rows = page.evaluate(
                    _EXTRACT_LINKS_JS,
                    {"hrefNeedle": needle, "timeSelector": ""},
                )
                links = len(rows) if isinstance(rows, list) else 0
            except Exception as exc:
                err = str(exc)[:200]
            out.append(
                {
                    "source_id": site["source_id"],
                    "url": url,
                    "links": links,
                    "ok": links > 0,
                    "error": err,
                }
            )
        browser.close()
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe policy browser_zh search URLs")
    parser.add_argument("--query", default="无人机", help="Search keyword")
    parser.add_argument("--json-out", default="", help="Write results to JSON file")
    parser.add_argument("--no-headless", action="store_true")
    args = parser.parse_args()
    rows = probe_with_playwright(args.query, headless=not args.no_headless)
    for row in rows:
        status = "OK" if row["ok"] else "FAIL"
        print(f"[{status}] {row['source_id']} links={row['links']} {row.get('error', '')}")
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"query": args.query, "results": rows}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    ok_n = sum(1 for r in rows if r["ok"])
    print(f"summary: {ok_n}/{len(rows)} sites with links>0")
    return 0 if ok_n >= 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
