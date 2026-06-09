"""Unified event graph API — event-centric graph + memory + history."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.config import Settings
from src.services.event_history_mvp import build_event_history_payload
from src.services.event_map_mvp import build_event_map_payload
from src.services.event_memory.graph_store import NetworkXGraphStore
from src.services.event_memory_mvp import EventMemoryStore
from src.storage import JsonStore

logger = logging.getLogger(__name__)

_RELATION_LABEL_ZH: dict[str, str] = {
    "current": "当前",
    "semantic_neighbor": "语义关联",
    "same_topic": "同主题",
    "evolves_from": "演化自",
    "continuation": "延续",
    "related_to": "关联",
    "follows": "后续",
    "new_event": "新事件",
    "same_event": "同题更新",
}


def _graph_store(settings: Settings) -> NetworkXGraphStore:
    graph_dir = settings.data_path() / "event_graph"
    graph_dir.mkdir(parents=True, exist_ok=True)
    return NetworkXGraphStore(graph_dir / "graph_snapshot.json")


def _timeline_kind_label(entry: Any) -> str:
    kind = getattr(entry, "kind", None)
    if kind is not None:
        raw = kind.value if hasattr(kind, "value") else str(kind)
        return _RELATION_LABEL_ZH.get(raw, raw)
    src = str(getattr(entry, "source", "") or "").strip()
    return _RELATION_LABEL_ZH.get(src, src or "更新")


def _load_lexicon_names(settings: Settings) -> set[str]:
    names: set[str] = set()
    path = Path(settings.event_graph_config_path or "config/event_graph.json")
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_file():
        return names
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        for vals in (doc.get("domain_lexicon") or {}).values():
            if isinstance(vals, list):
                for v in vals:
                    s = str(v).strip()
                    if s:
                        names.add(s.lower())
    except Exception:
        logger.warning("event graph lexicon load failed", exc_info=True)
    return names


def _event_title_zh(store: JsonStore, event_id: str, fallback: str = "") -> str:
    ev = store.get_event(event_id)
    if not ev:
        return fallback
    return str(
        ev.get("headline_zh") or ev.get("title_zh") or ev.get("title") or fallback
    ).strip()


def _subgraph_for_external_id(store: NetworkXGraphStore, external_id: str) -> dict[str, Any]:
    ev_node = store.get_event_by_external_id(external_id)
    if not ev_node:
        return {"nodes": [], "edges": [], "graphEventId": None}

    gid = ev_node.event_id
    timeline = [
        {
            "date": t.date,
            "kind": _timeline_kind_label(t),
            "update": t.update,
            "source": t.source,
        }
        for t in (ev_node.timeline or [])
    ]
    return {
        "graphEventId": gid,
        "title": ev_node.title,
        "summary": ev_node.summary,
        "importanceScore": ev_node.importance_score,
        "evolutionKind": getattr(ev_node.evolution_kind, "value", str(ev_node.evolution_kind or "")),
        "relatedEventIds": list(ev_node.related_events or []),
        "timeline": timeline,
        "nodes": [],
        "edges": [],
    }


def _build_event_centric_graph(
    store: JsonStore,
    event_id: str,
    *,
    title: str,
    history_payload: dict[str, Any],
    graph_store: NetworkXGraphStore,
    lexicon: set[str],
) -> dict[str, Any]:
    """事件—事件图谱：中心为当前事件，关联链为邻居节点（不含文章节点）。"""
    nodes: list[dict[str, Any]] = [
        {
            "id": f"event:{event_id}",
            "type": "event",
            "label": title,
            "eventId": event_id,
            "isCurrent": True,
        }
    ]
    edges: list[dict[str, Any]] = []
    seen_ids: set[str] = {event_id}

    for item in history_payload.get("chain") or []:
        if not isinstance(item, dict):
            continue
        eid = str(item.get("eventId") or "").strip()
        if not eid or eid == event_id or eid in seen_ids:
            continue
        rel = str(item.get("relation") or "semantic_neighbor").strip()
        label = _event_title_zh(store, eid, str(item.get("title") or ""))
        if not label:
            continue
        seen_ids.add(eid)
        nodes.append(
            {
                "id": f"event:{eid}",
                "type": "event",
                "label": label,
                "eventId": eid,
                "isCurrent": False,
            }
        )
        edges.append(
            {
                "source": f"event:{eid}",
                "target": f"event:{event_id}",
                "relation": rel,
                "relationLabel": _RELATION_LABEL_ZH.get(rel, rel),
            }
        )

    # 事件详情「事件图谱」仅展示事件—事件关联；实体节点保留在 NetworkX 快照，不在此视图渲染。
    _ = graph_store, lexicon

    event_nodes = [n for n in nodes if n.get("type") == "event"]
    event_ids = {n.get("eventId") for n in event_nodes if n.get("eventId")}
    event_edges = [
        e
        for e in edges
        if e.get("source", "").startswith("event:")
        and e.get("target", "").startswith("event:")
        and e.get("source", "").replace("event:", "") in event_ids
        and e.get("target", "").replace("event:", "") in event_ids
    ]
    return {"nodes": event_nodes, "edges": event_edges}


def build_event_intelligence_graph(
    store: JsonStore, event_id: str, *, settings: Settings | None = None
) -> dict[str, Any]:
    settings = settings or Settings()
    ev = store.get_event(event_id)
    if not ev:
        raise ValueError("event not found")

    title = str(ev.get("headline_zh") or ev.get("title_zh") or ev.get("title") or "")
    articles = store.articles_for_event(event_id)
    map_payload = build_event_map_payload(ev, articles)
    history_payload = build_event_history_payload(store, event_id)

    mem_store = EventMemoryStore(settings.data_path())
    snap = mem_store.get_snapshot(event_id)
    if snap is None:
        snap = mem_store.upsert_snapshot(ev, articles)

    nx_store = _graph_store(settings)
    graph_part = _subgraph_for_external_id(nx_store, event_id)
    lexicon = _load_lexicon_names(settings)
    event_graph = _build_event_centric_graph(
        store,
        event_id,
        title=title,
        history_payload=history_payload,
        graph_store=nx_store,
        lexicon=lexicon,
    )

    memory_summary = {
        "title": snap.get("title") or title,
        "dominantTopicKey": snap.get("dominant_topic_key") or ev.get("dominant_topic_key"),
        "qaScore": snap.get("qa_score") or ev.get("event_press_qa_score"),
        "qaStoppedReason": snap.get("qa_stopped_reason") or ev.get("event_press_qa_stopped_reason"),
        "facts": snap.get("facts") or [],
        "updatedAt": snap.get("updated_at"),
    }

    return {
        "eventId": event_id,
        "title": title,
        "map": {
            "nodeCount": map_payload.get("nodeCount") or 0,
            "edgeCount": map_payload.get("edgeCount") or 0,
            "sourceDiversity": map_payload.get("sourceDiversity") or 0,
            "topSources": map_payload.get("topSources") or [],
            "evidence": map_payload.get("evidence") or [],
            "sourceHosts": [
                x.get("host") for x in (map_payload.get("topSources") or []) if x.get("host")
            ],
        },
        "graph": graph_part,
        "eventGraph": event_graph,
        "history": {
            "chain": history_payload.get("chain") or [],
            "timelineReport": history_payload.get("timelineReport") or "",
        },
        "memory": memory_summary,
        "visualization": event_graph,
    }


def rebuild_graph_from_store(store: JsonStore, settings: Settings | None = None) -> dict[str, Any]:
    """CLI helper: rerun EventMemoryService on all events."""
    import asyncio

    settings = settings or Settings()
    from src.services.event_memory.event_memory_service import EventMemoryService

    svc = EventMemoryService(settings)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        raise RuntimeError("rebuild_graph_from_store must be called from sync context")
    return asyncio.run(svc.process_events_from_store(store))
