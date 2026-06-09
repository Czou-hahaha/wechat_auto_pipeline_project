"""Event graph typed models."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class GraphNodeType(str, Enum):
    EVENT = "event"
    ENTITY = "entity"
    ORGANIZATION = "organization"
    COUNTRY = "country"
    POLICY = "policy"
    TECHNOLOGY = "technology"
    COMPANY = "company"


class GraphEdgeType(str, Enum):
    RELATED_TO = "related_to"
    EVOLVES_FROM = "evolves_from"
    ANNOUNCED_BY = "announced_by"
    IMPACTS = "impacts"
    REGULATES = "regulates"
    PARTNERS_WITH = "partners_with"
    COMPETES_WITH = "competes_with"
    REFERENCES = "references"
    FOLLOWS = "follows"


class EventEvolutionKind(str, Enum):
    NEW_EVENT = "new_event"
    SAME_EVENT = "same_event"
    CONTINUATION = "continuation"
    SUB_EVENT = "sub_event"
    ESCALATION = "escalation"


@dataclass
class TimelineEntry:
    date: str
    update: str
    source: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"date": self.date, "update": self.update, "source": self.source}


@dataclass
class EntityNode:
    entity_id: str
    name: str
    type: GraphNodeType
    aliases: list[str] = field(default_factory=list)
    first_seen: str = ""
    last_seen: str = ""
    embedding: list[float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "name": self.name,
            "type": self.type.value,
            "aliases": self.aliases,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "embedding": self.embedding,
        }


@dataclass
class EventNode:
    event_id: str
    title: str
    summary: str
    importance_score: int = 0
    created_at: str = ""
    updated_at: str = ""
    entities: list[str] = field(default_factory=list)
    related_events: list[str] = field(default_factory=list)
    timeline: list[TimelineEntry] = field(default_factory=list)
    embedding: list[float] | None = None
    evolution_kind: EventEvolutionKind = EventEvolutionKind.NEW_EVENT
    parent_event_id: str | None = None
    external_event_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "title": self.title,
            "summary": self.summary,
            "importance_score": self.importance_score,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "entities": self.entities,
            "related_events": self.related_events,
            "timeline": [t.to_dict() for t in self.timeline],
            "embedding": self.embedding,
            "evolution_kind": self.evolution_kind.value,
            "parent_event_id": self.parent_event_id,
            "external_event_id": self.external_event_id,
        }


@dataclass
class EdgeRecord:
    source: str
    target: str
    relation: GraphEdgeType
    confidence: float
    created_at: str = ""
    source_kind: str = "entity"
    target_kind: str = "entity"
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "relation": self.relation.value,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "source_kind": self.source_kind,
            "target_kind": self.target_kind,
            "evidence": self.evidence,
        }


@dataclass
class ExtractedEntity:
    name: str
    entity_type: GraphNodeType
    confidence: float
    span_start: int = 0
    span_end: int = 0


@dataclass
class ExtractedRelation:
    source_name: str
    target_name: str
    relation: GraphEdgeType
    confidence: float
    evidence: str = ""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_entity_type(raw: str) -> GraphNodeType:
    key = (raw or "entity").strip().lower()
    mapping = {
        "event": GraphNodeType.EVENT,
        "entity": GraphNodeType.ENTITY,
        "organization": GraphNodeType.ORGANIZATION,
        "org": GraphNodeType.ORGANIZATION,
        "country": GraphNodeType.COUNTRY,
        "policy": GraphNodeType.POLICY,
        "technology": GraphNodeType.TECHNOLOGY,
        "tech": GraphNodeType.TECHNOLOGY,
        "company": GraphNodeType.COMPANY,
    }
    return mapping.get(key, GraphNodeType.ENTITY)
