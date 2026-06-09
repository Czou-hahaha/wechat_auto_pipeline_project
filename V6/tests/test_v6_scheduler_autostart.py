"""V6 开发轨不自动启动 run-scheduler。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from src.bff import schedule_config as sc
from src.config import Settings


def test_apply_schedule_skips_scheduler_when_autostart_disabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BFF_SCHEDULER_AUTOSTART", "false")
    cfg_path = Path(__file__).resolve().parents[1] / "config" / "schedule_jobs.json"
    import shutil

    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    shutil.copy(cfg_path, tmp_path / "config" / "schedule_jobs.json")
    monkeypatch.chdir(tmp_path)

    with patch("src.bff.scheduler_run.stop_scheduler") as stop_mock:
        out = sc.put_schedule_config(
            {
                "enabled": True,
                "timezone": "Asia/Shanghai",
                "jobs": [{"id": "j1", "label": "早间", "hour": 8, "minute": 0}],
                "article_age": {"unit": "hours", "value": 14},
                "article_age_limit_enabled": True,
            }
        )
    stop_mock.assert_called_once()
    assert "V6 开发轨不启动" in (out.get("schedulerNote") or "")
    assert Settings().bff_scheduler_autostart is False
