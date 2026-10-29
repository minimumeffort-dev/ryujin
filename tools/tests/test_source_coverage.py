"""Coverage records must stay tied to reviewed source, topic snapshots and publication."""
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
import source_coverage as coverage


class CoverageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ryujin-coverage-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "host with spaces"
        self.root.mkdir()
        self.notes = self.root / "llm-wiki"; self.notes.mkdir()
        self.state = self.root / ".state"
        patch = mock.patch.multiple(bootstrap, PROJECT_ROOT=self.root, NOTES_DIR=self.notes,
                                    STATE_DIR=self.state, DATABASE_PATH=self.state / "ryujin.sqlite3")
        patch.start(); self.addCleanup(patch.stop)
        (self.root / "app.py").write_text("def run():\n    return 3\n")
        self.options = {"max_files": 2000, "max_bytes": 8000000, "max_file_bytes": 500000,
                        "chunk_chars": 16, "exclude": []}

    def initialize(self, read=True):
        state = bootstrap.start(self.options, refresh=True)
        if read:
            while bootstrap.next_chunk(state): bootstrap.read_chunk(state)
        return coverage.initialize()

    def topic(self, text="The application returns three."):
        path = self.notes / "application.md"
        path.write_text("# Application\n\n## Current behavior\n\n" + text + "\nSource: [app.py](../app.py#run).\n")
        return "llm-wiki/application.md"

    def record(self):
        return coverage.record(["app.py"], "reviewed", [self.topic()], ["feature:application"],
                               "Reviewed application behavior and source entry point.")

    def test_inventory_handles_nested_async_and_duplicate_definition_sites_without_execution(self):
        text = """raise RuntimeError('must not execute')
import os as operating_system
class Outer:
    def method(self):
        from .local import helper
        def inner(): pass
async def fetch(): pass
def repeated(): pass
def repeated(): pass
"""
        parsed = coverage.symbols("app.py", text)
        self.assertEqual({s["symbol"] for s in parsed["symbols"]},
                         {"Outer", "Outer.method", "Outer.method.inner", "fetch", "repeated"})
        repeated = next(s for s in parsed["symbols"] if s["symbol"] == "repeated")
        self.assertEqual(len(repeated["definitions"]), 2)
        self.assertEqual(parsed["imports"][1]["scope"], "Outer.method")
        self.assertEqual(parsed["imports"][1]["level"], 1)
        self.assertEqual(next(s for s in parsed["symbols"] if s["symbol"] == "fetch")["kind"], "async_function")

    def test_inventory_is_unresolved_until_recorded_and_never_creates_database(self):
        data = self.initialize()
        self.assertEqual(coverage.verify(data)["unresolved"], 1)
        self.assertFalse(bootstrap.DATABASE_PATH.exists())
        self.record()
        self.assertEqual(coverage.verify()["status"], "notes_ready")
        self.assertFalse(bootstrap.DATABASE_PATH.exists())

    def test_review_requires_delivered_chunks_source_links_and_canonical_entities(self):
        self.initialize(read=False)
        with self.assertRaisesRegex(ValueError, "Deliver all source chunks"):
            self.record()
        state = bootstrap.load_state()
        while bootstrap.next_chunk(state): bootstrap.read_chunk(state)
        with self.assertRaisesRegex(ValueError, "canonical"):
            coverage.record(["app.py"], "reviewed", [self.topic()], ["not-a-key"], "Reviewed.")
        (self.notes / "unrelated.md").write_text("# Unrelated\n\nNo application reference.")
        with self.assertRaisesRegex(ValueError, "source link"):
            coverage.record(["app.py"], "reviewed", ["llm-wiki/unrelated.md"], ["feature:application"], "Reviewed.")
        with self.assertRaisesRegex(ValueError, "substantive topic"):
            coverage.record(["app.py"], "reviewed", ["llm-wiki/source-coverage.md"], ["feature:application"], "Reviewed.")

    def test_source_and_topic_drift_invalidate_completion_and_refresh_resets_changed_files(self):
        self.initialize(); self.record()
        (self.notes / "application.md").write_text("Changed review evidence")
        self.assertTrue(any("changed topic" in issue for issue in coverage.verify()["issues"]))
        self.record()
        (self.root / "app.py").write_text("def run():\n    return 4\n")
        self.assertEqual(coverage.verify()["status"], "incomplete")
        self.initialize()
        self.assertEqual(coverage.verify()["unresolved"], 1)

    def test_parse_errors_and_budget_gaps_remain_visible(self):
        (self.root / "app.py").write_text("def broken(:\n")
        data = self.initialize()
        self.assertTrue(data["files"][0]["parse_error"])
        with self.assertRaisesRegex(ValueError, "parse errors"):
            self.record()
        (self.root / "large.py").write_text("value = 1\n" * 100)
        self.options["max_file_bytes"] = 64
        data = self.initialize()
        self.assertTrue(data["scan_gaps"])
        self.assertEqual(coverage.verify(data)["status"], "incomplete")

    def test_omission_requires_a_reason_and_excluded_sources_are_listed(self):
        (self.root / ".env").write_text("not source")
        (self.root / "binary.dat").write_bytes(b"binary\0data")
        data = self.initialize()
        self.assertTrue({".env", "binary.dat"}.issubset({f["path"] for f in data["excluded"]}))
        with self.assertRaisesRegex(ValueError, "reason"):
            coverage.record(["app.py"], "omitted", [], [], "")
        coverage.record(["app.py"], "omitted", [], [], "Fixture is deliberately excluded from semantic notes.")
        self.assertEqual(coverage.verify()["omitted"], 1)
        self.assertEqual(coverage.verify()["status"], "notes_ready")

    def test_publication_requires_current_note_hash_and_source_specific_entity(self):
        self.initialize(); self.record()
        self.assertEqual(coverage.verify(published=True)["status"], "incomplete")
        with closing(sqlite3.connect(bootstrap.DATABASE_PATH)) as db:
            db.executescript((TOOLS / "schema.sql").read_text())
            db.execute("INSERT INTO extraction_results(source_doc,revision,result_path,accepted_at,source_hash) VALUES ('llm-wiki/application.md',1,'result.json',0,'wrong')")
            db.execute("INSERT INTO graph_nodes VALUES ('application','Application','FEATURE')")
            db.execute("INSERT INTO graph_entity_keys(node_id,entity_key) VALUES ('application','feature:application')")
            db.execute("INSERT INTO graph_node_sources VALUES ('application','llm-wiki/other.md','Another source')")
            db.commit()
            self.assertEqual(coverage.verify(published=True)["status"], "incomplete")
            db.execute("UPDATE extraction_results SET source_hash=?", (bootstrap.digest((self.notes / "application.md").read_text()),))
            db.execute("INSERT INTO graph_node_sources VALUES ('application','llm-wiki/application.md','The application returns three.')")
            db.commit()
        self.assertEqual(coverage.verify(published=True)["status"], "published")

    def test_relocated_cli_inventory_record_export_and_stale_detection(self):
        shutil.copytree(TOOLS, self.root / "tools", ignore=shutil.ignore_patterns(".venv", "__pycache__", "tests"))
        def run(script, *args, success=True):
            result = subprocess.run([sys.executable, str(self.root / "tools" / script), *args],
                                    cwd=self.root, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode == 0, success, result.stderr)
            return json.loads(result.stdout) if result.stdout else None
        run("bootstrap_knowledge.py", "start", "--exclude", "tools/**")
        run("bootstrap_knowledge.py", "read")
        self.assertEqual(run("source_coverage.py", "init")["symbols"], 1)
        self.topic()
        run("source_coverage.py", "record", "app.py", "--topic", "llm-wiki/application.md",
            "--entity", "feature:application", "--reason", "Reviewed source.")
        self.assertEqual(run("source_coverage.py", "verify")["status"], "notes_ready")
        output = self.root / "raw" / "catalog.json"
        run("source_coverage.py", "export", "--output", str(output))
        self.assertNotIn("project_root", json.loads(output.read_text()))
        (self.root / "app.py").write_text("def run():\n    return 4\n")
        self.assertEqual(run("source_coverage.py", "verify", success=False)["status"], "incomplete")


if __name__ == "__main__":
    unittest.main()
