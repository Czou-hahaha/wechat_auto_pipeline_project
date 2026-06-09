"""JSON-serializable DTOs for the platform API."""

from __future__ import annotations

from typing import Any

# Types are plain dicts for FastAPI JSON responses; kept as documentation aliases.
EventIntelligenceDict = dict[str, Any]
EventListItemDict = dict[str, Any]
DashboardDict = dict[str, Any]
