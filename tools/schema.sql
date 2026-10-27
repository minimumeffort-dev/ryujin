CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    payload TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    claimed_revision INTEGER,
    state TEXT NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'processing', 'done', 'failed')),
    worker_id TEXT,
    claim_token TEXT,
    lease_until REAL,
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at REAL NOT NULL,
    created_at REAL NOT NULL,
    last_error TEXT
);

CREATE INDEX IF NOT EXISTS jobs_ready
ON jobs (state, available_at, id);

CREATE INDEX IF NOT EXISTS jobs_leases
ON jobs (state, lease_until);

CREATE TABLE IF NOT EXISTS extraction_results (
    source_doc TEXT PRIMARY KEY NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0),
    result_path TEXT NOT NULL,
    accepted_at REAL NOT NULL,
    source_hash TEXT,
    schema_version INTEGER NOT NULL DEFAULT 1,
    extraction_id TEXT
);

CREATE TABLE IF NOT EXISTS graph_nodes (
    id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS graph_node_sources (
    node_id TEXT NOT NULL REFERENCES graph_nodes(id),
    source_doc TEXT NOT NULL,
    description TEXT NOT NULL,
    PRIMARY KEY (node_id, source_doc)
);

CREATE TABLE IF NOT EXISTS graph_edges (
    source_id TEXT NOT NULL REFERENCES graph_nodes(id),
    predicate TEXT NOT NULL,
    target_id TEXT NOT NULL REFERENCES graph_nodes(id),
    source_doc TEXT NOT NULL,
    PRIMARY KEY (source_id, predicate, target_id, source_doc)
);

CREATE INDEX IF NOT EXISTS graph_edges_target
ON graph_edges (target_id);

CREATE TABLE IF NOT EXISTS graph_aliases (
    node_id TEXT NOT NULL REFERENCES graph_nodes(id),
    alias TEXT NOT NULL,
    source_doc TEXT NOT NULL,
    PRIMARY KEY (node_id, alias, source_doc)
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_sources (
    source_doc TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('topic', 'navigation', 'ledger')),
    content_hash TEXT,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS extraction_runs (
    id TEXT PRIMARY KEY,
    source_doc TEXT NOT NULL REFERENCES knowledge_sources(source_doc),
    revision INTEGER NOT NULL,
    result_path TEXT NOT NULL UNIQUE,
    result_hash TEXT NOT NULL,
    result_json TEXT NOT NULL,
    source_hash TEXT,
    source_snapshot TEXT,
    schema_version INTEGER NOT NULL,
    prompt_hash TEXT,
    accepted_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS graph_entity_keys (
    node_id TEXT PRIMARY KEY REFERENCES graph_nodes(id),
    entity_key TEXT NOT NULL UNIQUE,
    code_kind TEXT,
    code_path TEXT,
    symbol TEXT
);

CREATE TABLE IF NOT EXISTS graph_facts (
    id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL REFERENCES graph_nodes(id),
    fact_key TEXT NOT NULL,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('current', 'proposed', 'historical', 'superseded', 'disputed')),
    lifecycle TEXT NOT NULL DEFAULT '',
    rationale TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS graph_facts_subject ON graph_facts(node_id);
CREATE INDEX IF NOT EXISTS graph_facts_key ON graph_facts(fact_key);

CREATE TABLE IF NOT EXISTS graph_fact_sources (
    fact_id TEXT NOT NULL REFERENCES graph_facts(id),
    source_doc TEXT NOT NULL REFERENCES knowledge_sources(source_doc),
    extraction_id TEXT REFERENCES extraction_runs(id),
    section TEXT NOT NULL,
    excerpt TEXT NOT NULL,
    code_path TEXT,
    symbol TEXT,
    git_ref TEXT,
    verification TEXT NOT NULL DEFAULT 'source_reported',
    attribution_basis TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (fact_id, source_doc, section, excerpt)
);

CREATE TABLE IF NOT EXISTS graph_edge_facts (
    source_id TEXT NOT NULL REFERENCES graph_nodes(id),
    predicate TEXT NOT NULL,
    target_id TEXT NOT NULL REFERENCES graph_nodes(id),
    source_doc TEXT NOT NULL,
    fact_id TEXT NOT NULL REFERENCES graph_facts(id),
    PRIMARY KEY (source_id, predicate, target_id, source_doc, fact_id),
    FOREIGN KEY (source_id, predicate, target_id, source_doc)
        REFERENCES graph_edges(source_id, predicate, target_id, source_doc)
);

CREATE TABLE IF NOT EXISTS graph_fact_supersession (
    fact_id TEXT NOT NULL REFERENCES graph_facts(id),
    superseded_key TEXT NOT NULL,
    PRIMARY KEY (fact_id, superseded_key)
);

CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_search USING fts5(
    record_id UNINDEXED, node_id UNINDEXED, source_doc UNINDEXED,
    record_kind UNINDEXED, title, aliases, body, path,
    tokenize='porter unicode61'
);
