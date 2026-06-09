"""从 ``data_sources.json`` 聚合 RSS 与栏目页 HTML 列表，输出 ``SearchHit``（``from_rss=True``）。"""
from __future__ import annotations

import asyncio
import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import httpx

from src.config import Settings
from src.html_list_monitor import DEFAULT_INGEST_UA, fetch_html_list_hits
from src.search import SearchHit, _dedupe_hits, _is_blocked_url, normalize_snippet, normalize_title

try:
    from src.browser_zh_search import aggregate_browser_zh_search
except ImportError:
    aggregate_browser_zh_search = None  # type: ignore[misc, assignment]

logger = logging.getLogger(__name__)

_DC_NS = "{http://purl.org/dc/elements/1.1/}"


def _language_bucket(lang: str) -> str:
    s = (lang or "").strip().lower()
    if s.startswith("zh"):
        return "zh"
    if s.startswith("en"):
        return "en"
    return "zh"


def _text_matches_any_keyword(haystack: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    blob = haystack or ""
    for k in keywords:
        kw = (k or "").strip()
        if not kw:
            continue
        ascii_only = all(ord(c) < 128 for c in kw)
        if ascii_only:
            if kw.casefold() in blob.casefold():
                return True
        elif kw in blob:
            return True
    return False


def _parse_iso_from_pubdate(raw: str) -> str:
    """解析 RSS/DC 常见发布时间串（含 36 氪等非 RFC822 的 ``YYYY-MM-DD HH:MM:SS``）。"""
    s = (raw or "").strip()
    if not s:
        return ""
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        pass
    sh = ZoneInfo("Asia/Shanghai")
    for probe in (s, s.replace("T", " ", 1)):
        try:
            dtp = datetime.fromisoformat(probe.replace("Z", "+00:00"))
            if dtp.tzinfo is None:
                dtp = dtp.replace(tzinfo=timezone.utc)
            return dtp.astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            dtp = datetime.strptime(s[:32], fmt).replace(tzinfo=sh)
            return dtp.astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            dtp = datetime.strptime(s[:16], fmt).replace(tzinfo=sh)
            return dtp.astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    return ""


def _item_pubdate(node: ET.Element) -> str:
    for tag in ("pubDate", f"{_DC_NS}date", "published", "updated", "date"):
        raw = (node.findtext(tag) or "").strip()
        if raw:
            iso = _parse_iso_from_pubdate(raw)
            if iso:
                return iso
    return ""


def _parse_feed_items(
    xml_text: str,
    feed_url: str,
    *,
    max_items: int,
    keywords: list[str] | None,
    relevance_filter: bool,
) -> list[SearchHit]:
    rows: list[SearchHit] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        logger.warning("rss parse error feed=%s", feed_url[:80])
        return rows
    for node in root.findall(".//item"):
        t = (node.findtext("title") or "").strip()
        u = (node.findtext("link") or "").strip()
        desc = (node.findtext("description") or "").strip()
        if not t or not u:
            continue
        if not u.startswith("http"):
            u = urljoin(feed_url if feed_url.endswith("/") else feed_url + "/", u)
        if _is_blocked_url(u):
            continue
        title = normalize_title(t)
        snippet = normalize_snippet(desc)[:2000]
        if relevance_filter and keywords:
            if not _text_matches_any_keyword(f"{title} {snippet}", keywords):
                continue
        pub = _item_pubdate(node)
        rows.append(SearchHit(title=title, url=u, snippet=snippet, published_at=pub, from_rss=True))
        if len(rows) >= max_items:
            break
    return rows


async def _fetch_one_feed(
    client: httpx.AsyncClient,
    feed_url: str,
    *,
    per_feed_max: int,
    keywords: list[str] | None,
    relevance_filter: bool,
) -> list[SearchHit]:
    try:
        resp = await client.get(feed_url, headers={"User-Agent": DEFAULT_INGEST_UA})
        resp.raise_for_status()
        text = resp.text
        if not text.strip():
            return []
        return _parse_feed_items(
            text,
            feed_url,
            max_items=per_feed_max,
            keywords=keywords,
            relevance_filter=relevance_filter,
        )
    except Exception:
        logger.warning("rss fetch failed feed=%s", feed_url[:120], exc_info=True)
        return []


def _load_feed_rows(settings: Settings, *, allow_ids: set[str] | None = None) -> list[dict[str, str]]:
    path = Path((settings.his_data_sources_path or "").strip()).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_file():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("rss data_sources read failed: %s", path, exc_info=True)
        return []
    if not isinstance(rows, list):
        return []
    out: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("kind", "")).strip().lower() != "web":
            continue
        if not bool(row.get("rss_available", False)):
            continue
        rss = str(row.get("rss") or "").strip()
        if not rss.startswith("http"):
            continue
        sid = str(row.get("id") or "").strip()
        if allow_ids is not None and sid not in allow_ids:
            continue
        lang = str(row.get("language") or "zh").strip()
        out.append(
            {
                "id": sid,
                "rss": rss,
                "language": lang,
                "name": str(row.get("name") or "").strip(),
            }
        )
    return out


