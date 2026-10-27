from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock


TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

import consume_queue
import queue_store
import build_graph


class QueueCompletionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ryujin-completion-test-")
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        self.state = self.project / ".state"
        patches = mock.patch.multiple(
            queue_store,
            DATABASE_PATH=self.state / "ryujin.sqlite3",
            NOTES_DIR=self.project / "llm-wiki",
            PROJECT_ROOT=self.project,
            STATE_DIR=self.state,
        )
        patches.start()
        self.addCleanup(patches.stop)
        graph_patch = mock.patch.object(build_graph, "PROJECT_ROOT", self.project)
        graph_patch.start()
        self.addCleanup(graph_patch.stop)
        self.database = queue_store.open_database()
        self.addCleanup(self.database.close)

    def claim(self):
        queue_store.enqueue(self.database, {"path": "example.md"})
        return queue_store.claim(self.database, "test-worker")

    def candidate_path(self, job):
        return (
            self.state
            / "extractions"
            / str(job["id"])
            / str(job["claimed_revision"])
            / f"{job['claim_token']}.json"
        )

    def write_candidate(self, job, data=None):
        path = self.candidate_path(job)
        path.parent.mkdir(parents=True, exist_ok=True)
        if data is None:
            data = {
                "source_doc": "llm-wiki/example.md",
                "nodes": [],
                "edges": [],
                "aliases": [],
            }
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def acknowledge(self, job):
        return queue_store.acknowledge(
            self.database, job["id"], job["claim_token"]
        )

    def stored_job(self):
        return dict(self.database.execute("SELECT * FROM jobs").fetchone())

    def results(self):
        return [
            dict(row)
            for row in self.database.execute("SELECT * FROM extraction_results")
        ]

    def test_success_registers_result_and_replaces_it_on_next_revision(self):
        job = self.claim()
        first_path = self.write_candidate(job)
        self.assertEqual(self.acknowledge(job), "done")
        accepted = self.results()[0]
        self.assertEqual(accepted["source_doc"], "llm-wiki/example.md")
        self.assertEqual(accepted["revision"], job["claimed_revision"])
        self.assertEqual(
            accepted["result_path"], first_path.relative_to(self.project).as_posix()
        )
        self.assertGreater(accepted["accepted_at"], 0)
        self.assertEqual(self.stored_job()["state"], "done")
        self.assertIsNone(self.stored_job()["claim_token"])

        job = self.claim()
        next_path = self.write_candidate(job)
        self.assertEqual(self.acknowledge(job), "done")
        self.assertEqual(len(self.results()), 1)
        self.assertEqual(self.results()[0]["revision"], 2)
        self.assertEqual(
            self.results()[0]["result_path"],
            next_path.relative_to(self.project).as_posix(),
        )
        self.assertTrue(first_path.is_file())

        self.assertIsNone(self.acknowledge(job))
        self.assertTrue(next_path.is_file())

    def test_invalid_candidates_leave_the_job_claimed_without_accepting_results(self):
        job = self.claim()
        before = self.stored_job()
        path = self.candidate_path(job)
        path.parent.mkdir(parents=True)
        for text in (
            "{",
            "{}",
            json.dumps({
                "source_doc": "llm-wiki/wrong.md",
                "nodes": [], "edges": [], "aliases": [],
            }),
            json.dumps({
                "source_doc": "llm-wiki/example.md",
                "nodes": [],
                "edges": [{
                    "source": "Missing", "predicate": "references", "target": "Missing"
                }],
                "aliases": [],
            }),
        ):
            with self.subTest(candidate=text):
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    self.acknowledge(job)
                self.assertEqual(self.stored_job(), before)
                self.assertEqual(self.results(), [])
                self.assertFalse(self.database.in_transaction)

    def test_missing_candidate_leaves_the_job_claimed(self):
        job = self.claim()
        before = self.stored_job()
        with self.assertRaises(FileNotFoundError):
            self.acknowledge(job)
        self.assertEqual(self.stored_job(), before)
        self.assertEqual(self.results(), [])
        self.assertFalse(self.database.in_transaction)

    def test_changed_revision_returns_to_pending_and_preserves_previous_result(self):
        job = self.claim()
        self.write_candidate(job)
        self.assertEqual(self.acknowledge(job), "done")
        previous = self.results()

        job = self.claim()
        self.write_candidate(job, {})
        queue_store.enqueue(self.database, {"path": "example.md"})
        self.assertEqual(self.acknowledge(job), "pending")
        self.assertEqual(self.results(), previous)
        stored = self.stored_job()
        self.assertEqual(stored["revision"], 3)
        self.assertEqual(stored["attempts"], 0)
        self.assertIsNone(stored["claim_token"])

    def test_wrong_token_and_expired_lease_are_rejected_before_reading_json(self):
        job = self.claim()
        with mock.patch.object(queue_store, "load_extraction") as load:
            self.assertIsNone(
                queue_store.acknowledge(self.database, job["id"], "wrong-token")
            )
            self.database.execute("UPDATE jobs SET lease_until = 0")
            before = self.stored_job()
            self.assertIsNone(self.acknowledge(job))
            load.assert_not_called()
        self.assertEqual(self.stored_job(), before)
        self.assertEqual(self.results(), [])

    def test_lease_expiring_during_validation_cannot_publish_a_result(self):
        job = self.claim()
        self.write_candidate(job)
        before = self.stored_job()
        with mock.patch.object(
            queue_store.time,
            "time",
            side_effect=[job["lease_until"] - 1, job["lease_until"] + 1],
        ):
            self.assertIsNone(self.acknowledge(job))
        self.assertEqual(self.stored_job(), before)
        self.assertEqual(self.results(), [])

    def test_registration_failure_rolls_back_completion_and_keeps_previous_result(self):
        job = self.claim()
        self.write_candidate(job)
        self.assertEqual(self.acknowledge(job), "done")
        previous = self.results()

        job = self.claim()
        self.write_candidate(job)
        before = self.stored_job()
        self.database.execute(
            """
            CREATE TRIGGER reject_result BEFORE INSERT ON extraction_results
            BEGIN
                SELECT RAISE(ABORT, 'simulated registration failure');
            END
            """
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.acknowledge(job)
        self.assertEqual(self.stored_job(), before)
        self.assertEqual(self.results(), previous)
        self.assertFalse(self.database.in_transaction)

    def test_concurrent_acknowledgments_accept_one_result(self):
        job = self.claim()
        path = self.write_candidate(job)

        def acknowledge_once(_):
            database = queue_store.open_database()
            try:
                return queue_store.acknowledge(
                    database, job["id"], job["claim_token"]
                )
            finally:
                database.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(acknowledge_once, range(2)))
        self.assertCountEqual(outcomes, ["done", None])
        self.assertEqual(len(self.results()), 1)
        self.assertEqual(self.stored_job()["state"], "done")
        self.assertTrue(path.is_file())

    def test_successful_acknowledgment_builds_and_replaces_graph(self):
        job = self.claim()
        self.write_candidate(job, {
            "source_doc": "llm-wiki/example.md",
            "nodes": [
                {"name": "Doc", "type": "DOCUMENT", "description": "First version"},
                {"name": "Review", "type": "PROCESS", "description": "A process"},
            ],
            "edges": [{"source": "Doc", "predicate": "references", "target": "Review"}],
            "aliases": [{"entity": "Doc", "alias": "D"}],
        })
        self.assertEqual(self.acknowledge(job), "done")
        self.assertEqual(self.database.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0], 2)
        self.assertEqual(self.database.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0], 1)
        self.assertEqual(self.database.execute("SELECT COUNT(*) FROM graph_aliases").fetchone()[0], 1)
        self.assertEqual(build_graph.rebuild_graph(self.database)["documents"], 1)
        self.assertFalse(self.database.in_transaction)

        job = self.claim()
        self.write_candidate(job, {
            "source_doc": "llm-wiki/example.md",
            "nodes": [{"name": "Doc", "type": "DOCUMENT", "description": "Second version"}],
            "edges": [],
            "aliases": [],
        })
        self.assertEqual(self.acknowledge(job), "done")
        self.assertEqual(self.database.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0], 1)
        self.assertEqual(self.database.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0], 0)
        self.assertEqual(self.database.execute("SELECT COUNT(*) FROM graph_aliases").fetchone()[0], 0)
        self.assertEqual(
            self.database.execute("SELECT description FROM graph_node_sources").fetchone()[0],
            "Second version",
        )

    def test_graph_failure_rolls_back_acknowledgment_and_previous_graph(self):
        document = {
            "source_doc": "llm-wiki/example.md",
            "nodes": [{"name": "Doc", "type": "DOCUMENT", "description": "Original"}],
            "edges": [],
            "aliases": [],
        }
        job = self.claim()
        self.write_candidate(job, document)
        self.assertEqual(self.acknowledge(job), "done")
        previous_result = self.results()
        previous_nodes = [tuple(row) for row in self.database.execute("SELECT * FROM graph_nodes")]

        job = self.claim()
        self.write_candidate(job, document)
        before = self.stored_job()
        self.database.execute(
            """
            CREATE TRIGGER reject_graph BEFORE INSERT ON graph_nodes
            BEGIN
                SELECT RAISE(ABORT, 'simulated failure');
            END
            """
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.acknowledge(job)
        self.assertEqual(self.results(), previous_result)
        self.assertEqual(
            [tuple(row) for row in self.database.execute("SELECT * FROM graph_nodes")],
            previous_nodes,
        )
        self.assertEqual(self.stored_job(), before)
        self.assertFalse(self.database.in_transaction)

    def test_lease_expiring_during_graph_rebuild_rolls_back_all_changes(self):
        job = self.claim()
        self.write_candidate(job, {
            "source_doc": "llm-wiki/example.md",
            "nodes": [{"name": "Doc", "type": "DOCUMENT", "description": "Description"}],
            "edges": [],
            "aliases": [],
        })
        before = self.stored_job()
        with mock.patch.object(
            queue_store.time,
            "time",
            side_effect=[
                job["lease_until"] - 2,
                job["lease_until"] - 1,
                job["lease_until"] + 1,
            ],
        ):
            self.assertIsNone(self.acknowledge(job))
        self.assertEqual(self.stored_job(), before)
        self.assertEqual(self.results(), [])
        self.assertEqual(self.database.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0], 0)
        self.assertFalse(self.database.in_transaction)

    def test_concurrent_jobs_both_contribute_to_graph(self):
        for path in ("first.md", "second.md"):
            queue_store.enqueue(self.database, {"path": path})
        jobs = [queue_store.claim(self.database, f"worker-{index}") for index in range(2)]
        for job in jobs:
            self.write_candidate(job, {
                "source_doc": f"llm-wiki/{job['path']}",
                "nodes": [{"name": job["path"], "type": "DOCUMENT", "description": "Note"}],
                "edges": [],
                "aliases": [],
            })

        def acknowledge_job(job):
            database = queue_store.open_database()
            try:
                return queue_store.acknowledge(database, job["id"], job["claim_token"])
            finally:
                database.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(acknowledge_job, jobs))
        self.assertEqual(outcomes, ["done", "done"])
        self.assertEqual(
            {row["source_doc"] for row in self.results()},
            {"llm-wiki/first.md", "llm-wiki/second.md"},
        )
        self.assertEqual(
            {row["source_doc"] for row in self.database.execute("SELECT * FROM graph_node_sources")},
            {"llm-wiki/first.md", "llm-wiki/second.md"},
        )

    def test_cli_reports_missing_candidate_without_a_traceback(self):
        job = self.claim()
        before = self.stored_job()
        output = io.StringIO()
        with mock.patch.object(
            sys,
            "argv",
            ["consume_queue.py", "ack", str(job["id"]), "--token", job["claim_token"]],
        ), redirect_stderr(output), self.assertRaises(SystemExit) as raised:
            consume_queue.main()
        self.assertEqual(raised.exception.code, 2)
        self.assertIn(str(self.candidate_path(job)), output.getvalue())
        self.assertNotIn("Traceback", output.getvalue())
        self.assertEqual(self.stored_job(), before)
        self.assertEqual(self.results(), [])


if __name__ == "__main__":
    unittest.main()
