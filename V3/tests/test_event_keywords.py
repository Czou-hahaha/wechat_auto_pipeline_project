"""事件关键词提取：完整词匹配，不按字数截断。"""
from __future__ import annotations

from src.bff.event_mapper import (
    _configured_search_terms,
    _extract_keywords,
    aggregate_hot_keywords,
    catalog_keywords_in_text,
)


def test_extract_keywords_full_phrase_not_truncated() -> None:
    ev = {
        "title": "北京市无人驾驶航空器管理规定与低空经济试点",
        "dominant_topic_key": "",
    }
    articles = [{"title": "无人机物流在城市空中交通中的应用"}]
    kws = _extract_keywords(ev, articles)
    assert "低空经济" in kws
    assert "无人机" in kws
    assert "延长外国制造" not in kws
    assert "豁免并强化禁" not in kws
    allow = {t.casefold() for t in _configured_search_terms()}
    assert all(k.casefold() in allow for k in kws)


def test_extract_keywords_english_term() -> None:
    ev = {"title": "FAA expands BVLOS drone rules", "dominant_topic_key": ""}
    kws = _extract_keywords(ev, [])
    assert "FAA" in kws or "BVLOS" in kws or "drone" in kws


def test_catalog_keywords_reject_title_fragments() -> None:
    blob = (
        "延长外国制造设备固件更新豁免并强化禁令权力无人机英国无人机监管简史"
        "从简洁安全到复杂风险"
    )
    hits = catalog_keywords_in_text(blob)
    assert hits == ["无人机"]
    assert "延长外国制造" not in hits


def test_aggregate_hot_keywords_only_catalog() -> None:
    enriched = [
        {
            "title": "FCC drone firmware waiver",
            "summaryPreview": "涉及无人机与低空经济监管",
            "summary": "",
        },
        {
            "title": "英国无人机监管简史",
            "summaryPreview": "延长外国制造设备固件更新",
            "summary": "",
        },
    ]
    hot = aggregate_hot_keywords(enriched)
    keys = {h["keyword"] for h in hot}
    assert "无人机" in keys
    assert not any("延长" in k or "豁免" in k for k in keys)
