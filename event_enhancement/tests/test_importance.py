from __future__ import annotations

from datetime import datetime, timedelta, timezone

from event_enhancement.scoring.importance import article_count_score, compute_importance_score


def test_importance_reuters_host_scores_30() -> None:
    now = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)
    past = now - timedelta(hours=12)
    score = compute_importance_score(
        event_title="低空 无人机",
        article_titles=["Reuters headline"],
        article_hosts=["www.reuters.com"],
        article_published_ats=[past],
        important_hosts=["reuters.com"],
        keywords=["低空", "无人机"],
        now=now,
    )
    assert score >= 30 + 10 + 20


def test_article_count_score_cap() -> None:
    assert article_count_score(4) == 10
    assert article_count_score(1) == 5
