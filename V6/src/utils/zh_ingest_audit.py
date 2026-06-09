"""中文/升级入库路径审计落盘（每轮 run_once 写入 data/zh_ingest_audit_last_run.json）。"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_records: list[dict[str, Any]] = []
_run_started_at: str | None = None


def reset_zh_ingest_audit() -> None:
    global _records, _run_started_at
    _records = []
    _run_started_at = datetime.now(timezone.utc).isoformat()


def record_zh_ingest_audit(
    *,
    url: str,
    title: str = "",
    stage: str,
    keep: bool,
    reason: str = "",
    category: str = "",
    source_host: str = "",
) -> None:
    if _run_started_at is None:
        reset_zh_ingest_audit()
    _records.append(
        {
            "url": (url or "").strip(),
            "title": (title or "").strip()[:200],
            "stage": (stage or "").strip(),
            "keep": bool(keep),
            "reason": (reason or "").strip()[:120],
            "category": (category or "").strip(),
            "source_host": (source_host or "").strip(),
            "at": datetime.now(timezone.utc).isoformat(),
        }
    )


def flush_zh_ingest_audit(data_dir: Path) -> Path | None:
    """写入 ``zh_ingest_audit_last_run.json``；无记录时跳过。"""
    if not _records:
        return None
    out = Path(data_dir) / "zh_ingest_audit_last_run.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_started_at": _run_started_at,
        "count": len(_records),
        "items": _records[-500:],
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("zh_ingest_audit written path=%s count=%d", out, len(_records))
    return out
