"""Question-level selective recall, provenance, bounded delivery and detail expansion."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import engineering_graph
import recall_graph
import recall_hook
from recall_selection import analyze_query, deduplicate

BEHAVIOR = "Every successful extraction acknowledgment rebuilds the graph atomically with result acceptance."
FEATURE = "feature:publication"
CODE = "code:src/publication.py#publish"
TEST = "code:tests/test_publication.py"


class SelectiveRecallTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="ryujin-selective-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.path = self.root / "graph.sqlite3"
        self.db = sqlite3.connect(self.path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.addCleanup(self.db.close)
        self.db.executescript((TOOLS / "schema.sql").read_text())
        patch = mock.patch.multiple(recall_hook, DATABASE_PATH=self.path,
                                    PROJECT_ROOT=self.root, RECALL_LOG_PATH=self.root / "recall.jsonl")
        patch.start(); self.addCleanup(patch.stop)
        self.add_source("llm-wiki/publication.md")

    def add_source(self, source, text=BEHAVIOR, state="current", key="fact:trigger", references=True):
        feature = {"key": FEATURE, "name": "Accepted-result publication", "type": "FEATURE", "description": "Atomic graph publication."}
        nodes = [feature]
        evidence = {"section": "Behavior", "excerpt": text}
        edges = []
        if references:
            nodes += [{"key": CODE, "name": "publish", "type": "CODE_ELEMENT", "description": "Publishes graph updates.",
                       "code": {"path": "src/publication.py", "symbol": "publish", "kind": "function"}},
                      {"key": TEST, "name": "Publication regression tests", "type": "CODE_ELEMENT", "description": "Checks publication.",
                       "code": {"path": "tests/test_publication.py", "kind": "test"}}]
            evidence["code_path"] = "src/publication.py"
            evidence["symbol"] = "publish"
            edges = [{"source": CODE, "target": FEATURE, "predicate": "implements", "facts": [key]},
                     {"source": TEST, "target": FEATURE, "predicate": "implements", "facts": [key]}]
        data = {"schema_version": 2, "source_doc": source, "nodes": nodes,
                "facts": [{"key": key, "subject": FEATURE, "kind": "behavior", "text": text,
                           "state": state, "evidence": [evidence]}], "edges": edges, "aliases": []}
        self.db.execute("INSERT INTO knowledge_sources VALUES (?, 'topic', 'same', 1, 0)", (source,))
        engineering_graph.insert_engineering(self.db, data)
        engineering_graph.index_graph(self.db)
        path = self.root / source; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Publication\n\n## Behavior\n\n" + text)

    def recall(self, question="how often do we rebuild our knowledge graph?", **options):
        return recall_graph.recall_graph(self.db, question, view="auto", **options)

    def hook(self, client, question, *options):
        out = io.StringIO()
        with mock.patch.object(sys, "argv", ["recall_hook.py", client, *options]), \
             mock.patch.object(sys, "stdin", io.StringIO(json.dumps({"prompt": question}))), redirect_stdout(out):
            recall_hook.main()
        return json.loads(out.getvalue())

    def test_original_question_and_explicit_references_in_brief_context(self):
        result = self.recall()
        context, delivery = recall_hook.format_recall(result)
        self.assertIn(BEHAVIOR, context)
        self.assertIn("src/publication.py#publish", context)
        self.assertIn("tests/test_publication.py", context)
        self.assertIn(FEATURE, context)
        self.assertEqual(delivery["facts_supplied"], 1)
        self.assertEqual(result["edges"], [])
        self.assertEqual(result["edges_examined"], 0)
        self.assertLessEqual(len(context), 2000)

    def test_vague_approval_and_unrelated_prompts_inject_nothing_for_all_clients(self):
        for question in ("What next?", "Solid plan, go ahead and implement it.", "Thanks!", "Bake sourdough bread"):
            for client in ("claude", "codex", "cursor"):
                with self.subTest(question=question, client=client):
                    self.assertEqual(self.hook(client, question), {"continue": True} if client == "cursor" else {})
        record = json.loads((self.root / "recall.jsonl").read_text().splitlines()[-1])
        self.assertEqual(record["context_characters"], 0)
        self.assertEqual(record["delivery"]["facts_supplied"], 0)
        self.assertIn("selection", record["retrieval"])

    def test_exact_path_and_qualified_symbol_select_the_code_identity(self):
        result = self.recall("Explain src/publication.py#publish")
        self.assertEqual(result["status"], "matched")
        self.assertTrue(any(m["id"] == engineering_graph.entity_id(CODE) for m in result["matches"]))
        analysis = analyze_query("Change src/publication.py#publish")
        self.assertIn("src/publication.py#publish", analysis["locators"])

    def test_cross_page_duplicate_retains_both_sources_in_log_and_citations(self):
        self.add_source("llm-wiki/architecture.md")
        result = self.recall()
        self.assertEqual(len(result["facts"]), 1)
        self.assertEqual(len(result["facts"][0]["sources"]), 2)
        context, delivery = recall_hook.format_recall(result)
        self.assertEqual(context.count(BEHAVIOR), 1)
        self.assertEqual(delivery["facts_supplied"], 1)
        self.assertEqual(delivery["source_pages_supplied"], 2)
        self.assertEqual(result["selection"]["deduplicated"], 1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM graph_facts").fetchone()[0], 2)

    def test_conflicting_numbers_negation_and_state_are_not_collapsed(self):
        variants = [("Retries allow 3 attempts.", "current"), ("Retries allow 5 attempts.", "current"),
                    ("Retries do not allow 3 attempts.", "current"), ("Retries allow 3 attempts.", "proposed")]
        for index, (text, state) in enumerate(variants):
            self.add_source(f"llm-wiki/retry-{index}.md", text, state, key=f"fact:retry-{index}")
        result = recall_graph.recall_graph(self.db, "retry attempts", fact_limit=20)
        self.assertEqual(len([f for f in result["facts"] if "Retries" in f["text"]]), 4)

    def test_attribution_and_code_identity_are_not_merged_by_text_normalization(self):
        fact = self.recall()["facts"][0]
        other = deepcopy(fact); other["node_id"] = "different-code"; other["entity_key"] = "code:src/other.py#publish"
        self.assertEqual(len(deduplicate([fact, other])), 2)
        other = deepcopy(fact); other["text"] = "Alice implemented publication."
        another = deepcopy(other); another["text"] = "Bob implemented publication."
        self.assertEqual(len(deduplicate([other, another])), 2)

    def test_stale_exact_source_is_suppressed_and_detail_retains_the_label(self):
        self.db.execute("INSERT INTO extraction_results(source_doc,revision,result_path,accepted_at,source_hash) VALUES (?,1,'old.json',0,'old')", ("llm-wiki/publication.md",))
        result = self.recall("Accepted-result publication")
        self.assertEqual(recall_hook.format_recall(result)[0], "")
        self.assertEqual(result["selection"]["rejected"][0]["reason"], "stale_source")
        detail = recall_graph.recall_graph(self.db, "Accepted-result publication")
        self.assertEqual(detail["facts"][0]["freshness"], "stale")

    def test_deleted_and_superseded_sources_are_ineligible_in_both_views(self):
        self.db.execute("UPDATE knowledge_sources SET active=0")
        for view in ("auto", "detail"):
            self.assertEqual(recall_graph.recall_graph(self.db, "Accepted-result publication", view=view)["facts"], [])
        self.db.execute("UPDATE knowledge_sources SET active=1")
        self.db.execute("UPDATE graph_facts SET state='superseded'")
        engineering_graph.index_graph(self.db)
        self.assertEqual(self.recall("Accepted-result publication")["facts"], [])

    def test_entity_expansion_fetches_neighbor_facts_without_guessing_test_paths(self):
        detail = recall_graph.recall_graph(self.db, "", entity=FEATURE, hops=2)
        self.assertTrue(detail["edges"])
        self.assertEqual(detail["facts"][0]["text"].strip(), BEHAVIOR)
        self.assertEqual(detail["matches"][0]["matched_as"], FEATURE)
        with self.assertRaisesRegex(ValueError, "Unknown canonical"):
            recall_graph.recall_graph(self.db, "", entity="feature:missing")
        self.db.execute("DELETE FROM graph_edge_facts WHERE source_id=?", (engineering_graph.entity_id(TEST),))
        self.db.execute("DELETE FROM graph_edges WHERE source_id=?", (engineering_graph.entity_id(TEST),))
        refs = self.recall()["facts"][0]["references"]
        self.assertFalse(any(r["path"].startswith("tests/") for r in refs))

    def test_small_budget_omits_whole_claims_and_counts_only_delivery(self):
        result = self.recall()
        context, delivery = recall_hook.format_recall(result, max_chars=100)
        self.assertEqual(context, "")
        self.assertEqual(delivery["facts_supplied"], 0)
        self.assertTrue(delivery["context_truncated"])
        self.assertEqual(self.hook("codex", "graph rebuild", "--max-context-chars", "100"), {})

    def test_oversized_fact_does_not_hide_a_later_fitting_fact(self):
        result = self.recall()
        long = deepcopy(result["facts"][0]); long["id"] = "long"; long["text"] *= 100
        result["facts"].insert(0, long)
        context, delivery = recall_hook.format_recall(result)
        self.assertEqual(delivery["facts_supplied"], 1)
        self.assertEqual(delivery["facts"][0]["fact_id"], result["facts"][1]["id"])
        self.assertEqual(context.count(BEHAVIOR), 1)

    def test_cli_entity_only_is_read_only_and_bounded(self):
        out = io.StringIO()
        with mock.patch.object(recall_graph, "DATABASE_PATH", self.path), \
             mock.patch.object(sys, "argv", ["recall_graph.py", "--entity", FEATURE, "--view", "detail", "--limit", "1"]), redirect_stdout(out):
            recall_graph.main()
        result = json.loads(out.getvalue())
        self.assertEqual(len(result["facts"]), 1)
        self.assertEqual(result["view"], "detail")
        self.assertEqual(self.db.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_inactive_alias_does_not_seed_an_active_entity(self):
        self.db.execute("INSERT INTO knowledge_sources VALUES ('llm-wiki/deleted.md','topic','x',0,0)")
        self.db.execute("INSERT INTO graph_aliases VALUES (?,?,?)",
                        (engineering_graph.entity_id(FEATURE), "Ghost feature", "llm-wiki/deleted.md"))
        self.assertEqual(recall_graph.find_matches(self.db, "Ghost feature"), [])
        self.assertTrue(recall_graph.find_matches(self.db, "Ghost feature", include_history=True))

    def test_heading_passages_are_not_automatic_evidence(self):
        fact = deepcopy(self.recall()["facts"][0])
        fact.update(id="heading", kind="passage", text="# Accepted-result publication")
        from recall_selection import select_facts
        selected, diagnostics = select_facts([fact], "Accepted-result publication",
                                              [{"id": fact["node_id"], "matched_as": "Accepted-result publication"}], automatic=True)
        self.assertEqual(selected, [])
        self.assertEqual(diagnostics["rejected"][0]["reason"], "navigation_only_passage")

    def test_same_page_identical_text_with_different_states_survives_candidate_loading(self):
        original = self.db.execute("SELECT id FROM graph_facts").fetchone()[0]
        self.db.execute(
            """INSERT INTO graph_facts SELECT id || '-proposed',node_id,'fact:proposed-trigger',
               kind,text,'proposed',lifecycle,rationale FROM graph_facts WHERE id=?""", (original,))
        self.db.execute(
            """INSERT INTO graph_fact_sources SELECT fact_id || '-proposed',source_doc,extraction_id,
               section,excerpt,code_path,symbol,git_ref,verification,attribution_basis
               FROM graph_fact_sources WHERE fact_id=?""", (original,))
        engineering_graph.index_graph(self.db)
        result = recall_graph.recall_graph(self.db, "", entity=FEATURE)
        self.assertEqual({f["state"] for f in result["facts"]}, {"current", "proposed"})


if __name__ == "__main__":
    unittest.main()
