from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

import recall_graph
import recall_hook
from paths import SCHEMA_PATH


class RecallHookTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ryujin-recall-hook-test-")
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "graph.sqlite3"
        self.log_path = Path(temporary.name) / "recall_runs.jsonl"
        self.database = sqlite3.connect(self.path, isolation_level=None)
        self.addCleanup(self.database.close)
        self.database.execute("PRAGMA journal_mode = WAL")
        self.database.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.database.executemany(
            "INSERT INTO graph_nodes (id, name, type) VALUES (?, ?, ?)",
            [
                ("policy", "Refund policy", "POLICY"),
                ("role", "Finance lead", "ROLE"),
                ("person", "Alice", "PERSON"),
            ],
        )
        self.database.executemany(
            "INSERT INTO graph_edges VALUES (?, ?, ?, ?)",
            [
                ("policy", "approved_by", "role", "llm-wiki/policy.md"),
                ("role", "held_by", "person", "llm-wiki/roles.md"),
            ],
        )
        self.database.execute(
            "INSERT INTO graph_node_sources VALUES (?, ?, ?)",
            ("policy", "llm-wiki/policy.md", "Refunds need approval."),
        )
        patch = mock.patch.object(recall_hook, "DATABASE_PATH", self.path)
        patch.start()
        self.addCleanup(patch.stop)
        log_patch = mock.patch.object(recall_hook, "RECALL_LOG_PATH", self.log_path)
        log_patch.start()
        self.addCleanup(log_patch.stop)

    def records(self):
        return [json.loads(line) for line in self.log_path.read_text().splitlines()]

    def invoke(self, client, event, *, options=(), raw=None):
        output = io.StringIO()
        errors = io.StringIO()
        stdin = json.dumps(event) if raw is None else raw

        with mock.patch.object(sys, "argv", ["recall_hook.py", client, *options]), \
             mock.patch.object(sys, "stdin", io.StringIO(stdin)), \
             redirect_stdout(output), redirect_stderr(errors):
            recall_hook.main()

        return json.loads(output.getvalue()), errors.getvalue()

    def context(self, client, output):
        if client == "cursor":
            self.assertTrue(output["continue"])
            return output["additional_context"]
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        return output["hookSpecificOutput"]["additionalContext"]

    def assert_allowed_without_context(self, client, output):
        empty = {"continue": True} if client == "cursor" else {}
        if output != empty:
            context = self.context(client, output)
            self.assertIn("Ryujin recall status:", context)
            self.assertIn("llm-wiki/index.md", context)
            self.assertNotIn("decision", output)

    def test_clients_receive_two_hop_facts_types_and_sources(self):
        for client in ("claude", "codex", "cursor"):
            with self.subTest(client=client):
                output, errors = self.invoke(
                    client, {"prompt": "Explain Refund policy"}, options=("--view", "detail", "--hops", "2")
                )
                context = self.context(client, output)
                self.assertIn("Refund policy (POLICY)", context)
                self.assertIn("Finance lead (ROLE) --held_by--> Alice (PERSON)", context)
                self.assertIn("[source: llm-wiki/roles.md]", context)
                self.assertIn("Refunds need approval.", context)
                self.assertIn("reference data", context)
                self.assertEqual(errors, "")
                record = self.records()[-1]
                self.assertEqual(record["client"], client)
                self.assertEqual(record["context"], context)
                self.assertEqual(record["context_characters"], len(context))
                self.assertEqual(record["status"], "matched")
                self.assertEqual(record["hops"], 2)
                self.assertEqual(record["traversal_limit"], 100)
                self.assertEqual(record["error"], None)
                delivery = record["delivery"]
                self.assertEqual(delivery["facts_supplied"], 0)
                self.assertEqual(delivery["relationships_supplied"], 2)
                self.assertEqual(delivery["excerpts_supplied"], 1)
                self.assertEqual(delivery["source_pages_supplied"], 2)
                self.assertEqual(delivery["usage"], "not_assessed")
                self.assertNotIn("systemMessage", output)
                self.assertIn("person", {node["id"] for node in record["retrieval"]["nodes"]})
                self.assertEqual(record["retrieval"]["edges"][1]["source_doc"], "llm-wiki/roles.md")
        self.assertEqual(len(self.records()), 3)

    def test_unmatched_and_empty_prompts_allow_submission(self):
        for client in ("claude", "codex", "cursor"):
            for event in ({}, {"prompt": ""}, {"prompt": "  "}, {"prompt": None}, {"prompt": "Unknown topic"}):
                with self.subTest(client=client, event=event):
                    output, errors = self.invoke(client, event)
                    self.assert_allowed_without_context(client, output)
                    self.assertEqual(errors, "")
                    record = self.records()[-1]
                    self.assertEqual(record["status"], "no_matches" if event.get("prompt") == "Unknown topic" else "no_prompt")
                    self.assertEqual(record["prompt"], event.get("prompt"))
                    self.assertEqual(record["context"], "")

    def test_missing_database_is_not_created(self):
        missing = self.path.parent / "missing.sqlite3"
        with mock.patch.object(recall_hook, "DATABASE_PATH", missing):
            for client in ("claude", "codex", "cursor"):
                with self.subTest(client=client):
                    output, errors = self.invoke(client, {"prompt": "Refund policy"})
                    self.assert_allowed_without_context(client, output)
                    self.assertEqual(errors, "")
                    self.assertEqual(self.records()[-1]["status"], "missing_database")
                    self.assertIsNone(self.records()[-1]["retrieval"])
        self.assertFalse(missing.exists())

    def test_database_errors_allow_submission_and_report_to_stderr(self):
        broken = self.path.parent / "broken.sqlite3"
        broken.write_text("Not a SQLite database")
        with mock.patch.object(recall_hook, "DATABASE_PATH", broken):
            for client in ("claude", "codex", "cursor"):
                with self.subTest(client=client):
                    output, errors = self.invoke(client, {"prompt": "Refund policy"})
                    self.assert_allowed_without_context(client, output)
                    self.assertIn("Ryujin recall failed:", errors)
                    record = self.records()[-1]
                    self.assertEqual(record["status"], "error")
                    self.assertIn("status: error", record["context"])
                    self.assertIn("not a database", record["error"])

    def test_malformed_events_allow_submission_and_report_to_stderr(self):
        for client in ("claude", "codex", "cursor"):
            for raw in ("", "{invalid", "[]"):
                with self.subTest(client=client, raw=raw):
                    output, errors = self.invoke(client, None, raw=raw)
                    self.assert_allowed_without_context(client, output)
                    self.assertIn("Ryujin recall failed:", errors)
                    self.assertEqual(self.records()[-1]["status"], "error")
                    self.assertIsNotNone(self.records()[-1]["error"])

    def test_hook_database_connection_rejects_writes(self):
        def attempt_write(database, prompt, **options):
            database.execute("DELETE FROM graph_nodes")

        with mock.patch.object(recall_hook, "recall_graph", side_effect=attempt_write):
            output, errors = self.invoke("codex", {"prompt": "Refund policy"}, options=("--view", "detail"))

        self.assert_allowed_without_context("codex", output)
        self.assertIn("readonly", errors)
        self.assertEqual(self.database.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0], 3)

    def test_hook_keeps_one_snapshot_during_graph_updates(self):
        find_edges = recall_graph.find_edges

        def change_graph(database, matches, question, **options):
            self.database.execute(
                "UPDATE graph_nodes SET name = 'Renamed policy' WHERE id = 'policy'"
            )
            return find_edges(database, matches, question, **options)

        with mock.patch.object(recall_graph, "find_edges", side_effect=change_graph):
            output, errors = self.invoke("codex", {"prompt": "Refund policy"}, options=("--view", "detail"))

        context = self.context("codex", output)
        self.assertIn("Refund policy (POLICY)", context)
        self.assertNotIn("Renamed policy", context)
        self.assertEqual(errors, "")
        record = self.records()[-1]
        self.assertEqual(record["context"], context)
        self.assertEqual(
            self.database.execute("SELECT name FROM graph_nodes WHERE id = 'policy'").fetchone()[0],
            "Renamed policy",
        )

    def test_log_preserves_prompt_and_session_metadata_without_extra_lines(self):
        for client in ("claude", "codex", "cursor"):
            with self.subTest(client=client):
                event = {
                    "prompt": "Explain Refund policy\nこんにちは 🐉",
                    "turn_id": "turn-123",
                    "hook_event_name": "beforeSubmitPrompt" if client == "cursor" else "UserPromptSubmit",
                    "conversation_id" if client == "cursor" else "session_id": f"{client}-session",
                }
                self.invoke(client, event)
                record = self.records()[-1]
                self.assertEqual(record["prompt"], event["prompt"])
                self.assertEqual(record["session_id"], f"{client}-session")
                self.assertEqual(record["turn_id"], "turn-123")
                self.assertEqual(record["hook_event_name"], event["hook_event_name"])
                self.assertTrue(record["timestamp"].endswith("+00:00"))
        self.assertEqual(len(self.records()), 3)

    def test_log_failure_preserves_hook_context_and_reports_to_stderr(self):
        with mock.patch.object(recall_hook, "RECALL_LOG_PATH", self.path / "recall_runs.jsonl"):
            for client in ("claude", "codex", "cursor"):
                with self.subTest(client=client):
                    output, errors = self.invoke(client, {"prompt": "Refund policy"})
                    self.assertIn("Refund policy", self.context(client, output))
                    self.assertIn("Ryujin recall log failed:", errors)

    def test_concurrent_processes_append_complete_records(self):
        script = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import recall_hook
