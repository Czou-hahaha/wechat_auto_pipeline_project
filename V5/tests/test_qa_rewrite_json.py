from __future__ import annotations

from src.services.qa_rewrite.json_utils import extract_first_json_object, strip_code_fence
from src.services.qa_rewrite.qa_service import parse_qa_payload


def test_strip_code_fence_json() -> None:
    raw = "```json\n{\"a\": 1}\n```"
    assert strip_code_fence(raw).startswith("{")


def test_extract_first_json_object_with_prefix_noise() -> None:
    text = '说明\n```\n{"score": 82, "approved": true, "hallucination": false, "issues": [], "missing_points": [], "rewrite_suggestions": []}\n```'
    data = extract_first_json_object(text)
    assert data is not None
    assert data["score"] == 82


def test_parse_qa_payload_coercion() -> None:
    r = parse_qa_payload(
        {
            "score": "77",
            "approved": "false",
            "hallucination": 0,
            "issues": [{"type": "tone", "severity": "low", "description": "套话"}],
            "missing_points": ["关键时间未交代"],
            "rewrite_suggestions": ["删重复段"],
        }
    )
    assert r.score == 77
    assert r.approved is False
    assert r.hallucination is False
    assert len(r.issues) == 1
    assert r.issues[0].type == "tone"
