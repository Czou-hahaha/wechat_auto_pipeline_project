"""importance_score：source + article_count + keyword + recency。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def normalize_host(host: str) -> str:
    h = (host or "").strip().lower()
    if h.startswith("www."):
        h = h[4:]
    return h


def host_is_important(source_host: str, important_hosts: list[str]) -> bool:
    h = normalize_host(source_host)
    if not h:
        return False
    for raw in important_hosts:
        p = normalize_host(str(raw))
        if not p:
            continue
        if h == p or h.endswith("." + p):
            return True
    return False


def source_score_from_articles(source_hosts: list[str], important_hosts: list[str]) -> int:
    for sh in source_hosts:
        if host_is_important(sh, important_hosts):
            return 30
    return 10


def article_count_score(article_count: int) -> int:
    return min(max(0, article_count) * 5, 10)


def keyword_score(text: str, keywords: list[str]) -> int:
    blob = (text or "").lower()
    score = 0
    for kw in keywords:
        k = (kw or "").strip().lower()
        if k and k in blob:
            score += 10
    return score


def recency_score(
    *,
    anchor: datetime,
    now: datetime,
) -> int:
    """24h 内 +20；48h 内 +10；否则 0。锚点默认事件内最新稿发布时间。"""
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    delta = now - anchor
    hours = delta.total_seconds() / 3600.0
    if hours <= 24:
        return 20
    if hours <= 48:
        return 10
    return 0


def host_from_url(url: str) -> str:
    try:
        return normalize_host(urlparse(url).hostname or "")
    except Exception:
        logger.debug("host_from_url failed url=%s", url[:80], exc_info=True)
        return ""


def compute_importance_score(
    *,
    event_title: str,
    article_titles: list[str],
    article_hosts: list[str],
    article_published_ats: list[datetime | None],
    important_hosts: list[str],
    keywords: list[str],
    now: datetime,
) -> int:
    """返回总分（无 cap，除非调用方再截断）。"""
    n = len(article_titles)
    src = source_score_from_articles(article_hosts, important_hosts)
    ac = article_count_score(n)
    text_blob = event_title + "\n" + "\n".join(article_titles)
    kw = keyword_score(text_blob, keywords)
    anchor_times = [t for t in article_published_ats if t is not None]
    if anchor_times:
        anchor = max(anchor_times)
        if anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=timezone.utc)
    else:
        anchor = now
    rec = recency_score(anchor=anchor, now=now)
    return int(src + ac + kw + rec)
