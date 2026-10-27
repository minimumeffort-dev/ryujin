"""Completion capture is independent of extraction readiness; loops stay bounded."""
from contextlib import closing, redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import queue_hook
import queue_store


class StopCaptureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ryujin-stop-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.state = self.root / ".state"
        self.notes = self.root / "llm-wiki"
        for module in (queue_hook, queue_store):
            patch = mock.patch.multiple(
                module, DATABASE_PATH=self.state / "ryujin.sqlite3",
                NOTES_DIR=self.notes, PROJECT_ROOT=self.root,
            )
            patch.start()
            self.addCleanup(patch.stop)
        patch = mock.patch.object(queue_store, "STATE_DIR", self.state)
        patch.start()
        self.addCleanup(patch.stop)

    def invoke(self, client="codex", **event):
        output, errors = io.StringIO(), io.StringIO()
        payload = {"hook_event_name": "Stop", "status": "completed", **event}
        with mock.patch.object(sys, "argv", ["queue_hook.py", client]), \
             mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), \
             redirect_stdout(output), redirect_stderr(errors):
            queue_hook.main()
        return json.loads(output.getvalue()), errors.getvalue()

    def message(self, client, output):
        if client == "cursor":
            return output["followup_message"]
        self.assertEqual(output["decision"], "block")
        return output["reason"]

    def test_all_clients_request_capture_with_an_empty_queue(self):
        for client in ("codex", "claude", "cursor"):
            with self.subTest(client=client):
                output, errors = self.invoke(client)
                message = self.message(client, output)
                self.assertIn("No extraction jobs were ready", message)
                self.assertIn("Review this task", message)
                self.assertIn("no file changes", message)
                self.assertIn("If no capture is needed, leave the wiki unchanged", message)
                self.assertIn("prompt returned by claim", message)
                self.assertNotIn("jobs are waiting", message)
                self.assertEqual(errors, "")
        self.assertIn("queue=idle", (self.state / "hook_runs.log").read_text())

    def test_delayed_jobs_are_not_misreported_as_an_empty_queue(self):
        database = queue_store.open_database()
        try:
            queue_store.enqueue(database, {"path": "delayed.md"})
            database.execute("UPDATE jobs SET available_at = ?", (queue_hook.time.time() + 3600,))
        finally:
            database.close()
        output, errors = self.invoke()
        self.assertIn("No extraction jobs were ready", output["reason"])
        self.assertNotIn("queue was empty", output["reason"])
        self.assertEqual(errors, "")

    def test_pending_notes_request_capture_before_extraction(self):
        self.notes.mkdir()
        (self.notes / "feature.md").write_text("# Feature\n\n## Behavior\n\nSaved knowledge.\n")
        for client in ("codex", "claude", "cursor"):
            with self.subTest(client=client):
                output, errors = self.invoke(client)
                message = self.message(client, output)
                self.assertIn("Extraction jobs are waiting", message)
                self.assertLess(message.index("Before extraction"), message.index("jobs are waiting"))
                self.assertIn("Do not edit wiki pages during extraction", message)
                self.assertEqual(errors, "")
        with closing(sqlite3.connect(self.state / "ryujin.sqlite3")) as database:
            self.assertEqual(database.execute("SELECT path,revision,state FROM jobs").fetchall(),
                             [("feature.md", 1, "pending")])

    def test_continuation_guards_have_no_filesystem_or_queue_side_effects(self):
        for client, event in (
            ("codex", {"stop_hook_active": True}),
            ("claude", {"stop_hook_active": True}),
            ("cursor", {"loop_count": 1}),
            ("cursor", {"loop_count": 2}),
            ("cursor", {"status": "aborted"}),
            ("cursor", {"status": "error"}),
        ):
            with self.subTest(client=client, event=event), \
                 mock.patch.object(queue_hook, "open_database") as open_database, \
                 mock.patch.object(queue_hook, "has_work") as has_work:
                output, errors = self.invoke(client, **event)
                self.assertEqual(output, {})
                self.assertEqual(errors, "")
                open_database.assert_not_called()
                has_work.assert_not_called()
                self.assertFalse(self.state.exists())

    def test_queue_failure_still_requests_capture_and_reports_the_error(self):
        with mock.patch.object(queue_hook, "open_database", side_effect=sqlite3.OperationalError("busy")):
            output, errors = self.invoke()
        self.assertIn("Review this task", output["reason"])
        self.assertIn("could not be checked", output["reason"])
        self.assertNotIn("jobs are waiting", output["reason"])
        self.assertIn("Queue check failed: busy", errors)
        self.assertIn("queue=error", (self.state / "hook_runs.log").read_text())

    def test_log_failure_does_not_suppress_capture_review(self):
        self.state.mkdir()
        (self.state / "hook_runs.log").mkdir()
        output, errors = self.invoke()
        self.assertIn("No extraction jobs were ready", output["reason"])
        self.assertIn("Hook log failed", errors)


