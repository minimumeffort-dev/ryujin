# Session capture fallback

## Decision

Deferred on 2026-10-27. Continue using [AGENTS.md](../AGENTS.md) to maintain
the wiki during normal work. No transcript capture has been implemented.

The watcher queues notes after they are written. It cannot recover useful
conversation knowledge that an agent never saved before compaction or session end.

## Future proposal

- At compaction or session end, persist a bounded selection of user and assistant
  text for later review. Filter out tool output, thinking and injected harness text.
- Have an available agent turn useful material into concise wiki updates, keeping
  decisions, verified findings, proposals and open questions distinct.
- Reuse atomic claims, leases and retries for concurrent processing. Keep failures
  visible and retain staged input until processing succeeds.
- Adapt capture to each client's supported lifecycle events and transcript format.
  Keep topic pages as the main knowledge base; capture is a fallback.

This proposal is inspired by graph-memory-starter's
[session-end staging](https://github.com/Glitch-Cat-Club/graph-memory-starter/blob/496a6e9d9b9578943ec5ed34c2780de5a0fa5510/digest/session_end.py)
and [next-session handoff](https://github.com/Glitch-Cat-Club/graph-memory-starter/blob/496a6e9d9b9578943ec5ed34c2780de5a0fa5510/digest/session_start.py).
It does not guarantee that every session yields useful notes.

## Graph building

The [graph builder](../tools/build_graph.py) rebuilds the graph from accepted
extractions in one SQLite transaction. It preserves source-specific descriptions,
relationships and aliases. Node IDs use the exact entity type and name, so
distinct entities with the same type and name are treated as one node. Aliases
are stored but do not merge identities. Graph retrieval remains unimplemented.

Each successful extraction acknowledgment rebuilds the graph in the same SQLite
transaction as result acceptance and job completion. A failed rebuild rolls back
all three changes so the extraction workflow can retry. A manual rebuild remains
available from the project root with
`uv run --project tools --locked tools/build_graph.py`.

The [schema](../tools/schema.sql) defines shared nodes in `graph_nodes`,
source-specific descriptions in `graph_node_sources`, and source-supported
relationships and aliases in `graph_edges` and `graph_aliases`.
[The database helper](../tools/queue_store.py) enables foreign-key checks on
each connection it creates. The four tables were created in the project
database on 2026-10-27 and are populated by the graph builder.

As of 2026-10-27, the [extraction workflow](../tools/extraction/workflow.md) saves
candidate JSON and acknowledges jobs through [the queue](../tools/queue_store.py).
Acknowledgment validates the candidate, records its project-relative path in
`extraction_results`, rebuilds the graph and completes the job in one SQLite
transaction. Each document keeps one latest accepted result. Newer queued
revisions return to pending, and expired or mismatched claims cannot publish
results. Previously completed jobs are not automatically backfilled.
