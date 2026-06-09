#!/usr/bin/env python3
"""Apply Event Graph PostgreSQL DDL."""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
SQL_PATH = ROOT / "sql" / "001_event_graph.sql"


def _database_url() -> str:
    url = (os.environ.get("EVENT_GRAPH_DATABASE_URL") or os.environ.get("EVENT_ENHANCEMENT_DATABASE_URL") or "").strip()
    if not url:
        raise SystemExit("Set EVENT_GRAPH_DATABASE_URL or EVENT_ENHANCEMENT_DATABASE_URL")
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


async def main() -> None:
    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
    except ImportError as exc:
        raise SystemExit("pip install sqlalchemy asyncpg") from exc

    sync_url = _database_url()
    async_url = sync_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    ddl = SQL_PATH.read_text(encoding="utf-8")
    engine = create_async_engine(async_url, echo=False)
    async with engine.begin() as conn:
        for stmt in ddl.split(";"):
            s = stmt.strip()
            if s and not s.startswith("--"):
                await conn.execute(text(s))
    await engine.dispose()
    logger.info("event graph schema applied from %s", SQL_PATH)


if __name__ == "__main__":
    asyncio.run(main())
