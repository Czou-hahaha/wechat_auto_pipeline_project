"""Structured phase timings for run_once (V6)."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PhaseTimings:
    phases: dict[str, float] = field(default_factory=dict)
    _marks: dict[str, float] = field(default_factory=dict)
    _started: float = field(default_factory=perf_counter)

    def mark(self, name: str) -> None:
        now = perf_counter()
        if self._marks:
            last_name, last_t = next(reversed(self._marks.items()))
            self.phases[last_name] = round(now - last_t, 2)
        self._marks[name] = now

    def finish(self) -> dict[str, Any]:
        if self._marks:
            last_name, last_t = next(reversed(self._marks.items()))
            self.phases[last_name] = round(perf_counter() - last_t, 2)
        total = round(perf_counter() - self._started, 2)
        payload = {"total_sec": total, "phases": dict(self.phases)}
        logger.info("run_once phase_timings %s", json.dumps(payload, ensure_ascii=False))
        return payload
