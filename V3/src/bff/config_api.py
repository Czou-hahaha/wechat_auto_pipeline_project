"""读写采集配置：data_sources.json / search_keywords.json。"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import Settings


def _keywords_path() -> Path:
    return Settings()._search_keywords_file()


def _data_sources_path() -> Path:
    s = Settings()
    raw = (s.his_data_sources_path or "").strip()
    if raw:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = Path.cwd() / p
        return p
    return Path(__file__).resolve().parent.parent.parent / "config" / "data_sources.json"


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = path.with_suffix(path.suffix + f".bak.{ts}")
        shutil.copy2(path, backup)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def get_data_sources() -> list[dict[str, Any]]:
    rows = _read_json(_data_sources_path(), [])
    return rows if isinstance(rows, list) else []


def put_data_sources(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        raise ValueError("body must be a JSON array")
    _write_json(_data_sources_path(), rows)
    return get_data_sources()


def get_keywords() -> dict[str, Any]:
    data = _read_json(_keywords_path(), {})
    return data if isinstance(data, dict) else {}


def put_keywords(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("body must be a JSON object")
    _write_json(_keywords_path(), data)
    return get_keywords()
