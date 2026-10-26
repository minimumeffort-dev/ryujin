import argparse
import json
import sqlite3
import sys
import time

from paths import DATABASE_PATH


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

    log_path = DATABASE_PATH.parent / "hook_runs.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log.write(
            f"{timestamp} {client} "
            f"{event.get('hook_event_name', 'Stop')}\n"
        )

    try:
        ready = has_work()
    except sqlite3.Error as error:
        print(f"Queue check failed: {error}", file=sys.stderr)
        ready = False

    if not ready:
        print("{}")
        return

    message = (
        "Extraction jobs are waiting. Follow the extraction workflow in "
        "AGENTS.md using the prompt returned by claim. If that workflow "
        "is not configured, report pending work and stop without claiming jobs."
    )

    output = (
        {"followup_message": message}
        if client == "cursor"
        else {"decision": "block", "reason": message}
    )
    print(json.dumps(output))


if __name__ == "__main__":
    main()
