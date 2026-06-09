# Event Graph Memory System (V4)

Temporal event memory for the AI Industry Intelligence Platform — **event-first**, not article-first.

## Capabilities

| Capability | Module |
|------------|--------|
| Long-running event detection | `evolution.py` |
| Entity & relationship tracking | `entity_extractor.py`, `relationship_extractor.py` |
| Timeline persistence | `timeline.py` + PostgreSQL JSONB |
| Trend / policy evolution | graph queries + timeline |
| Semantic retrieval prep | event/entity embeddings in `eg_events` / `eg_entities` |

## Directory layout

```
V4/
├── config/event_graph.json          # thresholds, NER backend, relation patterns
├── docs/event_graph/
│   ├── README.md                    # this file
│   ├── schema.md                    # graph node/edge JSON schema
│   ├── postgresql_schema.sql        # DDL (also under sql/)
│   └── example_queries.md           # SQL + Python examples
├── sql/001_event_graph.sql
├── data/event_graph/
│   ├── graph_snapshot.json          # NetworkX export (JSON mode)
│   └── mock_visualization.json      # UI mock nodes/edges
├── src/services/event_memory/
│   ├── event_memory_service.py      # orchestrator
│   ├── schemas.py
│   ├── entity_extractor.py
│   ├── relationship_extractor.py
│   ├── evolution.py
│   ├── timeline.py
│   ├── graph_store.py               # NetworkX V1
│   └── postgres_store.py
└── scripts/init_event_graph_db.py
    scripts/run_event_memory_demo.py
```

## Quick start

```bash
cd V4
# JSON-only (no PostgreSQL):
export EVENT_GRAPH_ENABLED=true
export EVENT_GRAPH_DATABASE_URL=
python scripts/run_event_memory_demo.py

# PostgreSQL:
export EVENT_GRAPH_DATABASE_URL='postgresql+asyncpg://user:pass@127.0.0.1:5432/intel'
python scripts/init_event_graph_db.py
python scripts/run_event_memory_demo.py --pg
```

## Pipeline hook

After `run_once` writes `events.json`, `EventMemoryService.process_events_from_store()` runs when `EVENT_GRAPH_ENABLED=true`.

## Evolution thresholds (default)

| Similarity | Decision |
|------------|----------|
| ≥ 0.82 | `same_event` (link + timeline append) |
| ≥ 0.72 | check entity/action/time → `continuation` / `sub_event` / `escalation` |
| &lt; 0.72 | `new_event` |

Configure in `config/event_graph.json` or env `EVENT_GRAPH_*`.
