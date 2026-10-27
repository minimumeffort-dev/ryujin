import argparse
import json
import os
from pathlib import Path

from watchfiles import watch

from paths import NOTES_DIR, PROJECT_ROOT, EXTRACTION_PROMPT_PATH
from queue_store import open_database
from source_sync import synchronize_sources
from watcher_lock import watcher_lock


def notify_ready(ready_path, status):
    if ready_path is not None:
        ready_path.write_text(json.dumps({"status": status}), encoding="utf-8")


def run_watcher(ready_path):
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    database = open_database()

    try:
        starting = True
        for changes in watch(
            NOTES_DIR,
            debounce=1000,
            step=250,
            rust_timeout=250,
            yield_on_timeout=True,
        ):
            changed_paths = {Path(raw_path) for _, raw_path in changes}

            # The event listener is active before this scan, so startup has no gap.
            if starting:
                changed_paths.update(
                    path
                    for path in NOTES_DIR.rglob("*")
                    if path.is_file() and path.suffix.lower() == ".md"
                )

            if starting or changed_paths:
                queued = synchronize_sources(database, NOTES_DIR, PROJECT_ROOT, EXTRACTION_PROMPT_PATH)
                for job_id in queued:
                    print(f"Queued #{job_id}", flush=True)

            if starting:
                print(f"Watching {NOTES_DIR} (PID {os.getpid()})", flush=True)
                notify_ready(ready_path, "started")
                starting = False
    finally:
        database.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ready-file", type=Path)
    args = parser.parse_args()

    with watcher_lock() as acquired:
        if not acquired:
            notify_ready(args.ready_file, "already_running")
            return
        run_watcher(args.ready_file)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nWatcher stopped!")
