import argparse
import json
import sqlite3
import sys
import time

from paths import DATABASE_PATH, NOTES_DIR, PROJECT_ROOT, EXTRACTION_PROMPT_PATH
from queue_store import open_database
from source_sync import synchronize_sources


def has_work():
    if not DATABASE_PATH.is_file():
        return False

    database = sqlite3.connect(
        DATABASE_PATH.as_uri() + "?mode=ro",
        uri=True,
        timeout=1,
    )
    try:
        now = time.time()
        return bool(
            database.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM jobs
                    WHERE (state = 'pending' AND available_at <= ?)
                       OR (state = 'processing' AND lease_until <= ?)
                )
                """,
                (now, now),
            ).fetchone()[0]
        )
    finally:
        database.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("client", choices=["claude", "codex", "cursor"])
    client = parser.parse_args().client
    event = json.load(sys.stdin)

    if (
        event.get("stop_hook_active")
        or event.get("loop_count", 0) >= 1
        or (client == "cursor" and event.get("status") != "completed")
    ):
        print("{}")
        return

    try:
        database = open_database()
        try:
            synchronize_sources(database, NOTES_DIR, PROJECT_ROOT, EXTRACTION_PROMPT_PATH)
        finally:
            database.close()
        ready = has_work()
        queue_status = "ready" if ready else "idle"
    except (sqlite3.Error, OSError, ValueError) as error:
        print(f"Queue check failed: {error}", file=sys.stderr)
        queue_status = "error"

    log_path = DATABASE_PATH.parent / "hook_runs.log"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as log:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            log.write(
                f"{timestamp} {client} "
                f"{event.get('hook_event_name', 'Stop')} queue={queue_status}\n"
            )
    except OSError as error:
        print(f"Hook log failed: {error}", file=sys.stderr)

    message = (
        "Review this task for missing durable engineering knowledge before finishing, even "
        "when the extraction queue is empty. Follow AGENTS.md and the wiki's capture guidance. "
        "Before extraction, update relevant topic pages and the architecture map as needed "
        "with substantive behavior, code locations, changes, decisions and stated reasons, "
        "constraints, observed verification, open questions and explicit attribution. "
        "Preserve current knowledge and dated change history; keep the index and log current. "
        "Respect requests for no file changes; skip routine, duplicate or unsupported material. "
        "If no capture is needed, leave the wiki unchanged. "
    )
    message += {
        "ready": "Extraction jobs are waiting. ",
        "idle": "No extraction jobs were ready before this capture review; saved notes may create jobs. ",
        "error": "The extraction queue could not be checked; report any continuing queue error. ",
    }[queue_status]
    message += (
        "After capture, follow the extraction workflow in AGENTS.md, using the prompt returned "
        "by claim, until the queue is empty. Do not edit wiki pages during extraction. "
        "If the workflow is not configured, report that and stop without claiming jobs. "
        "If capture is unnecessary and claim returns empty, finish without further work."
    )

    output = (
        {"followup_message": message}
        if client == "cursor"
        else {"decision": "block", "reason": message}
    )
    print(json.dumps(output))


if __name__ == "__main__":
    main()
