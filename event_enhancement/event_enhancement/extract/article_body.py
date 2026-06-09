"""Fetch HTML and extract main text (trafilatura)."""
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    import httpx

from event_enhancement.google_news_url import decode_google_news_url

logger = logging.getLogger(__name__)

_CHROME_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _is_google_news_article_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
        path = urlparse(url).path or ""
    except Exception:
        return False
    if "news.google.com" not in host:
        return False
    return "/rss/articles/" in path or "/articles/" in path


def _extract_external_url_from_google_news_html(html: str) -> str | None:
    """从 Google News 跳转/包装页 HTML 中抽取第一条非 Google 的 https 外链。"""
    if not html or len(html) < 50:
        return None
    m = re.search(
        r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        re.I,
    )
    if m:
        u = m.group(1).strip()
        try:
            h = (urlparse(u).hostname or "").lower()
        except Exception:
            h = ""
        if h and "google." not in h and "news.google.com" not in h:
            return u
    m2 = re.search(r'rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']', html, re.I)
    if m2:
        u = m2.group(1).strip()
        try:
            h = (urlparse(u).hostname or "").lower()
        except Exception:
            h = ""
        if h and "google." not in h and "news.google.com" not in h:
            return u
    bad_substrings = (
        "google.",
        "gstatic.",
        "googleapis.",
        "doubleclick.",
        "googlesyndication.",
        "googleusercontent",
        "google-analytics",
        "googletagmanager",
        "googleadservices",
        "youtube.com",
        "youtu.be",
    )
    for raw in re.findall(r"https?://[^\s\"'<>)]+", html):
        u = raw.rstrip(".,);\\]}>'\"")
        if len(u) > 2048:
            continue
        try:
            parsed = urlparse(u)
            host = (parsed.hostname or "").lower()
            path_l = (parsed.path or "").lower()
        except Exception:
            continue
        if not host or "news.google.com" in host:
            continue
        if path_l.endswith((".js", ".css", ".json", ".woff2", ".ico")):
            continue
        if any(b in host for b in bad_substrings):
            continue
        return u
    return None


async def fetch_html_text_with_effective_url(
    client: "httpx.AsyncClient",
    url: str,
    *,
    timeout_sec: float,
) -> tuple[str, str]:
    """
    抓取 HTML，并对 ``news.google.com/rss/articles/...`` 等跳转页尝试解析 **落地外链** 再抓一次。

    返回 ``(html, page_url)``，其中 ``page_url`` 供 trafilatura 作页面语境；与最终 HTML 来源一致。
    """
    url = decode_google_news_url((url or "").strip())
    headers = {
        "User-Agent": _CHROME_UA,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    resp = await client.get(url, follow_redirects=True, timeout=timeout_sec, headers=headers)
    resp.raise_for_status()
    html = resp.text or ""
    effective = str(resp.url).strip() or url

    need_unpack = _is_google_news_article_url(url) or _is_google_news_article_url(effective)
    if need_unpack:
        ext = _extract_external_url_from_google_news_html(html)
        if ext and ext != url and ext != effective:
            try:
                r2 = await client.get(ext, follow_redirects=True, timeout=timeout_sec, headers=headers)
                r2.raise_for_status()
                return (r2.text or "", str(r2.url).strip() or ext)
            except Exception:
                logger.debug("google news follow external failed url=%s", ext[:80], exc_info=True)

    return html, effective


async def fetch_html_text(client: "httpx.AsyncClient", url: str, *, timeout_sec: float) -> str:
    html, _ = await fetch_html_text_with_effective_url(client, url, timeout_sec=timeout_sec)
    return html


def extract_body_trafilatura(html: str, *, page_url: str, min_chars: int) -> str | None:
    raw = (html or "").strip()
    if not raw or min_chars <= 0:
        return None
    try:
        import trafilatura
    except ImportError:
        logger.warning("trafilatura not installed")
        return None
    try:
        extracted = trafilatura.extract(
            raw,
            url=page_url or None,
            favor_recall=True,
            include_comments=False,
            include_tables=True,
        )
    except Exception:
        logger.debug("trafilatura.extract failed", exc_info=True)
        return None
    if not extracted:
        return None
    text = extracted.strip()
    if len(text) < min_chars:
        return None
    return text[:20000]
