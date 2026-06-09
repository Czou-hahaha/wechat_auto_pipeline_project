"""Relationship extraction from text and co-mentioned entities."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from src.services.event_memory.schemas import (
    ExtractedEntity,
    ExtractedRelation,
    GraphEdgeType,
)

logger = logging.getLogger(__name__)

# Canonical pairs for domain examples
_STATIC_RELATIONS: list[tuple[str, str, GraphEdgeType, float]] = [
    ("FAA BVLOS Rule", "Remote ID", GraphEdgeType.RELATED_TO, 0.82),
    ("DJI", "FAA", GraphEdgeType.REGULATES, 0.88),  # stored as FAA regulates DJI when normalized
    ("EHang", "Joby Aviation", GraphEdgeType.COMPETES_WITH, 0.8),
]

_REGULATED_BY = re.compile(
    r"(?P<target>[\w\u4e00-\u9fff][\w\u4e00-\u9fff\s\-]{0,40}?)\s+"
    r"(?:is\s+)?regulated\s+by\s+(?P<source>[\w\u4e00-\u9fff][\w\u4e00-\u9fff\s\-]{0,40})",
    re.I,
)
_COMPETES = re.compile(
    r"(?P<a>[\w\u4e00-\u9fff][\w\u4e00-\u9fff\s\-]{0,40}?)\s+competes\s+with\s+"
    r"(?P<b>[\w\u4e00-\u9fff][\w\u4e00-\u9fff\s\-]{0,40})",
    re.I,
)
_IMPACTS = re.compile(
    r"(?P<a>[\w\u4e00-\u9fff][\w\u4e00-\u9fff\s\-]{0,40}?)\s+impacts?\s+"
    r"(?P<b>[\w\u4e00-\u9fff][\w\u4e00-\u9fff\s\-]{0,40})",
    re.I,
)


class RelationshipExtractor:
    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        ext = config.get("extraction") or {}
        self._min_conf = float(ext.get("min_edge_confidence", 0.5))
        self._patterns: list[tuple[re.Pattern[str], GraphEdgeType, float]] = []
        for item in config.get("relation_patterns") or []:
            if not isinstance(item, dict):
                continue
            pat = str(item.get("pattern", "")).strip()
            rel = str(item.get("relation", "related_to"))
            try:
                relation = GraphEdgeType(rel)
            except ValueError:
                relation = GraphEdgeType.RELATED_TO
            conf = float(item.get("confidence", 0.65))
            if pat:
                self._patterns.append((re.compile(pat, re.I | re.U), relation, conf))

    async def extract(
        self,
        text: str,
        entities: list[ExtractedEntity],
        *,
        timeout_sec: float = 15.0,
    ) -> list[ExtractedRelation]:
        return await asyncio.wait_for(
            asyncio.to_thread(self._extract_sync, text, entities),
            timeout=timeout_sec,
        )

    def _extract_sync(self, text: str, entities: list[ExtractedEntity]) -> list[ExtractedRelation]:
        relations: dict[tuple[str, str, str], ExtractedRelation] = {}
        names = {e.name for e in entities}
        name_lower = {e.name.lower(): e.name for e in entities}

        def add(src: str, tgt: str, rel: GraphEdgeType, conf: float, evidence: str = "") -> None:
            if conf < self._min_conf:
                return
            src_c = name_lower.get(src.lower(), src)
            tgt_c = name_lower.get(tgt.lower(), tgt)
            if rel == GraphEdgeType.REGULATES and src_c not in names and tgt_c in names:
                src_c, tgt_c = tgt_c, src_c
            key = (src_c.lower(), tgt_c.lower(), rel.value)
            relations[key] = ExtractedRelation(
                source_name=src_c,
                target_name=tgt_c,
                relation=rel,
                confidence=conf,
                evidence=evidence[:500],
            )

        for m in _REGULATED_BY.finditer(text):
            add(m.group("source"), m.group("target"), GraphEdgeType.REGULATES, 0.85, m.group(0))
        for m in _COMPETES.finditer(text):
            add(m.group("a"), m.group("b"), GraphEdgeType.COMPETES_WITH, 0.8, m.group(0))
        for m in _IMPACTS.finditer(text):
            add(m.group("a"), m.group("b"), GraphEdgeType.IMPACTS, 0.75, m.group(0))

        for regex, rel, conf in self._patterns:
            for m in regex.finditer(text):
                gd = m.groupdict()
                a = (gd.get("a") or "").strip()
                b = (gd.get("b") or "").strip()
                if a and b:
                    add(a, b, rel, conf, m.group(0))

        self._cooccurrence(entities, relations)
        self._static_domain(text, names, add)
        return list(relations.values())

    def _cooccurrence(
        self,
        entities: list[ExtractedEntity],
        relations: dict[tuple[str, str, str], ExtractedRelation],
    ) -> None:
        orgs = [e for e in entities if e.entity_type.value in ("organization", "company", "policy")]
        if len(orgs) < 2:
            return
        for i, a in enumerate(orgs):
            for b in orgs[i + 1 :]:
                key = (a.name.lower(), b.name.lower(), GraphEdgeType.RELATED_TO.value)
                if key not in relations:
                    relations[key] = ExtractedRelation(
                        source_name=a.name,
                        target_name=b.name,
                        relation=GraphEdgeType.RELATED_TO,
                        confidence=0.55,
                        evidence="co-occurrence",
                    )

    def _static_domain(self, text: str, names: set[str], add) -> None:
        blob = f"{text} {' '.join(names)}"
        for a, b, rel, conf in _STATIC_RELATIONS:
            if a.lower() in blob.lower() and b.lower() in blob.lower():
                if rel == GraphEdgeType.REGULATES:
                    add("FAA", "DJI", rel, conf, "domain:aviation-regulation")
                else:
                    add(a, b, rel, conf, "domain:static")
