"""Timeline append logic for event evolution."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.services.event_memory.schemas import EventEvolutionKind, EventNode, TimelineEntry, utc_now_iso

logger = logging.getLogger(__name__)


def _today_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class TimelineService:
    """Maintain per-event chronological updates."""

    def initial_entry(self, event: EventNode, *, source: str = "ingest") -> TimelineEntry:
        snippet = (event.summary or event.title or "").strip()
        if len(snippet) > 240:
            snippet = snippet[:237] + "..."
        return TimelineEntry(date=_today_date(), update=snippet or event.title, source=source)

    def append(
        self,
        event: EventNode,
        *,
        update: str,
        source: str = "",
        entry_date: str | None = None,
        evolution_kind: EventEvolutionKind | None = None,
    ) -> TimelineEntry:
        entry = TimelineEntry(
            date=entry_date or _today_date(),
            update=(update or "").strip() or "Graph memory update",
            source=source or "event_memory",
        )
        if evolution_kind and evolution_kind != EventEvolutionKind.NEW_EVENT:
            entry.update = f"[{evolution_kind.value}] {entry.update}"
        event.timeline.append(entry)
        event.updated_at = utc_now_iso()
        logger.info(
            "timeline append event_id=%s date=%s kind=%s",
            event.event_id[:8],
            entry.date,
            evolution_kind.value if evolution_kind else "n/a",
        )
        return entry

    def merge_from_prior(self, target: EventNode, prior: EventNode) -> None:
        seen = {(t.date, t.update) for t in target.timeline}
        for t in prior.timeline:
            key = (t.date, t.update)
            if key not in seen:
                target.timeline.append(t)
                seen.add(key)
        target.timeline.sort(key=lambda x: x.date)
