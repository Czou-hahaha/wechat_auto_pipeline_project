"""后台 ``run-scheduler``：保存定时配置后由 BFF 自动拉起/停止。"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_STATUS_FILENAME = "scheduler_run_status.json"
_LOG_FILENAME = "scheduler_run.log"
_LOCK = threading.Lock()

_IDLE: dict[str, Any] = {
    "state": "stopped",
    "message": "定时调度未运行；启用定时采集并保存后将自动启动。",
    "startedAt": "",
    "pid": None,
    "jobsSummary": "",
}


def _status_path(data_dir: Path) -> Path:
    return data_dir / _STATUS_FILENAME


def _log_path(data_dir: Path) -> Path:
    return data_dir / _LOG_FILENAME


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _write_status(data_dir: Path, payload: dict[str, Any]) -> None:
    path = _status_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_status(data_dir: Path) -> dict[str, Any]:
    path = _status_path(data_dir)
    if not path.is_file():
        return dict(_IDLE)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("status must be object")
        out = {**_IDLE, **raw}
    except (OSError, ValueError, json.JSONDecodeError):
        logger.warning("invalid scheduler status file", exc_info=True)
        out = dict(_IDLE)
        out["message"] = "调度状态文件损坏，请重新保存定时配置。"
    if str(out.get("state")) == "running":
        pid = out.get("pid")
        if pid and not _pid_alive(int(pid)):
            out["state"] = "stopped"
            out["message"] = "调度进程已退出，请重新保存定时配置以拉起。"
            out["pid"] = None
            _write_status(data_dir, out)
    return out


def _jobs_summary(jobs: list[dict[str, Any]], tz: str) -> str:
    if not jobs:
        return ""
    parts = [
        f"{j.get('label', j.get('id'))} {int(j.get('hour', 0)):02d}:{int(j.get('minute', 0)):02d}"
        for j in jobs
        if isinstance(j, dict)
    ]
    return f"{tz} · " + "、".join(parts) if parts else ""


def start_scheduler(
    data_dir: Path,
    *,
    jobs: list[dict[str, Any]] | None = None,
    timezone: str = "Asia/Shanghai",
) -> dict[str, Any]:
    """启动 ``run-scheduler`` 子进程（已运行则直接返回）。"""
    with _LOCK:
        current = read_status(data_dir)
        pid = current.get("pid")
        if current.get("state") == "running" and pid and _pid_alive(int(pid)):
            return {"ok": True, "already_running": True, "status": current}

        v3_root = data_dir.parent
        log_path = _log_path(data_dir)
        started_at = _now_iso()
        summary = _jobs_summary(jobs or [], timezone)

        env = os.environ.copy()
        env["V3_MAIN_INNER"] = "1"
        env["PYTHONPATH"] = str(v3_root)

        log_file = open(log_path, "a", encoding="utf-8")
        log_file.write(f"\n\n===== scheduler started {started_at} =====\n")
        log_file.flush()

        proc = subprocess.Popen(
            [sys.executable, "-m", "src.main", "run-scheduler"],
            cwd=str(v3_root),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        log_file.close()

        payload: dict[str, Any] = {
            "state": "running",
            "message": f"定时调度已启动（{summary or '见 schedule_jobs.json'}）",
            "startedAt": started_at,
            "pid": proc.pid,
            "jobsSummary": summary,
        }
        _write_status(data_dir, payload)
        logger.info("run-scheduler started pid=%s", proc.pid)
        return {"ok": True, "already_running": False, "status": payload}


def stop_scheduler(data_dir: Path) -> dict[str, Any]:
    """停止正在运行的调度进程。"""
    with _LOCK:
        current = read_status(data_dir)
        pid = current.get("pid")
        if pid and _pid_alive(int(pid)):
            try:
                os.kill(int(pid), signal.SIGTERM)
            except OSError:
                logger.warning("stop scheduler SIGTERM failed pid=%s", pid, exc_info=True)
        payload: dict[str, Any] = {
            "state": "stopped",
            "message": "定时调度已停止（已关闭启用定时采集）",
            "startedAt": current.get("startedAt") or "",
            "pid": None,
            "jobsSummary": "",
        }
        _write_status(data_dir, payload)
        logger.info("run-scheduler stopped pid=%s", pid)
        return {"ok": True, "status": payload}


def sync_scheduler(
    data_dir: Path,
    *,
    enabled: bool,
    jobs: list[dict[str, Any]] | None = None,
    timezone: str = "Asia/Shanghai",
) -> dict[str, Any]:
    """按配置启用/停用后台 ``run-scheduler``；保存新时刻时会先停再起以加载 cron。"""
    if not enabled:
        return stop_scheduler(data_dir)
    if not jobs:
        return {
            "ok": False,
            "error": "no_jobs",
            "status": read_status(data_dir),
        }
    current = read_status(data_dir)
    pid = current.get("pid")
    if current.get("state") == "running" and pid and _pid_alive(int(pid)):
        stop_scheduler(data_dir)
    return start_scheduler(data_dir, jobs=jobs, timezone=timezone)
