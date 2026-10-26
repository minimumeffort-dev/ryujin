from pathlib import Path
from watchfiles import watch

from paths import NOTES_DIR
from queue_store import open_queue


def main():
    if not NOTES_DIR.is_dir():
        raise SystemExit(f"Notes directory does not exist: {NOTES_DIR}")

    queue = open_queue()

    try:
        print(f"Watching {NOTES_DIR}", flush=True)
        print("Press Ctrl+C to stop.", flush=True)

        for changes in watch(NOTES_DIR, debounce=1000, step=250):
            for change, raw_path in changes:
                path = Path(raw_path)

                if path.suffix.lower() != ".md":
                    continue

                relative_path = path.relative_to(NOTES_DIR)

                job = {
                    "path": relative_path.as_posix(),
                    "event": change.name,
                }
                job_id = queue.put(job)

                print(f"Queued #{job_id}: {job['event']} {job['path']}", flush=True)
    finally:
        queue.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nWatcher stopped!")
