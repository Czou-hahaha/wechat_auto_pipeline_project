"""Google News RSS search → ``GdeltHit`` rows (sync; run via ``asyncio.to_thread``)."""
from __future__ import annotations

import html as html_lib
import logging
import urllib.parse
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import httpx

from event_enhancement.gdelt.types import GdeltHit
from event_enhancement.google_news_url import decode_google_news_url

logger = logging.getLogger(__name__)


def google_news_rss_search_sync(query: str, max_results: int, *, timeout_sec: float = 25.0) -> list[GdeltHit]:
    """Fetch Google News RSS (zh-CN); returns hits compatible with GDELT downstream."""
    q = (query or "").strip()
    if not q:
        return []
    mx = max(1, min(int(max_results), 40))
    qenc = urllib.parse.quote(q, safe="")
    url = f"https://news.google.com/rss/search?q={qenc}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    try:
        with httpx.Client(timeout=timeout_sec, follow_redirects=True, trust_env=True) as client:
            resp = client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; EventEnhancement/1.0)"},
            )
            resp.raise_for_status()
            text = resp.text or ""
    except Exception as e:
        logger.warning("google news rss fetch failed err=%s", type(e).__name__)
        return []

    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        logger.warning("google news rss parse error query_prefix=%s", q[:60])
        return []

    channel = root.find("channel")
    if channel is None:
        return []

    hits: list[GdeltHit] = []
    seen: set[str] = set()
    for it in channel.findall("item"):
        if len(hits) >= mx:
            break
        t_el = it.find("title")
        l_el = it.find("link")
        d_el = it.find("description")
        title = html_lib.unescape((t_el.text or "").strip()) if t_el is not None else ""
        link = (l_el.text or "").strip() if l_el is not None else ""
        desc = html_lib.unescape((d_el.text or "").strip()) if d_el is not None else ""
        if not link:
            continue
        # 略放慢解码节奏，降低对 Google batchexecute 的 429 概率
        resolved = decode_google_news_url(link, decoder_interval=1.0)
        if not resolved or resolved in seen:
            continue
        seen.add(resolved)
        dom = (urlparse(resolved).netloc or "").lower()
        snippet = (desc or title)[:2000]
        hits.append(
            GdeltHit(title=title or "未命名", url=resolved, snippet=snippet, published_at="", domain=dom)
        )
    return hits
