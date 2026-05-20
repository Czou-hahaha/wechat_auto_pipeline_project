"""BFF pipeline_run: status file + log parse."""
from __future__ import annotations

import json
from pathlib import Path

from src.bff.pipeline_run import _parse_run_stats_from_log, read_status, start_run_once


def test_parse_run_stats_from_log() -> None:
    log = (
        "INFO root - run_once done: candidates=12 published=2 staged_for_review=1 "
        "skipped_duplicate=3 skipped_policy=0 skipped_prefilter=0 "
        "skipped_summarize_cap=0 skipped_insufficient_articles=0 skipped_encoding=0 "
        "skipped_digest=0 skipped_too_short=1 skipped_summary_fallback=0 skipped_qa=0 failed=0"
    )
    stats = _parse_run_stats_from_log(log)
    assert stats["candidates"] == 12
    assert stats["published"] == 2
    assert stats["failed"] == 0


def test_read_status_idle_when_missing(tmp_path: Path) -> None:
    st = read_status(tmp_path)
    assert st["state"] == "idle"
    assert "尚未执行" in st["message"]


def test_start_run_once_rejects_double_start(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("src.bff.pipeline_run._pid_alive", lambda _pid: True)
    status_path = tmp_path / "pipeline_run_status.json"
    status_path.write_text(
        json.dumps({"state": "running", "message": "x", "pid": 999999}),
        encoding="utf-8",
    )
    result = start_run_once(tmp_path)
    assert result["ok"] is False
    assert result["error"] == "already_running"
