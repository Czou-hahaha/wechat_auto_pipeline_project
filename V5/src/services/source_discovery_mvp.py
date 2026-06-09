from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.services.data_source_health import probe_data_source


def _host(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        host = (urlparse(raw).netloc or "").lower()
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


class SourceCandidateStore:
    def __init__(self, data_dir: Path):
        self._path = data_dir / "source_candidates.json"
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

    def discover_from_articles(self, article_rows: list[dict[str, Any]], *, top_n: int = 20) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for row in article_rows:
            url = str(row.get("resolved_url") or row.get("source_url") or "").strip()
            host = _host(url)
            if not host:
                continue
            counts[host] = counts.get(host, 0) + 1
        ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:top_n]
        existing = {str(x.get("host") or ""): x for x in self._read()}
        now = datetime.now(timezone.utc).isoformat()
        merged: list[dict[str, Any]] = []
        for host, cnt in ranked:
            row = existing.get(host, {})
            merged.append(
                {
                    "host": host,
                    "mention_count": max(int(row.get("mention_count") or 0), cnt),
                    "status": str(row.get("status") or "new"),
                    "ingest_mode": str(row.get("ingest_mode") or "unknown"),
                    "probe_url": str(row.get("probe_url") or ""),
                    "last_probe_status": str(row.get("last_probe_status") or ""),
                    "last_probe_message": str(row.get("last_probe_message") or ""),
                    "last_seen_at": now,
                }
            )
        self._write(merged)
        return {"total": len(merged), "items": merged}

    async def probe_candidate(self, *, host: str) -> dict[str, Any]:
        rows = self._read()
        hit = None
        for row in rows:
            if str(row.get("host") or "") == host:
                hit = row
                break
        if hit is None:
            raise ValueError("candidate host not found")

        rss_row = {
            "id": f"auto_{host}_rss",
            "name": f"Auto {host} RSS",
            "value": host,
            "kind": "web",
            "ingest_mode": "rss",
            "rss": f"https://{host}/rss",
        }
        html_row = {
            "id": f"auto_{host}_html",
            "name": f"Auto {host} HTML",
            "value": host,
            "kind": "web",
            "ingest_mode": "html_list",
            "list_monitor_url": f"https://{host}/",
        }

        rss_result = await probe_data_source(rss_row)
        chosen_mode = "rss"
        chosen_url = rss_row["rss"]
        chosen_result = rss_result
        if not rss_result.ok:
            html_result = await probe_data_source(html_row)
            chosen_mode = "html_list"
            chosen_url = html_row["list_monitor_url"]
            chosen_result = html_result

        hit["status"] = "ready" if chosen_result.ok else "blocked"
        hit["ingest_mode"] = chosen_mode
        hit["probe_url"] = chosen_url
        hit["last_probe_status"] = chosen_result.status
        hit["last_probe_message"] = chosen_result.message
        hit["last_probe_sample_count"] = chosen_result.sample_count
        hit["last_probed_at"] = datetime.now(timezone.utc).isoformat()
        self._write(rows)
        return hit

    def list_all(self) -> list[dict[str, Any]]:
        return self._read()
