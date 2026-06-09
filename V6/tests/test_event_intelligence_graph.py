"""Tests for unified event intelligence graph API."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.config import Settings
from src.services.event_intelligence_graph.service import build_event_intelligence_graph
from src.storage import JsonStore


@pytest.fixture
def demo_store(tmp_path: Path) -> JsonStore:
    demo = Path(__file__).resolve().parents[1] / "data" / "demo"
    if not (demo / "events.json").is_file():
        pytest.skip("demo data missing")
    store = JsonStore(tmp_path)
    import shutil

    for name in ("events.json", "articles.json", "event_article_map.json"):
        shutil.copy(demo / name, tmp_path / name)
    return store


def test_build_event_intelligence_graph_shape(demo_store: JsonStore) -> None:
    events = demo_store.list_events()
    assert events
    eid = str(events[0].get("id") or "")
    payload = build_event_intelligence_graph(demo_store, eid, settings=Settings(data_dir=str(demo_store.data_dir)))
    assert payload["eventId"] == eid
    assert "map" in payload
    assert "graph" in payload
    assert "history" in payload
    assert "memory" in payload
    assert "visualization" in payload
    assert "eventGraph" in payload
    eg = payload.get("eventGraph") or {}
    nodes = eg.get("nodes") or []
    assert any(n.get("type") == "event" for n in nodes)
    assert all(n.get("type") != "article" for n in nodes)


def test_build_event_intelligence_graph_missing_event(demo_store: JsonStore) -> None:
    with pytest.raises(ValueError, match="not found"):
        build_event_intelligence_graph(demo_store, "missing-event-id")
