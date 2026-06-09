"""BFF 事件检索：统一打分。"""
from __future__ import annotations

from src.bff.event_search import event_search_score, filter_and_rank_events


def _row(**kwargs: object) -> dict:
    base = {
        "title": "",
        "summaryPreview": "",
        "keywords": [],
        "countries": [],
        "importance_score": 50,
        "createdAt": "2026-05-20",
    }
    base.update(kwargs)
    return base


def test_title_match_scores_higher_than_summary() -> None:
    a = _row(title="eVTOL 新规", summaryPreview="其他内容")
    b = _row(title="无关", summaryPreview="文中提到 eVTOL 试点")
    assert event_search_score(a, "evtol") > event_search_score(b, "evtol")


def test_keyword_match_included() -> None:
    r = _row(title="新闻", keywords=["低空经济", "无人机"])
    assert event_search_score(r, "低空经济") >= 70.0


def test_filter_and_rank_prefers_title_hit() -> None:
    rows = [
        _row(id="b", title="其他", summaryPreview="eVTOL 细节", importance_score=90),
        _row(id="a", title="eVTOL 政策", summaryPreview="", importance_score=10),
    ]
    out = filter_and_rank_events(rows, "evtol")
    assert out[0]["id"] == "a"
