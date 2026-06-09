"""数据源健康状态持久化（data/data_source_health.json）。"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import Settings
from src.services.data_source_health import (
    STATUS_FAILED,
    STATUS_OK,
    ProbeResult,
    source_health_key,
)

logger = logging.getLogger(__name__)

_HEALTH_VERSION = 1


def _health_path() -> Path:
    s = Settings()
    return Path(s.data_dir).expanduser().resolve() / "data_source_health.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_health_doc() -> dict[str, Any]:
    path = _health_path()
    if not path.is_file():
        return {"version": _HEALTH_VERSION, "last_full_scan_at": "", "sources": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("health doc must be object")
        sources = raw.get("sources")
        if not isinstance(sources, dict):
            sources = {}
        return {
            "version": int(raw.get("version") or _HEALTH_VERSION),
            "last_full_scan_at": str(raw.get("last_full_scan_at") or ""),
            "sources": sources,
        }
    except Exception:
        logger.warning("corrupt data_source_health.json, resetting", exc_info=True)
        return {"version": _HEALTH_VERSION, "last_full_scan_at": "", "sources": {}}


def save_health_doc(doc: dict[str, Any]) -> None:
    path = _health_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _entry_from_probe(row: dict[str, Any], probe: ProbeResult) -> dict[str, Any]:
    key = source_health_key(row)
    prev = load_health_doc()["sources"].get(key, {})
    ack_at = prev.get("user_ack_at") if isinstance(prev, dict) else None
    if probe.status == STATUS_FAILED:
        # 新失败清除旧确认，以便再次提醒
        if isinstance(prev, dict) and prev.get("status") == STATUS_FAILED:
            ack_at = prev.get("user_ack_at")
        else:
            ack_at = None
    return {
        "key": key,
        "source_id": str(row.get("id") or "").strip(),
        "name": str(row.get("name") or "").strip(),
        "status": probe.status,
        "message": probe.message,
        "checked_at": _now_iso(),
        "sample_count": probe.sample_count,
        "http_status": probe.http_status,
        "ingest_mode": probe.ingest_mode,
        "probe_url": probe.probe_url,
        "user_ack_at": ack_at,
        "user_ack_note": (prev.get("user_ack_note") if isinstance(prev, dict) else "") or "",
    }


def record_probe(row: dict[str, Any], probe: ProbeResult) -> dict[str, Any]:
    doc = load_health_doc()
    key = source_health_key(row)
    entry = _entry_from_probe(row, probe)
    doc["sources"][key] = entry
    save_health_doc(doc)
    return entry


def record_full_scan(results: dict[str, tuple[dict[str, Any], ProbeResult]]) -> dict[str, Any]:
    doc = load_health_doc()
    now = _now_iso()
    for _key, (row, probe) in results.items():
        entry = _entry_from_probe(row, probe)
        doc["sources"][entry["key"]] = entry
    doc["last_full_scan_at"] = now
    save_health_doc(doc)
    return doc


async def run_full_health_scan(settings: Settings | None = None) -> dict[str, Any]:
    from src.bff import config_api
    from src.services.data_source_health import probe_data_source, source_health_key

    s = settings or Settings()
    rows = config_api.get_data_sources()
    packed: dict[str, tuple[dict[str, Any], ProbeResult]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = source_health_key(row)
        probe = await probe_data_source(row, s)
        packed[key] = (row, probe)
    record_full_scan(packed)
    return build_health_response(rows if isinstance(rows, list) else [])


def needs_attention(entry: dict[str, Any]) -> bool:
    if str(entry.get("status")) != STATUS_FAILED:
        return False
    ack = str(entry.get("user_ack_at") or "").strip()
    checked = str(entry.get("checked_at") or "").strip()
    if not ack:
        return True
    return ack < checked


def acknowledge_source(key: str, note: str = "") -> dict[str, Any] | None:
    doc = load_health_doc()
    entry = doc["sources"].get(key)
    if not isinstance(entry, dict):
        return None
    entry["user_ack_at"] = _now_iso()
    entry["user_ack_note"] = (note or "").strip()[:500]
    doc["sources"][key] = entry
    save_health_doc(doc)
    return entry


def build_health_response(rows: list[dict[str, Any]]) -> dict[str, Any]:
    doc = load_health_doc()
    stored: dict[str, Any] = doc.get("sources") or {}
    by_key: dict[str, Any] = {}
    alerts: list[dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        key = source_health_key(row)
        entry = stored.get(key)
        if isinstance(entry, dict):
            merged = {**entry, "key": key, "needs_attention": needs_attention(entry)}
        else:
            merged = {
                "key": key,
                "source_id": str(row.get("id") or "").strip(),
                "name": str(row.get("name") or "").strip(),
                "status": "unknown",
                "message": "尚未探测",
                "checked_at": "",
                "needs_attention": False,
            }
        by_key[key] = merged
        if merged.get("needs_attention"):
            alerts.append(
                {
                    "key": key,
                    "source_id": merged.get("source_id"),
                    "name": merged.get("name"),
                    "message": merged.get("message"),
                    "checked_at": merged.get("checked_at"),
                    "probe_url": merged.get("probe_url"),
                }
            )

    ok_count = sum(1 for e in by_key.values() if e.get("status") == STATUS_OK)
    failed_count = sum(1 for e in by_key.values() if e.get("status") == STATUS_FAILED)

    return {
        "sources": by_key,
        "alerts": alerts,
        "last_full_scan_at": doc.get("last_full_scan_at") or "",
        "summary": {
            "total": len(by_key),
            "ok": ok_count,
            "failed": failed_count,
            "needs_attention": len(alerts),
        },
    }
