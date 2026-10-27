import argparse
import json
import re
import sqlite3
from collections import deque

from paths import DATABASE_PATH

MAX_MATCHES = 5
MAX_EDGES = 8
DEFAULT_HOPS = 1
DEFAULT_TRAVERSAL_LIMIT = 100


def find_matches(database, question):
    question = question.casefold()
    database.create_function(
        "casefold", 1, str.casefold, deterministic=True
    )

    candidates = database.execute(
        """
        SELECT id, name, type, name AS term
        FROM graph_nodes
        WHERE instr(?, casefold(name)) > 0

        UNION ALL

        SELECT node.id, node.name, node.type, alias.alias AS term
        FROM graph_aliases AS alias
        JOIN graph_nodes AS node ON node.id = alias.node_id
        WHERE instr(?, casefold(alias.alias)) > 0
        """,
        (question, question),
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
            FROM graph_edges AS edge
            JOIN graph_nodes AS source ON source.id = edge.source_id
            JOIN graph_nodes AS target ON target.id = edge.target_id
            WHERE edge.source_id = ? OR edge.target_id = ?
            LIMIT ?
            """,
            (node_id, node_id, remaining),
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


def load_nodes(database, matches, edges):
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
        SELECT node_id, source_doc, description
        FROM graph_node_sources
        WHERE node_id IN ({placeholders})
        ORDER BY source_doc
        """,
        list(node_ids),
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
):
    if hops < 0:
        raise ValueError("hops must be zero or greater")
    if traversal_limit < 1:
        raise ValueError("traversal_limit must be positive")

    all_matches = find_matches(database, question)
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
        }

    edges, edges_truncated, limit_reached, examined = find_edges(
        database,
        matches,
        question,
        hops=hops,
        traversal_limit=traversal_limit,
    )
    nodes = load_nodes(database, matches, edges)

    return {
        "matches": matches,
        "nodes": nodes,
        "edges": edges,
        "matches_truncated": len(all_matches) > MAX_MATCHES,
        "edges_truncated": edges_truncated,
        "traversal_limit_reached": limit_reached,
        "edges_examined": examined,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Retrieve graph context for a question"
    )
    parser.add_argument("question")
    parser.add_argument("--hops", type=int, default=DEFAULT_HOPS)
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
        )
    finally:
        database.close()

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
