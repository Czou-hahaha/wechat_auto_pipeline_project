"""PostgreSQL persistence for event graph (async SQLAlchemy)."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, Text, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from src.services.event_memory.schemas import EdgeRecord, EntityNode, EventNode, TimelineEntry

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class EgEvent(Base):
    __tablename__ = "eg_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_event_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="")
    importance_score: Mapped[int] = mapped_column(default=0)
    evolution_kind: Mapped[str] = mapped_column(String(32), default="new_event")
    parent_event_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("eg_events.id"), nullable=True)
    timeline: Mapped[list] = mapped_column(JSONB, default=list)
    embedding: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class EgEntity(Base):
    __tablename__ = "eg_entities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    aliases: Mapped[list] = mapped_column(JSONB, default=list)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    embedding: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)


class EgEdge(Base):
    __tablename__ = "eg_edges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    relation: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    evidence: Mapped[str] = mapped_column(Text, default="")


class EgTimelineEntry(Base):
    __tablename__ = "eg_timeline_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("eg_events.id", ondelete="CASCADE"))
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    update_text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, default="")


class PostgresGraphStore:
    def __init__(self, database_url: str) -> None:
        url = database_url.strip()
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif not url.startswith("postgresql+asyncpg://"):
            raise ValueError("EVENT_GRAPH_DATABASE_URL must be postgresql+asyncpg:// or postgresql://")
        self._engine = create_async_engine(url, echo=False, pool_pre_ping=True)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        self._id_map: dict[str, uuid.UUID] = {}  # graph string id -> pg uuid

    async def close(self) -> None:
        await self._engine.dispose()

    async def upsert_event(self, session: AsyncSession, ev: EventNode) -> uuid.UUID:
        ext = ev.external_event_id or ev.event_id
        row = await session.scalar(select(EgEvent).where(EgEvent.external_event_id == ext))
        tl = [t.to_dict() for t in ev.timeline]
        if row is None:
            row = EgEvent(
                external_event_id=ext,
                title=ev.title,
                summary=ev.summary,
                importance_score=ev.importance_score,
                evolution_kind=ev.evolution_kind.value,
                timeline=tl,
                embedding=ev.embedding,
            )
            if ev.parent_event_id and ev.parent_event_id in self._id_map:
                row.parent_event_id = self._id_map[ev.parent_event_id]
            session.add(row)
            await session.flush()
        else:
            row.title = ev.title
            row.summary = ev.summary
            row.importance_score = ev.importance_score
            row.evolution_kind = ev.evolution_kind.value
            row.timeline = tl
            row.embedding = ev.embedding
            row.updated_at = datetime.now(timezone.utc)
        self._id_map[ev.event_id] = row.id
        return row.id

    async def upsert_entity(self, session: AsyncSession, ent: EntityNode) -> uuid.UUID:
        row = await session.scalar(
            select(EgEntity).where(
                EgEntity.canonical_name == ent.name,
                EgEntity.entity_type == ent.type.value,
            )
        )
        if row is None:
            row = EgEntity(
                canonical_name=ent.name,
                entity_type=ent.type.value,
                aliases=ent.aliases,
                embedding=ent.embedding,
            )
            session.add(row)
            await session.flush()
        else:
            row.last_seen = datetime.now(timezone.utc)
            if ent.aliases:
                row.aliases = sorted(set(row.aliases or []) | set(ent.aliases))
        self._id_map[ent.entity_id] = row.id
        return row.id

    async def upsert_edge(self, session: AsyncSession, edge: EdgeRecord) -> None:
        src = self._id_map.get(edge.source)
        tgt = self._id_map.get(edge.target)
        if not src or not tgt:
            return
        existing = await session.scalar(
            select(EgEdge).where(
                EgEdge.source_id == src,
                EgEdge.target_id == tgt,
                EgEdge.relation == edge.relation.value,
            )
        )
        if existing:
            existing.confidence = max(existing.confidence, edge.confidence)
            return
        session.add(
            EgEdge(
                source_id=src,
                target_id=tgt,
                source_kind=edge.source_kind,
                target_kind=edge.target_kind,
                relation=edge.relation.value,
                confidence=edge.confidence,
                evidence=edge.evidence,
            )
        )

    async def append_timeline(self, session: AsyncSession, event_graph_id: uuid.UUID, entry: TimelineEntry) -> None:
        try:
            d = date.fromisoformat(entry.date)
        except ValueError:
            d = datetime.now(timezone.utc).date()
        session.add(
            EgTimelineEntry(
                event_id=event_graph_id,
                entry_date=d,
                update_text=entry.update,
                source=entry.source,
            )
        )

    async def list_events_for_evolution(self, session: AsyncSession, limit: int = 200) -> list[EventNode]:
        rows = (
            await session.scalars(select(EgEvent).order_by(EgEvent.updated_at.desc()).limit(limit))
        ).all()
        out: list[EventNode] = []
        for row in rows:
            gid = str(row.id)
            self._id_map[gid] = row.id
            tl = [TimelineEntry(**t) for t in (row.timeline or []) if isinstance(t, dict)]
            ev = EventNode(
                event_id=gid,
                external_event_id=row.external_event_id,
                title=row.title,
                summary=row.summary or "",
                importance_score=row.importance_score,
                created_at=row.created_at.isoformat(),
                updated_at=row.updated_at.isoformat(),
                timeline=tl,
                embedding=row.embedding if isinstance(row.embedding, list) else None,
            )
            out.append(ev)
        return out

    async def commit_batch(self, graph: Any, events: list[EventNode], edges: list[EdgeRecord]) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                for ev in events:
                    pg_id = await self.upsert_event(session, ev)
                    for entry in ev.timeline:
                        await self.append_timeline(session, pg_id, entry)
                for ent in graph._entity_nodes.values():
                    await self.upsert_entity(session, ent)
                for edge in edges:
                    await self.upsert_edge(session, edge)
        logger.info("postgres graph commit events=%d edges=%d", len(events), len(edges))
