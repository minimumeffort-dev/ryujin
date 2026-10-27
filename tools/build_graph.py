import json
from uuid import NAMESPACE_URL, uuid5

from extraction.validate import load_extraction
from paths import PROJECT_ROOT
from queue_store import open_database
from engineering_graph import index_graph, insert_engineering, insert_legacy_facts
from migrations import digest

GRAPH_TABLES = ("knowledge_search", "graph_fact_supersession", "graph_edge_facts",
                "graph_fact_sources", "graph_facts", "graph_entity_keys",
                "graph_edges", "graph_aliases", "graph_node_sources", "graph_nodes")


def node_id(node):
    key = f"ryujin:{node['type']}:{node['name']}"
    return uuid5(NAMESPACE_URL, key).hex


def insert_extraction(database, data, run_id=None):
    if data.get("schema_version") == 2:
        return insert_engineering(database, data, run_id)
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

    insert_legacy_facts(database, data, ids, run_id)


def rebuild_graph(database):
    owns_transaction = not database.in_transaction

    if owns_transaction:
        database.execute("BEGIN IMMEDIATE")

    try:
        accepted = database.execute(
            """
            SELECT source_doc, result_path, extraction_id
            FROM extraction_results
            ORDER BY source_doc
            """
        ).fetchall()

        documents = []
        for row in accepted:
            run = database.execute("SELECT * FROM extraction_runs WHERE id=?",
                                   (row["extraction_id"],)).fetchone()
            path = (PROJECT_ROOT / row["result_path"]).resolve()
            if not path.is_relative_to(PROJECT_ROOT.resolve()):
                raise ValueError("Extraction path escaped the project")
            if run and digest(path.read_text(encoding="utf-8")) != run["result_hash"]:
                raise ValueError("An accepted extraction was modified")
            snapshot = run["source_snapshot"] if run else None
            data = load_extraction(path, row["source_doc"], source_text=snapshot)
            documents.append((data,row["extraction_id"]))

        for table in GRAPH_TABLES:
            database.execute(f"DELETE FROM {table}")

        for document, run_id in documents:
            insert_extraction(database, document, run_id)
        index_graph(database)

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
