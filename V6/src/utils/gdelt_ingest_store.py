"""Persist GDELT search hits to local JSON for downstream pipeline (decoupled from live API)."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _hit_to_dict(hit: Any) -> dict[str, str]:
    if is_dataclass(hit):
        d = asdict(hit)
    elif isinstance(hit, dict):
        d = hit
    else:
        d = {
            "title": getattr(hit, "title", ""),
            "url": getattr(hit, "url", ""),
            "snippet": getattr(hit, "snippet", ""),
            "published_at": getattr(hit, "published_at", ""),
        }
    return {
        "title": str(d.get("title") or ""),
        "url": str(d.get("url") or ""),
        "snippet": str(d.get("snippet") or ""),
        "published_at": str(d.get("published_at") or ""),
    }


def write_gdelt_ingest_snapshot(
    data_dir: Path,
    hits: list[Any],
    *,
    meta: dict[str, Any] | None = None,
) -> Path:
    """Write ``data/gdelt_ingest/{utc_timestamp}.json`` and update ``latest.json``."""
    ingest_dir = Path(data_dir) / "gdelt_ingest"
    ingest_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    payload: dict[str, Any] = {
        "fetched_at": now.isoformat(),
        "count": len(hits),
        "hits": [_hit_to_dict(h) for h in hits],
        "meta": meta or {},
    }
    path = ingest_dir / f"{stamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest = ingest_dir / "latest.json"
    latest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("gdelt ingest snapshot rows=%d path=%s", len(hits), path)
    return path
