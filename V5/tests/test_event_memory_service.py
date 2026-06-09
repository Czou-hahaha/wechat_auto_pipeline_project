"""Event Graph Memory unit tests (no embedding model required)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.services.event_memory.entity_extractor import EntityExtractor
from src.services.event_memory.evolution import EventEvolutionTracker
from src.services.event_memory.graph_store import NetworkXGraphStore
from src.services.event_memory.relationship_extractor import RelationshipExtractor
from src.services.event_memory.schemas import EventEvolutionKind, EventNode, GraphEdgeType, utc_now_iso


@pytest.fixture
def graph_config(tmp_path: Path) -> dict:
    cfg_path = tmp_path / "event_graph.json"
    cfg_path.write_text(
        json.dumps(
            {
                "ner_backend": "lexicon",
                "domain_lexicon": {
                    "organization": ["FAA", "CAAC"],
                    "company": ["DJI", "EHang", "Joby Aviation"],
                    "policy": ["BVLOS", "Remote ID"],
                },
                "evolution": {"same_event_threshold": 0.82, "continuation_threshold": 0.72},
            }
        ),
        encoding="utf-8",
    )
    return json.loads(cfg_path.read_text())


def test_entity_extractor_lexicon(graph_config: dict) -> None:
    ext = EntityExtractor(graph_config)
    text = "FAA BVLOS Rule requires Remote ID. DJI complies."
    entities = __import__("asyncio").run(ext.extract(text, timeout_sec=5))
    names = {e.name for e in entities}
    assert "FAA" in names
    assert "BVLOS" in names or "Remote ID" in names


def test_relationship_extractor_regulates(graph_config: dict) -> None:
    ext = EntityExtractor(graph_config)
    rel_ext = RelationshipExtractor(graph_config)
    text = "DJI is regulated by FAA. EHang competes with Joby Aviation."
    entities = __import__("asyncio").run(ext.extract(text, timeout_sec=5))
    relations = __import__("asyncio").run(rel_ext.extract(text, entities, timeout_sec=5))
    rel_types = {r.relation for r in relations}
    assert GraphEdgeType.REGULATES in rel_types or GraphEdgeType.COMPETES_WITH in rel_types


def test_evolution_same_event_threshold(graph_config: dict) -> None:
    tracker = EventEvolutionTracker(graph_config)
    emb = [1.0, 0.0, 0.0]
    prior = EventNode(
        event_id="p1",
        title="FAA BVLOS",
        summary="Remote ID rule",
        embedding=emb,
        created_at=utc_now_iso(),
    )
    cand = EventNode(
        event_id="c1",
        title="FAA BVLOS update",
        summary="Remote ID enforcement",
        embedding=emb,
        created_at=utc_now_iso(),
    )
    decision = tracker.classify(cand, {"faa", "bvlos", "remote id"}, [prior], {"p1": {"faa", "remote id"}})
    assert decision.kind == EventEvolutionKind.SAME_EVENT


def test_networkx_graph_store(tmp_path: Path) -> None:
    store = NetworkXGraphStore(tmp_path / "snap.json")
    from src.services.event_memory.schemas import EntityNode, GraphNodeType

    ent = EntityNode(entity_id="", name="FAA", type=GraphNodeType.ORGANIZATION)
    store.upsert_entity(ent)
    ev = EventNode(event_id="", title="BVLOS Rule", summary="test", external_event_id="ext-1")
    store.upsert_event(ev)
    store.link_event_entity(ev.event_id, ent.entity_id)
    store.save()
    store2 = NetworkXGraphStore(tmp_path / "snap.json")
    assert len(store2.list_events()) == 1
    assert store2.get_event_by_external_id("ext-1") is not None


def test_process_event_dict_mock_embed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from src.config import Settings
    from src.services.event_memory.event_memory_service import EventMemoryService

    settings = Settings(data_dir=str(tmp_path / "data"), event_graph_enabled=True)
    svc = EventMemoryService(settings)

    async def fake_embed(text: str):
        return [0.5, 0.5, 0.0]

    monkeypatch.setattr(svc, "_embed_text", fake_embed)

    async def _run():
        return await svc.process_event_dict(
            {
                "id": "test-evt-1",
                "title": "FAA BVLOS and Remote ID",
                "summary_zh": "DJI regulated by FAA. EHang competes with Joby Aviation.",
            }
        )

    out = asyncio.run(_run())
    assert out["external_event_id"] == "test-evt-1"
    assert out["timeline_len"] >= 1
    assert len(svc._nx.list_events()) >= 1
