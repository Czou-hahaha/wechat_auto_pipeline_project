"""读写 V3/.env 中的定时任务配置（仅 SCHEDULE_* 键）。"""

from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import Settings

_SCHEDULE_KEYS = (
    "SCHEDULE_ENABLED",
    "SCHEDULE_TIMEZONE",
    "SCHEDULE_MORNING_HOUR",
    "SCHEDULE_EVENING_HOUR",
)


def _env_path() -> Path:
    return Path.cwd() / ".env"


def _parse_env_lines(text: str) -> list[str]:
    return text.splitlines()


def _read_env_map(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in _parse_env_lines(path.read_text(encoding="utf-8")):
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, val = s.partition("=")
        out[key.strip()] = val.strip()
    return out


def _bool_str(v: bool) -> str:
    return "true" if v else "false"


def _parse_bool(raw: str, default: bool) -> bool:
    s = (raw or "").strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off"):
        return False
    return default


def _parse_hour(raw: str, default: int) -> int:
    try:
        h = int(str(raw).strip())
        return max(0, min(23, h))
    except (TypeError, ValueError):
        return default


def get_schedule_config() -> dict[str, Any]:
    """当前定时配置 + 人类可读说明。"""
    s = Settings()
    path = _env_path()
    env_map = _read_env_map(path)

    enabled = _parse_bool(env_map.get("SCHEDULE_ENABLED", ""), s.schedule_enabled)
    tz = env_map.get("SCHEDULE_TIMEZONE") or s.schedule_timezone
    morning = _parse_hour(env_map.get("SCHEDULE_MORNING_HOUR", ""), s.schedule_morning_hour)
    evening = _parse_hour(env_map.get("SCHEDULE_EVENING_HOUR", ""), s.schedule_evening_hour)

    return {
        "enabled": enabled,
        "timezone": tz,
        "morning_hour": morning,
        "evening_hour": evening,
        "morning_time": f"{morning:02d}:00",
        "evening_time": f"{evening:02d}:00",
        "summary": f"每日 {morning:02d}:00、{evening:02d}:00（{tz}）各执行一次 run-once",
        "env_path": str(path.resolve()),
        "restart_hint": "修改后需重启 run-scheduler 进程后生效",
    }


def put_schedule_config(body: dict[str, Any]) -> dict[str, Any]:
    """更新 .env 中 SCHEDULE_* 行。"""
    enabled = bool(body.get("enabled", False))
    tz = str(body.get("timezone") or "Asia/Shanghai").strip() or "Asia/Shanghai"
    morning = _parse_hour(str(body.get("morning_hour", 8)), 8)
    evening = _parse_hour(str(body.get("evening_hour", 20)), 20)

    updates = {
        "SCHEDULE_ENABLED": _bool_str(enabled),
        "SCHEDULE_TIMEZONE": tz,
        "SCHEDULE_MORNING_HOUR": str(morning),
        "SCHEDULE_EVENING_HOUR": str(evening),
    }

    path = _env_path()
    if path.is_file():
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        shutil.copy2(path, path.with_suffix(f".env.bak.{ts}"))

    lines: list[str] = []
    seen: set[str] = set()
    if path.is_file():
        for line in _parse_env_lines(path.read_text(encoding="utf-8")):
            s = line.strip()
            if s and not s.startswith("#") and "=" in s:
                key = s.partition("=")[0].strip()
                if key in updates:
                    lines.append(f"{key}={updates[key]}")
                    seen.add(key)
                    continue
            lines.append(line)

    missing = [k for k in updates if k not in seen]
    if missing:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("# === 定时任务（run-scheduler）===")
        for key in missing:
            lines.append(f"{key}={updates[key]}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return get_schedule_config()
