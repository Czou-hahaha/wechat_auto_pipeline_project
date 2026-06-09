"""扩搜语言路由：中文跳过 GDELT，英文使用简短纯文本 query。"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_PKG = _REPO / "event_enhancement"
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

from event_enhancement.config_expansion import ExpansionConfig
from event_enhancement.expansion_cascade import expansion_sources_for_event_lang
from event_enhancement.gdelt.query import gdelt_english_query_from_plain, gdelt_query_from_plain
from event_enhancement.lang_detect import detect_event_expansion_lang


def _exp() -> ExpansionConfig:
    return ExpansionConfig.from_path(_REPO / "event_enhancement" / "config" / "expansion.yaml")


def test_detect_zh_from_cjk_title_and_body() -> None:
    lang = detect_event_expansion_lang(
        event_title="哈萨克斯坦开通低空出租车航线",
        member_articles=[
            {
                "title": "主稿",
                "extracted_text": "据当地媒体报道，低空经济试点城市将扩大运营范围。",
                "status": "ready_for_review",
            }
        ],
        cjk_threshold=0.15,
    )
    assert lang == "zh"


def test_detect_en_from_english_title() -> None:
    lang = detect_event_expansion_lang(
        event_title="UK approves SORA framework for drone operations",
        member_articles=[
            {
                "title": "Primary",
                "extracted_text": "The Civil Aviation Authority published new guidance for operators.",
                "status": "ready_for_review",
            }
        ],
        cjk_threshold=0.15,
    )
    assert lang == "en"


def test_zh_event_sources_skip_gdelt() -> None:
    exp = _exp()
    order = expansion_sources_for_event_lang("zh", exp)
    assert order == ("google_rss", "ddgs")
    assert "gdelt" not in order


def test_en_event_sources_include_gdelt_when_enabled() -> None:
    exp = _exp()
    order = expansion_sources_for_event_lang("en", exp)
    assert order == ("gdelt", "google_rss", "ddgs")


def test_en_event_sources_skip_gdelt_when_disabled() -> None:
    from dataclasses import replace

    exp = replace(_exp(), expansion_gdelt_en_enabled=False)
    order = expansion_sources_for_event_lang("en", exp)
    assert order == ("google_rss", "ddgs")
    assert "gdelt" not in order


def test_gdelt_plain_query_no_sourcelang() -> None:
    q = gdelt_english_query_from_plain("drone regulation UK")
    assert q == "drone regulation UK"
    assert gdelt_query_from_plain("drone", lang="en") == "drone"
    assert gdelt_query_from_plain("低空", lang="zh") == "低空"
