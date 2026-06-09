"""簇摘要 prompt 载荷。"""
from __future__ import annotations

from src.utils.cluster_summary_payload import build_cluster_summary_items


def test_caps_sources_and_includes_url() -> None:
    rows = [
        {
            "title": f"稿{i}",
            "extracted_text": "x" * 3000,
            "source_url": f"https://example.com/{i}",
            "resolved_url": f"https://example.com/{i}",
            "source_host": "example.com",
        }
        for i in range(8)
    ]
    items = build_cluster_summary_items(rows, max_sources=5, excerpt_chars=500)
    assert len(items) == 5
    assert "链接：https://example.com/" in items[0]["text"]
    assert len(items[0]["text"]) < 700
