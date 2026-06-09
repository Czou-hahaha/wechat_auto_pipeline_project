"""GDELT query sanitization for long English titles."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_PKG = _REPO / "event_enhancement"
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

from event_enhancement.gdelt.query import limit_english_words


def test_limit_english_words_strips_em_dash() -> None:
    title = "Drone delivery — FAA approves new BVLOS routes in Texas"
    out = limit_english_words(title, 12)
    assert "—" not in out
    assert len(out.split()) <= 12


def test_limit_english_words_truncates() -> None:
    title = "One two three four five six seven eight nine ten eleven twelve thirteen"
    out = limit_english_words(title, 8)
    assert len(out.split()) == 8
