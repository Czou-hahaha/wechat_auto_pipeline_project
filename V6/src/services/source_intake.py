"""Probe user-supplied URLs and recommend ingest mode (RSS / html_list / browser_zh)."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import httpx

logger = logging.getLogger(__name__)


def _host(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower().replace("www.", "")
    except Exception:
        return ""


async def _probe_rss(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    try:
        resp = await client.get(url, follow_redirects=True, timeout=25.0)
        text = resp.text[:8000]
        items = len(re.findall(r"<item[\s>]", text, re.I))
        if items == 0:
            items = len(re.findall(r"<entry[\s>]", text, re.I))
        ok = resp.status_code < 400 and items >= 1
        return {"ok": ok, "sampleCount": items, "status": resp.status_code, "probeUrl": str(resp.url)}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "probeUrl": url}


async def _probe_html_list(url: str, domain: str) -> dict[str, Any]:
    try:
        from src.html_list_monitor import fetch_html_list_hits

        hits = await fetch_html_list_hits(
            list_url=url,
            source_domain=domain or _host(url),
            relevance_filter=False,
            max_rows=5,
        )
        ok = len(hits) >= 1
        return {"ok": ok, "sampleCount": len(hits), "probeUrl": url}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "probeUrl": url}


def _guess_browser_search_url(url: str, domain: str) -> str | None:
    host = domain or _host(url)
    templates = {
        "cls.cn": "https://www.cls.cn/searchPage?keyword={query}",
        "36kr.com": "https://36kr.com/search/articles/{query}",
        "yicai.com": "https://www.yicai.com/search?keys={query}",
        "huxiu.com": "https://www.huxiu.com/search?s={query}",
        "jiemian.com": "https://a.jiemian.com/index.php?m=search&a=index&word={query}",
        "tmtpost.com": "https://www.tmtpost.com/search?q={query}",
    }
    for key, tpl in templates.items():
        if key in host:
            return tpl
    if "{query}" in url:
        return url
    return None


async def probe_source_intake(*, url: str, domain: str = "", language: str = "zh") -> dict[str, Any]:
    raw_url = (url or "").strip()
    dom = (domain or _host(raw_url)).strip()
    if not raw_url:
        raise ValueError("url required")

    results: list[dict[str, Any]] = []
    recommended = "html_list"
    confidence = 0.5

    async with httpx.AsyncClient(follow_redirects=True, trust_env=True) as client:
        rss_candidates = [raw_url]
        if dom and not raw_url.rstrip("/").endswith(("/rss", "/feed", ".xml")):
            rss_candidates.append(f"https://{dom}/rss")
        for rc in rss_candidates:
            r = await _probe_rss(client, rc)
            r["mode"] = "rss"
            results.append(r)
            if r.get("ok"):
                recommended = "rss"
                confidence = 0.9
                break

    if recommended != "rss":
        hl = await _probe_html_list(raw_url, dom)
        hl["mode"] = "html_list"
        results.append(hl)
        if hl.get("ok"):
            recommended = "html_list"
            confidence = 0.85

    browser_url = _guess_browser_search_url(raw_url, dom)
    browser_probe: dict[str, Any] = {
        "mode": "browser_zh",
        "ok": bool(browser_url),
        "searchUrlTemplate": browser_url,
    }
    if browser_url and language.startswith("zh"):
        browser_probe["smokeHint"] = browser_url.replace("{query}", quote("无人机"))
    results.append(browser_probe)
    if language.startswith("zh") and browser_url and recommended == "html_list":
        recommended = "browser_zh"
        confidence = 0.75

    draft: dict[str, Any] = {
        "name": dom or "新数据源",
        "kind": "web",
        "value": dom,
        "language": language or "zh",
        "region": "CN" if language.startswith("zh") else "GLOBAL",
        "source_type": "tech_media",
        "importance_score": 80,
        "tags": ["user_added"],
    }
    if recommended == "rss":
        probe = next(r for r in results if r.get("mode") == "rss" and r.get("ok"))
        draft["rss"] = probe.get("probeUrl") or raw_url
        draft["rss_available"] = True
    elif recommended == "browser_zh":
        draft["ingest_mode_note"] = "browser_zh"
        draft["browser_zh_search_url"] = browser_url
    else:
        draft["ingest_mode"] = "html_list"
        draft["list_monitor_url"] = raw_url

    return {
        "recommendedMode": recommended,
        "confidence": confidence,
        "probes": results,
        "draftSource": draft,
        "draftBrowserZh": (
            {"source_id": f"cn_{dom.replace('.', '_')}_001", "search_url": browser_url, "language": "zh"}
            if browser_url
            else None
        ),
    }


async def save_source_intake(
    *,
    draft_source: dict[str, Any],
    draft_browser_zh: dict[str, Any] | None,
    data_sources_path: str,
    browser_zh_path: str,
) -> dict[str, Any]:
    ds_path = Path(data_sources_path)
    if not ds_path.is_absolute():
        ds_path = Path.cwd() / ds_path
    rows = json.loads(ds_path.read_text(encoding="utf-8")) if ds_path.is_file() else []
    if not isinstance(rows, list):
        rows = []
    new_id = str(draft_source.get("id") or f"cn_user_{len(rows) + 1:03d}")
    draft_source["id"] = new_id
    rows.append(draft_source)
    ds_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    bz_saved = False
    if draft_browser_zh and draft_browser_zh.get("search_url"):
        draft_browser_zh["source_id"] = draft_browser_zh.get("source_id") or new_id
        bz_path = Path(browser_zh_path)
        if not bz_path.is_absolute():
            bz_path = Path.cwd() / bz_path
        bz = json.loads(bz_path.read_text(encoding="utf-8")) if bz_path.is_file() else []
        if not isinstance(bz, list):
            bz = []
        bz.append(draft_browser_zh)
        bz_path.write_text(json.dumps(bz, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        bz_saved = True

    return {"ok": True, "sourceId": new_id, "browserZhSaved": bz_saved, "path": str(ds_path)}
