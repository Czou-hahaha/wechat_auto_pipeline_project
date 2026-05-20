"""簇级 importance 打分（与 event_enhancement.scoring 对齐）。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.pipeline import PreparedArticle


def parse_cluster_published_at(iso: str) -> datetime | None:
    s = (iso or "").strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def score_prepared_cluster(
    cluster: list["PreparedArticle"],
    *,
    important_hosts: list[str],
    keywords: list[str],
    now: datetime | None = None,
) -> int:
    from event_enhancement.scoring.importance import compute_importance_score

    if not cluster:
        return 0
    now = now or datetime.now(timezone.utc)
    titles = [str(p.title or "") for p in cluster]
    hosts = [str(p.source_host or "") for p in cluster]
    times = [parse_cluster_published_at(p.source_published_at) for p in cluster]
    event_title = titles[0] if titles else ""
    return compute_importance_score(
        event_title=event_title,
        article_titles=titles,
        article_hosts=hosts,
        article_published_ats=times,
        important_hosts=important_hosts,
        keywords=keywords,
        now=now,
    )
