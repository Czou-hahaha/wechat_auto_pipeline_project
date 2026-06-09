"""事件列表 DTO 构建与内存缓存（避免每次请求全量 event_to_intelligence）。"""
from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.bff.enhancement_loader import load_enhancement_runs_by_event
from src.bff.event_mapper import event_to_list_item
from src.storage import JsonStore

logger = logging.getLogger(__name__)

_cache_mtime: float = -1.0
_cache_rows: list[dict[str, Any]] | None = None


def _data_mtime(store: JsonStore) -> float:
    latest = 0.0
    for name in ("events.json", "articles.json", "event_article_map.json", "event_enhancement_last_run.json"):
        p = Path(store.data_dir) / name
        if p.is_file():
            latest = max(latest, p.stat().st_mtime)
    return latest


def _articles_by_event(store: JsonStore) -> dict[str, list[dict[str, Any]]]:
    by_eid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in store.list_all():
        if not isinstance(row, dict):
            continue
        eid = str(row.get("event_id") or "").strip()
        if eid:
            by_eid[eid].append(row)
    return by_eid


def _url_roles_by_event(store: JsonStore) -> dict[str, dict[str, str]]:
    by_eid: dict[str, dict[str, str]] = defaultdict(dict)
    for m in store._read_event_map():  # noqa: SLF001
        if not isinstance(m, dict):
            continue
        eid = str(m.get("event_id") or "").strip()
        if not eid:
            continue
        role = str(m.get("role") or "source").strip()
        for key in ("resolved_url", "source_url"):
            u = str(m.get(key) or "").strip()
            if u:
                by_eid[eid][u] = role
    return by_eid


def build_event_list_items(store: JsonStore) -> list[dict[str, Any]]:
    """构建列表项；按重要性预排序。"""
    enh_idx = load_enhancement_runs_by_event(Path(store.data_dir))
    arts_by_event = _articles_by_event(store)
    roles_by_event = _url_roles_by_event(store)
    out: list[dict[str, Any]] = []
    for ev in store.list_events():
        if not isinstance(ev, dict):
            continue
        eid = str(ev.get("id") or "").strip()
        if not eid:
            continue
        articles = arts_by_event.get(eid, [])
        out.append(
            event_to_list_item(
                ev,
                articles,
                url_roles=roles_by_event.get(eid, {}),
                enhancement_row=enh_idx.get(eid),
            )
        )
    out.sort(key=lambda x: (-int(x.get("importance_score") or 0), x.get("createdAt") or ""))
    return out


def get_cached_event_list_items(store: JsonStore) -> list[dict[str, Any]]:
    """按 data 目录 mtime 缓存列表，同一次进程内重复请求复用。"""
    global _cache_mtime, _cache_rows
    mtime = _data_mtime(store)
    if _cache_rows is not None and mtime == _cache_mtime:
        return _cache_rows
    rows = build_event_list_items(store)
    _cache_mtime = mtime
    _cache_rows = rows
    logger.debug("event list cache rebuilt events=%d", len(rows))
    return rows


def invalidate_event_list_cache() -> None:
    global _cache_mtime, _cache_rows
    _cache_mtime = -1.0
    _cache_rows = None
