import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from paths import PROJECT_ROOT, STATE_DIR, WATCHER_LOG_PATH
from watcher_lock import watcher_is_running


def ensure_watcher():
    if watcher_is_running():
        return

    descriptor, name = tempfile.mkstemp(
        prefix="watcher-start-", suffix=".json", dir=STATE_DIR
    )
    os.close(descriptor)
    ready_path = Path(name)
    process = None

    try:
        options = (
            {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
            if os.name == "nt"
            else {"start_new_session": True}
        )
        with WATCHER_LOG_PATH.open("ab") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-u",
                    str(PROJECT_ROOT / "tools" / "watch_llm_wiki.py"),
                    "--ready-file",
                    str(ready_path),
                ],
                cwd=PROJECT_ROOT,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                close_fds=True,
                **options,
            )

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                status = json.loads(ready_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                status = {}

            if status.get("status") in ("started", "already_running"):
                return
            if process.poll() is not None:
                raise RuntimeError(f"Watcher failed to start; see {WATCHER_LOG_PATH}")
            time.sleep(0.05)

        raise RuntimeError(f"Watcher startup timed out; see {WATCHER_LOG_PATH}")
    except BaseException:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        raise
    finally:
        ready_path.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        ensure_watcher()
    except (OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
    print("{}")
