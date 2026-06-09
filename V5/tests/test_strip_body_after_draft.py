"""草稿推送后清空 extracted_text。"""
from __future__ import annotations

from pathlib import Path

from src.storage import JsonStore


def test_clear_extracted_text_for_event(tmp_path: Path) -> None:
    store = JsonStore(tmp_path)
    rows = [
        {
            "id": "a1",
            "event_id": "ev1",
            "extracted_text": "正文甲" * 100,
            "summary": "摘要甲",
        },
        {
            "id": "a2",
            "event_id": "ev1",
            "extracted_text": "正文乙" * 100,
            "summary": "",
        },
        {
            "id": "a3",
            "event_id": "ev2",
            "extracted_text": "其他事件",
            "summary": "",
        },
    ]
    store._write(rows)
    assert store.clear_extracted_text_for_event("ev1") == 2
    all_rows = store.list_all()
    assert all_rows[0]["extracted_text"] == ""
    assert all_rows[0]["summary"] == "摘要甲"
    assert all_rows[1]["extracted_text"] == ""
    assert all_rows[2]["extracted_text"] == "其他事件"


def test_clear_extracted_text_for_article(tmp_path: Path) -> None:
    store = JsonStore(tmp_path)
    store._write(
        [
            {
                "id": "x1",
                "event_id": "",
                "extracted_text": "单篇正文",
                "summary": "单篇摘要",
            }
        ]
    )
    assert store.clear_extracted_text_for_article("x1") is True
    row = store.list_all()[0]
    assert row["extracted_text"] == ""
    assert row["summary"] == "单篇摘要"
    assert store.clear_extracted_text_for_article("x1") is False
