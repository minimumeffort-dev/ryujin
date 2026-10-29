import argparse
import json
import re
import sqlite3
from collections import deque

from paths import DATABASE_PATH
from search_knowledge import search_knowledge
from recall_selection import analyze_query, GENERIC, select_facts

MAX_MATCHES = 5
MAX_EDGES = 8
DEFAULT_HOPS = 1
DEFAULT_TRAVERSAL_LIMIT = 100


def find_matches(database, question, *, include_history=False):
    question = question.casefold()
    database.create_function(
        "casefold", 1, str.casefold, deterministic=True
    )

    candidates = database.execute(
        """
        SELECT candidate.* FROM (
        SELECT id, name, type, name AS term
        FROM graph_nodes
        WHERE instr(?, casefold(name)) > 0

        UNION ALL

        SELECT node.id, node.name, node.type, alias.alias AS term
        FROM graph_aliases AS alias
        JOIN graph_nodes AS node ON node.id = alias.node_id
        WHERE instr(?, casefold(alias.alias)) > 0
          AND (? OR NOT EXISTS (SELECT 1 FROM knowledge_sources ks
               WHERE ks.source_doc=alias.source_doc AND (ks.active=0 OR ks.kind<>'topic')))

        UNION ALL

        SELECT node.id,node.name,node.type,key.code_path AS term
        FROM graph_entity_keys key JOIN graph_nodes node ON node.id=key.node_id
        WHERE key.code_path IS NOT NULL AND instr(?,casefold(key.code_path)) > 0

        UNION ALL

        SELECT node.id,node.name,node.type,key.symbol AS term
        FROM graph_entity_keys key JOIN graph_nodes node ON node.id=key.node_id
        WHERE key.symbol IS NOT NULL AND instr(?,casefold(key.symbol)) > 0

        UNION ALL

        SELECT node.id,node.name,node.type,key.code_path || '#' || key.symbol AS term
        FROM graph_entity_keys key JOIN graph_nodes node ON node.id=key.node_id
        WHERE key.symbol IS NOT NULL AND instr(?,casefold(key.code_path || '#' || key.symbol)) > 0
        ) candidate
        WHERE ? OR ((NOT EXISTS (SELECT 1 FROM graph_node_sources ns WHERE ns.node_id=candidate.id)
          OR EXISTS (SELECT 1 FROM graph_node_sources ns LEFT JOIN knowledge_sources ks
            ON ks.source_doc=ns.source_doc WHERE ns.node_id=candidate.id
            AND COALESCE(ks.active,1)=1 AND COALESCE(ks.kind,'topic')='topic'))
          AND (NOT EXISTS (SELECT 1 FROM graph_facts f WHERE f.node_id=candidate.id)
            OR EXISTS (SELECT 1 FROM graph_facts f JOIN graph_fact_sources fs ON fs.fact_id=f.id
              LEFT JOIN knowledge_sources ks ON ks.source_doc=fs.source_doc
              WHERE f.node_id=candidate.id AND f.state NOT IN ('superseded','historical')
                AND COALESCE(ks.active,1)=1 AND COALESCE(ks.kind,'topic')='topic')))
        """,
        (question, question, int(include_history), question, question, question, int(include_history)),
    ).fetchall()

    matches = {}

    for candidate in candidates:
        term = candidate["term"]
        pattern = rf"(?<!\w){re.escape(term.casefold())}(?!\w)"

        if not re.search(pattern, question):
            continue

        node = {
            "id": candidate["id"],
            "name": candidate["name"],
            "type": candidate["type"],
            "matched_as": term,
        }
        previous = matches.get(node["id"])

        if previous is None or len(term) > len(previous["matched_as"]):
            matches[node["id"]] = node

    return sorted(
        matches.values(),
        key=lambda node: (
            -len(node["matched_as"]),
            node["name"].casefold(),
            node["id"],
        ),
    )


