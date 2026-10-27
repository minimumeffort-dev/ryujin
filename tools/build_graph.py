import json
from uuid import NAMESPACE_URL, uuid5

from extraction.validate import load_extraction
from paths import PROJECT_ROOT
from queue_store import open_database

GRAPH_TABLES = ("graph_edges", "graph_aliases", "graph_node_sources", "graph_nodes")


def node_id(node):
    key = f"ryujin:{node['type']}:{node['name']}"
    return uuid5(NAMESPACE_URL, key).hex


def insert_extraction(database, data):
    source_doc = data["source_doc"]
    ids = {}

    for node in data["nodes"]:
        entity_id = node_id(node)
        ids[node["name"]] = entity_id

        database.execute(
            """
            INSERT INTO graph_nodes (id, name, type)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (entity_id, node["name"], node["type"]),
        )

        database.execute(
            """
            INSERT INTO graph_node_sources (
                node_id, source_doc, description
            )
            VALUES (?, ?, ?)
            """,
            (entity_id, source_doc, node["description"]),
        )

    for edge in data["edges"]:
        database.execute(
            """
            INSERT INTO graph_edges (
                source_id, predicate, target_id, source_doc
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT DO NOTHING
            """,
            (
                ids[edge["source"]],
                edge["predicate"],
                ids[edge["target"]],
                source_doc,
            ),
        )

    for alias in data["aliases"]:
        database.execute(
            """
            INSERT INTO graph_aliases (node_id, alias, source_doc)
            VALUES (?, ?, ?)
            ON CONFLICT DO NOTHING
            """,
            (ids[alias["entity"]], alias["alias"], source_doc),
        )


def rebuild_graph(database):
    owns_transaction = not database.in_transaction

    if owns_transaction:
        database.execute("BEGIN IMMEDIATE")

    try:
        accepted = database.execute(
            """
            SELECT source_doc, result_path
            FROM extraction_results
            ORDER BY source_doc
            """
        ).fetchall()

        documents = [
            load_extraction(
                PROJECT_ROOT / row["result_path"],
                row["source_doc"],
            )
            for row in accepted
        ]

        for table in GRAPH_TABLES:
            database.execute(f"DELETE FROM {table}")

        for document in documents:
            insert_extraction(database, document)

        summary = {"documents": len(documents)}

        for table in GRAPH_TABLES:
            summary[table] = database.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]

        if owns_transaction:
            database.execute("COMMIT")
        return summary
    except BaseException:
        if owns_transaction and database.in_transaction:
            database.execute("ROLLBACK")
        raise


def main():
    database = open_database()

    try:
        summary = rebuild_graph(database)
    finally:
        database.close()

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
