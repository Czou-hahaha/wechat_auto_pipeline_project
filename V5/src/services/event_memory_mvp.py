from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class EventMemoryStore:
    def __init__(self, data_dir: Path):
        self._path = data_dir / "event_memory_snapshots.json"
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

    def upsert_snapshot(self, event_row: dict[str, Any], article_rows: list[dict[str, Any]]) -> dict[str, Any]:
        eid = str(event_row.get("id") or "").strip()
        if not eid:
            raise ValueError("event id missing")
        fact_rows: list[dict[str, str]] = []
        for row in article_rows[:10]:
            fact_rows.append(
                {
                    "title": str(row.get("title") or "").strip()[:90],
                    "source_url": str(row.get("resolved_url") or row.get("source_url") or "").strip(),
                    "source_published_at": str(row.get("source_published_at") or "").strip(),
                }
            )
        snap = {
            "event_id": eid,
            "title": str(event_row.get("title_zh") or event_row.get("title") or "").strip(),
            "dominant_topic_key": str(event_row.get("dominant_topic_key") or "").strip(),
            "qa_score": int(event_row.get("event_press_qa_score") or 0),
            "qa_stopped_reason": str(event_row.get("event_press_qa_stopped_reason") or "").strip(),
            "facts": fact_rows,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        rows = self._read()
        replaced = False
        for idx, row in enumerate(rows):
            if str(row.get("event_id") or "").strip() == eid:
                rows[idx] = snap
                replaced = True
                break
        if not replaced:
            rows.append(snap)
        self._write(rows)
        return snap

    def get_snapshot(self, event_id: str) -> dict[str, Any] | None:
        eid = (event_id or "").strip()
        if not eid:
            return None
        for row in self._read():
            if str(row.get("event_id") or "").strip() == eid:
                return row
        return None
