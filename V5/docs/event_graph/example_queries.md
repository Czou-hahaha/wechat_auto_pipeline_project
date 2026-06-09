# Event Graph — Example Queries

## Python (NetworkX in-process)

```python
from pathlib import Path
import asyncio
from src.config import Settings
from src.services.event_memory import EventMemoryService

async def main():
    svc = EventMemoryService(Settings())
    # Process demo event
    await svc.process_event_dict({
        "id": "demo-faa-bvlos",
        "title": "FAA BVLOS Rule aligns with Remote ID rollout",
        "summary_zh": "The FAA published BVLOS guidance. DJI and operators must comply with Remote ID. EHang competes with Joby Aviation in UAM.",
        "created_at": "2026-05-20T08:00:00+00:00",
        "importance_score": 75,
    })
    ev = svc._nx.list_events()[0]
    neighbors = svc.query_neighbors(ev.event_id)
    print(neighbors)

asyncio.run(main())
```

## SQL — policy evolution timeline

```sql
SELECT external_event_id, title, evolution_kind, jsonb_array_length(timeline) AS n_updates,
       timeline
FROM eg_events
WHERE title ILIKE '%BVLOS%' OR title ILIKE '%Remote ID%'
ORDER BY updated_at DESC
LIMIT 10;
```

## SQL — regulator → company edges

```sql
SELECT e1.canonical_name AS regulator, e2.canonical_name AS regulated, g.relation, g.confidence
FROM eg_edges g
JOIN eg_entities e1 ON e1.id = g.source_id
JOIN eg_entities e2 ON e2.id = g.target_id
WHERE g.relation = 'regulates'
ORDER BY g.confidence DESC;
```

## SQL — competing companies

```sql
SELECT e1.canonical_name AS a, e2.canonical_name AS b, g.confidence
FROM eg_edges g
JOIN eg_entities e1 ON e1.id = g.source_id
JOIN eg_entities e2 ON e2.id = g.target_id
WHERE g.relation = 'competes_with';
```

## SQL — event evolution chain

```sql
SELECT child.external_event_id AS child_id, parent.external_event_id AS parent_id, l.link_type, l.confidence
FROM eg_event_links l
JOIN eg_events child ON child.id = l.from_event_id
JOIN eg_events parent ON parent.id = l.to_event_id
WHERE l.link_type IN ('evolves_from', 'sub_event', 'escalation')
ORDER BY l.created_at DESC;
```

## SQL — trend: entities by last_seen

```sql
SELECT entity_type, canonical_name, last_seen
FROM eg_entities
WHERE entity_type IN ('policy', 'technology', 'company')
ORDER BY last_seen DESC
LIMIT 30;
```