recall_hook.RECALL_LOG_PATH = Path(sys.argv[2])
for index in range(10):
    recall_hook.append_recall_log({
        'worker': sys.argv[3],
        'index': index,
        'context': 'Knowledge 🐉\\n' * 2000,
    })
"""
        processes = [
            subprocess.Popen(
                [sys.executable, "-c", script, str(TOOLS_DIR), str(self.log_path), str(worker)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for worker in range(4)
        ]
        for process in processes:
            self.addCleanup(process.wait)
            self.addCleanup(process.kill if process.poll() is None else lambda: None)
        for process in processes:
            stdout, stderr = process.communicate(timeout=15)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertEqual(stdout, "")
        records = self.records()
        self.assertEqual(len(records), 40)
        self.assertEqual(
            {(record["worker"], record["index"]) for record in records},
            {(str(worker), index) for worker in range(4) for index in range(10)},
        )
        self.assertTrue(all(record["context"] == "Knowledge 🐉\n" * 2000 for record in records))

    def test_hop_and_traversal_options_control_context(self):
        output, errors = self.invoke(
            "codex", {"prompt": "Refund policy"}, options=("--view", "detail", "--hops", "0")
        )
        context = self.context("codex", output)
        self.assertIn("Refunds need approval.", context)
        self.assertNotIn("Finance lead", context)
        self.assertEqual(errors, "")

        output, errors = self.invoke(
            "codex", {"prompt": "Refund policy"},
            options=("--view", "detail", "--hops", "2", "--traversal-limit", "1"),
        )
        context = self.context("codex", output)
        self.assertIn("results are partial", context)
        self.assertIn("Finance lead", context)
        self.assertNotIn("Alice", context)
        self.assertEqual(errors, "")

    def test_long_context_stays_within_limit_and_marks_omission(self):
        self.database.execute(
            "UPDATE graph_node_sources SET description = ?", ("Knowledge " * 1000,)
        )
        output, errors = self.invoke("codex", {"prompt": "Refund policy"}, options=("--view", "detail"))
        context = self.context("codex", output)
        self.assertLessEqual(len(context), recall_hook.MAX_CONTEXT_CHARS)
        self.assertTrue(context.endswith("[Additional context omitted.]"))
        self.assertIn("[source: llm-wiki/policy.md]", context)
        self.assertEqual(errors, "")
        record = self.records()[-1]
        self.assertEqual(record["context"], context)
        policy = next(node for node in record["retrieval"]["nodes"] if node["id"] == "policy")
        self.assertGreater(len(policy["descriptions"][0]["description"]), recall_hook.MAX_CONTEXT_CHARS)


class RecallDeliveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ryujin-source-links-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "host project (with spaces)"
        self.notes = self.root / "llm-wiki"
        self.notes.mkdir(parents=True)
        (self.notes / "publication.md").write_text(
            "# Publication\n\n## Behavior\n\nPublication is atomic.\n\n## Design [v2]\n\nKeep evidence.\n"
        )
        patch = mock.patch.object(recall_hook, "PROJECT_ROOT", self.root)
        patch.start()
        self.addCleanup(patch.stop)

    def fact(self, identity, text, section="Behavior", source="llm-wiki/publication.md"):
        return {"id": identity, "title": "Publication", "text": text,
                "state": "current", "lifecycle": "implemented", "freshness": "snapshot",
                "source_doc": source, "evidence": [{"section": section}]}

    def result(self, *facts, **extra):
        return {"matches": [{"id": "publication"}], "nodes": [], "edges": [],
                "facts": list(facts), "status": "matched", "matches_truncated": False,
                "edges_truncated": False, "traversal_limit_reached": False, **extra}

    def test_counts_distinct_pages_and_links_exact_source_sections(self):
        context, delivery = recall_hook.format_recall(self.result(
            self.fact("atomic", "Publication is atomic."),
            self.fact("evidence", "Keep evidence.", "Design [v2]"),
        ))
        self.assertEqual(delivery["facts_supplied"], 2)
        self.assertEqual(delivery["source_pages_supplied"], 1)
        self.assertEqual([c["line"] for c in delivery["citations"]], [3, 7])
        target = str((self.notes / "publication.md").resolve())
        self.assertIn(f"[Behavior](<{target}:3>)", context)
        self.assertIn(f"[Design \\[v2\\]](<{target}:7>)", context)
        self.assertEqual(delivery["facts"], [
            {"label": "F1", "fact_id": "atomic", "citation": "S1"},
            {"label": "F2", "fact_id": "evidence", "citation": "S2"},
        ])
        self.assertEqual(delivery["usage"], "not_assessed")
        self.assertIn("Respect explicit user response-format constraints", context)

    def test_oversized_facts_are_not_counted_or_cut_into_incomplete_claims(self):
        context, delivery = recall_hook.format_recall(self.result(
            self.fact("too-long", "UNSUPPLIED " * 2000, source="llm-wiki/omitted.md"),
            self.fact("small", "Publication is atomic."),
        ))
        self.assertLessEqual(len(context), recall_hook.MAX_CONTEXT_CHARS)
        self.assertNotIn("UNSUPPLIED", context)
        self.assertNotIn("omitted.md", context)
        self.assertIn("Publication is atomic.", context)
        self.assertEqual(delivery["facts_supplied"], 1)
        self.assertEqual(delivery["source_pages_supplied"], 1)
        self.assertEqual(delivery["facts"][0]["fact_id"], "small")
        self.assertEqual(re.findall(r"^- \[(F\d+);", context, re.M), ["F1"])
        self.assertTrue(delivery["partial"])
        self.assertTrue(delivery["context_truncated"])
        self.assertTrue(context.endswith("[Additional context omitted.]"))

    def test_upstream_partial_flag_is_separate_from_context_omission(self):
        context, delivery = recall_hook.format_recall(self.result(
            self.fact("atomic", "Publication is atomic."), matches_truncated=True,
        ))
        self.assertTrue(delivery["partial"])
        self.assertFalse(delivery["context_truncated"])
        self.assertIn("results are partial", context)
        self.assertNotIn("[Additional context omitted.]", context)

    def test_full_text_passages_are_counted_as_excerpts_rather_than_facts(self):
        passage = self.fact("passage:publication", "# Publication\n\n")
        passage["kind"] = "passage"
        passage["title"] = "Publication"
        passage["evidence"] = []
        context, delivery = recall_hook.format_recall(self.result(
            self.fact("atomic", "Publication is atomic."), passage,
        ))
        self.assertEqual(delivery["facts_supplied"], 1)
        self.assertEqual(delivery["excerpts_supplied"], 1)
        self.assertEqual(delivery["source_pages_supplied"], 1)
        self.assertEqual(delivery["excerpts"][0]["record_id"], "passage:publication")
        self.assertIn("[P1; S2]", context)
        self.assertEqual(delivery["citations"][1]["line"], 1)

    def test_misses_supply_no_evidence_or_graph_use_claim(self):
        context, delivery = recall_hook.format_recall({
            "matches": [], "facts": [], "status": "no_matches",
        })
        self.assertEqual(delivery["facts_supplied"], 0)
        self.assertEqual(delivery["citations"], [])
        self.assertEqual(delivery["usage"], "not_assessed")
        self.assertIn("do not show a graph-use callout", context)

    def test_source_links_do_not_invent_heading_lines_or_read_outside_project(self):
        missing = recall_hook.citation("llm-wiki/publication.md", "Missing heading")
        self.assertIsNone(missing["line"])
        self.assertNotIn(":1>", missing["markdown"])
        with mock.patch.object(Path, "read_text") as read:
            outside = recall_hook.citation("../private.md", "Secret")
            read.assert_not_called()
        self.assertEqual(outside["markdown"], "../private.md#Secret")


if __name__ == "__main__":
    unittest.main()
