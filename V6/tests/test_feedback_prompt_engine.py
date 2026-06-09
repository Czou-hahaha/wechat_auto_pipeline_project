"""Tests for FeedbackPromptEngine."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.config import Settings
from src.services.feedback_loop_mvp import FeedbackStore
from src.services.feedback_prompt_engine import FeedbackPromptEngine


@pytest.fixture
def engine(tmp_path: Path) -> FeedbackPromptEngine:
    s = Settings(data_dir=str(tmp_path))
    return FeedbackPromptEngine(s)


def test_recompute_prompt_suggestions_empty(engine: FeedbackPromptEngine) -> None:
    rec = engine.recompute_prompt_suggestions(window_days=14)
    assert rec["feedback_total"] == 0
    assert "proposed_contract" in rec


def test_recompute_with_category_feedback(engine: FeedbackPromptEngine, tmp_path: Path) -> None:
    fb = FeedbackStore(engine.data_dir)
    for _ in range(3):
        fb.add(event_id="ev1", stage="qa", category="factual_error", note="数据不对")
    rec = engine.recompute_prompt_suggestions(window_days=14)
    assert rec["feedback_total"] >= 3
    additions = rec.get("additions") or {}
    assert additions.get("hard_rules")


def test_apply_requires_confirm_token(engine: FeedbackPromptEngine, tmp_path: Path) -> None:
    fb = FeedbackStore(tmp_path)
    for _ in range(3):
        fb.add(event_id="ev1", stage="qa", category="style_issue", note="表达问题")
    rec = engine.recompute_prompt_suggestions(window_days=14)
    if not rec.get("safe_to_apply"):
        pytest.skip("not enough categorized feedback for apply")
    with pytest.raises(ValueError, match="confirm token"):
        engine.apply_prompt_suggestion(suggestion_id=str(rec["id"]), confirm_token="wrong")
