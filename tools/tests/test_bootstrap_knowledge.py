from contextlib import closing
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
import bootstrap_knowledge as bootstrap
import build_graph
import queue_store
import recall_hook


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ryujin-bootstrap-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "host project (with spaces)"
        self.root.mkdir()
        self.notes = self.root / "llm-wiki"
        self.notes.mkdir()
        self.state = self.root / ".state"
        self.db_path = self.state / "ryujin.sqlite3"
        for module in (bootstrap, queue_store):
            patch = mock.patch.multiple(module, PROJECT_ROOT=self.root, NOTES_DIR=self.notes,
                                        STATE_DIR=self.state, DATABASE_PATH=self.db_path)
            patch.start()
            self.addCleanup(patch.stop)
        patch = mock.patch.object(build_graph, "PROJECT_ROOT", self.root)
        patch.start()
        self.addCleanup(patch.stop)
        self.options = {"max_files": 2000, "max_bytes": 8 * 1024 * 1024,
                        "max_file_bytes": 512 * 1024, "chunk_chars": 12, "exclude": []}
        (self.root / "app.py").write_bytes(b"def attempts():\r\n    return 3\r\n")

    def start(self, **options):
        return bootstrap.start({**self.options, **options})

    def read_all(self, state):
        chunks = []
        while bootstrap.next_chunk(state):
            chunks.append(bootstrap.read_chunk(state))
        return chunks

    def note(self, name="architecture.md", gap=False):
        text = "# Host architecture\n\n## Current behavior\n\nThe retry limit is three attempts.\nImplementation: [app.py](../app.py#attempts).\n"
        if gap:
            text += "\n## Open questions\n\nSource review is incomplete; remaining chunks and budget gaps need follow-up.\n"
        path = self.notes / name
        path.write_text(text)
        return path.relative_to(self.root).as_posix()

    def publish(self, relative):
        with closing(queue_store.open_database()) as database:
            job = queue_store.claim(database, "bootstrap-test")
            self.assertEqual("llm-wiki/" + job["path"], relative)
            document = {
                "schema_version": 2, "source_doc": relative,
                "nodes": [{"key": "feature:retry", "name": "Retry limit", "type": "FEATURE",
                           "description": "Configured retry limit."}],
                "facts": [{"key": "fact:retry", "subject": "feature:retry", "kind": "behavior",
                           "text": "The retry limit is three attempts.", "state": "current",
                           "evidence": [{"section": "Current behavior", "excerpt": "The retry limit is three attempts."}]}],
                "edges": [], "aliases": [],
            }
            path = self.state / "extractions" / str(job["id"]) / str(job["claimed_revision"]) / (job["claim_token"] + ".json")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(document))
            self.assertEqual(queue_store.acknowledge(database, job["id"], job["claim_token"]), "done")

    def test_git_ignore_defaults_binary_and_symlink_scope(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / ".gitignore").write_text("ignored.py\n")
        for name in ("ignored.py", ".env", "secret.pem"):
            (self.root / name).write_text("Do not ingest this content.")
        (self.root / "binary.dat").write_bytes(b"binary\0data")
        (self.root / "external.py").symlink_to(Path(self.root.parent) / "private.py")
        (self.root / "node_modules").mkdir()
        (self.root / "node_modules/code.js").write_text("generated dependency")
        self.note()
        state = self.start()
        self.assertEqual(state["inventory"]["discovery"], "git")
        paths = {f["path"] for f in state["inventory"]["files"]}
        self.assertEqual(paths, {".gitignore", "app.py"})
        self.assertFalse(state["inventory"]["gaps"])

    def test_chunk_resume_and_crlf_source_are_exact(self):
        state = self.start()
        first = bootstrap.read_chunk(state)
        resumed = bootstrap.start(self.options)
        self.assertEqual(resumed["delivered"], state["delivered"])
        chunks = [first, *self.read_all(resumed)]
        self.assertEqual("".join(c["content"] for c in chunks), (self.root / "app.py").read_bytes().decode())
        self.assertTrue(all(len(c["content"]) <= 12 for c in chunks))
        self.assertEqual(bootstrap.status(resumed)["status"], "ready_for_notes")
        self.assertFalse(self.db_path.exists())

    def test_changed_or_new_sources_require_refresh_and_keep_other_progress(self):
        (self.root / "stable.py").write_text("stable = True\n")
        state = self.start()
        self.read_all(state)
        (self.root / "app.py").write_text("def attempts():\n    return 4\n")
        with self.assertRaisesRegex(ValueError, "Source changed"):
            bootstrap.read_chunk(state, "app.py")
        with self.assertRaisesRegex(ValueError, "inventory changed"):
            bootstrap.register_notes(state, [self.note()])
        refreshed = bootstrap.start(self.options, refresh=True)
        self.assertNotIn("app.py", refreshed["delivered"])
        self.assertEqual(refreshed["delivered"]["stable.py"], state["delivered"]["stable.py"])
        self.read_all(refreshed)
        (self.root / "new.py").write_text("new = True\n")
        with self.assertRaisesRegex(ValueError, "inventory changed"):
            bootstrap.register_notes(refreshed, [self.note()])

    def test_incomplete_coverage_cannot_be_published_as_complete(self):
        (self.root / "large.py").write_text("value = 1\n" * 100)
        state = self.start(max_file_bytes=64)
        self.assertTrue(state["inventory"]["gaps"])
        note = self.note(gap=True)
        with self.assertRaisesRegex(ValueError, "coverage is partial"):
            bootstrap.register_notes(state, [note])
        self.read_all(state)
        with self.assertRaisesRegex(ValueError, "coverage is partial"):
            bootstrap.register_notes(state, [note])
        bootstrap.register_notes(state, [note], allow_partial=True, gaps_note=note)
        self.assertEqual(bootstrap.status(state)["status"], "extraction_pending")
        self.publish(note)
        self.assertEqual(bootstrap.status(state)["status"], "complete_partial")

    def test_finish_requires_source_linked_architecture_and_is_idempotent(self):
        state = self.start()
        self.read_all(state)
        plain = self.notes / "plain.md"
        plain.write_text("# Unsupported\n\nNo source references.\n")
        with self.assertRaisesRegex(ValueError, "link to at least one"):
            bootstrap.register_notes(state, ["llm-wiki/plain.md"])
        other = self.note("feature.md")
        with self.assertRaisesRegex(ValueError, "architecture topic"):
            bootstrap.register_notes(state, [other])
        plain.unlink()
        (self.notes / "feature.md").unlink()
        note = self.note()
        bootstrap.register_notes(state, [note])
        before = state["finished_at"]
        bootstrap.register_notes(state, [note])
        self.assertEqual(state["finished_at"], before)
        self.publish(note)
        self.assertEqual(bootstrap.status(state)["status"], "complete")

    def test_angle_bracket_source_links_support_route_groups_and_line_numbers(self):
        grouped = self.root / "src/(legacy)/app.py"
        grouped.parent.mkdir(parents=True)
        grouped.write_text("value = 3\n")
        state = self.start()
        self.read_all(state)
        note = self.notes / "architecture.md"
        note.write_text(f"# Architecture\n\nSource: [app.py](<{grouped}:1>).\n")
        bootstrap.register_notes(state, ["llm-wiki/architecture.md"])
        self.assertEqual(bootstrap.status(state)["status"], "extraction_pending")

    def test_empty_recall_points_to_onboarding_without_bootstrapping_every_miss(self):
        for state in ("empty_index", "missing_database"):
            self.assertIn("bootstrap_knowledge.py start", recall_hook.fallback_context(state))
            self.assertIn("baseline wiki notes already exist", recall_hook.fallback_context(state))
        self.assertNotIn("bootstrap_knowledge.py start", recall_hook.fallback_context("no_matches"))


