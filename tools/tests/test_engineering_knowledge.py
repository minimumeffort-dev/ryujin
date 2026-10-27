"""Engineering-memory contracts, migration preservation and question-level regressions."""
from copy import deepcopy
from contextlib import closing, redirect_stdout
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(TOOLS))
import build_graph
import queue_store
import recall_graph
import recall_hook
from extraction.validate import validate_extraction
from migrations import digest
from source_sync import synchronize_sources

QUESTION = "how often do we rebuild our knowledge graph?"
BEHAVIOR = ("Every successful extraction acknowledgment rebuilds the graph in the same "
            "SQLite transaction as result acceptance and job completion.")
NOTE = "# Publication\n\n## Behavior\n\n" + BEHAVIOR + "\nImplementation: tools/queue_store.py#acknowledge.\n"


def document(source="llm-wiki/publication.md", behavior=BEHAVIOR):
    return {
        "schema_version":2,"source_doc":source,
        "nodes":[
            {"key":"feature:publication","name":"Accepted-result publication","type":"FEATURE",
             "description":"Atomically publishes accepted engineering knowledge."},
            {"key":"code:tools/queue_store.py#acknowledge","name":"acknowledge",
             "type":"CODE_ELEMENT","description":"Publishes the accepted extraction.",
             "code":{"path":"tools/queue_store.py","symbol":"acknowledge","kind":"function"}},
        ],
        "facts":[{"key":"fact:publication-trigger","subject":"feature:publication",
                  "kind":"behavior","text":behavior,"state":"current","lifecycle":"implemented",
                  "evidence":[{"section":"Behavior","excerpt":behavior,
                               "code_path":"tools/queue_store.py","symbol":"acknowledge"}]}],
        "edges":[{"source":"code:tools/queue_store.py#acknowledge","predicate":"implements",
                  "target":"feature:publication","facts":["fact:publication-trigger"]}],
        "aliases":[],
    }


class EngineeringKnowledgeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ryujin-engineering-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.notes = self.root/"llm-wiki"
        self.notes.mkdir()
        self.state = self.root/".state"
        self.path = self.state/"ryujin.sqlite3"
        patch = mock.patch.multiple(queue_store,DATABASE_PATH=self.path,NOTES_DIR=self.notes,
                                    PROJECT_ROOT=self.root,STATE_DIR=self.state)
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.object(build_graph,"PROJECT_ROOT",self.root)
        patch.start()
        self.addCleanup(patch.stop)
        self.db = queue_store.open_database()
        self.addCleanup(self.db.close)

    def sync(self):
        return synchronize_sources(self.db,self.notes,self.root,TOOLS/"extraction/prompt.md")

    def candidate(self, job, data):
        path = self.state/"extractions"/str(job["id"])/str(job["claimed_revision"])/(job["claim_token"]+".json")
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(data),encoding="utf-8")
        return path

    def publish(self, data=None, note=NOTE, filename="publication.md"):
        (self.notes/filename).write_text(note,encoding="utf-8")
        self.sync()
        job = queue_store.claim(self.db,"test-agent")
        self.assertIsNotNone(job)
        data = data or document("llm-wiki/"+filename)
        path = self.candidate(job,data)
        self.assertEqual(queue_store.acknowledge(self.db,job["id"],job["claim_token"]),"done")
        return job,path

    def recall(self, question=QUESTION, **options):
        self.db.execute("BEGIN")
        try:
            return recall_graph.recall_graph(self.db,question,**options)
        finally:
            self.db.execute("ROLLBACK")

    def test_original_question_retrieves_fact_without_exact_entity_name(self):
        self.publish()
        self.assertEqual(recall_graph.find_matches(self.db,QUESTION),[])
        result = self.recall()
        self.assertEqual(result["status"],"matched")
        self.assertEqual(result["facts"][0]["text"].strip(),BEHAVIOR)
        self.assertEqual(result["facts"][0]["evidence"][0]["symbol"],"acknowledge")
        self.assertEqual(result["facts"][0]["freshness"],"snapshot")
        context = recall_hook.format_context(result)
        self.assertIn(BEHAVIOR,context)
        self.assertIn("tools/queue_store.py#acknowledge",context)
        self.assertIn("llm-wiki/publication.md#Behavior",context)
        self.assertLessEqual(len(context),recall_hook.MAX_CONTEXT_CHARS)
        self.assertEqual(self.db.execute("PRAGMA foreign_key_check").fetchall(),[])

    def test_client_hooks_receive_fact_or_explicit_miss_status(self):
        self.publish()
        for client in ("claude","codex","cursor"):
            for question in (QUESTION,"zeppelins marmalade"):
                out = io.StringIO()
                with mock.patch.object(recall_hook,"DATABASE_PATH",self.path), \
                     mock.patch.object(recall_hook,"RECALL_LOG_PATH",self.state/"test-recall.jsonl"), \
                     mock.patch.object(sys,"argv",["recall_hook.py",client]), \
                     mock.patch.object(sys,"stdin",io.StringIO(json.dumps({"prompt":question}))), \
                     redirect_stdout(out):
                    recall_hook.main()
                output = json.loads(out.getvalue())
                context = output["additional_context"] if client=="cursor" else output["hookSpecificOutput"]["additionalContext"]
                self.assertIn(BEHAVIOR if question==QUESTION else "no_matches",context)
                self.assertNotIn("decision",output)

    def test_hash_reconciliation_is_idempotent_and_skips_index_log(self):
        self.publish()
        (self.notes/"index.md").write_text("# Navigation")
        (self.notes/"log.md").write_text("# Ledger")
        original = self.db.execute("SELECT revision FROM jobs").fetchone()[0]
        for _ in range(3):
            self.assertEqual(self.sync(),[])
        self.assertEqual(self.db.execute("SELECT revision FROM jobs").fetchone()[0],original)
        self.assertEqual(self.db.execute("SELECT count(*) FROM jobs").fetchone()[0],1)
        (self.notes/"publication.md").write_text(NOTE+"\nChanged note.\n")
        self.assertEqual(len(self.sync()),1)
        self.assertEqual(self.recall()["facts"][0]["freshness"],"stale")

    def test_unobserved_edit_cannot_publish_stale_claim(self):
        (self.notes/"publication.md").write_text(NOTE)
        self.sync()
        job = queue_store.claim(self.db,"test")
        self.candidate(job,document())
        (self.notes/"publication.md").write_text(NOTE+"\nAn edit before watcher delivery.\n")
        self.assertEqual(queue_store.acknowledge(self.db,job["id"],job["claim_token"]),"pending")
        self.assertEqual(self.db.execute("SELECT count(*) FROM extraction_results").fetchone()[0],0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM extraction_runs").fetchone()[0],0)

    def test_source_snapshot_preserves_history_and_evidence_after_edit(self):
        _,original = self.publish()
        replacement = "Accepted results are now published by an explicit synchronization command."
        data = document(behavior=replacement)
        data["facts"][0]["key"]="fact:manual-publication"
        data["facts"][0]["supersedes"]=["fact:publication-trigger"]
        data["edges"][0]["facts"]=["fact:manual-publication"]
        self.publish(data,note=NOTE.replace(BEHAVIOR,replacement))
        self.assertTrue(original.exists())
        self.assertEqual(self.db.execute("SELECT count(*) FROM extraction_runs").fetchone()[0],2)
        old_fact=next(f for f in self.recall(include_history=True)["facts"] if BEHAVIOR in f["text"])
        self.assertEqual(old_fact["source_hash"],digest(NOTE))
        old_run=self.db.execute("SELECT id FROM extraction_runs ORDER BY accepted_at LIMIT 1").fetchone()[0]
        self.assertEqual(old_fact["extraction_id"],old_run)
        self.assertEqual(old_fact["state"],"historical")
        self.assertFalse(any(BEHAVIOR in f["text"] for f in self.recall()["facts"]))
        self.assertEqual(self.db.execute("SELECT source_snapshot FROM extraction_runs ORDER BY accepted_at LIMIT 1").fetchone()[0],NOTE)

    def test_deleted_source_is_hidden_but_other_support_survives(self):
        self.publish()
        self.publish(document("llm-wiki/other.md"),filename="other.md")
        (self.notes/"publication.md").unlink()
        self.sync()
        result = self.recall()
        self.assertTrue(result["facts"])
        self.assertTrue(all(f["source_doc"]=="llm-wiki/other.md" for f in result["facts"]))
        history = self.recall(include_history=True)
        self.assertTrue(any(f["source_doc"]=="llm-wiki/publication.md" and f["state"]=="historical"
                            for f in history["facts"]))

    def test_same_named_symbols_keep_distinct_canonical_identity(self):
        data = document()
        other = deepcopy(data["nodes"][1])
        other["key"]="code:other/store.py#acknowledge"
        other["code"]["path"]="other/store.py"
        data["nodes"].append(other)
        data["edges"].append({**data["edges"][0],"source":other["key"]})
        self.publish(data)
        identities = list(self.db.execute("SELECT id FROM graph_nodes WHERE name='acknowledge'"))
        self.assertEqual(len(identities),2)
        self.assertNotEqual(identities[0][0],identities[1][0])

    def test_superseded_facts_do_not_return_through_exact_seeds_or_passages(self):
        data=document()
        data["nodes"].append({"key":"feature:retired-publication","name":"Retired publication",
                              "type":"FEATURE","description":"Previous publication behavior."})
        old_text="Retired publication used a nightly graph rebuild."
        data["facts"].append({"key":"fact:nightly-publication","subject":"feature:retired-publication",
            "kind":"behavior","text":old_text,"state":"current",
            "evidence":[{"section":"Behavior","excerpt":old_text}]})
        data["facts"][0]["supersedes"]=["fact:nightly-publication"]
        self.publish(data,note=NOTE+"\n"+old_text+"\n")
        self.assertEqual(recall_graph.find_matches(self.db,"Retired publication"),[])
        self.assertEqual(self.recall("nightly")["status"],"no_matches")
        self.assertTrue(any(f["state"]=="superseded" for f in self.recall("nightly",include_history=True)["facts"]))

    def test_attribution_roles_are_supported_and_not_inferred_from_git_authorship(self):
        data = document()
        actor={"key":"person:mira","name":"Mira","type":"PERSON","description":"Explicitly named project contributor."}
        data["nodes"].append(actor)
        excerpt="Mira implemented acknowledge."
        fact={"key":"fact:implementation-author","subject":data["nodes"][1]["key"],
              "kind":"ownership","text":excerpt,"state":"current",
              "evidence":[{"section":"Attribution","excerpt":excerpt,
                           "attribution_basis":"explicit_statement","git_ref":"abc123"}]}
        data["facts"].append(fact)
        data["edges"].append({"source":fact["subject"],"predicate":"implemented_by",
                              "target":actor["key"],"facts":[fact["key"]]})
        self.publish(data,note=NOTE+"\n## Attribution\n\n"+excerpt+"\n")
        result=self.recall("Who implemented acknowledge?",hops=2)
        self.assertTrue(any(e["predicate"]=="implemented_by" and e["target"]=="Mira" for e in result["edges"]))
        self.assertTrue(any(f["kind"]=="ownership" for f in result["facts"]))
        invalid=deepcopy(data)
        invalid["facts"][1]["evidence"][0]["attribution_basis"]="git_author"
        with self.assertRaisesRegex(ValueError,"authorship is not ownership"):
            validate_extraction(invalid,data["source_doc"])
        invalid["edges"][-1]["predicate"]="owned_by"
        with self.assertRaises(ValueError):
            validate_extraction(invalid,data["source_doc"])
        invalid["edges"][-1]["predicate"]="authored_by"
        validate_extraction(invalid,data["source_doc"])

    def test_decision_maker_and_maintainer_remain_separate(self):
        data=document()
        data["nodes"] += [
            {"key":"decision:atomic","name":"Atomic publication","type":"DECISION","description":"Recorded decision."},
            {"key":"person:mira","name":"Mira","type":"PERSON","description":"Recorded decision maker."},
            {"key":"team:core","name":"Core team","type":"TEAM","description":"Explicit ongoing maintainer."},
        ]
        for key,subject,statement in [
            ("fact:decider","decision:atomic","Mira decided to use atomic publication."),
            ("fact:maintainer",data["nodes"][1]["key"],"Core team maintains acknowledge."),
        ]:
            data["facts"].append({"key":key,"subject":subject,"kind":"ownership","text":statement,
                "state":"current","evidence":[{"section":"Attribution","excerpt":statement,
                                             "attribution_basis":"explicit_statement"}]})
        data["edges"] += [
            {"source":"decision:atomic","predicate":"decided_by","target":"person:mira","facts":["fact:decider"]},
            {"source":data["nodes"][1]["key"],"predicate":"maintained_by","target":"team:core","facts":["fact:maintainer"]},
        ]
        note=NOTE+"\n## Attribution\n\nMira decided to use atomic publication.\nCore team maintains acknowledge.\n"
        self.publish(data,note=note)
        self.assertEqual(set(row[0] for row in self.db.execute(
            "SELECT predicate FROM graph_edges WHERE predicate IN ('decided_by','maintained_by','owned_by')")),
            {"decided_by","maintained_by"})
        self.assertIn("Mira",recall_hook.format_context(self.recall("Who decided atomic publication?",hops=2)))

    def test_invalid_evidence_and_endpoint_contracts_are_rejected(self):
        data=document()
        data["facts"][0]["evidence"][0]["excerpt"]="Fabricated fact."
        with self.assertRaisesRegex(ValueError,"excerpt"):
            validate_extraction(data,data["source_doc"],source_text=NOTE)
        data=document()
        data["edges"][0]["predicate"]="decided_by"
        with self.assertRaisesRegex(ValueError,"endpoint types"):
            validate_extraction(data,data["source_doc"],source_text=NOTE)

    def test_query_syntax_is_data_and_unrelated_questions_miss(self):
        self.publish()
        result=self.recall('graph" OR (rebuild) NEAR(**')
        self.assertEqual(result["status"],"matched")
        self.assertEqual(self.recall("zeppelins marmalade")["status"],"no_matches")
        self.assertEqual(self.recall("Why not?")["status"],"no_matches")

    def test_failed_v2_graph_publication_rolls_back_archive_and_search(self):
        (self.notes/"publication.md").write_text(NOTE)
        self.sync()
        job=queue_store.claim(self.db,"test")
        self.candidate(job,document())
        self.db.execute("""CREATE TRIGGER reject_facts BEFORE INSERT ON graph_facts
                           BEGIN SELECT RAISE(ABORT,'failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            queue_store.acknowledge(self.db,job["id"],job["claim_token"])
        for table in ("extraction_runs","extraction_results","knowledge_search","graph_nodes"):
            self.assertEqual(self.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0],0)

    def test_v1_database_migration_backs_up_and_preserves_claims_and_knowledge(self):
        self.db.close()
        self.path.unlink()
        baseline=(TOOLS/"schema.sql").read_text().split("CREATE TABLE IF NOT EXISTS schema_migrations")[0]
        baseline=baseline.replace(",\n    source_hash TEXT,\n    schema_version INTEGER NOT NULL DEFAULT 1,\n    extraction_id TEXT","")
        baseline=baseline.replace("type TEXT NOT NULL\n);","type TEXT NOT NULL,\n    UNIQUE (type,name)\n);",1)
        path=self.state/"original.json"
        legacy={"source_doc":"llm-wiki/legacy.md","nodes":[
            {"name":"Previous publication","type":"PROCESS","description":"Legacy publication preserves the original implementation."}],
            "edges":[],"aliases":[]}
        path.write_text(json.dumps(legacy))
        with closing(sqlite3.connect(self.path)) as old:
            old.executescript(baseline)
            old.execute("INSERT INTO graph_nodes VALUES('old','Previous publication','PROCESS')")
            old.execute("INSERT INTO graph_node_sources VALUES('old','llm-wiki/legacy.md',?)",
                        (legacy["nodes"][0]["description"],))
            old.execute("INSERT INTO extraction_results VALUES('llm-wiki/legacy.md',1,'.state/original.json',1)")
            old.execute("""INSERT INTO jobs(path,payload,state,revision,claimed_revision,claim_token,lease_until,available_at,created_at)
                           VALUES('claimed.md','{}','processing',4,4,'keep-token',9999999999,1,1)""")
            old.commit()
        before=path.read_bytes()
        self.db=queue_store.open_database()
        self.addCleanup(self.db.close)
        self.assertTrue(list((self.state/"backups").glob("pre-v2-*.sqlite3")))
        job=self.db.execute("SELECT * FROM jobs").fetchone()
        self.assertEqual((job["state"],job["claim_token"],job["revision"]),("processing","keep-token",4))
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual(self.db.execute("SELECT count(*) FROM extraction_runs").fetchone()[0],1)
        self.assertIsNone(self.db.execute("SELECT source_snapshot FROM extraction_runs").fetchone()[0])
        self.assertIn("Legacy publication",self.recall("original implementation")["facts"][0]["text"])
        build_graph.rebuild_graph(self.db)
        self.assertIn("Legacy publication",self.recall("Previous publication")["facts"][0]["text"])
        self.assertEqual(self.db.execute("PRAGMA foreign_key_check").fetchall(),[])
        backup=list((self.state/"backups").glob("*.sqlite3"))[0]
        with closing(sqlite3.connect(backup)) as old:
            self.assertEqual(old.execute("SELECT count(*) FROM graph_nodes").fetchone()[0],1)


if __name__=="__main__":
    unittest.main()
