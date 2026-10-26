from pathlib import Path
from watchfiles import watch

from paths import NOTES_DIR
from queue_store import enqueue, open_database


def main():
    if not NOTES_DIR.is_dir():
        raise SystemExit(f"Notes directory does not exist: {NOTES_DIR}")

    database = open_database()

    try:
        print(f"Watching {NOTES_DIR}", flush=True)
        print("Press Ctrl+C to stop.", flush=True)

        for changes in watch(NOTES_DIR, debounce=1000, step=250):
            changed_paths = {Path(raw_path) for _, raw_path in changes}

            for path in sorted(changed_paths):
                if path.suffix.lower() != ".md":
                    continue

                relative_path = path.relative_to(NOTES_DIR)

                job = {
                    "path": relative_path.as_posix(),
                }
                job_id = enqueue(database, job)

                print(f"Queued #{job_id}: {job['path']}", flush=True)
    finally:
        database.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nWatcher stopped!")
