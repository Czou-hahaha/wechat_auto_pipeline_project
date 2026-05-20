"""扩搜 plain phrase + GDELT 中文 query。"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_PKG = _REPO / "event_enhancement"
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

from event_enhancement.config_expansion import ExpansionConfig
from event_enhancement.gdelt.query import (
    build_expansion_plain_phrase,
    build_gdelt_query_strings,
    format_english_event_title,
    gdelt_chinese_query_from_plain,
    strip_gdelt_query_lang_suffix,
)


def test_plain_phrase_zh_event_name_plus_anchor() -> None:
    yaml_path = _REPO / "event_enhancement" / "config" / "expansion.yaml"
    exp = ExpansionConfig.from_path(yaml_path)
    long_title = "《北京市无人驾驶航空器管理规定》今年5月1日实施 对无人驾驶航空器飞行和销售运输存储作出新规定"
    plain = build_expansion_plain_phrase(
        event_title=long_title,
        anchor_terms=list(exp.anchor_terms),
        event_title_max_chars=exp.gdelt_event_title_max_chars,
        primary_anchor=exp.gdelt_primary_anchor,
        event_lang="zh",
    )
    assert "低空经济" in plain
    assert "《" not in plain and "》" not in plain
    assert " AND " not in plain
    assert plain.endswith("低空经济") or "低空经济" in plain


def test_plain_phrase_en_no_chinese_anchor() -> None:
    yaml_path = _REPO / "event_enhancement" / "config" / "expansion.yaml"
    exp = ExpansionConfig.from_path(yaml_path)
    title = (
        "FCC just saved millions of DJI drones from going obsolete after firmware dispute "
        "with regulators and industry groups"
    )
    plain = build_expansion_plain_phrase(
        event_title=title,
        anchor_terms=list(exp.anchor_terms),
        event_title_max_chars=exp.gdelt_event_title_max_chars,
        primary_anchor=exp.gdelt_primary_anchor,
        event_lang="en",
        max_english_words=exp.gdelt_event_title_max_words_en,
    )
    assert "低空经济" not in plain
    assert len(plain.split()) <= exp.gdelt_event_title_max_words_en
    assert "FCC" in plain


def test_format_english_event_title_merges_members() -> None:
    t = format_english_event_title(
        "FCC saves DJI drones",
        ["Autel also benefits from FCC ruling"],
        max_words=20,
    )
    assert "FCC" in t
    assert "Autel" in t
    assert len(t.split()) <= 20


def test_gdelt_query_list_matches_plain_text() -> None:
    yaml_path = _REPO / "event_enhancement" / "config" / "expansion.yaml"
    exp = ExpansionConfig.from_path(yaml_path)
    long_title = "《北京市无人驾驶航空器管理规定》今年5月1日实施"
    q = build_gdelt_query_strings(
        event_title=long_title,
        member_titles=[],
        anchor_terms=list(exp.anchor_terms),
        event_title_max_chars=exp.gdelt_event_title_max_chars,
        include_member_titles_in_query=False,
        max_or_terms=4,
        primary_anchor=exp.gdelt_primary_anchor,
    )
    assert len(q) == 1
    assert "sourcelang:" not in q[0]
    assert " OR " not in q[0]
    assert "低空经济" in q[0]


def test_strip_gdelt_lang_suffix() -> None:
    s = "北京市无人驾驶航空器管理规定 低空经济 sourcelang:chinese"
    assert strip_gdelt_query_lang_suffix(s) == "北京市无人驾驶航空器管理规定 低空经济"


def test_primary_anchor_override_plain() -> None:
    plain = build_expansion_plain_phrase(
        event_title="某事件标题很长用于截断测试内容",
        anchor_terms=["drone", "eVTOL"],
        event_title_max_chars=8,
        primary_anchor="低空经济",
        event_lang="zh",
    )
    assert plain.endswith("低空经济")
    assert "drone" not in plain


def test_gdelt_chinese_query_from_plain() -> None:
    assert gdelt_chinese_query_from_plain("a b") == "a b"
