"""In-app notifications — data source health + feedback pending."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.bff import config_api, data_source_health_store
from src.config import Settings


def build_notifications(settings: Settings) -> dict[str, Any]:
    rows = config_api.get_data_sources()
    health = data_source_health_store.build_health_response(rows if isinstance(rows, list) else [])
    alerts = [a for a in (health.get("alerts") or []) if isinstance(a, dict)]

    items: list[dict[str, Any]] = []
    for a in alerts[:20]:
        items.append(
            {
                "id": f"health:{a.get('source_id')}:{str(a.get('probe_url', ''))[:40]}",
                "kind": "data_source_health",
                "level": "warning",
                "title": f"数据源异常：{a.get('name') or a.get('source_id')}",
                "message": str(a.get("message") or "探测失败，请更新 RSS/栏目 URL"),
                "sourceId": a.get("source_id"),
                "probeUrl": a.get("probe_url"),
                "createdAt": a.get("checked_at") or datetime.now(timezone.utc).isoformat(),
                "action": "edit_source",
            }
        )

    return {
        "items": items,
        "total": len(items),
        "healthSummary": {
            "lastScanAt": health.get("last_full_scan_at") or "",
            "alertCount": len(alerts),
            "unacknowledgedCount": len(alerts),
            **(health.get("summary") or {}),
        },
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }
