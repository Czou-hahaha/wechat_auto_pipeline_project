from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.config import Settings
from src.services.feedback_policy_mvp import FeedbackPolicyEngine


def test_feedback_policy_recompute_and_apply(tmp_path: Path, monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "feedback_events.json").write_text(
        json.dumps(
            [
                {
                    "id": "1",
                    "event_id": "evt",
                    "stage": "qa",
                    "category": "factual_error",
                    "note": "bad fact",
                    "created_at": (now - timedelta(minutes=10)).isoformat(),
                },
                {
                    "id": "2",
                    "event_id": "evt",
                    "stage": "qa",
                    "category": "factual_error",
                    "note": "bad fact 2",
                    "created_at": (now - timedelta(minutes=9)).isoformat(),
                },
                {
                    "id": "3",
                    "event_id": "evt",
                    "stage": "qa",
                    "category": "factual_error",
                    "note": "bad fact 3",
                    "created_at": (now - timedelta(minutes=8)).isoformat(),
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    override_path = cfg_dir / "feedback_policy_overrides.json"
    override_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("FEEDBACK_POLICY_OVERRIDES_PATH", str(override_path))
    settings = Settings()
    eng = FeedbackPolicyEngine(settings)

    rec = eng.recompute(window_days=365)
    assert rec["feedback_total"] == 3
    assert rec["safe_to_apply"] is True
    assert int(rec["proposed_overrides"]["qa_rewrite_pass_threshold"]) >= int(
        settings.qa_rewrite_pass_threshold
    )

    applied = eng.apply(
        recommendation_id=rec["id"],
        confirm_token="APPLY_FEEDBACK_POLICY",
    )
    assert applied["ok"] is True
    loaded = json.loads(override_path.read_text(encoding="utf-8"))
    assert "qa_rewrite_pass_threshold" in loaded
