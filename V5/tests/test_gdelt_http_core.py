"""GDELT timespan cap and http_core helpers."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_PKG = _REPO / "event_enhancement"
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

from src.gdelt_search import gdelt_timespan_for_hours, resolve_gdelt_timespan


def test_timespan_never_7d() -> None:
    assert gdelt_timespan_for_hours(168) == "24h"
    assert gdelt_timespan_for_hours(72) == "24h"
    assert gdelt_timespan_for_hours(1) == "1h"


def test_resolve_explicit_timespan() -> None:
    assert resolve_gdelt_timespan(explicit="1h", max_article_age_hours=48) == "1h"
    assert resolve_gdelt_timespan(explicit="", max_article_age_hours=6) == "6h"
