import argparse
import json
import re
import sqlite3
from collections import deque

from paths import DATABASE_PATH
from search_knowledge import search_knowledge

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
        (question, question, int(include_history)),
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
):
    if hops < 0:
        raise ValueError("hops must be zero or greater")
    if traversal_limit < 1:
        raise ValueError("traversal_limit must be positive")

    facts = search_knowledge(database, question, include_history=include_history)
    all_matches = find_matches(database, question, include_history=include_history)
    exact_ids = {node["id"] for node in all_matches}
    for fact in facts:
        if fact["node_id"] and fact["node_id"] not in exact_ids:
            node = database.execute("SELECT id,name,type FROM graph_nodes WHERE id=?", (fact["node_id"],)).fetchone()
            if node:
                all_matches.append({**dict(node), "matched_as": fact["title"], "method": "full_text"})
                exact_ids.add(fact["node_id"])
    matches = all_matches[:MAX_MATCHES]

    if not matches:
        return {
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

    edges, edges_truncated, limit_reached, examined = find_edges(
        database,
        matches,
        question,
        hops=hops,
        traversal_limit=traversal_limit,
        include_history=include_history,
    )
    nodes = load_nodes(database, matches, edges, include_history=include_history)

    return {
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


def main():
    parser = argparse.ArgumentParser(
        description="Retrieve graph context for a question"
    )
    parser.add_argument("question")
    parser.add_argument("--hops", type=int, default=DEFAULT_HOPS)
    parser.add_argument("--include-history", action="store_true",
                        help="Include archived, deleted and superseded knowledge")
    parser.add_argument(
        "--traversal-limit", type=int, default=DEFAULT_TRAVERSAL_LIMIT
    )
    args = parser.parse_args()

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
        )
    finally:
        database.close()

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
