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
    accepted_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS graph_nodes (
    id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    UNIQUE (type, name)
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