def find_edges(
    database,
    matches,
    question,
    *,
    hops=DEFAULT_HOPS,
    traversal_limit=DEFAULT_TRAVERSAL_LIMIT,
    include_history=False,
):
    frontier = deque((node["id"], 0) for node in matches)
    visited = {node["id"] for node in matches}
    found = {}
    examined = 0

    while frontier and examined < traversal_limit:
        node_id, depth = frontier.popleft()

        if depth >= hops:
            continue

        remaining = traversal_limit - examined

        rows = database.execute(
            """
            SELECT
                source.id AS source_id,
                source.name AS source,
                edge.predicate,
                target.id AS target_id,
                target.name AS target,
                edge.source_doc
                ,COALESCE((SELECT group_concat(DISTINCT f.state)
                   FROM graph_edge_facts ef JOIN graph_facts f ON f.id=ef.fact_id
                   WHERE ef.source_id=edge.source_id AND ef.predicate=edge.predicate
                     AND ef.target_id=edge.target_id AND ef.source_doc=edge.source_doc),'legacy') AS state
            FROM graph_edges AS edge
            JOIN graph_nodes AS source ON source.id = edge.source_id
            JOIN graph_nodes AS target ON target.id = edge.target_id
            WHERE (edge.source_id = ? OR edge.target_id = ?)
              AND (? OR (NOT EXISTS (SELECT 1 FROM knowledge_sources ks
                    WHERE ks.source_doc=edge.source_doc AND (ks.active=0 OR ks.kind<>'topic'))
                AND (NOT EXISTS (SELECT 1 FROM graph_edge_facts ef
                      WHERE ef.source_id=edge.source_id AND ef.predicate=edge.predicate
                        AND ef.target_id=edge.target_id AND ef.source_doc=edge.source_doc)
                  OR EXISTS (SELECT 1 FROM graph_edge_facts ef JOIN graph_facts f ON f.id=ef.fact_id
                      WHERE ef.source_id=edge.source_id AND ef.predicate=edge.predicate
                        AND ef.target_id=edge.target_id AND ef.source_doc=edge.source_doc
                        AND f.state NOT IN ('superseded','historical')))))
            LIMIT ?
            """,
            (node_id, node_id, int(include_history), remaining),
        )

        for row in rows:
            examined += 1

            key = (
                row["source_id"],
                row["predicate"],
                row["target_id"],
                row["source_doc"],
            )

            if key in found:
                continue

            edge = dict(row)
            edge["distance"] = depth + 1
            found[key] = edge

            neighbor = (
                row["target_id"]
                if row["source_id"] == node_id
                else row["source_id"]
            )

            if neighbor not in visited:
                visited.add(neighbor)
                frontier.append((neighbor, depth + 1))

    question_words = set(re.findall(r"[^\W_]+", question.casefold()))

    def rank(edge):
        labels = f"{edge['source']} {edge['target']}".casefold()
        words = set(re.findall(r"[^\W_]+", labels))

        return (
            edge["distance"],
            -len(question_words & words),
            edge["source"].casefold(),
            edge["target"].casefold(),
            edge["predicate"],
            edge["source_doc"],
            edge["source_id"],
            edge["target_id"],
        )

    all_edges = sorted(found.values(), key=rank)

    return (
        all_edges[:MAX_EDGES],
        len(all_edges) > MAX_EDGES,
        examined >= traversal_limit,
        examined,
    )


def load_nodes(database, matches, edges, *, include_history=False):
    node_ids = {node["id"] for node in matches}

    for edge in edges:
        node_ids.update((edge["source_id"], edge["target_id"]))

    placeholders = ", ".join("?" for _ in node_ids)

    nodes = {
        row["id"]: {
            "id": row["id"],
            "name": row["name"],
            "type": row["type"],
            "descriptions": [],
        }
        for row in database.execute(
            f"""
            SELECT id, name, type
            FROM graph_nodes
            WHERE id IN ({placeholders})
            """,
            list(node_ids),
        )
    }

    descriptions = database.execute(
        f"""
        SELECT ns.node_id, ns.source_doc, ns.description
        FROM graph_node_sources ns
        WHERE node_id IN ({placeholders})
          AND (? OR NOT EXISTS (SELECT 1 FROM knowledge_sources ks
                WHERE ks.source_doc=ns.source_doc AND (ks.active=0 OR ks.kind<>'topic')))
        ORDER BY source_doc
        """,
        [*node_ids, int(include_history)],
    )

    for description in descriptions:
        nodes[description["node_id"]]["descriptions"].append(
            {
                "source_doc": description["source_doc"],
                "description": description["description"],
            }
        )

    return sorted(
        nodes.values(),
        key=lambda node: (node["name"].casefold(), node["id"]),
    )


