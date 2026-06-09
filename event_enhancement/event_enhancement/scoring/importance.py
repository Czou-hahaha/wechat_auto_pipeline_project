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
    """2 篇起有区分度，6 篇以上触顶。"""
    n = max(0, int(article_count))
    if n <= 1:
        return 4
    return min(8 + n * 3, 28)


def keyword_score(text: str, keywords: list[str], *, max_points: int = 36) -> int:
    blob = (text or "").lower()
    score = 0
    for kw in keywords:
        k = (kw or "").strip().lower()
        if k and k in blob:
            score += 12
    return min(score, max_points)


def recency_score(
    *,
    anchor: datetime,
    now: datetime,
) -> int:
    """阶梯时效：避免库内数天前的事件全部落在同一分数。"""
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    delta = now - anchor
    hours = max(0.0, delta.total_seconds() / 3600.0)
    if hours <= 24:
        return 24
    if hours <= 72:
        return 18
    if hours <= 168:
        return 12
    if hours <= 336:
        return 6
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
    if not anchor_times:
        # 无稿级发布时间时不假装「刚发生」，时效分为 0
        rec = 0
    else:
        anchor = max(anchor_times)
        if anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=timezone.utc)
        rec = recency_score(anchor=anchor, now=now)
    return int(src + ac + kw + rec)
