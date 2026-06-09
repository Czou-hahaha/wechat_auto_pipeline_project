"""中文站点 Playwright 站内搜索：按关键词打开各站 search_url，抽取稿件链接。

仅处理 ``browser_zh_sources.json`` 中 ``search_url`` 策略 + ``browser_zh_keywords.json`` 词表；
不爬 list/首页/电报流（Playwright 成本高，全站列表改走 html_list/RSS）。
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

from src.config import Settings
from src.search import SearchHit, _dedupe_hits, normalize_title

logger = logging.getLogger(__name__)

_SH_TZ = ZoneInfo("Asia/Shanghai")

_DATE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(20\d{2})-(\d{1,2})-(\d{1,2})(?:\s+(\d{1,2}):(\d{1,2}))?"), "iso"),
    (re.compile(r"(20\d{2})年(\d{1,2})月(\d{1,2})日(?:\s*(\d{1,2}):(\d{1,2}))?"), "zh"),
    (re.compile(r"(\d{1,2})月(\d{1,2})日(?:\s*(\d{1,2}):(\d{1,2}))?"), "zh_no_year"),
]

_EXTRACT_LINKS_JS = """
(hrefNeedle) => {
  const needle = (hrefNeedle || '').toLowerCase();
  const out = [];
  const seen = new Set();
  for (const a of document.querySelectorAll('a[href]')) {
    const href = (a.href || '').split('#')[0];
    if (!href || !href.startsWith('http')) continue;
    if (needle && !href.toLowerCase().includes(needle)) continue;
    let title = (a.innerText || a.textContent || '').replace(/\\s+/g, ' ').trim();
    if (title.length < 8) {
      const alt = (a.getAttribute('title') || a.getAttribute('aria-label') || '').replace(/\\s+/g, ' ').trim();
      if (alt.length >= 8) title = alt;
    }
    if (title.length < 8 || title.length > 300) continue;
    if (seen.has(href)) continue;
    seen.add(href);
    let ctx = '';
    const p = a.closest('div, li, article, section');
    if (p) ctx = (p.innerText || '').slice(0, 400);
    out.push({ href, title, ctx });
    if (out.length >= 80) break;
  }
  return out;
}
"""


def _repo_browser_zh_config_path(settings: Settings) -> Path:
    raw = (settings.browser_zh_sources_path or "config/browser_zh_sources.json").strip()
    p = Path(raw)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p


def load_browser_zh_site_configs(settings: Settings) -> list[dict]:
    path = _repo_browser_zh_config_path(settings)
    if not path.is_file():
        logger.warning("browser_zh_sources missing: %s", path)
        return []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("browser_zh_sources parse failed: %s", path, exc_info=True)
        return []
    sites = doc.get("sites") if isinstance(doc, dict) else None
    if not isinstance(sites, list):
        return []
    out: list[dict] = []
    for row in sites:
        if isinstance(row, dict) and row.get("source_id") and row.get("strategies"):
            out.append(row)
    return out


def _parse_context_datetime(blob: str, *, now: datetime) -> str:
    """从链接周边文本解析发布时间，返回 UTC ISO；解析失败返回空串。"""
    s = (blob or "").strip()
    if not s:
        return ""
    for pat, kind in _DATE_PATTERNS:
        m = pat.search(s)
        if not m:
            continue
        try:
            if kind == "iso":
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                hh = int(m.group(4)) if m.lastindex and m.group(4) else 12
                mi = int(m.group(5)) if m.lastindex and m.group(5) else 0
            elif kind == "zh":
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                hh = int(m.group(4)) if m.lastindex and m.group(4) else 12
                mi = int(m.group(5)) if m.lastindex and m.group(5) else 0
            else:
                y = now.year
                mo, d = int(m.group(1)), int(m.group(2))
                hh = int(m.group(3)) if m.lastindex and m.group(3) else 12
                mi = int(m.group(4)) if m.lastindex and m.group(4) else 0
            dt = datetime(y, mo, d, hh, mi, tzinfo=_SH_TZ)
            return dt.astimezone(timezone.utc).isoformat()
        except (ValueError, TypeError):
            continue
    return ""


def _within_max_age(published_at: str, *, max_hours: int, now: datetime) -> bool:
    """无发布时间时保留（由 pipeline 落地页补全后再 filter_by_age）。"""
    raw = (published_at or "").strip()
    if not raw:
        return True
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = now - dt.astimezone(timezone.utc)
        return age <= timedelta(hours=max(1, max_hours))
    except Exception:
        return True


def _published_at_for_browser_hit(published_at: str, *, max_hours: int, now: datetime) -> str:
    """列表/搜索页解析到的发布时间；超出 browser 窗则清空，避免侧栏旧日期误杀链接。"""
    pub = (published_at or "").strip()
    if pub and not _within_max_age(pub, max_hours=max_hours, now=now):
        return ""
    return pub


def _host_ok(url: str, domain: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    dom = (domain or "").lower().strip()
    if dom.startswith("www."):
        dom = dom[4:]
    return host == dom or host.endswith("." + dom)


async def _collect_from_page(page, *, strategy: dict, domain: str, now: datetime, max_hours: int) -> list[tuple[str, str, str]]:
    wait_ms = int(strategy.get("wait_ms") or 3000)
    needle = str(strategy.get("link_href_contains") or "").strip()
    await page.wait_for_timeout(min(max(wait_ms, 1000), 15000))
    scroll_rounds = int(strategy.get("scroll_rounds") or 1)
    scroll_rounds = min(max(scroll_rounds, 1), 12)
    for _ in range(scroll_rounds):
        try:
            await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(700)
        except Exception:
            break
    try:
        rows = await page.evaluate(_EXTRACT_LINKS_JS, needle)
    except Exception:
        logger.warning("browser_zh evaluate failed domain=%s", domain, exc_info=True)
        return []
    if not isinstance(rows, list):
        return []
    triples: list[tuple[str, str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        href = str(row.get("href") or "").strip()
        title = str(row.get("title") or "").strip()
        ctx = str(row.get("ctx") or "").strip()
        if not href or not _host_ok(href, domain):
            continue
        pub = _published_at_for_browser_hit(
            _parse_context_datetime(ctx, now=now),
            max_hours=max_hours,
            now=now,
        )
        triples.append((href, title, pub))
    return triples


async def aggregate_browser_zh_search(settings: Settings) -> list[SearchHit]:
    """Playwright 按词表打开各中文站 search_url，合并为 ``SearchHit``。"""
    if not settings.browser_zh_search_enabled:
        return []

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning(
            "browser_zh_search enabled but playwright not installed; "
            "pip install playwright && playwright install chromium"
        )
        return []

    sites = load_browser_zh_site_configs(settings)
    if not sites:
        return []

    keywords = list(settings.parsed_browser_zh_keywords())
    if not keywords:
        logger.warning("browser_zh_search: no keywords in browser_zh_keywords.json")
        return []
    kw_cap = max(1, int(settings.browser_zh_max_keywords))
    keywords = keywords[:kw_cap]
    per_site = max(5, int(settings.browser_zh_per_site_max))
    max_hours = max(1, int(settings.browser_zh_max_age_hours))
    now = datetime.now(timezone.utc)
    headless = bool(settings.browser_zh_headless)
    nav_timeout = max(15.0, float(settings.browser_zh_nav_timeout_sec)) * 1000

    all_triples: list[tuple[str, str, str, str]] = []
    page_opens = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        try:
            context = await browser.new_context(
                locale="zh-CN",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            for site in sites:
                domain = str(site.get("domain") or "").strip()
                name = str(site.get("source_id") or domain)
                strategies = site.get("strategies")
                if not domain or not isinstance(strategies, list):
                    continue
                site_triples: list[tuple[str, str, str]] = []

                search_strategies = [
                    s
                    for s in strategies
                    if isinstance(s, dict) and s.get("kind") == "search_url"
                ]
                if not search_strategies:
                    logger.warning("browser_zh skip source=%s: no search_url strategy", name)
                    continue

                async def _visit(target: str, strat: dict, *, kw_label: str) -> None:
                    page = await context.new_page()
                    try:
                        await page.goto(target, wait_until="domcontentloaded", timeout=nav_timeout)
                        got = await _collect_from_page(
                            page,
                            strategy=strat,
                            domain=domain,
                            now=now,
                            max_hours=max_hours,
                        )
                        site_triples.extend(got)
                        logger.info(
                            "browser_zh ok source=%s kw=%s url=%s links=%d",
                            name,
                            kw_label[:20],
                            target[:80],
                            len(got),
                        )
                    except Exception:
                        logger.warning(
                            "browser_zh navigate failed source=%s url=%s",
                            name,
                            target[:100],
                            exc_info=True,
                        )
                    finally:
                        await page.close()

                for kw in keywords:
                    q = quote(kw.strip(), safe="")
                    for strat in search_strategies:
                        url_tpl = str(strat.get("url") or "").strip()
                        if not url_tpl or "{query}" not in url_tpl:
                            continue
                        target = url_tpl.replace("{query}", q)
                        await _visit(target, strat, kw_label=kw)
                        page_opens += 1
                by_url: dict[str, tuple[str, str]] = {}
                for u, t, pub in site_triples:
                    if u not in by_url or (pub and not by_url[u][1]):
                        by_url[u] = (t, pub)
                for u, (t, pub) in list(by_url.items())[:per_site]:
                    all_triples.append((u, t, pub, name))
        finally:
            await browser.close()

    hits: list[SearchHit] = []
    for url, title, pub, _src in all_triples:
        hits.append(
            SearchHit(
                title=normalize_title(title),
                url=url,
                snippet="",
                published_at=pub,
                from_rss=True,
            )
        )
    cap = max(50, int(settings.browser_zh_total_max))
    hits = _dedupe_hits(hits, max_results=cap)
    logger.info(
        "browser_zh_search done sites=%d keywords=%d page_opens=%d hits=%d max_age_h=%d",
        len(sites),
        len(keywords),
        page_opens,
        len(hits),
        max_hours,
    )
    return hits
