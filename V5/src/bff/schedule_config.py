"""定时任务列表（config/schedule_jobs.json）+ 采集时间窗写入 .env。"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import Settings

_MAX_AGE_HOURS_CAP = 24 * 365
_ENV_AGE_KEY = "MAX_ARTICLE_AGE_HOURS"
_ENV_ENABLED = "SCHEDULE_ENABLED"
_ENV_TZ = "SCHEDULE_TIMEZONE"


def _jobs_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "config" / "schedule_jobs.json"


def _env_path() -> Path:
    return Path.cwd() / ".env"


def _parse_bool(raw: str, default: bool) -> bool:
    s = (raw or "").strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off"):
        return False
    return default


def _clamp_hour(h: int) -> int:
    return max(0, min(23, int(h)))


def _clamp_minute(m: int) -> int:
    return max(0, min(59, int(m)))


def _article_age_to_hours(unit: str, value: int) -> int:
    u = (unit or "hours").strip().lower()
    v = max(1, int(value))
    if u == "days":
        hours = v * 24
    else:
        hours = v
    return min(_MAX_AGE_HOURS_CAP, max(1, hours))


def _hours_to_article_age(hours: int) -> dict[str, Any]:
    h = max(1, min(_MAX_AGE_HOURS_CAP, int(hours)))
    if h % 24 == 0 and h >= 24:
        return {"unit": "days", "value": h // 24}
    return {"unit": "hours", "value": h}


def _default_jobs_from_settings(s: Settings) -> list[dict[str, Any]]:
    return [
        {
            "id": "job_morning",
            "label": "早间采集",
            "hour": s.schedule_morning_hour,
            "minute": 0,
        },
        {
            "id": "job_evening",
            "label": "晚间采集",
            "hour": s.schedule_evening_hour,
            "minute": 0,
        },
    ]


def _normalize_job(raw: dict[str, Any], *, idx: int) -> dict[str, Any]:
    jid = str(raw.get("id") or "").strip() or f"job_{uuid.uuid4().hex[:8]}"
    label = str(raw.get("label") or f"定时任务 {idx + 1}").strip() or f"定时任务 {idx + 1}"
    return {
        "id": jid,
        "label": label,
        "hour": _clamp_hour(int(raw.get("hour", 8))),
        "minute": _clamp_minute(int(raw.get("minute", 0))),
    }


def _read_jobs_file() -> dict[str, Any]:
    path = _jobs_path()
    s = Settings()
    if not path.is_file():
        env_map = _read_env_map(_env_path())
        age_h = _parse_age_hours_env(env_map.get(_ENV_AGE_KEY, ""), s.max_article_age_hours)
        limit_enabled = age_h > 0
        return {
            "enabled": _parse_bool(env_map.get(_ENV_ENABLED, ""), s.schedule_enabled),
            "timezone": env_map.get(_ENV_TZ) or s.schedule_timezone,
            "jobs": _default_jobs_from_settings(s),
            "article_age": _hours_to_article_age(age_h) if limit_enabled else {"unit": "hours", "value": 14},
            "article_age_limit_enabled": limit_enabled,
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("schedule_jobs must be object")
    except (OSError, ValueError, json.JSONDecodeError):
        return _read_jobs_file_fallback()

    env_map = _read_env_map(_env_path())
    enabled = _parse_bool(
        str(data.get("enabled", env_map.get(_ENV_ENABLED, ""))),
        s.schedule_enabled,
    )
    tz = str(data.get("timezone") or env_map.get(_ENV_TZ) or s.schedule_timezone).strip()
    raw_jobs = data.get("jobs")
    if isinstance(raw_jobs, list):
        jobs = [_normalize_job(j, idx=i) for i, j in enumerate(raw_jobs) if isinstance(j, dict)]
    else:
        jobs = _default_jobs_from_settings(s)

    if "article_age_limit_enabled" in data:
        limit_enabled = bool(data.get("article_age_limit_enabled"))
    else:
        env_age = _parse_age_hours_env(env_map.get(_ENV_AGE_KEY, ""), s.max_article_age_hours)
        limit_enabled = env_age > 0

    age_raw = data.get("article_age")
    if limit_enabled and isinstance(age_raw, dict):
        age_h = _article_age_to_hours(
            str(age_raw.get("unit") or "hours"),
            int(age_raw.get("value") or 14),
        )
    elif limit_enabled:
        age_h = _parse_age_hours_env(env_map.get(_ENV_AGE_KEY, ""), s.max_article_age_hours)
    else:
        age_h = 0

    return {
        "enabled": enabled,
        "timezone": tz or "Asia/Shanghai",
        "jobs": jobs,
        "article_age": _hours_to_article_age(age_h) if limit_enabled else {"unit": "hours", "value": 14},
        "article_age_limit_enabled": limit_enabled,
    }


# fallback when JSON corrupt — avoid infinite recursion
def _read_jobs_file_fallback() -> dict[str, Any]:
    s = Settings()
    return {
        "enabled": s.schedule_enabled,
        "timezone": s.schedule_timezone,
        "jobs": _default_jobs_from_settings(s),
        "article_age": _hours_to_article_age(s.max_article_age_hours),
    }


def _parse_age_hours_env(raw: str, default: int) -> int:
    try:
        return max(1, min(_MAX_AGE_HOURS_CAP, int(str(raw).strip())))
    except (TypeError, ValueError):
        return max(1, min(_MAX_AGE_HOURS_CAP, default))


def _read_env_map(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, val = s.partition("=")
        out[key.strip()] = val.strip()
    return out


def _write_env_keys(updates: dict[str, str]) -> None:
    path = _env_path()
    if path.is_file():
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        shutil.copy2(path, path.with_suffix(f".env.bak.{ts}"))

    lines: list[str] = []
    seen: set[str] = set()
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
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
        lines.append("# === 定时与采集时间窗（由平台 schedule_jobs.json 同步）===")
        for key in missing:
            lines.append(f"{key}={updates[key]}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _write_jobs_file(data: dict[str, Any]) -> None:
    path = _jobs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        shutil.copy2(path, path.with_suffix(f".json.bak.{ts}"))
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _format_summary(data: dict[str, Any], age_hours: int) -> str:
    limit_on = bool(data.get("article_age_limit_enabled", age_hours > 0))
    jobs = data.get("jobs") or []
    times = [
        f"{int(j.get('hour', 0)):02d}:{int(j.get('minute', 0)):02d}"
        for j in jobs
        if isinstance(j, dict)
    ]
    times_txt = "、".join(times) if times else "（未配置）"
    age = data.get("article_age") or {}
    unit = str(age.get("unit") or "hours")
    val = int(age.get("value") or age_hours)
    if not limit_on or age_hours <= 0:
        return f"已配置 {len(times)} 个定时点（{times_txt}）；不限制文章发布时间"
    if unit == "days":
        age_txt = f"近 {val} 天"
    else:
        age_txt = f"近 {val} 小时"
    return f"已配置 {len(times)} 个定时点（{times_txt}）；仅采集 {age_txt} 内发布的文章"


def get_schedule_config() -> dict[str, Any]:
    data = _read_jobs_file()
    age = data.get("article_age") or {}
    limit_enabled = bool(data.get("article_age_limit_enabled", True))
    age_hours = (
        _article_age_to_hours(str(age.get("unit")), int(age.get("value", 14)))
        if limit_enabled
        else 0
    )
    out = {
        "enabled": bool(data.get("enabled")),
        "timezone": str(data.get("timezone") or "Asia/Shanghai"),
        "jobs": data.get("jobs") or [],
        "article_age": age,
        "article_age_limit_enabled": limit_enabled,
        "article_age_hours": age_hours,
    }
    out["summary"] = _format_summary(data, age_hours)
    try:
        from src.bff.scheduler_run import read_status as read_scheduler_status
        from src.config import Settings

        out["scheduler"] = read_scheduler_status(Path(Settings().data_dir))
    except Exception:
        pass
    return out


def put_schedule_config(body: dict[str, Any]) -> dict[str, Any]:
    enabled = bool(body.get("enabled", False))
    tz = str(body.get("timezone") or "Asia/Shanghai").strip() or "Asia/Shanghai"

    raw_jobs = body.get("jobs")
    jobs: list[dict[str, Any]] = []
    if isinstance(raw_jobs, list):
        for i, item in enumerate(raw_jobs):
            if isinstance(item, dict):
                jobs.append(_normalize_job(item, idx=i))
    if not jobs and enabled:
        raise ValueError("启用定时采集时请至少保留一个定时任务")

    limit_enabled = bool(body.get("article_age_limit_enabled", True))
    age_raw = body.get("article_age")
    if limit_enabled and isinstance(age_raw, dict):
        article_age = {
            "unit": "days"
            if str(age_raw.get("unit") or "").lower() == "days"
            else "hours",
            "value": max(1, int(age_raw.get("value") or 1)),
        }
    elif limit_enabled and "article_age_hours" in body:
        article_age = _hours_to_article_age(int(body.get("article_age_hours") or 14))
    else:
        article_age = {"unit": "hours", "value": 14}

    age_hours = (
        _article_age_to_hours(article_age["unit"], article_age["value"])
        if limit_enabled
        else 0
    )

    payload = {
        "enabled": enabled,
        "timezone": tz,
        "jobs": jobs,
        "article_age": article_age,
        "article_age_limit_enabled": limit_enabled,
    }
    _write_jobs_file(payload)
    _write_env_keys(
        {
            _ENV_ENABLED: "true" if enabled else "false",
            _ENV_TZ: tz,
            _ENV_AGE_KEY: str(age_hours),
        }
    )
    out = get_schedule_config()
    from src.bff.scheduler_run import sync_scheduler
    from src.config import Settings

    data_dir = Path(Settings().data_dir)
    sync = sync_scheduler(
        data_dir,
        enabled=enabled,
        jobs=jobs,
        timezone=tz,
    )
    out["scheduler"] = sync.get("status") or {}
    if not sync.get("ok") and sync.get("error") == "no_jobs":
        out["schedulerWarning"] = "已启用定时采集但未配置执行时刻，请添加至少一个任务。"
    elif sync.get("ok") and enabled:
        out["schedulerNote"] = "已自动启动 run-scheduler，将按设定时刻执行采集。"
    elif not enabled:
        out["schedulerNote"] = "已停止后台调度进程。"
    return out


def load_scheduler_jobs() -> list[dict[str, Any]]:
    """供 ``run-scheduler`` 注册 APScheduler 任务。"""
    data = _read_jobs_file()
    if not data.get("enabled"):
        return []
    return list(data.get("jobs") or [])


def scheduler_timezone() -> str:
    return str(_read_jobs_file().get("timezone") or "Asia/Shanghai")
