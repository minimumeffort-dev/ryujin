from contextlib import redirect_stderr, redirect_stdout
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

import recall_graph
from paths import SCHEMA_PATH


class GraphRecallTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ryujin-recall-test-")
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "graph.sqlite3"
        self.database = sqlite3.connect(self.path, isolation_level=None)
        self.database.row_factory = sqlite3.Row
        self.addCleanup(self.database.close)
        self.database.execute("PRAGMA journal_mode = WAL")
        self.database.execute("PRAGMA foreign_keys = ON")
        self.database.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        patch = mock.patch.object(recall_graph, "DATABASE_PATH", self.path)
        patch.start()
        self.addCleanup(patch.stop)

    def node(self, name, kind="DOCUMENT"):
        node_id = f"{kind}:{name}"
        self.database.execute(
            "INSERT INTO graph_nodes (id, name, type) VALUES (?, ?, ?)",
            (node_id, name, kind),
        )
        self.database.execute(
            "INSERT INTO graph_node_sources (node_id, source_doc, description) VALUES (?, ?, ?)",
            (node_id, "llm-wiki/source.md", f"Details about {name}."),
        )
        return node_id

    def alias(self, node_id, alias, source="llm-wiki/source.md"):
        self.database.execute(
            "INSERT INTO graph_aliases (node_id, alias, source_doc) VALUES (?, ?, ?)",
            (node_id, alias, source),
        )

    def edge(self, source_id, target_id, predicate="references", source="llm-wiki/source.md"):
        self.database.execute(
            "INSERT INTO graph_edges (source_id, predicate, target_id, source_doc) VALUES (?, ?, ?, ?)",
            (source_id, predicate, target_id, source),
        )

    def test_aliases_are_case_insensitive_deduplicated_and_prefer_longest_match(self):
        node_id = self.node("Canonical policy", "POLICY")
        self.alias(node_id, "Policy")
        self.alias(node_id, "Policy", "llm-wiki/other.md")
        self.alias(node_id, "Policy guide")

        result = recall_graph.recall_graph(self.database, "Explain POLICY GUIDE and policy.")
        self.assertEqual(len(result["matches"]), 1)
        self.assertEqual(result["matches"][0]["id"], node_id)
        self.assertEqual(result["matches"][0]["matched_as"], "Policy guide")

    def test_literal_labels_word_boundaries_and_no_match(self):
        literal = self.node("Policy (v1)", "POLICY")
        schema = self.node("Database schema")
        self.alias(schema, "schema")

        matches = recall_graph.find_matches(self.database, "Explain POLICY (V1)")
        self.assertEqual([node["id"] for node in matches], [literal])
        self.assertEqual(recall_graph.find_matches(self.database, "policy v1"), [])
        self.assertEqual(recall_graph.find_matches(self.database, "schematic"), [])
        self.assertEqual(
            recall_graph.recall_graph(self.database, "unrelated question"),
            {
                "matches": [],
                "nodes": [],
                "edges": [],
                "matches_truncated": False,
                "edges_truncated": False,
                "traversal_limit_reached": False,
                "edges_examined": 0,
            },
        )

    def test_sql_filter_preserves_unicode_matching(self):
        street = self.node("Straße")
        plan = self.node("Annual plan")
        self.alias(plan, "Årsplan")

        matches = recall_graph.find_matches(self.database, "STRASSE and ÅRSPLAN")
        self.assertEqual({node["id"] for node in matches}, {street, plan})

    def test_sql_filter_does_not_materialize_unrelated_nodes(self):
        watcher = self.node("Watcher startup")
        launcher = self.node("Launcher")
        self.alias(launcher, "watcher")
        for index in range(100):
            self.node(f"Unrelated{index}")

        materialized = []

        def record_row(cursor, values):
            row = sqlite3.Row(cursor, values)
            materialized.append(row["id"])
            return row

        self.database.row_factory = record_row
        try:
            matches = recall_graph.find_matches(self.database, "Watcher startup")
        finally:
            self.database.row_factory = sqlite3.Row

        self.assertEqual({node["id"] for node in matches}, {watcher, launcher})
        self.assertCountEqual(materialized, [watcher, launcher])

    def test_incoming_and_outgoing_edges_keep_source_descriptions(self):
        policy = self.node("Refund policy", "POLICY")
        approver = self.node("Approver", "ROLE")
        handbook = self.node("Handbook")
        distant = self.node("Distant document")
        self.edge(policy, approver, "approved_by", "llm-wiki/policy.md")
        self.edge(handbook, policy, source="llm-wiki/handbook.md")
        self.edge(approver, distant)
        self.database.execute(
            "INSERT INTO graph_node_sources VALUES (?, ?, ?)",
            (policy, "llm-wiki/policy.md", "Refunds need approval."),
        )

        result = recall_graph.recall_graph(self.database, "Explain Refund policy")
        nodes = {node["id"]: node for node in result["nodes"]}
        self.assertEqual(set(nodes), {policy, approver, handbook})
        self.assertEqual(
            {item["source_doc"] for item in nodes[policy]["descriptions"]},
            {"llm-wiki/source.md", "llm-wiki/policy.md"},
        )
        self.assertEqual(
            {(edge["source"], edge["predicate"], edge["target"], edge["source_doc"])
             for edge in result["edges"]},
            {
                ("Refund policy", "approved_by", "Approver", "llm-wiki/policy.md"),
                ("Handbook", "references", "Refund policy", "llm-wiki/handbook.md"),
            },
        )

    def test_limits_report_truncation_and_relevant_neighbors_rank_first(self):
        names = [f"Topic{index}" for index in range(recall_graph.MAX_MATCHES + 1)]
        for name in names:
            self.node(name)
        limited = recall_graph.recall_graph(self.database, " ".join(names))
        self.assertEqual(len(limited["matches"]), recall_graph.MAX_MATCHES)
        self.assertTrue(limited["matches_truncated"])
        self.assertEqual(limited["edges"], [])

        watcher = self.node("Watch helper", "PROCESS")
        self.alias(watcher, "watcher")
        for index in range(recall_graph.MAX_EDGES + 1):
            self.edge(watcher, self.node(f"Arbitrary{index}"))
        relevant = self.node("Watcher startup procedure", "PROCESS")
        self.edge(watcher, relevant)

        result = recall_graph.recall_graph(self.database, "How does watcher startup work?")
        self.assertEqual(len(result["edges"]), recall_graph.MAX_EDGES)
        self.assertTrue(result["edges_truncated"])
        self.assertEqual(result["edges"][0]["target_id"], relevant)
        self.assertIn(relevant, {node["id"] for node in result["nodes"]})

    def test_configurable_hops_follow_chain_and_zero_keeps_only_seed(self):
        policy = self.node("Refund policy", "POLICY")
        role = self.node("Finance lead", "ROLE")
        person = self.node("Alice", "PERSON")
        self.edge(policy, role, "approved_by")
        self.edge(role, person, "held_by")

        zero = recall_graph.recall_graph(self.database, "Refund policy", hops=0)
        self.assertEqual([node["id"] for node in zero["nodes"]], [policy])
        self.assertEqual(zero["edges"], [])
        self.assertEqual(zero["edges_examined"], 0)

        one = recall_graph.recall_graph(self.database, "Refund policy", hops=1)
        self.assertEqual(len(one["edges"]), 1)
        self.assertEqual(one["edges"][0]["distance"], 1)

        two = recall_graph.recall_graph(self.database, "Refund policy", hops=2)
        self.assertEqual({node["id"] for node in two["nodes"]}, {policy, role, person})
        self.assertEqual(
            [(edge["predicate"], edge["distance"]) for edge in two["edges"]],
            [("approved_by", 1), ("held_by", 2)],
        )
        self.assertFalse(two["traversal_limit_reached"])

    def test_cycles_stop_and_traversal_budget_caps_examined_rows(self):
        start = self.node("Start")
        middle = self.node("Middle")
        end = self.node("End")
        self.edge(start, middle)
        self.edge(middle, end)
        self.edge(end, start)

        complete = recall_graph.recall_graph(self.database, "Start", hops=50)
        self.assertEqual(len(complete["edges"]), 3)
        self.assertEqual(complete["edges_examined"], 6)
        self.assertFalse(complete["traversal_limit_reached"])

        limited = recall_graph.recall_graph(
            self.database, "Start", hops=50, traversal_limit=2
        )
        self.assertEqual(limited["edges_examined"], 2)
        self.assertTrue(limited["traversal_limit_reached"])
        self.assertLessEqual(len(limited["edges"]), 2)

    def test_invalid_traversal_options_are_rejected(self):
        for options in ({"hops": -1}, {"traversal_limit": 0}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                recall_graph.recall_graph(self.database, "Anything", **options)

        for flags in (["--hops", "-1"], ["--traversal-limit", "0"]):
            with self.subTest(flags=flags), \
                 mock.patch.object(sys, "argv", ["recall_graph.py", "Anything", *flags]), \
                 redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    recall_graph.main()
            self.assertEqual(raised.exception.code, 2)

    def test_cli_connection_is_read_only(self):
        self.node("Original")

        def attempt_write(database, question, **options):
            database.execute("DELETE FROM graph_nodes")

        with mock.patch.object(sys, "argv", ["recall_graph.py", "Original"]), \
             mock.patch.object(recall_graph, "recall_graph", side_effect=attempt_write):
            with self.assertRaisesRegex(sqlite3.OperationalError, "readonly"):
                recall_graph.main()
        self.assertEqual(self.database.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0], 1)

    def test_missing_database_reports_error_without_creating_it(self):
        missing = self.path.parent / "missing.sqlite3"
        output = io.StringIO()
        with mock.patch.object(recall_graph, "DATABASE_PATH", missing), \
             mock.patch.object(sys, "argv", ["recall_graph.py", "Anything"]), \
             redirect_stderr(output):
            with self.assertRaises(SystemExit) as raised:
                recall_graph.main()
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("does not exist", output.getvalue())
        self.assertFalse(missing.exists())

    def test_cli_uses_one_snapshot_during_concurrent_graph_changes(self):
        original = self.node("Original label")
        self.edge(original, self.node("Related document"))
        find_edges = recall_graph.find_edges

        def change_graph(database, matches, question, **options):
            self.database.execute(
                "UPDATE graph_nodes SET name = ? WHERE id = ?",
                ("Renamed label", original),
            )
            return find_edges(database, matches, question, **options)

        output = io.StringIO()
        with mock.patch.object(sys, "argv", ["recall_graph.py", "Original label"]), \
             mock.patch.object(recall_graph, "find_edges", side_effect=change_graph), \
             redirect_stdout(output):
            recall_graph.main()
        result = json.loads(output.getvalue())
        self.assertEqual(result["matches"][0]["name"], "Original label")
        self.assertEqual(
            next(node["name"] for node in result["nodes"] if node["id"] == original),
            "Original label",
        )
        self.assertEqual(result["edges"][0]["source"], "Original label")
        self.assertEqual(
            self.database.execute("SELECT name FROM graph_nodes WHERE id = ?", (original,)).fetchone()[0],
            "Renamed label",
        )


if __name__ == "__main__":
    unittest.main()