def recall_graph(
    database,
    question,
    *,
    hops=DEFAULT_HOPS,
    traversal_limit=DEFAULT_TRAVERSAL_LIMIT,
    include_history=False,
    view="detail",
    entity=None,
    fact_limit=10,
):
    if hops < 0:
        raise ValueError("hops must be zero or greater")
    if traversal_limit < 1:
        raise ValueError("traversal_limit must be positive")
    if view not in ("auto", "detail"):
        raise ValueError("view must be auto or detail")
    if fact_limit < 1 or fact_limit > 50:
        raise ValueError("fact_limit must be between 1 and 50")

    all_matches = find_matches(database, question, include_history=include_history)
    if entity:
        row = database.execute(
            """SELECT n.id,n.name,n.type FROM graph_entity_keys k JOIN graph_nodes n
               ON n.id=k.node_id WHERE k.entity_key=?""", (entity,)).fetchone()
        if not row:
            raise ValueError("Unknown canonical entity key")
        # Reuse lifecycle eligibility, including sources deleted since publication.
        eligible = find_matches(database, row["name"], include_history=include_history)
        all_matches = [{**dict(row), "matched_as": entity}] if any(n["id"] == row["id"] for n in eligible) else []
    anchors = [n for n in all_matches if entity or (
        n["type"] not in ("PERSON", "TEAM", "AGENT") and
        any(t not in GENERIC for t in analyze_query(n["matched_as"])["terms"]))]
    if view == "auto" and not anchors and not analyze_query(question)["terms"]:
        return {"matches": [], "nodes": [], "edges": [], "facts": [], "status": "no_matches",
                "matches_truncated": False, "edges_truncated": False,
                "traversal_limit_reached": False, "edges_examined": 0, "view": view,
                "selection": {"policy": view, "terms": [], "locators": [], "candidate_count": 0,
                              "selected_count": 0, "deduplicated": 0, "rejected": [],
                              "more_available": False, "reason": "unscoped_prompt"}}
    candidates = search_knowledge(database, question, include_history=include_history, limit=80)
    if all_matches:
        support = {}
        related_ids = set()
        for node in anchors:
            if node["type"] == "CODE_ELEMENT":
                for row in database.execute(
                    """SELECT ef.fact_id,ef.target_id FROM graph_edge_facts ef
                       WHERE ef.source_id=? AND ef.predicate='implements' LIMIT 80""", (node["id"],)):
                    support[row["fact_id"]] = node["id"]
                    related_ids.add(row["target_id"])
        anchored = search_knowledge(database, "", include_history=include_history,
                                    limit=80, node_ids=[n["id"] for n in all_matches[:MAX_MATCHES]] + sorted(related_ids)[:10])
        candidates = anchored + candidates
        candidates = [{**f, "anchor_node_id": support[f["id"]]} if f["id"] in support else f for f in candidates]
    if entity:
        candidates = [f for f in candidates if f["node_id"] in {n["id"] for n in all_matches}]
    facts, selection = select_facts(candidates, question, anchors, automatic=view == "auto",
                                   limit=min(3, fact_limit) if view == "auto" else fact_limit)
    if view == "auto":
        selected_ids = {f["node_id"] for f in facts}
        selected_ids.update(f["anchor_node_id"] for f in facts if f.get("anchor_node_id"))
        # Legacy graphs may only have exact, source-backed descriptions.
        all_matches = [n for n in anchors if n["id"] in selected_ids or not candidates]
    exact_ids = {node["id"] for node in all_matches}
    for fact in facts:
        if fact["node_id"] and fact["node_id"] not in exact_ids:
            node = database.execute("SELECT id,name,type FROM graph_nodes WHERE id=?", (fact["node_id"],)).fetchone()
            if node:
                all_matches.append({**dict(node), "matched_as": fact["title"], "method": "full_text"})
                exact_ids.add(fact["node_id"])
    matches = all_matches[:MAX_MATCHES]

    if not matches:
        result = {
            "matches": [],
            "nodes": [],
            "edges": [],
            "matches_truncated": False,
            "edges_truncated": False,
            "traversal_limit_reached": False,
            "edges_examined": 0,
            "facts": facts,
            "status": "matched" if facts else "no_matches" if database.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0] else "empty_index",
        }
        if view == "auto" or entity:
            result.update(view=view, selection=selection)
        return result

    edges, edges_truncated, limit_reached, examined = find_edges(
        database,
        matches,
        question,
        hops=0 if view == "auto" else hops,
        traversal_limit=traversal_limit,
        include_history=include_history,
    )
    nodes = load_nodes(database, matches, edges, include_history=include_history)
    for node in nodes:
        locator = database.execute("SELECT entity_key,code_path,symbol,code_kind FROM graph_entity_keys WHERE node_id=?",
                                   (node["id"],)).fetchone()
        if locator:
            node["entity_key"] = locator["entity_key"]
            if locator["code_path"]:
                node["code"] = {"path": locator["code_path"], "symbol": locator["symbol"], "kind": locator["code_kind"]}
    if entity and view == "detail":
        neighborhood = search_knowledge(database, "", include_history=include_history,
                                        limit=80, node_ids=[n["id"] for n in nodes])
        facts, selection = select_facts(neighborhood, question, matches, limit=fact_limit)
    attach_references(database, facts, include_history=include_history, automatic=view == "auto")

    result = {
        "matches": matches,
        "nodes": nodes,
        "edges": edges,
        "matches_truncated": len(all_matches) > MAX_MATCHES,
        "edges_truncated": edges_truncated,
        "traversal_limit_reached": limit_reached,
        "edges_examined": examined,
        "facts": facts,
        "status": "matched",
    }
    result.update(view=view, selection=selection)
    return result


