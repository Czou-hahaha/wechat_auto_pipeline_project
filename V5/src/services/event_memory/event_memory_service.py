"""Event Graph Memory orchestrator — entity/relationship extraction, evolution, timeline."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any

import httpx

from src.config import Settings
from src.embed_dedupe import fetch_embeddings_batch, truncate_for_embedding
from src.services.event_memory.entity_extractor import EntityExtractor
from src.services.event_memory.evolution import EventEvolutionTracker
from src.services.event_memory.graph_store import NetworkXGraphStore
from src.services.event_memory.postgres_store import PostgresGraphStore
from src.services.event_memory.relationship_extractor import RelationshipExtractor
from src.services.event_memory.schemas import (
    EdgeRecord,
    EntityNode,
    EventEvolutionKind,
    EventNode,
    ExtractedEntity,
    GraphEdgeType,
    TimelineEntry,
    utc_now_iso,
)
from src.services.event_memory.timeline import TimelineService
from src.storage import JsonStore

logger = logging.getLogger(__name__)


async def _retry_async(coro_factory, *, max_attempts: int, backoff_sec: float, label: str):
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await coro_factory()
        except Exception as exc:
            last_exc = exc
            if attempt >= max_attempts:
                break
            wait = backoff_sec * attempt
            logger.warning("%s attempt %d failed: %s; retry in %.1fs", label, attempt, exc, wait)
            await asyncio.sleep(wait)
    raise last_exc  # type: ignore[misc]


class EventMemoryService:
    """
    Event-first temporal memory layer.

    Responsibilities:
    1. entity extraction
    2. relationship extraction
    3. graph update (NetworkX + optional PostgreSQL)
    4. timeline append
    5. related event linking / evolution tracking
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self._config = self._load_graph_config()
        self._timeouts = self._config.get("timeouts") or {}
        self._retries = self._config.get("retries") or {}
        data_dir = Path(self.settings.data_dir)
        graph_dir = data_dir / "event_graph"
        graph_dir.mkdir(parents=True, exist_ok=True)
        self._nx = NetworkXGraphStore(graph_dir / "graph_snapshot.json")
        self._timeline = TimelineService()
        self._entities = EntityExtractor(self._config)
        self._relations = RelationshipExtractor(self._config)
        self._evolution = EventEvolutionTracker(self._config)
        self._pg: PostgresGraphStore | None = None
        pg_url = (self.settings.event_graph_database_url or "").strip()
        if pg_url:
            self._pg = PostgresGraphStore(pg_url)

    def _load_graph_config(self) -> dict[str, Any]:
        path = Path(self.settings.event_graph_config_path or "config/event_graph.json")
        if not path.is_absolute():
            path = Path.cwd() / path
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                logger.warning("event_graph config load failed path=%s", path, exc_info=True)
        return {"enabled": True, "evolution": {}, "extraction": {}}

    async def process_events_from_store(self, store: JsonStore | None = None) -> dict[str, Any]:
        """Ingest all events from ``events.json`` into the graph memory layer."""
        if not self.settings.event_graph_enabled:
            logger.info("event graph disabled (EVENT_GRAPH_ENABLED=false)")
            return {"processed": 0, "skipped": "disabled"}
        store = store or JsonStore(Path(self.settings.data_dir))
        rows = store.list_events()
        stats = {"processed": 0, "new": 0, "linked": 0, "errors": 0}
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                result = await self.process_event_dict(row)
                stats["processed"] += 1
                if result.get("evolution_kind") == EventEvolutionKind.NEW_EVENT.value:
                    stats["new"] += 1
                elif result.get("matched_event_id"):
                    stats["linked"] += 1
            except Exception:
                stats["errors"] += 1
                logger.error("event_memory failed external_id=%s", row.get("id"), exc_info=True)
        self._nx.save()
        if self._pg:
            await self._flush_to_postgres()
        return stats

    async def process_event_dict(self, row: dict[str, Any]) -> dict[str, Any]:
        external_id = str(row.get("id") or "").strip()
        title = str(row.get("title") or row.get("summary_zh") or "").strip()
        summary = str(row.get("summary_zh") or row.get("summary") or "").strip()
        text = f"{title}\n{summary}"
        importance = int(row.get("importance_score") or 0)

        embedding = await self._embed_text(text)
        entities = await _retry_async(
            lambda: self._entities.extract(text, timeout_sec=float(self._timeouts.get("ner_sec", 15))),
            max_attempts=int(self._retries.get("max_attempts", 3)),
            backoff_sec=float(self._retries.get("backoff_sec", 1.5)),
            label="entity_extraction",
        )
        relations = await _retry_async(
            lambda: self._relations.extract(text, entities, timeout_sec=float(self._timeouts.get("ner_sec", 15))),
            max_attempts=int(self._retries.get("max_attempts", 3)),
            backoff_sec=float(self._retries.get("backoff_sec", 1.5)),
            label="relationship_extraction",
        )

        existing = self._nx.get_event_by_external_id(external_id) if external_id else None
        ev = EventNode(
            event_id=existing.event_id if existing else str(uuid.uuid4()),
            external_event_id=external_id,
            title=title,
            summary=summary,
            importance_score=importance,
            created_at=str(row.get("created_at") or utc_now_iso()),
            embedding=embedding,
        )
        ev.timeline.append(self._timeline.initial_entry(ev, source="v3_events"))

        entity_ids: list[str] = []
        entity_name_set: set[str] = set()
        for ext in entities:
            ent = self._entity_from_extracted(ext)
            stored = self._nx.upsert_entity(ent)
            entity_ids.append(stored.entity_id)
            entity_name_set.add(stored.name.lower())
            self._nx.link_event_entity(ev.event_id, stored.entity_id)

        history = [h for h in self._nx.list_events() if h.event_id != ev.event_id]
        hist_entity_map = self._build_entity_map(history)
        decision = self._evolution.classify(ev, entity_name_set, history, hist_entity_map)
        ev.evolution_kind = decision.kind

        if decision.matched_event_id and decision.kind != EventEvolutionKind.NEW_EVENT:
            prior = self._nx.get_event(decision.matched_event_id)
            if prior:
                ev.parent_event_id = prior.event_id
                rel = GraphEdgeType.EVOLVES_FROM if decision.kind != EventEvolutionKind.SAME_EVENT else GraphEdgeType.RELATED_TO
                self._nx.link_events(ev.event_id, prior.event_id, rel, confidence=decision.similarity)
                self._timeline.merge_from_prior(ev, prior)
                self._timeline.append(
                    ev,
                    update=summary[:300] or title,
                    source="evolution",
                    evolution_kind=decision.kind,
                )
                if decision.kind == EventEvolutionKind.SAME_EVENT:
                    ev.event_id = prior.event_id
                    prior.summary = summary or prior.summary
                    prior.importance_score = max(prior.importance_score, importance)
                    prior.updated_at = utc_now_iso()
                    prior.timeline = ev.timeline
                    self._nx.upsert_event(prior)
                    await self._apply_relations(prior.event_id, relations, entities)
                    return self._result_dict(prior, decision)
        else:
            self._timeline.append(ev, update=title[:200], source="new_event", evolution_kind=EventEvolutionKind.NEW_EVENT)

        self._nx.upsert_event(ev)
        await self._apply_relations(ev.event_id, relations, entities)
        return self._result_dict(ev, decision)

    async def _apply_relations(
        self,
        event_id: str,
        relations: list,
        entities: list[ExtractedEntity],
    ) -> None:
        name_to_id: dict[str, str] = {}
        for ext in entities:
            ent = self._nx.get_entity_by_name(ext.name, ext.entity_type.value)
            if ent:
                name_to_id[ext.name.lower()] = ent.entity_id
        for rel in relations:
            src_id = name_to_id.get(rel.source_name.lower())
            tgt_id = name_to_id.get(rel.target_name.lower())
            if not src_id or not tgt_id:
                continue
            self._nx.add_edge(
                EdgeRecord(
                    source=src_id,
                    target=tgt_id,
                    relation=rel.relation,
                    confidence=rel.confidence,
                    evidence=rel.evidence,
                )
            )

    def _entity_from_extracted(self, ext: ExtractedEntity) -> EntityNode:
        return EntityNode(
            entity_id="",
            name=ext.name,
            type=ext.entity_type,
            aliases=[],
            first_seen=utc_now_iso(),
            last_seen=utc_now_iso(),
        )

    def _build_entity_map(self, events: list[EventNode]) -> dict[str, set[str]]:
        out: dict[str, set[str]] = {}
        for ev in events:
            names: set[str] = set()
            for eid in ev.entities:
                for ent in self._nx._entity_nodes.values():
                    if ent.entity_id == eid:
                        names.add(ent.name.lower())
            out[ev.event_id] = names
        return out

    async def _embed_text(self, text: str) -> list[float] | None:
        t = truncate_for_embedding(text, 2000)
        timeout = float(self._timeouts.get("embedding_sec", 60))

        async def _run():
            async with httpx.AsyncClient(timeout=timeout) as client:
                batch = await fetch_embeddings_batch(
                    settings=self.settings,
                    inputs=[t],
                    client=client,
                )
                return batch[0] if batch else None

        try:
            return await _retry_async(
                _run,
                max_attempts=int(self._retries.get("max_attempts", 3)),
                backoff_sec=float(self._retries.get("backoff_sec", 1.5)),
                label="embedding",
            )
        except Exception:
            logger.warning("event embedding failed", exc_info=True)
            return None

    async def _flush_to_postgres(self) -> None:
        if not self._pg:
            return
        events = self._nx.list_events()
        edges: list[EdgeRecord] = []
        for u, v, k, data in self._nx.graph.edges(keys=True, data=True):
            try:
                rel = GraphEdgeType(str(data.get("relation", k)))
            except ValueError:
                continue
            edges.append(
                EdgeRecord(
                    source=u,
                    target=v,
                    relation=rel,
                    confidence=float(data.get("confidence", 0.5)),
                    source_kind=str(data.get("source_kind", "entity")),
                    target_kind=str(data.get("target_kind", "entity")),
                    evidence=str(data.get("evidence", "")),
                )
            )
        await _retry_async(
            lambda: self._pg.commit_batch(self._nx, events, edges),  # type: ignore[union-attr]
            max_attempts=int(self._retries.get("max_attempts", 3)),
            backoff_sec=float(self._retries.get("backoff_sec", 1.5)),
            label="postgres_commit",
        )

    @staticmethod
    def _result_dict(ev: EventNode, decision) -> dict[str, Any]:
        return {
            "event_id": ev.event_id,
            "external_event_id": ev.external_event_id,
            "evolution_kind": ev.evolution_kind.value,
            "matched_event_id": decision.matched_event_id,
            "similarity": decision.similarity,
            "entity_overlap": decision.entity_overlap,
            "timeline_len": len(ev.timeline),
        }

    def query_neighbors(self, node_id: str, relation: str | None = None) -> list[dict[str, Any]]:
        return [
            {"from": u, "to": v, **data}
            for u, v, data in self._nx.neighbors(node_id, relation=relation)
        ]

    def export_mock_visualization(self) -> dict[str, Any]:
        return self._nx.export_visualization()
