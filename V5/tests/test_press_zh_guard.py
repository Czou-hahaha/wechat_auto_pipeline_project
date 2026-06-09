"""通稿中文门禁。"""
from __future__ import annotations

from src.ai import SummaryService


def test_skillsusa_press_sample_is_detected_non_cjk() -> None:
    body = (
        "University of Arkansas at Monticello College of Technology-Crossett "
        "(UAM-CTC) welding students earned five medals"
    )
    svc = SummaryService(api_key="", base_url="https://api.deepseek.com", model="deepseek-chat")
    assert svc._text_is_mostly_non_cjk(body) is True
