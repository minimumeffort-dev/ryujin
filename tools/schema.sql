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
