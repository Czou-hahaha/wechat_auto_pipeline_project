"""簇级 / 事件级 importance 打分（与 event_enhancement.scoring 对齐）。"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.pipeline import PreparedArticle


def _ensure_event_enhancement_pkg() -> None:
    pkg = Path(__file__).resolve().parents[2].parent / "event_enhancement"
    p = str(pkg)
    if p not in sys.path:
        sys.path.insert(0, p)


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
    _ensure_event_enhancement_pkg()
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


def score_event_for_display(
    *,
    event: dict[str, Any],
    articles: list[dict[str, Any]],
    important_hosts: list[str],
    keywords: list[str],
    now: datetime | None = None,
) -> int:
    """
    列表/详情 IMP：与 pipeline Top-N 同源公式，并按主题门禁压低离题事件。
    不使用通稿 QA 分（QA 是质量，不是业务重要性）。
    """
    _ensure_event_enhancement_pkg()
    from event_enhancement.scoring.importance import compute_importance_score
    from src.utils.topic_prefilter import should_keep_editorial_content

    now = now or datetime.now(timezone.utc)
    titles = [str(a.get("title") or "") for a in articles if isinstance(a, dict)]
    hosts = [str(a.get("source_host") or "") for a in articles if isinstance(a, dict)]
    times: list[datetime | None] = []
    for a in articles:
        if not isinstance(a, dict):
            continue
        times.append(parse_cluster_published_at(str(a.get("source_published_at") or "")))
    for field in (
        "event_press_generated_at",
        "created_at",
        "updated_at",
        "last_enhancement_at",
    ):
        dt = parse_cluster_published_at(str(event.get(field) or ""))
        if dt is not None:
            times.append(dt)
    event_title = str(event.get("title_zh") or event.get("title") or "").strip()
    if not event_title and titles:
        event_title = titles[0]
    text_blob = "\n".join(
        p
        for p in (
            event_title,
            str(event.get("headline_zh") or ""),
            str(event.get("summary_zh") or ""),
            str(event.get("summary") or "")[:1200],
            str(event.get("event_press_zh") or "")[:2000],
            *titles,
        )
        if p and str(p).strip()
    )
    base = compute_importance_score(
        event_title=text_blob[:500] or event_title,
        article_titles=titles or [event_title],
        article_hosts=hosts,
        article_published_ats=times,
        important_hosts=important_hosts,
        keywords=keywords,
        now=now,
    )
    # 通稿已生成、标记为重要主题 → 适度加分（仍受离题封顶约束）
    bonus = 0
    if str(event.get("event_press_generated_at") or "").strip():
        bonus += 10
    if any(isinstance(a, dict) and a.get("topic_is_important") for a in articles):
        bonus += 8
    unique_hosts = len({str(h or "").strip().lower() for h in hosts if h})
    if unique_hosts >= 3:
        bonus += 6

    press = str(event.get("event_press_zh") or event.get("summary_zh") or event.get("summary") or "")
    primary_title = event_title
    from src.utils.topic_prefilter import EDITORIAL_FULL_TEXT_MAX

    if not should_keep_editorial_content(
        title=primary_title,
        snippet=press[:800] or (titles[0] if titles else ""),
        text=press[:EDITORIAL_FULL_TEXT_MAX],
    ):
        return min(int(base), 12)
    return min(100, int(base) + bonus)
