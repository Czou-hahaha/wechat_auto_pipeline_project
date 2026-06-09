# Event Graph Schema

## Node types

| `type` | Description |
|--------|-------------|
| `event` | Clustered intelligence event |
| `entity` | Generic named entity |
| `organization` | Org / agency / NGO |
| `country` | Sovereign state or region |
| `policy` | Regulation, rule, standard |
| `technology` | Tech capability or product class |
| `company` | Commercial firm |

## Edge types

| `relation` | Semantics |
|------------|-----------|
| `related_to` | Thematic or causal association |
| `evolves_from` | New event/state derives from prior event |
| `announced_by` | Actor publishes policy/product |
| `impacts` | Subject affects object (market, sector) |
| `regulates` | Regulator → regulated entity/domain |
| `partners_with` | Cooperation |
| `competes_with` | Rivalry |
| `references` | Citation or dependency |
| `follows` | Temporal sequence (A after B) |

## EventNode (logical)

```json
{
  "event_id": "uuid",
  "title": "FAA BVLOS Rule",
  "summary": "...",
  "importance_score": 72,
  "created_at": "2026-05-20T08:00:00Z",
  "updated_at": "2026-05-21T10:00:00Z",
  "entities": ["entity-uuid-1"],
  "related_events": ["event-uuid-2"],
  "timeline": [
    {"date": "2026-05-20", "update": "Draft rule published", "source": "FAA"}
  ],
  "embedding": [0.01, 0.02]
}
```

## EntityNode

```json
{
  "entity_id": "uuid",
  "name": "FAA",
  "type": "organization",
  "aliases": ["Federal Aviation Administration"],
  "first_seen": "2026-05-01T00:00:00Z",
  "last_seen": "2026-05-21T10:00:00Z"
}
```

## Edge

```json
{
  "source": "entity-id-dji",
  "target": "entity-id-faa",
  "relation": "regulated_by",
  "confidence": 0.85,
  "created_at": "2026-05-20T12:00:00Z"
}
```

Note: storage uses canonical direction; `regulated_by` is stored as `regulates` with inverted source/target when normalizing.

## Evolution classification

| `evolution_kind` | Meaning |
|------------------|---------|
| `new_event` | No strong prior match |
| `same_event` | Embedding ≥ same threshold |
| `continuation` | Same storyline, new development |
| `sub_event` | Child development under parent |
| `escalation` | Severity/importance step-up |
