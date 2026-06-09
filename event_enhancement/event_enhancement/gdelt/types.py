"""GDELT DOC API hit row (standalone, no V3 dependency)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GdeltHit:
    title: str
    url: str
    snippet: str
    published_at: str
    domain: str
