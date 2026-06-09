from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient


def _seed_minimal_data(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "articles.json").write_text(
        json.dumps(
            [
                {
                    "id": "art_1",
                    "event_id": "evt_1",
                    "title": "低空经济示例稿",
                    "source_url": "https://example.com/a",
                    "resolved_url": "https://example.com/a",
                    "summary": "示例摘要",
                    "source_published_at": "2026-06-02T12:00:00+00:00",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (data_dir / "events.json").write_text(
        json.dumps(
            [
                {
                    "id": "evt_1",
                    "title": "低空经济事件",
                    "event_press_qa_score": 86,
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (data_dir / "event_article_map.json").write_text("[]", encoding="utf-8")


def test_mvp_feedback_and_map_endpoints(tmp_path, monkeypatch) -> None:
    _seed_minimal_data(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    from src.bff.app import app

    client = TestClient(app)

    map_resp = client.get("/api/events/evt_1/map")
    assert map_resp.status_code == 200
    map_body = map_resp.json()
    assert map_body["eventId"] == "evt_1"
    assert map_body["nodeCount"] >= 2

    history_resp = client.get("/api/events/evt_1/history")
    assert history_resp.status_code == 200
    assert history_resp.json()["eventId"] == "evt_1"

    feedback_resp = client.post(
        "/api/feedback",
        json={
            "eventId": "evt_1",
            "stage": "qa",
            "category": "factual_error",
            "note": "timeline needs correction",
        },
    )
    assert feedback_resp.status_code == 200
    assert feedback_resp.json()["ok"] is True

    summary_resp = client.get("/api/feedback/summary")
    assert summary_resp.status_code == 200
    assert summary_resp.json()["total"] == 1

    discover_resp = client.post("/api/sources/discover")
    assert discover_resp.status_code == 200
    assert discover_resp.json()["total"] >= 1

    prompt_contract = client.get("/api/prompts/contract")
    assert prompt_contract.status_code == 200
    assert "contract" in prompt_contract.json()

    prompt_preview = client.get("/api/prompts/preview")
    assert prompt_preview.status_code == 200
    assert "systemPreview" in prompt_preview.json()
