import json
import sqlite3
import time
from math import isfinite
from uuid import uuid4
from migrations import archive_result, digest, migrate
from extraction.engineering import relative_path

from extraction.validate import load_extraction
from paths import (
    DATABASE_PATH,
    NOTES_DIR,
    PROJECT_ROOT,
    SCHEMA_PATH,
    STATE_DIR,
)


def open_database():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    database = sqlite3.connect(
        DATABASE_PATH,
        timeout=10,
        isolation_level=None,
    )
    database.row_factory = sqlite3.Row

    try:
        database.execute("PRAGMA foreign_keys = ON")
        database.execute("PRAGMA journal_mode = WAL").fetchone()
        database.execute("PRAGMA synchronous = FULL")
        migrate(database, DATABASE_PATH, SCHEMA_PATH, PROJECT_ROOT)
    except Exception:
        database.close()
        raise

    return database


def enqueue(database, job):
    path = job["path"]
    if not isinstance(path, str) or not path.strip():
        raise ValueError("job path must not be empty")
    relative_path(path)

    now = time.time()

    cursor = database.execute(
        """
        INSERT INTO jobs (path, payload, available_at, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            payload = excluded.payload,
            revision = jobs.revision + 1,
            state = CASE
                WHEN jobs.state = 'processing' THEN 'processing'
                ELSE 'pending'
            END,
            attempts = CASE
                WHEN jobs.state = 'processing' THEN jobs.attempts
                ELSE 0
            END,
            available_at = excluded.available_at,
            last_error = CASE
                WHEN jobs.state = 'processing' THEN jobs.last_error
                ELSE NULL
            END
        RETURNING id
        """,
        (path, json.dumps(job), now, now),
    )

    row = cursor.fetchone()
    cursor.close()
    return row["id"]


def claim(database, worker_id, lease_seconds=300):
    if not worker_id.strip():
        raise ValueError("worker_id must not be empty")
    if not isfinite(lease_seconds) or lease_seconds <= 0:
        raise ValueError("lease_seconds must be finite and positive")

    database.execute("BEGIN IMMEDIATE")

    try:
        now = time.time()
        token = uuid4().hex

        cursor = database.execute(
            """
            UPDATE jobs
            SET state = 'processing',
                claimed_revision = revision,
                worker_id = ?,
                claim_token = ?,
                lease_until = ?,
                attempts = attempts + 1
            WHERE id = (
                SELECT id FROM jobs
                WHERE state = 'pending' AND available_at <= ?
                ORDER BY available_at, id
                LIMIT 1
            )
            AND state = 'pending'
            RETURNING id, path, payload, revision, claimed_revision,
                      worker_id, claim_token, lease_until, attempts
            """,
            (worker_id, token, now + lease_seconds, now),
        )

        row = cursor.fetchone()
        cursor.close()

        result = None
        if row is not None:
            result = dict(row)
            result["job"] = json.loads(result.pop("payload"))

        database.execute("COMMIT")
        return result

    except BaseException:
        if database.in_transaction:
            database.execute("ROLLBACK")
        raise


def acknowledge(database, job_id, claim_token):
    database.execute("BEGIN IMMEDIATE")

    try:
        job = database.execute(
            """
            SELECT path, payload, revision, claimed_revision, lease_until
            FROM jobs
            WHERE id = ?
              AND state = 'processing'
              AND claim_token = ?
              AND lease_until > ?
            """,
            (job_id, claim_token, time.time()),
        ).fetchone()

        if job is None:
            database.execute("COMMIT")
            return None

        source_doc = (NOTES_DIR / job["path"]).relative_to(PROJECT_ROOT).as_posix()
        result_path = (
            STATE_DIR
            / "extractions"
            / str(job_id)
            / str(job["claimed_revision"])
            / f"{claim_token}.json"
        )

        metadata = json.loads(job["payload"])
        snapshot = None
        source_hash = None
        data = None
        if job["revision"] == job["claimed_revision"]:
            if metadata.get("schema_version") == 2:
                snapshot = (NOTES_DIR / job["path"]).read_text(encoding="utf-8")
                source_hash = digest(snapshot)
                if source_hash != metadata.get("source_hash"):
                    enqueue(database, {**metadata, "source_hash": source_hash})
            latest = database.execute("SELECT revision FROM jobs WHERE id=?", (job_id,)).fetchone()[0]
            if latest == job["claimed_revision"]:
                data = load_extraction(result_path, source_doc, source_text=snapshot)
                if metadata.get("schema_version") == 2 and data.get("schema_version") != 2:
                    raise ValueError("This claim requires extraction schema_version 2")

        now = time.time()

        cursor = database.execute(
            """
            UPDATE jobs
            SET state = CASE
                    WHEN revision = claimed_revision THEN 'done'
                    ELSE 'pending'
                END,
                attempts = CASE
                    WHEN revision = claimed_revision THEN attempts
                    ELSE 0
                END,
                available_at = ?,
                claimed_revision = NULL,
                worker_id = NULL,
                claim_token = NULL,
                lease_until = NULL,
                last_error = NULL
            WHERE id = ?
              AND state = 'processing'
              AND claim_token = ?
              AND lease_until > ?
            RETURNING state
            """,
            (now, job_id, claim_token, now),
        )

        row = cursor.fetchone()
        cursor.close()

        if row is not None and row["state"] == "done":
            run_id = archive_result(
                database, PROJECT_ROOT, source_doc, job["claimed_revision"],
                result_path.relative_to(PROJECT_ROOT).as_posix(), now,
                snapshot=snapshot, source_hash=source_hash,
                prompt_hash=metadata.get("prompt_hash"),
            )
            database.execute(
                """UPDATE knowledge_sources SET content_hash=COALESCE(?,content_hash),
                   active=1,updated_at=? WHERE source_doc=?""", (source_hash,now,source_doc))
            database.execute(
                """
                INSERT INTO extraction_results (
                    source_doc, revision, result_path, accepted_at, source_hash, schema_version, extraction_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_doc) DO UPDATE SET
                    revision = excluded.revision,
                    result_path = excluded.result_path,
                    accepted_at = excluded.accepted_at,
                    source_hash = excluded.source_hash,
                    schema_version = excluded.schema_version,
                    extraction_id = excluded.extraction_id
                """,
                (
                    source_doc,
                    job["claimed_revision"],
                    result_path.relative_to(PROJECT_ROOT).as_posix(),
                    now,
                    source_hash,
                    data.get("schema_version", 1),
                    run_id,
                ),
            )

            # The graph builder imports this module, so load it after initialization.
            from build_graph import rebuild_graph

            rebuild_graph(database)

            if time.time() >= job["lease_until"]:
                database.execute("ROLLBACK")
                return None

            if snapshot is not None and (NOTES_DIR / job["path"]).read_text(encoding="utf-8") != snapshot:
                database.execute("ROLLBACK")
                changed = (NOTES_DIR / job["path"]).read_text(encoding="utf-8")
                enqueue(database, {**metadata, "source_hash": digest(changed)})
                return acknowledge(database, job_id, claim_token)

        database.execute("COMMIT")
        return row["state"] if row is not None else None

    except BaseException:
        if database.in_transaction:
            database.execute("ROLLBACK")
        raise