class BootstrapFlowTests(unittest.TestCase):
    def test_real_cli_bootstrap_then_normal_capture_preserves_baseline_and_existing_knowledge(self):
        with tempfile.TemporaryDirectory(prefix="ryujin-bootstrap-flow-") as name:
            root = Path(name) / "existing host with spaces"
            shutil.copytree(TOOLS, root / "tools",
                            ignore=shutil.ignore_patterns(".venv", "__pycache__", "tests"))
            notes = root / "llm-wiki"
            notes.mkdir()
            (root / "app.py").write_text("from retry_policy import attempts\nprint(attempts())\n")
            (root / "retry_policy.py").write_text("def attempts():\n    return 3\n")
            (root / "README.md").write_text("# Existing demo CLI\nRun python app.py to print the retry limit.\n")

            def run(script, *args):
                result = subprocess.run(["sh", str(root / "tools/run_hook.sh"), script, *args],
                                        cwd=root, text=True, capture_output=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout)

            def write_note(filename, statement, source):
                (notes / filename).write_text(f"# {filename}\n\n## Current behavior\n\n{statement}\n\nSource: [{source}](../{source}).\n")

            def extract(statement):
                job = run("consume_queue.py", "claim", "--worker", "bootstrap-flow")
                document = {"schema_version": 2, "source_doc": "llm-wiki/" + job["path"],
                            "nodes": [{"key": "feature:" + Path(job["path"]).stem, "name": Path(job["path"]).stem,
                                       "type": "FEATURE", "description": statement}],
                            "facts": [{"key": "fact:" + Path(job["path"]).stem,
                                       "subject": "feature:" + Path(job["path"]).stem,
                                       "kind": "behavior", "text": statement, "state": "current",
                                       "evidence": [{"section": "Current behavior", "excerpt": statement}]}],
                            "edges": [], "aliases": []}
                candidate = root / ".state/extractions" / str(job["id"]) / str(job["claimed_revision"]) / (job["claim_token"] + ".json")
                candidate.parent.mkdir(parents=True, exist_ok=True)
                candidate.write_text(json.dumps(document))
                self.assertEqual(run("consume_queue.py", "ack", str(job["id"]), "--token", job["claim_token"])["status"], "done")
                return candidate

            original = "The demo CLI prints its retry limit."
            write_note("prior.md", original, "app.py")
            original_result = extract(original)
            original_json = original_result.read_bytes()
            first = run("bootstrap_knowledge.py", "start", "--exclude", "tools/**")
            self.assertEqual(first["source_files"], 3)
            returned = []
            while True:
                item = run("bootstrap_knowledge.py", "read")
                if item["status"] == "sources_delivered":
                    break
                returned.append(item)
            self.assertEqual({i["path"] for i in returned}, {"README.md", "app.py", "retry_policy.py"})
            observed = subprocess.run([sys.executable, "app.py"], cwd=root, capture_output=True, text=True, check=True)
            self.assertEqual(observed.stdout, "3\n")
            architecture = "The CLI obtains its retry limit from retry_policy.py."
            retry = "The retry policy allows three attempts."
            write_note("architecture.md", architecture, "app.py")
            write_note("retry.md", retry, "retry_policy.py")
            finished = run("bootstrap_knowledge.py", "finish", "--notes", "llm-wiki/architecture.md", "llm-wiki/retry.md")
            self.assertEqual(finished["status"], "extraction_pending")
            # Jobs follow note-path reconciliation order in this controlled fixture.
            extract(architecture)
            extract(retry)
            self.assertEqual(run("bootstrap_knowledge.py", "status")["status"], "complete")
            self.assertEqual(original_result.read_bytes(), original_json)

            (root / "retry_policy.py").write_text("def attempts():\n    return 4\n")
            replacement = "The retry policy now allows four attempts."
            write_note("retry.md", replacement, "retry_policy.py")
            extract(replacement)
            result = run("recall_graph.py", "How many retry attempts are allowed?")
            self.assertTrue(any(replacement in f["text"] for f in result["facts"]))
            self.assertEqual(run("bootstrap_knowledge.py", "status")["status"], "complete")
            self.assertEqual(run("bootstrap_knowledge.py", "start")["status"], "complete")
            self.assertEqual(run("consume_queue.py", "claim", "--worker", "bootstrap-flow"), {"status": "empty"})
            with closing(sqlite3.connect(root / ".state/ryujin.sqlite3")) as database:
                self.assertEqual(database.execute("SELECT count(*) FROM extraction_runs").fetchone()[0], 4)
                self.assertEqual(database.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(database.execute("PRAGMA foreign_key_check").fetchall(), [])


if __name__ == "__main__":
    unittest.main()
