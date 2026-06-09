"""已入库事件检索：标题 / 摘要 / 关键词统一打分排序（非采集词表、非向量语义）。"""

from __future__ import annotations

from typing import Any


def event_search_score(row: dict[str, Any], needle: str) -> float:
    """子串匹配 + 字段权重；0 表示不匹配。"""
    n = (needle or "").strip().lower()
    if not n:
        return 0.0
    title = (row.get("title") or "").lower()
    summary = (
        row.get("summaryPreview") or row.get("summary") or ""
    ).lower()
    keywords = [str(k).lower() for k in row.get("keywords") or [] if k]
    countries = [str(c).lower() for c in row.get("countries") or [] if c]

    score = 0.0
    if n == title:
        score += 100.0
    elif n in title:
        score += 80.0
    if any(n == k for k in keywords):
        score += 70.0
    elif any(n in k for k in keywords):
        score += 55.0
    if n in summary:
        score += 40.0
    if any(n in c for c in countries):
        score += 15.0
    return score


def filter_and_rank_events(
    rows: list[dict[str, Any]], needle: str
) -> list[dict[str, Any]]:
    n = (needle or "").strip()
    if not n:
        return []
    scored = [(r, event_search_score(r, n)) for r in rows]
    matched = [(r, s) for r, s in scored if s > 0]
    matched.sort(
        key=lambda pair: (
            -pair[1],
            -int(pair[0].get("importance_score") or 0),
            pair[0].get("createdAt") or "",
        ),
        reverse=False,
    )
    return [r for r, _ in matched]
