"""Reconcile source hashes without repeatedly extracting navigation or log pages."""
import json
import time

from migrations import digest, source_kind
from extraction.engineering import SCHEMA_VERSION


def synchronize_sources(database, notes_dir, project_root, prompt_path):
    from queue_store import enqueue

    prompt_hash = digest(prompt_path.read_text(encoding="utf-8")) if prompt_path.exists() else None
    owns_transaction = not database.in_transaction
    if owns_transaction:
        database.execute("BEGIN IMMEDIATE")
    queued = []
    try:
        found = set()
        for path in sorted(notes_dir.rglob("*")) if notes_dir.exists() else []:
            if not path.is_file() or path.suffix.casefold() != ".md":
                continue
            if not path.resolve().is_relative_to(project_root.resolve()):
                continue
            source = path.relative_to(project_root).as_posix()
            found.add(source)
            content_hash = digest(path.read_text(encoding="utf-8"))
            kind = source_kind(source)
            database.execute(
                """INSERT INTO knowledge_sources VALUES(?,?,?,1,?)
                   ON CONFLICT(source_doc) DO UPDATE SET content_hash=excluded.content_hash,
                   active=1,kind=excluded.kind,updated_at=excluded.updated_at""",
                (source,kind,content_hash,time.time()),
            )
            relative = path.relative_to(notes_dir).as_posix()
            if kind != "topic":
                database.execute(
                    """UPDATE jobs SET state='done',claimed_revision=NULL,claim_token=NULL,
                       worker_id=NULL,lease_until=NULL WHERE path=? AND state<>'done'""",(relative,))
                continue
            job = {"path":relative,"source_hash":content_hash,"schema_version":SCHEMA_VERSION,
                   "prompt_hash":prompt_hash}
            previous = database.execute("SELECT payload FROM jobs WHERE path=?",(relative,)).fetchone()
            if previous is None or json.loads(previous["payload"]) != job:
                queued.append(enqueue(database,job))
        prefix = notes_dir.relative_to(project_root).as_posix() + "/"
        for row in database.execute("SELECT source_doc FROM knowledge_sources WHERE active=1").fetchall():
            source = row["source_doc"]
            if source.startswith(prefix) and source not in found:
                database.execute("UPDATE knowledge_sources SET active=0,updated_at=? WHERE source_doc=?",
                                 (time.time(),source))
                database.execute(
                    """UPDATE jobs SET state='done',revision=revision+1,claimed_revision=NULL,
                       claim_token=NULL,worker_id=NULL,lease_until=NULL WHERE path=?""",
                    (source[len(prefix):],))
        if owns_transaction:
            database.execute("COMMIT")
    except BaseException:
        if owns_transaction and database.in_transaction:
            database.execute("ROLLBACK")
        raise
    return queued
