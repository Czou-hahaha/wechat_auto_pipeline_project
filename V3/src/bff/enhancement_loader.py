"""Load ``event_enhancement_last_run.json`` for BFF / UI."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def load_enhancement_runs_by_event(data_dir: Path) -> dict[str, dict[str, Any]]:
    """``event_id`` → last-run row from ``event_enhancement_last_run.json``."""
    path = data_dir / "event_enhancement_last_run.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("enhancement_loader: failed to read %s", path)
        return {}
    if not isinstance(payload, dict):
        return {}
    generated_at = str(payload.get("generated_at") or "")
    out: dict[str, dict[str, Any]] = {}
    for row in payload.get("events") or []:
        if not isinstance(row, dict):
            continue
        eid = str(row.get("event_id") or "").strip()
        if not eid:
            continue
        out[eid] = {**row, "_run_generated_at": generated_at}
    return out
