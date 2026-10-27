"""Publish canonical engineering facts and build the derived full-text index."""
from uuid import NAMESPACE_URL, uuid5
import re
import json


def entity_id(key):
    return uuid5(NAMESPACE_URL, "ryujin:entity:" + key).hex


def fact_id(source_doc, key):
    return uuid5(NAMESPACE_URL, "ryujin:fact:" + source_doc + ":" + key).hex


def insert_engineering(database, data, run_id=None):
    source = data["source_doc"]
    ids = {}
    for node in data["nodes"]:
        identity = entity_id(node["key"])
        ids[node["key"]] = identity
        database.execute("INSERT INTO graph_nodes VALUES(?,?,?) ON CONFLICT(id) DO NOTHING",
                         (identity,node["name"],node["type"]))
        code = node.get("code", {})
        database.execute("INSERT INTO graph_entity_keys VALUES(?,?,?,?,?) ON CONFLICT(node_id) DO NOTHING",
                         (identity,node["key"],code.get("kind"),code.get("path"),code.get("symbol")))
        database.execute("INSERT INTO graph_node_sources VALUES(?,?,?)",
                         (identity,source,node["description"]))
    fact_ids = {}
    for fact in data["facts"]:
        identity = fact_id(source,fact["key"])
        fact_ids[fact["key"]] = identity
        database.execute("INSERT INTO graph_facts VALUES(?,?,?,?,?,?,?,?)",
                         (identity,ids[fact["subject"]],fact["key"],fact["kind"],fact["text"],
                          fact["state"],fact.get("lifecycle",""),fact.get("rationale","")))
        for evidence in fact["evidence"]:
            # Extraction reads a note, not the code/test/git system it describes.
            verification = "source_reported"
            if evidence.get("attribution_basis") in ("git_author","git_committer"):
                verification = "git_metadata_reported"
            database.execute(
                "INSERT OR IGNORE INTO graph_fact_sources VALUES(?,?,?,?,?,?,?,?,?,?)",
                (identity,source,run_id,evidence["section"],evidence["excerpt"],
                 evidence.get("code_path"),evidence.get("symbol"),evidence.get("git_ref"),verification,
                 evidence.get("attribution_basis","")),
            )
        for superseded in fact.get("supersedes",[]):
            database.execute("INSERT INTO graph_fact_supersession VALUES(?,?)",(identity,superseded))
    for edge in data["edges"]:
        values = (ids[edge["source"]],edge["predicate"],ids[edge["target"]],source)
        database.execute("INSERT OR IGNORE INTO graph_edges VALUES(?,?,?,?)",values)
        for key in edge["facts"]:
            database.execute("INSERT OR IGNORE INTO graph_edge_facts VALUES(?,?,?,?,?)",
                             (*values,fact_ids[key]))
    for alias in data["aliases"]:
        database.execute("INSERT OR IGNORE INTO graph_aliases VALUES(?,?,?)",
                         (ids[alias["entity"]],alias["alias"],source))


def insert_legacy_facts(database, data, ids, run_id=None):
    source = data["source_doc"]
    for node in data["nodes"]:
        identity = ids[node["name"]]
        key = "legacy:" + node["type"] + ":" + node["name"]
        database.execute("INSERT OR IGNORE INTO graph_entity_keys(node_id,entity_key) VALUES(?,?)",
                         (identity,key))
        fact_key = "fact:legacy:" + key
        fid = fact_id(source,fact_key)
        database.execute("INSERT INTO graph_facts VALUES(?,?,?,?,?,?,?,?)",
                         (fid,identity,fact_key,"legacy_description",node["description"],
                          "current","legacy",""))
        database.execute("INSERT INTO graph_fact_sources VALUES(?,?,?,?,?,?,?,?,?,?)",
                         (fid,source,run_id,"(legacy extraction)",node["description"],
                          None,None,None,"legacy_unverified",""))


def index_graph(database):
    database.execute(
        """UPDATE graph_facts SET state='superseded' WHERE fact_key IN
           (SELECT s.superseded_key FROM graph_fact_supersession s
            JOIN graph_facts replacement ON replacement.id=s.fact_id
            WHERE replacement.state='current')"""
    )
    database.execute("DELETE FROM knowledge_search")
    database.execute(
        """INSERT INTO knowledge_search
           (record_id,node_id,source_doc,record_kind,title,aliases,body,path)
           SELECT f.id,n.id,s.source_doc,'fact',n.name,
             COALESCE((SELECT group_concat(alias,' ') FROM graph_aliases a WHERE a.node_id=n.id),''),
             f.text || ' ' || f.rationale,COALESCE(k.code_path,'')
           FROM graph_facts f JOIN graph_nodes n ON n.id=f.node_id
           JOIN (SELECT DISTINCT fact_id,source_doc FROM graph_fact_sources) s ON s.fact_id=f.id
           LEFT JOIN graph_entity_keys k ON k.node_id=n.id"""
    )
    # Passages are a fallback when an extractor omitted a useful source statement.
    for run in database.execute(
        """SELECT r.source_doc,r.source_snapshot FROM extraction_results r0
           JOIN extraction_runs r ON r.id=r0.extraction_id
           WHERE r.source_snapshot IS NOT NULL"""
    ).fetchall():
        covered_sections = {row[0] for row in database.execute(
            "SELECT DISTINCT section FROM graph_fact_sources WHERE source_doc=?",(run["source_doc"],))}
        parts = re.split(r"(?m)^(?=#{1,6}\s)",run["source_snapshot"])
        for index, part in enumerate(parts):
            if not part.strip():
                continue
            title = part.splitlines()[0].lstrip("# ").strip()
            if title in covered_sections:
                continue
            # Bound each record; overlapping windows preserve section continuity.
            for offset in range(0,len(part),1400):
                body = part[offset:offset+1800]
                database.execute("INSERT INTO knowledge_search VALUES(?,?,?,?,?,?,?,?)",
                    (f"passage:{run['source_doc']}:{index}:{offset}",None,run["source_doc"],
                     "passage",title,"",body,""))
    for run in database.execute(
        """SELECT id,source_doc,result_json FROM extraction_runs WHERE id NOT IN
           (SELECT extraction_id FROM extraction_results WHERE extraction_id IS NOT NULL)"""
    ).fetchall():
        data = json.loads(run["result_json"])
        names = {node.get("key",node["name"]):node["name"] for node in data["nodes"]}
        if data.get("schema_version") == 2:
            records = [(fact["subject"],fact["text"],fact["key"]) for fact in data["facts"]]
        else:
            records = [(node["name"],node["description"],None) for node in data["nodes"]]
        for index, (subject,body,fact_key) in enumerate(records):
            relationships = [f"{names.get(edge['source'],edge['source'])} --{edge['predicate']}--> {names.get(edge['target'],edge['target'])}"
                             for edge in data["edges"] if fact_key in edge.get("facts",[]) or
                             (fact_key is None and subject in (edge["source"],edge["target"]))]
            if relationships:
                body += " Relationships: " + "; ".join(relationships)
            database.execute("INSERT INTO knowledge_search VALUES(?,?,?,?,?,?,?,?)",
                (f"archive:{run['id']}:{index}",None,run["source_doc"],"archive",names.get(subject,subject),"",body,""))
