"""BFF 列表 IMP 与 pipeline 对齐、离题事件压低。"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_PKG = _REPO / "event_enhancement"
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

from src.bff.event_mapper import _importance_score


def test_war_drone_event_importance_capped() -> None:
    ev = {
        "title": "Europe faces stray Ukrainian drones as Kyiv targets Russian oil exports",
        "title_zh": "基辅打击俄石油出口　欧洲遭乌无人机误入",
        "event_press_zh": "乌克兰无人机在打击俄罗斯石油出口设施的过程中偏航进入北约领土。",
        "event_press_qa_score": 85,
    }
    articles = [{"title": "Ukraine drone war", "source_host": "reuters.com"}] * 6
    score = _importance_score(ev, articles)
    assert score <= 12


def test_skillsusa_importance_not_inflated_by_qa() -> None:
    ev = {
        "title": "Five UAM-CTC Welding Students dominate at 2026 SkillsUSA",
        "event_press_zh": "University welding students earned medals at SkillsUSA.",
        "event_press_qa_score": 95,
    }
    articles = [{"title": ev["title"], "source_host": "stuttgartdailyleader.com"}]
    score = _importance_score(ev, articles)
    assert score <= 12


def test_policy_drone_event_importance_reasonable() -> None:
    ev = {
        "title": "FCC extends firmware waiver for DJI drones on Covered List",
        "summary": "低空无人机监管政策更新，涉及 DJI 与 Autel 固件豁免。",
    }
    articles = [
        {
            "title": "FCC DA 26-454 drone firmware",
            "source_host": "faa.gov",
            "source_published_at": "2026-05-20T08:00:00+00:00",
        }
    ]
    score = _importance_score(ev, articles)
    assert score >= 40


def test_stale_multi_article_not_flat_20() -> None:
    """数天前的多稿事件不应全部挤在 20 分。"""
    ev = {
        "title": "ACSL Draganfly Canada",
        "summary": "日本无人机制造商与加拿大分销商合作。",
        "event_press_generated_at": "2026-05-17T15:31:33+00:00",
        "event_press_zh": "日本无人机制造商ACSL与Draganfly签署协议。",
    }
    articles = [
        {
            "title": "ACSL SOTEN Canada",
            "source_host": "dronedj.com",
            "source_published_at": "2026-05-11T08:27:07+00:00",
            "topic_is_important": True,
        },
        {"title": "support", "source_host": "autelpilot.com", "source_published_at": "2026-05-12T00:00:00+00:00"},
    ]
    score = _importance_score(ev, articles)
    assert score > 28
