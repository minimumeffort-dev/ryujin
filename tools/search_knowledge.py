"""Bounded lexical retrieval over facts, passages and explicitly requested history."""
import re
import json

STOPWORDS = set("""a an the and or of for to in on at by from with as is are was were
be been being this that these those it its we us our you your they them their i me
my do does did have has had can could would should will may might what which when
where why how who whose often about explain tell please some any all also basically
given something specific piece need make right now know""".split())


def has_table(database, name):
    return database.execute("SELECT 1 FROM sqlite_master WHERE name=?",(name,)).fetchone() is not None


def query_terms(question):
    return list(dict.fromkeys(word.casefold() for word in re.findall(r"[^\W_]+",question)
                              if len(word)>1 and word.casefold() not in STOPWORDS))[:20]


def search_knowledge(database, question, *, include_history=False, limit=10, node_ids=None):
    if not has_table(database,"knowledge_search"):
        return []
    terms = query_terms(question)
    if not terms and not node_ids:
        return []
    query = " OR ".join('"' + term.replace('"','""') + '"' for term in terms)
    condition = "knowledge_search MATCH ?"
    parameters = [query]
    score = "bm25(knowledge_search,0,0,0,0,4,2,1,2)"
    if node_ids is not None:
        if not node_ids:
            return []
        condition = "k.node_id IN (" + ",".join("?" for _ in node_ids) + ")"
        parameters = list(node_ids)
        score = "0.0"
    rows = database.execute(
        f"""SELECT k.record_id,k.node_id,k.source_doc,k.record_kind,k.title,k.body,k.path,
             {score} AS score, e.entity_key,e.code_path,e.symbol,e.code_kind,
             f.kind AS fact_kind,f.state,f.lifecycle,f.rationale,
             s.active,s.kind AS source_kind,s.content_hash,r.source_hash,r.extraction_id
           FROM knowledge_search k
           LEFT JOIN graph_facts f ON f.id=k.record_id
           LEFT JOIN knowledge_sources s ON s.source_doc=k.source_doc
           LEFT JOIN extraction_results r ON r.source_doc=k.source_doc
           LEFT JOIN graph_entity_keys e ON e.node_id=k.node_id
           WHERE {condition}
             AND (? OR (COALESCE(s.active,1)=1 AND COALESCE(s.kind,'topic')='topic'
                        AND k.record_kind<>'archive'
                        AND COALESCE(f.state,'current') NOT IN ('superseded','historical')))
           ORDER BY score, CASE f.kind WHEN 'behavior' THEN 0 WHEN 'constraint' THEN 1
             WHEN 'rationale' THEN 2 ELSE 3 END,k.record_id LIMIT 80""",
        (*parameters,int(include_history)),
    ).fetchall()
    ranked = []
    ownership = bool(re.search(r"\b(who|owner|ownership|author|maintainer|implemented|decided)\b",question,re.I))
    for row in rows:
        item = dict(row)
        multiplier = 1.0
        if item["record_kind"] == "passage":
            multiplier *= 0.25
        if item["record_kind"] == "archive":
            multiplier *= 0.2
        if item["fact_kind"] == "legacy_description":
            multiplier *= 0.65
        if item["state"] == "proposed":
            multiplier *= 0.5
        if item["state"] in ("historical","superseded"):
            multiplier *= 0.2
        if ownership and item["fact_kind"] == "ownership":
            multiplier *= 2
        item["score"] *= multiplier
        ranked.append(item)
    ranked.sort(key=lambda row:(row["score"],row["record_id"]))
    results = []
    seen = set()
    for row in ranked:
        # Distinct facts in one page may share text but disagree in state, scope
        # or provenance. Compatible-assertion grouping belongs to select_facts.
        dedup = (row["source_doc"],row["record_id"])
        if dedup in seen:
            continue
        seen.add(dedup)
        evidence = [dict(item) for item in database.execute(
            """SELECT section,excerpt,code_path,symbol,git_ref,verification,extraction_id,attribution_basis
               FROM graph_fact_sources WHERE fact_id=? AND source_doc=?
               ORDER BY section,excerpt LIMIT 8""",(row["record_id"],row["source_doc"]))]
        if row["record_kind"] == "archive":
            _, run_id, position = row["record_id"].split(":")
            run = database.execute("SELECT source_hash,result_json FROM extraction_runs WHERE id=?",(run_id,)).fetchone()
            row["extraction_id"] = run_id
            row["source_hash"] = run["source_hash"]
            original = json.loads(run["result_json"])
            if original.get("schema_version") == 2:
                evidence = [{**item,"verification":"archived_source_reported","extraction_id":run_id}
                            for item in original["facts"][int(position)]["evidence"]]
        state = row["state"] or ("historical" if row["record_kind"]=="archive" else "unclassified")
        if row["active"] == 0:
            state = "historical"
        results.append({
            "id":row["record_id"],"node_id":row["node_id"],"title":row["title"],
            "text":row["body"],"kind":row["fact_kind"] or row["record_kind"],"state":state,
            "lifecycle":row["lifecycle"] or "","rationale":row["rationale"] or "",
            "source_doc":row["source_doc"],"source_hash":row["source_hash"],
            "extraction_id":row["extraction_id"],
            "source_active": row["active"] != 0,
            "freshness":("stale" if row["source_hash"] and row["content_hash"] != row["source_hash"]
                         else "snapshot" if row["source_hash"] else "unknown"),
            "evidence":evidence,"score":row["score"],
            "entity_key":row["entity_key"],
            "code":({"path":row["code_path"],"symbol":row["symbol"],"kind":row["code_kind"]}
                    if row["code_path"] else None),
        })
        if len(results)>=limit:
            break
    return results
