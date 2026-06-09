"""Entity extraction: domain lexicon + optional GLiNER/spaCy."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from src.services.event_memory.schemas import ExtractedEntity, GraphNodeType, normalize_entity_type

logger = logging.getLogger(__name__)

_ORG_SUFFIX = re.compile(
    r"\b([A-Z][A-Za-z0-9&\-\.]{1,48}(?:\s+[A-Z][A-Za-z0-9&\-\.]{1,24}){0,4})\s+"
    r"(Inc\.|Corp\.|Ltd\.|LLC|Aviation|Group|科技|公司|集团)\b"
)
_CJK_ORG = re.compile(r"[\u4e00-\u9fff]{2,12}(?:局|部|委|公司|集团|航空)")


class EntityExtractor:
    """Extract entities from event title + summary (+ optional article bodies)."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        ext = config.get("extraction") or {}
        self._min_conf = float(ext.get("min_entity_confidence", 0.55))
        self._max_entities = int(ext.get("max_entities_per_event", 40))
        self._backend = str(config.get("ner_backend", "lexicon")).strip().lower()
        self._lexicon: dict[str, list[str]] = {}
        raw_lex = config.get("domain_lexicon") or {}
        for k, vals in raw_lex.items():
            if isinstance(vals, list):
                self._lexicon[k] = [str(v).strip() for v in vals if str(v).strip()]

    async def extract(
        self,
        text: str,
        *,
        timeout_sec: float = 15.0,
    ) -> list[ExtractedEntity]:
        return await asyncio.wait_for(
            asyncio.to_thread(self._extract_sync, text),
            timeout=timeout_sec,
        )

    def _extract_sync(self, text: str) -> list[ExtractedEntity]:
        if not (text or "").strip():
            return []
        found: dict[tuple[str, str], ExtractedEntity] = {}
        self._from_lexicon(text, found)
        self._from_regex(text, found)
        if self._backend == "gliner":
            self._from_gliner(text, found)
        elif self._backend == "spacy":
            self._from_spacy(text, found)
        out = sorted(found.values(), key=lambda e: (-e.confidence, e.name))
        return out[: self._max_entities]

    def _from_lexicon(self, text: str, found: dict[tuple[str, str], ExtractedEntity]) -> None:
        lower = text.lower()
        for type_key, names in self._lexicon.items():
            et = normalize_entity_type(type_key)
            for name in names:
                if not name:
                    continue
                if name.lower() in lower or name in text:
                    key = (name.lower(), et.value)
                    conf = 0.9 if len(name) >= 3 else 0.7
                    found[key] = ExtractedEntity(name=name, entity_type=et, confidence=conf)

    def _from_regex(self, text: str, found: dict[tuple[str, str], ExtractedEntity]) -> None:
        for m in _ORG_SUFFIX.finditer(text):
            name = f"{m.group(1)} {m.group(2)}".strip()
            key = (name.lower(), GraphNodeType.COMPANY.value)
            found[key] = ExtractedEntity(name=name, entity_type=GraphNodeType.COMPANY, confidence=0.65)
        for m in _CJK_ORG.finditer(text):
            name = m.group(0).strip()
            et = GraphNodeType.ORGANIZATION if "局" in name or "部" in name else GraphNodeType.COMPANY
            key = (name.lower(), et.value)
            found[key] = ExtractedEntity(name=name, entity_type=et, confidence=0.68)

    def _from_gliner(self, text: str, found: dict[tuple[str, str], ExtractedEntity]) -> None:
        try:
            from gliner import GLiNER  # type: ignore
        except ImportError:
            logger.debug("gliner not installed; skip")
            return
        labels = ["organization", "company", "policy", "technology", "country"]
        model = GLiNER.from_pretrained("urchade/gliner_medium-v2.1")
        for ent in model.predict_entities(text, labels, threshold=self._min_conf):
            name = str(ent.get("text", "")).strip()
            if not name:
                continue
            label = str(ent.get("label", "entity"))
            et = normalize_entity_type(label)
            key = (name.lower(), et.value)
            found[key] = ExtractedEntity(
                name=name,
                entity_type=et,
                confidence=float(ent.get("score", 0.6)),
            )

    def _from_spacy(self, text: str, found: dict[tuple[str, str], ExtractedEntity]) -> None:
        try:
            import spacy  # type: ignore
        except ImportError:
            logger.debug("spacy not installed; skip")
            return
        try:
            nlp = spacy.load("en_core_web_sm")
        except OSError:
            logger.warning("spacy model en_core_web_sm missing")
            return
        doc = nlp(text[:100_000])
        label_map = {
            "ORG": GraphNodeType.ORGANIZATION,
            "GPE": GraphNodeType.COUNTRY,
            "PRODUCT": GraphNodeType.TECHNOLOGY,
        }
        for ent in doc.ents:
            if ent.label_ not in label_map:
                continue
            name = ent.text.strip()
            if len(name) < 2:
                continue
            et = label_map[ent.label_]
            key = (name.lower(), et.value)
            found[key] = ExtractedEntity(name=name, entity_type=et, confidence=0.72)
