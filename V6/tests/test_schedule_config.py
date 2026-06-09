"""schedule_jobs.json 读写与采集时间窗换算。"""
from __future__ import annotations

import json
from pathlib import Path

from src.bff import schedule_config as sc


def test_article_age_days_to_hours(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sc, "_jobs_path", lambda: tmp_path / "schedule_jobs.json")
    monkeypatch.setattr(sc, "_env_path", lambda: tmp_path / ".env")
    tmp_path.mkdir(parents=True, exist_ok=True)
    out = sc.put_schedule_config(
        {
            "enabled": True,
            "timezone": "Asia/Shanghai",
            "jobs": [{"id": "j1", "label": "测试", "hour": 10, "minute": 30}],
            "article_age": {"unit": "days", "value": 7},
        }
    )
    assert out["article_age_hours"] == 168
    assert len(out["jobs"]) == 1
    assert out["jobs"][0]["minute"] == 30


def test_article_age_limit_can_be_disabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sc, "_jobs_path", lambda: tmp_path / "schedule_jobs.json")
    monkeypatch.setattr(sc, "_env_path", lambda: tmp_path / ".env")
    tmp_path.mkdir(parents=True, exist_ok=True)
    out = sc.put_schedule_config(
        {
            "enabled": False,
            "timezone": "Asia/Shanghai",
            "jobs": [],
            "article_age_limit_enabled": False,
            "article_age": {"unit": "days", "value": 3},
        }
    )
    assert out["article_age_hours"] == 0
    assert out["article_age_limit_enabled"] is False
    env = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "MAX_ARTICLE_AGE_HOURS=0" in env


def test_put_requires_job_when_enabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sc, "_jobs_path", lambda: tmp_path / "schedule_jobs.json")
    monkeypatch.setattr(sc, "_env_path", lambda: tmp_path / ".env")
    try:
        sc.put_schedule_config({"enabled": True, "jobs": []})
        assert False, "expected ValueError"
    except ValueError as e:
        assert "至少" in str(e)


def test_empty_jobs_ok_when_disabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sc, "_jobs_path", lambda: tmp_path / "schedule_jobs.json")
    monkeypatch.setattr(sc, "_env_path", lambda: tmp_path / ".env")
    tmp_path.mkdir(parents=True, exist_ok=True)
    out = sc.put_schedule_config(
        {"enabled": False, "timezone": "UTC", "jobs": [], "article_age_limit_enabled": True}
    )
    assert out["jobs"] == []