def retry(database, job_id, claim_token, error, delay_seconds=5, max_attempts=5):
    if not isfinite(delay_seconds) or delay_seconds < 0:
        raise ValueError("delay_seconds must be finite and not negative")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    database.execute("BEGIN IMMEDIATE")

    try:
        now = time.time()

        cursor = database.execute(
            """
            UPDATE jobs
            SET state = CASE
                    WHEN revision <> claimed_revision THEN 'pending'
                    WHEN attempts >= ? THEN 'failed'
                    ELSE 'pending'
                END,
                attempts = CASE
                    WHEN revision <> claimed_revision THEN 0
                    ELSE attempts
                END,
                available_at = CASE
                    WHEN revision <> claimed_revision THEN ?
                    ELSE ?
                END,
                last_error = CASE
                    WHEN revision <> claimed_revision THEN NULL
                    ELSE ?
                END,
                claimed_revision = NULL,
                worker_id = NULL,
                claim_token = NULL,
                lease_until = NULL
            WHERE id = ?
              AND state = 'processing'
              AND claim_token = ?
              AND lease_until > ?
            RETURNING state
            """,
            (
                max_attempts,
                now,
                now + delay_seconds,
                str(error),
                job_id,
                claim_token,
                now,
            ),
        )

        row = cursor.fetchone()
        cursor.close()

        database.execute("COMMIT")
        return row["state"] if row is not None else None

    except BaseException:
        if database.in_transaction:
            database.execute("ROLLBACK")
        raise


def renew(database, job_id, claim_token, lease_seconds=300):
    if not isfinite(lease_seconds) or lease_seconds <= 0:
        raise ValueError("lease_seconds must be finite and positive")

    database.execute("BEGIN IMMEDIATE")

    try:
        now = time.time()

        cursor = database.execute(
            """
            UPDATE jobs
            SET lease_until = MAX(lease_until, ?)
            WHERE id = ?
              AND state = 'processing'
              AND claim_token = ?
              AND lease_until > ?
            RETURNING lease_until
            """,
            (now + lease_seconds, job_id, claim_token, now),
        )

        row = cursor.fetchone()
        cursor.close()

        database.execute("COMMIT")
        return row["lease_until"] if row is not None else None

    except BaseException:
        if database.in_transaction:
            database.execute("ROLLBACK")
        raise


def recover_expired(database, delay_seconds=5, max_attempts=5):
    if not isfinite(delay_seconds) or delay_seconds < 0:
        raise ValueError("delay_seconds must be finite and not negative")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    database.execute("BEGIN IMMEDIATE")

    try:
        now = time.time()

        cursor = database.execute(
            """
            UPDATE jobs
            SET state = CASE
                    WHEN revision <> claimed_revision THEN 'pending'
                    WHEN attempts >= ? THEN 'failed'
                    ELSE 'pending'
                END,
                attempts = CASE
                    WHEN revision <> claimed_revision THEN 0
                    ELSE attempts
                END,
                available_at = CASE
                    WHEN revision <> claimed_revision THEN ?
                    ELSE ?
                END,
                last_error = CASE
                    WHEN revision <> claimed_revision THEN NULL
                    ELSE 'Lease expired'
                END,
                claimed_revision = NULL,
                worker_id = NULL,
                claim_token = NULL,
                lease_until = NULL
            WHERE state = 'processing'
              AND lease_until <= ?
            RETURNING id, state
            """,
            (max_attempts, now, now + delay_seconds, now),
        )

        rows = cursor.fetchall()
        cursor.close()

        database.execute("COMMIT")
        return [dict(row) for row in rows]

    except BaseException:
        if database.in_transaction:
            database.execute("ROLLBACK")
        raise


if __name__ == "__main__":
    database = open_database()

    try:
        print(f"SQLite database ready: {DATABASE_PATH}")
    finally:
        database.close()
