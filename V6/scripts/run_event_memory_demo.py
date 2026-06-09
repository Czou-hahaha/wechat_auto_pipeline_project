#!/usr/bin/env python3
"""Demo: Event Graph Memory on sample aviation/policy text."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("event_memory_demo")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Event Graph Memory demo")
    parser.add_argument("--pg", action="store_true", help="Flush to PostgreSQL after run")
    args = parser.parse_args()

    from src.config import Settings
    from src.services.event_memory import EventMemoryService

    settings = Settings()
    if args.pg and not settings.event_graph_database_url:
        logger.error("Set EVENT_GRAPH_DATABASE_URL for --pg")
        sys.exit(1)

    svc = EventMemoryService(settings)
    samples = [
        {
            "id": "demo-faa-bvlos-1",
            "title": "FAA BVLOS Rule published alongside Remote ID requirements",
            "summary_zh": "The Federal Aviation Administration announced BVLOS operational guidance. Remote ID compliance is required. DJI is regulated by FAA policies.",
            "importance_score": 80,
        },
        {
            "id": "demo-uam-compete-1",
            "title": "EHang and Joby Aviation compete in urban air mobility",
            "summary_zh": "EHang expands eVTOL trials while Joby Aviation advances FAA certification. Both companies compete with in the UAM sector.",
            "importance_score": 65,
        },
    ]
    for row in samples:
        out = await svc.process_event_dict(row)
        logger.info("processed %s -> %s", row["id"], out)

    viz_path = ROOT / "data" / "event_graph" / "demo_visualization.json"
    viz = svc.export_mock_visualization()
    viz_path.write_text(json.dumps(viz, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("wrote visualization %s nodes=%d edges=%d", viz_path, len(viz.get("nodes", [])), len(viz.get("edges", [])))
    svc._nx.save()
    if svc._pg:
        await svc._flush_to_postgres()
        await svc._pg.close()
    print(json.dumps({"events": len(svc._nx.list_events()), "viz": str(viz_path)}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
