from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass
class FeedbackRecord:
    id: str
    event_id: str
    stage: str
    category: str
    note: str
    created_at: str


class FeedbackStore:
    def __init__(self, data_dir: Path):
        self._path = data_dir / "feedback_events.json"
        if not self._path.exists():
            self._path.write_text("[]", encoding="utf-8")

    def _read(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _write(self, rows: list[dict[str, Any]]) -> None:
        self._path.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def add(self, *, event_id: str, stage: str, category: str, note: str) -> dict[str, Any]:
        rec = FeedbackRecord(
            id=str(uuid4()),
            event_id=(event_id or "").strip(),
            stage=(stage or "qa").strip().lower(),
            category=(category or "general").strip().lower(),
            note=(note or "").strip(),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        rows = self._read()
        rows.append(rec.__dict__)
        self._write(rows)
        return rec.__dict__

    def list_all(self) -> list[dict[str, Any]]:
        return self._read()

    def summary(self) -> dict[str, Any]:
        rows = self._read()
        by_stage: dict[str, int] = {}
        by_category: dict[str, int] = {}
        for row in rows:
            stage = str(row.get("stage") or "unknown")
            category = str(row.get("category") or "unknown")
            by_stage[stage] = by_stage.get(stage, 0) + 1
            by_category[category] = by_category.get(category, 0) + 1
        return {
            "total": len(rows),
            "byStage": by_stage,
            "byCategory": by_category,
            "latest": rows[-10:],
        }
