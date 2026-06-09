"""Background ``run-once`` for manual trigger from the intelligence UI."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_STATUS_FILENAME = "pipeline_run_status.json"
_LOG_FILENAME = "pipeline_run.log"
_LOCK = threading.Lock()

_IDLE: dict[str, Any] = {
    "state": "idle",
    "message": "尚未执行采集；点击下方按钮开始搜索与入库。",
    "startedAt": "",
    "finishedAt": "",
    "exitCode": None,
    "pid": None,
    "logTail": "",
    "stats": {},
}


def _status_path(data_dir: Path) -> Path:
    return data_dir / _STATUS_FILENAME


def _log_path(data_dir: Path) -> Path:
    return data_dir / _LOG_FILENAME


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tail_log(log_path: Path, max_chars: int = 4000) -> str:
    if not log_path.is_file():
        return ""
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
        return text[-max_chars:] if len(text) > max_chars else text
    except OSError:
        logger.warning("read pipeline log failed", exc_info=True)
        return ""


def _parse_run_stats_from_log(log_text: str) -> dict[str, Any]:
    m = re.search(
        r"run_once done: candidates=(\d+) published=(\d+).*?failed=(\d+)",
        log_text,
    )
    if not m:
        return {}
    return {
        "candidates": int(m.group(1)),
        "published": int(m.group(2)),
        "failed": int(m.group(3)),
    }


def read_status(data_dir: Path) -> dict[str, Any]:
    path = _status_path(data_dir)
    if not path.is_file():
        out = dict(_IDLE)
        out["logTail"] = _tail_log(_log_path(data_dir))
        return out
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("status must be object")
        out = {**_IDLE, **raw}
    except (OSError, ValueError, json.JSONDecodeError):
        logger.warning("invalid pipeline status file", exc_info=True)
        out = dict(_IDLE)
        out["message"] = "状态文件损坏，可重新触发采集。"
    state = str(out.get("state") or "idle")
    if state == "running":
        pid = out.get("pid")
        if pid and not _pid_alive(int(pid)):
            out["state"] = "failed"
            out["message"] = "采集进程已意外退出，请重新触发。"
            out["pid"] = None
    out["logTail"] = _tail_log(_log_path(data_dir))
    if out["state"] == "completed" and not out.get("stats"):
        out["stats"] = _parse_run_stats_from_log(out.get("logTail") or "")
    return out


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


def _monitor_process(
    proc: subprocess.Popen[Any],
    log_file: Any,
    data_dir: Path,
    started_at: str,
) -> None:
    try:
        code = proc.wait()
    finally:
        try:
            log_file.close()
        except Exception:
            pass
    log_path = _log_path(data_dir)
    log_tail = _tail_log(log_path)
    stats = _parse_run_stats_from_log(log_tail)
    finished = _now_iso()
    if code == 0:
        msg = "采集流水线已完成"
        if stats:
            msg += (
                f"（候选 {stats.get('candidates', 0)} 篇，"
                f"发布 {stats.get('published', 0)} 篇）"
            )
        payload: dict[str, Any] = {
            "state": "completed",
            "message": msg,
            "startedAt": started_at,
            "finishedAt": finished,
            "exitCode": code,
            "pid": None,
            "logTail": log_tail,
            "stats": stats,
        }
    else:
        payload = {
            "state": "failed",
            "message": f"采集失败（退出码 {code}），请查看日志或终端重试。",
            "startedAt": started_at,
            "finishedAt": finished,
            "exitCode": code,
            "pid": None,
            "logTail": log_tail,
            "stats": stats,
        }
    _write_status(data_dir, payload)
    logger.info("pipeline run-once finished exit_code=%s", code)


def start_run_once(data_dir: Path) -> dict[str, Any]:
    """Launch ``python -m src.main run-once`` in background; return immediately."""
    with _LOCK:
        current = read_status(data_dir)
        if current.get("state") == "running":
            return {"ok": False, "error": "already_running", "status": current}

        v3_root = data_dir.parent
        log_path = _log_path(data_dir)
        started_at = _now_iso()

        running_payload: dict[str, Any] = {
            "state": "running",
            "message": "开始进行搜索了…（RSS / 栏目页 + GDELT → 聚类 → 摘要 → 通稿 → QA）",
            "startedAt": started_at,
            "finishedAt": "",
            "exitCode": None,
            "pid": None,
            "logTail": "",
            "stats": {},
        }
        _write_status(data_dir, running_payload)

        env = os.environ.copy()
        env["V3_MAIN_INNER"] = "1"
        env["PYTHONPATH"] = str(v3_root)

        log_file = open(log_path, "a", encoding="utf-8")
        log_file.write(f"\n\n===== pipeline run started {started_at} =====\n")
        log_file.flush()

        proc = subprocess.Popen(
            [sys.executable, "-m", "src.main", "run-once"],
            cwd=str(v3_root),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        running_payload["pid"] = proc.pid
        _write_status(data_dir, running_payload)

        thread = threading.Thread(
            target=_monitor_process,
            args=(proc, log_file, data_dir, started_at),
            daemon=True,
            name="pipeline-run-once",
        )
        thread.start()
        logger.info("pipeline run-once started pid=%s", proc.pid)
        return {"ok": True, "status": running_payload}
