"""Tests for run_once phase timing helper."""
from __future__ import annotations

from src.utils.phase_timings import PhaseTimings


def test_phase_timings_finish() -> None:
    pt = PhaseTimings()
    pt.mark("ingest")
    pt.mark("cluster")
    pt.mark("done")
    payload = pt.finish()
    assert payload["total_sec"] >= 0
    assert "ingest" in payload["phases"]
    assert "cluster" in payload["phases"]