def attach_references(database, facts, *, include_history=False, automatic=False):
    """Use only explicit evidence and supported code relationships; never guess tests."""
    for fact in facts:
        refs = []
        for source in fact.get("sources", [fact]):
            for evidence in source["evidence"]:
                if evidence.get("code_path"):
                    refs.append({"path": evidence["code_path"], "symbol": evidence.get("symbol"),
                                 "source_doc": source["source_doc"]})
        if fact.get("code"):
            refs.append({**fact["code"], "source_doc": fact["source_doc"]})
        rows = database.execute(
            """SELECT DISTINCT k.code_path,k.symbol,e.source_doc
               FROM graph_edges e JOIN graph_entity_keys k ON k.node_id=e.source_id
               JOIN graph_edge_facts ef ON ef.source_id=e.source_id AND ef.target_id=e.target_id
                 AND ef.predicate=e.predicate AND ef.source_doc=e.source_doc
               JOIN graph_facts f ON f.id=ef.fact_id
               LEFT JOIN knowledge_sources s ON s.source_doc=e.source_doc
               LEFT JOIN extraction_results r ON r.source_doc=e.source_doc
               WHERE e.target_id=? AND e.predicate='implements' AND k.code_path IS NOT NULL
                 AND (? OR (COALESCE(s.active,1)=1 AND COALESCE(s.kind,'topic')='topic'
                   AND f.state NOT IN ('historical','superseded')))
                 AND (? OR r.source_hash IS NULL OR r.source_hash=s.content_hash)
               ORDER BY k.code_path,k.symbol LIMIT 5""", (fact["node_id"], int(include_history), int(not automatic)))
        refs.extend({"path": r["code_path"], "symbol": r["symbol"], "source_doc": r["source_doc"]} for r in rows)
        seen = set()
        fact["references"] = []
        for ref in refs:
            identity = (ref["path"], ref.get("symbol"), ref["source_doc"])
            if identity not in seen:
                seen.add(identity)
                fact["references"].append(ref)


def main():
    parser = argparse.ArgumentParser(
        description="Retrieve graph context for a question"
    )
    parser.add_argument("question", nargs="?", default="")
    parser.add_argument("--view", choices=("auto", "detail"), default="detail")
    parser.add_argument("--entity", help="Expand one canonical entity key")
    parser.add_argument("--limit", type=int, default=10, help="Maximum facts, 1 to 50; auto caps at three")
    parser.add_argument("--hops", type=int, default=DEFAULT_HOPS)
    parser.add_argument("--include-history", action="store_true",
                        help="Include archived, deleted and superseded knowledge")
    parser.add_argument(
        "--traversal-limit", type=int, default=DEFAULT_TRAVERSAL_LIMIT
    )
    args = parser.parse_args()

    if not args.question.strip() and not args.entity:
        parser.error("Provide a question or --entity")
    if not 1 <= args.limit <= 50:
        parser.error("--limit must be between 1 and 50")

    if args.hops < 0:
        parser.error("--hops must be zero or greater")
    if args.traversal_limit < 1:
        parser.error("--traversal-limit must be positive")

    if not DATABASE_PATH.is_file():
        parser.error("The project database does not exist yet")

    database = sqlite3.connect(
        DATABASE_PATH.as_uri() + "?mode=ro",
        uri=True,
        timeout=10,
    )
    database.row_factory = sqlite3.Row

    try:
        database.execute("BEGIN")
        result = recall_graph(
            database,
            args.question,
            hops=args.hops,
            traversal_limit=args.traversal_limit,
            include_history=args.include_history,
            view=args.view,
            entity=args.entity,
            fact_limit=args.limit,
        )
    except ValueError as error:
        parser.error(str(error))
    finally:
        database.close()

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
