"""Top-N importance 摘要选取与 3 日推送冷却。"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_PKG = _REPO / "event_enhancement"
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))
from src.config import Settings
from src.pipeline import PipelineRunner, PreparedArticle
from src.search import SearchHit


def _prepared(title: str, *, host: str = "faa.gov", topic_key: str = "") -> PreparedArticle:
    return PreparedArticle(
        hit=SearchHit(title=title, url=f"https://{host}/a", snippet="", published_at="2026-05-19T08:00:00Z"),
        title=title,
        text="x" * 500,
        final_url=f"https://{host}/a",
        first_image_url=None,
        source_host=host,
        source_published_at="2026-05-19T08:00:00Z",
        source_published_at_date_only=False,
        topic_is_important=bool(topic_key),
        topic_category="policy",
        topic_key=topic_key,
        deepseek_semantic_decision="",
        novelty_passed=True,
    )


def test_select_top_importance_respects_top_n(monkeypatch) -> None:
    settings = Settings(wechat_publish_top_n=3, wechat_publish_cooldown_days=0)
    runner = PipelineRunner(settings)
    monkeypatch.setattr(runner, "_expansion_scoring_lists", lambda: (["faa.gov"], ["drone", "evtol"]))
    clusters = [
        [_prepared("low drone news", host="example.com")],
        [_prepared("FAA eVTOL rulemaking", host="faa.gov")],
        [_prepared("CAAC drone policy", host="caac.gov.cn")],
        [_prepared("UAM urban air mobility", host="reuters.com")],
    ]
    picked = runner._select_top_importance_clusters(clusters)
    assert len(picked) == 3
    scores = [s for s, _ in picked]
    assert scores == sorted(scores, reverse=True)


def test_select_skips_recently_published_topic(monkeypatch) -> None:
    settings = Settings(wechat_publish_top_n=3, wechat_publish_cooldown_days=3)
    runner = PipelineRunner(settings)
    monkeypatch.setattr(runner, "_expansion_scoring_lists", lambda: (["faa.gov"], ["drone"]))
    pushed_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    runner.store._write(
        [
            {
                "id": "1",
                "title": "FAA eVTOL rulemaking",
                "topic_key": "evtol_faa",
                "wechat_draft_pushed_at": pushed_at,
                "published_at": pushed_at,
                "status": "published",
            }
        ]
    )
    clusters = [
        [_prepared("FAA eVTOL rulemaking", host="faa.gov", topic_key="evtol_faa")],
        [_prepared("Other drone story", host="example.com")],
    ]
    picked = runner._select_top_importance_clusters(clusters)
    titles = [runner._pick_primary_article(c).title for _, c in picked]
    assert "FAA eVTOL rulemaking" not in titles
