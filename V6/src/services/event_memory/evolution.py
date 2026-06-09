"""Event evolution classification via embedding + entity/action overlap."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.embed_dedupe import cosine_similarity
from src.services.event_memory.schemas import EventEvolutionKind, EventNode

logger = logging.getLogger(__name__)

_ACTION_VERBS = re.compile(
    r"\b(announce|publish|approve|ban|restrict|launch|partner|acquire|raise|file|rule|规定|发布|批准|禁止|合作)\w*\b",
    re.I,
)


@dataclass
class EvolutionDecision:
    kind: EventEvolutionKind
    matched_event_id: str | None
    similarity: float
    entity_overlap: float
    action_overlap: float
    reason: str


class EventEvolutionTracker:
    def __init__(self, config: dict[str, Any]) -> None:
        evo = config.get("evolution") or {}
        self._same_threshold = float(evo.get("same_event_threshold", 0.82))
        self._cont_threshold = float(evo.get("continuation_threshold", 0.72))
        self._entity_min = float(evo.get("entity_overlap_min", 0.35))
        self._action_min = float(evo.get("action_overlap_min", 0.25))
        self._max_days = int(evo.get("max_days_continuation", 30))

    def classify(
        self,
        candidate: EventNode,
        candidate_entities: set[str],
        history: list[EventNode],
        history_entity_map: dict[str, set[str]],
    ) -> EvolutionDecision:
        if not history or not candidate.embedding:
            return EvolutionDecision(
                kind=EventEvolutionKind.NEW_EVENT,
                matched_event_id=None,
                similarity=0.0,
                entity_overlap=0.0,
                action_overlap=0.0,
                reason="no_history_or_embedding",
            )

        best_id: str | None = None
        best_sim = 0.0
        best_entity_ov = 0.0
        best_action_ov = 0.0

        cand_actions = _extract_actions(f"{candidate.title} {candidate.summary}")
        cand_time = _parse_dt(candidate.created_at)

        for prior in history:
            if not prior.embedding or prior.event_id == candidate.event_id:
                continue
            sim = cosine_similarity(candidate.embedding, prior.embedding)
            if sim <= best_sim:
                continue
            prior_entities = history_entity_map.get(prior.event_id, set())
            ent_ov = _jaccard(candidate_entities, prior_entities)
            act_ov = _jaccard(cand_actions, _extract_actions(f"{prior.title} {prior.summary}"))
            if not _time_ok(cand_time, _parse_dt(prior.updated_at or prior.created_at), self._max_days):
                continue
            best_sim = sim
            best_id = prior.event_id
            best_entity_ov = ent_ov
            best_action_ov = act_ov

        if best_sim >= self._same_threshold:
            return EvolutionDecision(
                kind=EventEvolutionKind.SAME_EVENT,
                matched_event_id=best_id,
                similarity=best_sim,
                entity_overlap=best_entity_ov,
                action_overlap=best_action_ov,
                reason="embedding>=same_threshold",
            )

        if best_sim >= self._cont_threshold:
            if best_entity_ov >= self._entity_min or best_action_ov >= self._action_min:
                kind = EventEvolutionKind.ESCALATION if _is_escalation(candidate, best_action_ov) else EventEvolutionKind.CONTINUATION
                if best_entity_ov >= 0.55 and best_sim < self._same_threshold:
                    kind = EventEvolutionKind.SUB_EVENT
                return EvolutionDecision(
                    kind=kind,
                    matched_event_id=best_id,
                    similarity=best_sim,
                    entity_overlap=best_entity_ov,
                    action_overlap=best_action_ov,
                    reason="embedding>=continuation_threshold+overlap",
                )

        return EvolutionDecision(
            kind=EventEvolutionKind.NEW_EVENT,
            matched_event_id=None,
            similarity=best_sim,
            entity_overlap=best_entity_ov,
            action_overlap=best_action_ov,
            reason="below_continuation_threshold",
        )

def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _extract_actions(text: str) -> set[str]:
    return {m.group(0).lower() for m in _ACTION_VERBS.finditer(text or "")}


def _parse_dt(iso: str) -> datetime | None:
    s = (iso or "").strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _is_escalation(candidate: EventNode, action_overlap: float) -> bool:
    text = f"{candidate.title} {candidate.summary}".lower()
    markers = ("ban", "emergency", "crackdown", "禁止", "紧急", "全面")
    return any(m in text for m in markers) and action_overlap >= 0.2


def _time_ok(cand: datetime | None, prior: datetime | None, max_days: int) -> bool:
    if not cand or not prior:
        return True
    return abs((cand - prior).total_seconds()) / 86400.0 <= max_days