class CaptureFlowTests(unittest.TestCase):
    def test_empty_stop_saved_note_claim_acknowledge_and_prompt_recall(self):
        # Real relocated tools and bootstrap, no mocked database or client adapters.
        with tempfile.TemporaryDirectory(prefix="ryujin-capture-flow-") as name:
            root = Path(name) / "host project with spaces"
            shutil.copytree(TOOLS, root / "tools",
                            ignore=shutil.ignore_patterns(".venv", "__pycache__", "tests"))
            notes = root / "llm-wiki"
            notes.mkdir()
            def run(script, *args, event=None):
                result = subprocess.run(
                    ["sh", str(root / "tools/run_hook.sh"), script, *args],
                    cwd=root, input=json.dumps(event) if event is not None else None,
                    text=True, capture_output=True, timeout=20,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout)

            first = run("queue_hook.py", "codex", event={"stop_hook_active": False})
            self.assertEqual(first["decision"], "block")
            self.assertIn("No extraction jobs were ready", first["reason"])
            path = root / ".state/ryujin.sqlite3"
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute("SELECT count(*) FROM jobs").fetchone()[0], 0)

            behavior = "The first Stop requests a capture review even when the extraction queue is empty."
            (notes / "capture.md").write_text("# Completion capture\n\n## Current behavior\n\n" + behavior + "\n")
            claim = run("consume_queue.py", "claim", "--worker", "capture-flow-test")
            self.assertEqual(claim["status"], "claimed")
            self.assertIn("schema_version 2", claim["extraction_prompt"])
            self.assertEqual(claim["path"], "capture.md")
            candidate = {
                "schema_version": 2, "source_doc": "llm-wiki/capture.md",
                "nodes": [{"key": "feature:completion-capture", "name": "Completion capture",
                           "type": "FEATURE", "description": "Capture review before completion."}],
                "facts": [{"key": "fact:empty-queue-capture", "subject": "feature:completion-capture",
                           "kind": "behavior", "text": behavior, "state": "current",
                           "evidence": [{"section": "Current behavior", "excerpt": behavior}]}],
                "edges": [], "aliases": [],
            }
            result_path = root / ".state/extractions" / str(claim["id"]) / str(claim["claimed_revision"]) / (claim["claim_token"] + ".json")
            result_path.parent.mkdir(parents=True)
            result_path.write_text(json.dumps(candidate))
            accepted = run("consume_queue.py", "ack", str(claim["id"]), "--token", claim["claim_token"])
            self.assertEqual(accepted["status"], "done")
            self.assertEqual(run("consume_queue.py", "claim", "--worker", "capture-flow-test"), {"status": "empty"})
            recall = run("recall_hook.py", "codex", event={"prompt": "Do we capture knowledge with an empty queue?"})
            self.assertIn(behavior, recall["hookSpecificOutput"]["additionalContext"])
            log = root / ".state/hook_runs.log"
            before = log.read_bytes()
            self.assertEqual(run("queue_hook.py", "codex", event={"stop_hook_active": True}), {})
            self.assertEqual(log.read_bytes(), before)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute("SELECT state FROM jobs").fetchall(), [("done",)])
                self.assertEqual(db.execute("SELECT count(*) FROM extraction_runs").fetchone()[0], 1)
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])


if __name__ == "__main__":
    unittest.main()
