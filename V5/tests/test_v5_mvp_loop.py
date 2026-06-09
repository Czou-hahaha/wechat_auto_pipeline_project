from __future__ import annotations

from src.services.feedback_loop_mvp import FeedbackStore
from src.services.source_discovery_mvp import SourceCandidateStore


def test_feedback_store_roundtrip(tmp_path) -> None:
    store = FeedbackStore(tmp_path)
    row = store.add(
        event_id="evt_1",
        stage="qa",
        category="factual_error",
        note="time line mismatch",
    )
    assert row["event_id"] == "evt_1"
    summary = store.summary()
    assert summary["total"] == 1
    assert summary["byStage"]["qa"] == 1
    assert summary["byCategory"]["factual_error"] == 1


def test_source_candidate_discovery(tmp_path) -> None:
    store = SourceCandidateStore(tmp_path)
    rows = [
        {"source_url": "https://example.com/news/a"},
        {"source_url": "https://example.com/news/b"},
        {"source_url": "https://foo.bar/item/1"},
    ]
    result = store.discover_from_articles(rows, top_n=10)
    assert result["total"] == 2
    hosts = {x["host"] for x in result["items"]}
    assert "example.com" in hosts
    assert "foo.bar" in hosts
