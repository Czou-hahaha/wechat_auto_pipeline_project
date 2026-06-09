-- Event Graph Memory System — PostgreSQL DDL (V4)
-- Apply: psql $DATABASE_URL -f sql/001_event_graph.sql
-- Or: python scripts/init_event_graph_db.py

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Events (temporal memory nodes)
CREATE TABLE IF NOT EXISTS eg_events (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    external_event_id   TEXT NOT NULL UNIQUE,  -- V3 events.json id
    title               TEXT NOT NULL,
    summary             TEXT NOT NULL DEFAULT '',
    importance_score    INTEGER NOT NULL DEFAULT 0,
    evolution_kind      TEXT NOT NULL DEFAULT 'new_event',
    parent_event_id     UUID REFERENCES eg_events(id) ON DELETE SET NULL,
    timeline            JSONB NOT NULL DEFAULT '[]'::jsonb,
    embedding           JSONB,  -- float[] serialized
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_eg_events_external ON eg_events(external_event_id);
CREATE INDEX IF NOT EXISTS idx_eg_events_parent ON eg_events(parent_event_id);
CREATE INDEX IF NOT EXISTS idx_eg_events_updated ON eg_events(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_eg_events_timeline ON eg_events USING GIN (timeline);

-- Entities (organizations, policies, companies, …)
CREATE TABLE IF NOT EXISTS eg_entities (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    canonical_name  TEXT NOT NULL,
    entity_type     TEXT NOT NULL,  -- event|entity|organization|country|policy|technology|company
    aliases         JSONB NOT NULL DEFAULT '[]'::jsonb,
    first_seen      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    embedding       JSONB,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (canonical_name, entity_type)
);

CREATE INDEX IF NOT EXISTS idx_eg_entities_type ON eg_entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_eg_entities_name ON eg_entities(canonical_name);

-- Event ↔ entity membership
CREATE TABLE IF NOT EXISTS eg_event_entities (
    event_id    UUID NOT NULL REFERENCES eg_events(id) ON DELETE CASCADE,
    entity_id   UUID NOT NULL REFERENCES eg_entities(id) ON DELETE CASCADE,
    role        TEXT NOT NULL DEFAULT 'mentioned',
    confidence  REAL NOT NULL DEFAULT 1.0,
    PRIMARY KEY (event_id, entity_id)
);

-- Directed edges (graph relations)
CREATE TABLE IF NOT EXISTS eg_edges (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id   UUID NOT NULL,
    target_id   UUID NOT NULL,
    source_kind TEXT NOT NULL,  -- event | entity
    target_kind TEXT NOT NULL,
    relation    TEXT NOT NULL,
    confidence  REAL NOT NULL DEFAULT 0.5,
    evidence    TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_id, target_id, relation, source_kind, target_kind)
);

CREATE INDEX IF NOT EXISTS idx_eg_edges_source ON eg_edges(source_id, relation);
CREATE INDEX IF NOT EXISTS idx_eg_edges_target ON eg_edges(target_id, relation);
CREATE INDEX IF NOT EXISTS idx_eg_edges_relation ON eg_edges(relation);

-- Event ↔ event evolution links
CREATE TABLE IF NOT EXISTS eg_event_links (
    from_event_id   UUID NOT NULL REFERENCES eg_events(id) ON DELETE CASCADE,
    to_event_id     UUID NOT NULL REFERENCES eg_events(id) ON DELETE CASCADE,
    link_type       TEXT NOT NULL,  -- evolves_from | related_to | sub_event | escalation
    confidence      REAL NOT NULL DEFAULT 0.5,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (from_event_id, to_event_id, link_type)
);

-- Timeline append-only audit (optional; main timeline also on eg_events.timeline)
CREATE TABLE IF NOT EXISTS eg_timeline_entries (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id    UUID NOT NULL REFERENCES eg_events(id) ON DELETE CASCADE,
    entry_date  DATE NOT NULL,
    update_text TEXT NOT NULL,
    source      TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_eg_timeline_event ON eg_timeline_entries(event_id, entry_date DESC);
