"""BFF event_mapper：扩搜增强字段。"""
from __future__ import annotations

from src.bff.event_mapper import event_to_intelligence


def test_event_intelligence_marks_expansion_articles() -> None:
    ev = {"id": "ev1", "title": "Test Event", "created_at": "2026-05-17T12:00:00+00:00"}
    articles = [
        {
            "id": "a1",
            "title": "Seed article",
            "source_url": "https://example.com/seed",
            "resolved_url": "https://example.com/seed",
            "status": "ready_for_review",
            "source_host": "example.com",
        },
        {
            "id": "a2",
            "title": "Expansion article",
            "source_url": "https://example.com/exp",
            "resolved_url": "https://example.com/exp",
            "status": "event_enhancement",
            "source_host": "news.com",
        },
    ]
    roles = {"https://example.com/seed": "primary", "https://example.com/exp": "support"}
    enh_row = {
        "_run_generated_at": "2026-05-17T15:00:00+00:00",
        "status": "success",
        "seed_article_count": 1,
        "articles_inserted": 1,
        "candidates_fetched": 10,
        "similarity_threshold": 0.7,
        "queries": ["test query"],
        "source_trace": [{"source": "ddgs", "query": "q", "attempts": 1, "hits": 5}],
        "urls_passed_similarity": [
            {"url": "https://example.com/exp", "title": "Expansion article", "similarity": 0.81}
        ],
    }
    dto = event_to_intelligence(ev, articles, url_roles=roles, enhancement_row=enh_row)
    assert dto["seed_article_count"] == 1
    assert dto["expansion_article_count"] == 1
    assert dto["enhancement"]["ran"] is True
    assert dto["enhancement"]["articlesInserted"] == 1
    kinds = {a["sourceKind"] for a in dto["articles"]}
    assert kinds == {"seed", "expansion"}
    types = {n["type"] for n in dto["timeline"]}
    assert "enhancement" in types
