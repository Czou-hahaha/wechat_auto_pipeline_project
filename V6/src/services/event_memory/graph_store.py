"""NetworkX in-memory graph (V1) with JSON snapshot persistence."""
from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

import networkx as nx

from src.services.event_memory.schemas import EdgeRecord, EntityNode, EventNode, GraphEdgeType, utc_now_iso

logger = logging.getLogger(__name__)


class NetworkXGraphStore:
    """Directed multi-relational graph backed by NetworkX."""

    def __init__(self, snapshot_path: Path) -> None:
        self._path = snapshot_path
        self._g = nx.MultiDiGraph()
        self._event_nodes: dict[str, EventNode] = {}
        self._entity_nodes: dict[str, EntityNode] = {}
        self._load()

    @property
    def graph(self) -> nx.MultiDiGraph:
        return self._g

    def list_events(self) -> list[EventNode]:
        return list(self._event_nodes.values())

    def get_event(self, event_id: str) -> EventNode | None:
        return self._event_nodes.get(event_id)

    def get_event_by_external_id(self, external_event_id: str) -> EventNode | None:
        ext = (external_event_id or "").strip()
        if not ext:
            return None
        for ev in self._event_nodes.values():
            if ev.external_event_id == ext:
                return ev
        return None

    def get_entity(self, entity_id: str) -> EntityNode | None:
        return self._entity_nodes.get((entity_id or "").strip())

    def get_entity_by_name(self, name: str, entity_type: str) -> EntityNode | None:
        key = f"{name.lower()}::{entity_type}"
        for ent in self._entity_nodes.values():
            if f"{ent.name.lower()}::{ent.type.value}" == key:
                return ent
        return None

    def upsert_entity(self, ent: EntityNode) -> EntityNode:
        existing = self.get_entity_by_name(ent.name, ent.type.value)
        if existing:
            existing.last_seen = ent.last_seen or utc_now_iso()
            if ent.aliases:
                merged = set(existing.aliases) | set(ent.aliases)
                existing.aliases = sorted(merged)
            return existing
        if not ent.entity_id:
            ent.entity_id = str(uuid.uuid4())
        if not ent.first_seen:
            ent.first_seen = utc_now_iso()
        ent.last_seen = ent.last_seen or ent.first_seen
        self._entity_nodes[ent.entity_id] = ent
        self._g.add_node(ent.entity_id, kind="entity", **ent.to_dict())
        return ent

    def upsert_event(self, ev: EventNode) -> EventNode:
        if not ev.event_id:
            ev.event_id = str(uuid.uuid4())
        if not ev.created_at:
            ev.created_at = utc_now_iso()
        ev.updated_at = ev.updated_at or ev.created_at
        self._event_nodes[ev.event_id] = ev
        self._g.add_node(ev.event_id, kind="event", **ev.to_dict())
        return ev

    def add_edge(self, edge: EdgeRecord) -> None:
        if not edge.created_at:
            edge.created_at = utc_now_iso()
        self._g.add_edge(
            edge.source,
            edge.target,
            key=edge.relation.value,
            relation=edge.relation.value,
            confidence=edge.confidence,
            created_at=edge.created_at,
            source_kind=edge.source_kind,
            target_kind=edge.target_kind,
            evidence=edge.evidence,
        )

    def link_event_entity(self, event_id: str, entity_id: str, *, confidence: float = 1.0) -> None:
        self.add_edge(
            EdgeRecord(
                source=event_id,
                target=entity_id,
                relation=GraphEdgeType.REFERENCES,
                confidence=confidence,
                source_kind="event",
                target_kind="entity",
                evidence="event-entity membership",
            )
        )
        ev = self._event_nodes.get(event_id)
        if ev and entity_id not in ev.entities:
            ev.entities.append(entity_id)

    def link_events(self, from_id: str, to_id: str, relation: GraphEdgeType, *, confidence: float) -> None:
        self.add_edge(
            EdgeRecord(
                source=from_id,
                target=to_id,
                relation=relation,
                confidence=confidence,
                source_kind="event",
                target_kind="event",
            )
        )
        ev = self._event_nodes.get(from_id)
        if ev and to_id not in ev.related_events:
            ev.related_events.append(to_id)

    def neighbors(self, node_id: str, *, relation: str | None = None) -> list[tuple[str, str, dict[str, Any]]]:
        out: list[tuple[str, str, dict[str, Any]]] = []
        for _u, v, k, data in self._g.out_edges(node_id, keys=True, data=True):
            if relation and data.get("relation") != relation:
                continue
            out.append((node_id, v, data))
        return out

    def export_visualization(self) -> dict[str, Any]:
        nodes = []
        for nid, data in self._g.nodes(data=True):
            nodes.append({"id": nid, "label": data.get("name") or data.get("title") or nid[:8], **data})
        edges = []
        for u, v, k, data in self._g.edges(keys=True, data=True):
            edges.append(
                {
                    "id": f"{u}-{v}-{k}",
                    "source": u,
                    "target": v,
                    "relation": data.get("relation", k),
                    "confidence": data.get("confidence", 0.5),
                }
            )
        return {"nodes": nodes, "edges": edges}

    def save(self) -> None:
        payload = {
            "events": [e.to_dict() for e in self._event_nodes.values()],
            "entities": [e.to_dict() for e in self._entity_nodes.values()],
            "graph": nx.node_link_data(self._g),
            "saved_at": utc_now_iso(),
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("graph snapshot saved path=%s events=%d entities=%d", self._path, len(self._event_nodes), len(self._entity_nodes))

    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("graph snapshot corrupt; starting fresh", exc_info=True)
            return
        from src.services.event_memory.schemas import GraphNodeType, TimelineEntry

        for row in raw.get("events") or []:
            if not isinstance(row, dict):
                continue
            tl = [
                TimelineEntry(
                    date=str(t.get("date") or ""),
                    update=str(t.get("update") or ""),
                    source=str(t.get("source") or ""),
                )
                for t in row.get("timeline") or []
                if isinstance(t, dict)
            ]
            ev = EventNode(
                event_id=str(row.get("event_id", "")),
                title=str(row.get("title", "")),
                summary=str(row.get("summary", "")),
                importance_score=int(row.get("importance_score", 0)),
                created_at=str(row.get("created_at", "")),
                updated_at=str(row.get("updated_at", "")),
                entities=list(row.get("entities") or []),
                related_events=list(row.get("related_events") or []),
                timeline=tl,
                embedding=row.get("embedding"),
                external_event_id=str(row.get("external_event_id", "")),
            )
            self.upsert_event(ev)
        for row in raw.get("entities") or []:
            if not isinstance(row, dict):
                continue
            ent = EntityNode(
                entity_id=str(row.get("entity_id", "")),
                name=str(row.get("name", "")),
                type=GraphNodeType(str(row.get("type", "entity"))),
                aliases=list(row.get("aliases") or []),
                first_seen=str(row.get("first_seen", "")),
                last_seen=str(row.get("last_seen", "")),
                embedding=row.get("embedding"),
            )
            self.upsert_entity(ent)
        gdata = raw.get("graph")
        if isinstance(gdata, dict):
            self._g = nx.node_link_graph(gdata, directed=True, multigraph=True)