def _load_html_list_rows(settings: Settings) -> list[dict[str, str]]:
    path = Path((settings.his_data_sources_path or "").strip()).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_file():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("html list data_sources read failed: %s", path, exc_info=True)
        return []
    if not isinstance(rows, list):
        return []
    out: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("kind", "")).strip().lower() != "web":
            continue
        if str(row.get("ingest_mode", "")).strip().lower() != "html_list":
            continue
        lu = str(row.get("list_monitor_url") or "").strip()
        if not lu.startswith("http"):
            continue
        val = str(row.get("value") or "").strip()
        if not val:
            continue
        lang = str(row.get("language") or "zh").strip()
        name = str(row.get("name") or "").strip()
        sid = str(row.get("id") or "").strip()
        out.append(
            {
                "id": sid,
                "list_monitor_url": lu,
                "value": val,
                "language": lang,
                "name": name,
            }
        )
    return out


async def aggregate_rss_from_data_sources(settings: Settings) -> list[SearchHit]:
    if not settings.rss_aggregate_enabled:
        logger.info("rss aggregate disabled by config")
        return []
    feed_rows = _load_feed_rows(settings)
    list_rows = _load_html_list_rows(settings)
    if settings.ingest_zh_html_only:
        allow_ids = set(settings.parsed_ingest_zh_html_source_ids())
        if allow_ids:
            list_rows = [r for r in list_rows if r.get("id") in allow_ids]
            feed_rows = _load_feed_rows(settings, allow_ids=allow_ids)
        else:
            list_rows = [r for r in list_rows if _language_bucket(r.get("language", "zh")) == "zh"]
            feed_rows = [
                r
                for r in _load_feed_rows(settings)
                if _language_bucket(r.get("language", "zh")) == "zh"
            ]
        logger.info(
            "rss aggregate: zh_html_only mode rss=%d html_list=%d ids=%s",
            len(feed_rows),
            len(list_rows),
            ",".join(sorted(allow_ids)) if allow_ids else "(all_zh)",
        )
    if not feed_rows and not list_rows:
        logger.info("rss aggregate: no rss or html_list sources in data_sources")
        return []
    zh_feed_rows = [r for r in feed_rows if _language_bucket(r.get("language", "zh")) == "zh"]
    en_feed_rows = [r for r in feed_rows if _language_bucket(r.get("language", "zh")) != "zh"]
    zh_list_rows = [r for r in list_rows if _language_bucket(r.get("language", "zh")) == "zh"]
    en_list_rows = [r for r in list_rows if _language_bucket(r.get("language", "zh")) != "zh"]

    per = max(1, int(settings.rss_per_feed_max))
    total_cap = max(per, int(settings.rss_total_max))
    timeout = float(settings.rss_timeout_sec)
    sem = asyncio.Semaphore(5)
    zh_kw = settings.parsed_chinese_keywords()
    en_kw = settings.parsed_english_keywords()
    relevance = bool(settings.rss_relevance_filter_enabled)

    async def bounded(row: dict) -> list[SearchHit]:
        bucket = _language_bucket(row.get("language", "zh"))
        kws = zh_kw if bucket == "zh" else en_kw
        eff_filter = relevance and bool(kws)
        async with sem:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                return await _fetch_one_feed(
                    client,
                    row["rss"],
                    per_feed_max=per,
                    keywords=kws if eff_filter else None,
                    relevance_filter=eff_filter,
                )

    async def bounded_list(row: dict) -> list[SearchHit]:
        bucket = _language_bucket(row.get("language", "zh"))
        kws = zh_kw if bucket == "zh" else en_kw
        eff_filter = relevance and bool(kws)
        list_cap = float(settings.html_list_timeout_sec)
        list_timeout = httpx.Timeout(list_cap, connect=min(20.0, list_cap))
        async with sem:
            async with httpx.AsyncClient(timeout=list_timeout, follow_redirects=True) as client:
                return await fetch_html_list_hits(
                    client,
                    list_url=row["list_monitor_url"],
                    site_value=row["value"],
                    per_feed_max=per,
                    keywords=kws if eff_filter else None,
                    relevance_filter=eff_filter,
                    source_name=row.get("name") or row["value"],
                )

    parts_en_rss = await asyncio.gather(*[bounded(r) for r in en_feed_rows]) if en_feed_rows else []
    parts_en_list = await asyncio.gather(*[bounded_list(r) for r in en_list_rows]) if en_list_rows else []
    parts_zh_rss = await asyncio.gather(*[bounded(r) for r in zh_feed_rows]) if zh_feed_rows else []
    parts_zh_list = await asyncio.gather(*[bounded_list(r) for r in zh_list_rows]) if zh_list_rows else []

    browser_hits: list[SearchHit] = []
    browser_failed = False
    if settings.browser_zh_search_enabled and aggregate_browser_zh_search is not None:
        try:
            browser_hits = await aggregate_browser_zh_search(settings)
        except Exception:
            browser_failed = True
            logger.warning("browser_zh_search failed; fallback to html/rss", exc_info=True)

    merged: list[SearchHit] = []
    # 非中文源始终保留传统路径
    for chunk in parts_en_list:
        merged.extend(chunk)
    for chunk in parts_en_rss:
        merged.extend(chunk)

    # 中文源：Playwright 主路径，命中不足或失败时回退 html_list/rss
    use_primary = bool(settings.browser_zh_search_enabled and settings.browser_zh_primary_mode)
    min_hits = max(1, int(settings.browser_zh_min_hits_for_primary))
    if use_primary and not browser_failed and len(browser_hits) >= min_hits:
        merged.extend(browser_hits)
        logger.info(
            "rss aggregate zh primary: browser_hits=%d >= min_hits=%d, skip zh html/rss",
            len(browser_hits),
            min_hits,
        )
    else:
        if browser_hits:
            merged.extend(browser_hits)
        for chunk in parts_zh_list:
            merged.extend(chunk)
        for chunk in parts_zh_rss:
            merged.extend(chunk)
        if use_primary:
            logger.info(
                "rss aggregate zh fallback: browser_hits=%d min_hits=%d browser_failed=%s",
                len(browser_hits),
                min_hits,
                browser_failed,
            )

    merged = _dedupe_hits(merged, max_results=total_cap)
    logger.info(
        "rss aggregate: rss_feeds=%d html_list=%d browser_zh=%d rows=%d filter=%s zh_primary=%s",
        len(feed_rows),
        len(list_rows),
        len(browser_hits),
        len(merged),
        relevance,
        bool(settings.browser_zh_search_enabled and settings.browser_zh_primary_mode),
    )
    return merged
