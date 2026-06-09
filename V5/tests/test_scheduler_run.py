"""后台 run-scheduler 拉起/停止。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.bff import scheduler_run as sr


def test_sync_starts_when_enabled(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    jobs = [{"id": "j1", "label": "早间", "hour": 8, "minute": 0}]
    with patch.object(sr, "subprocess") as sp, patch.object(sr, "_pid_alive", return_value=True):
        proc = MagicMock()
        proc.pid = 4242
        sp.Popen.return_value = proc
        out = sr.sync_scheduler(
            data_dir, enabled=True, jobs=jobs, timezone="Asia/Shanghai"
        )
    assert out["ok"] is True
    assert out["status"]["state"] == "running"
    assert out["status"]["pid"] == 4242


def test_sync_stops_when_disabled(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    sr._write_status(
        data_dir,
        {"state": "running", "message": "x", "startedAt": "", "pid": 99999, "jobsSummary": ""},
    )
    with patch.object(sr, "_pid_alive", return_value=True), patch.object(sr.os, "kill") as kill:
        out = sr.sync_scheduler(data_dir, enabled=False, jobs=[])
    assert out["ok"] is True
    assert sr.read_status(data_dir)["state"] == "stopped"
    kill.assert_called_once()
