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
are stored but do not merge identities. Graph retrieval is available through
[recall_graph.py](../tools/recall_graph.py).

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

## Graph retrieval

Run `uv run --project tools --locked tools/recall_graph.py "watcher startup"`
from the project root. The command matches full node names and aliases
case-insensitively, keeps up to five matching nodes, and follows incoming and
outgoing relationships with breadth-first traversal. The default is one hop;
set `--hops 2` to include a second hop or `--hops 0` for matched nodes alone.
It returns up to eight relationships, ranked by distance first and then
overlapping question words in endpoint names, plus descriptions and their
supporting `source_doc` paths. Each relationship includes its `distance`.

`--traversal-limit` defaults to 100 relationship rows examined across the walk.
Repeated rows count toward this budget, while returned relationships are
deduplicated per source. Visited nodes prevent cycles from expanding forever.
For example:

```sh
uv run --project tools --locked tools/recall_graph.py "ensure_watcher.py" --hops 2 --traversal-limit 100
```

`matches_truncated` and `edges_truncated` report output caps.
`edges_examined` reports consumed traversal rows, and
`traversal_limit_reached` signals that the budget was consumed, even if no
additional relationships existed. A budget-limited subset can depend on
SQLite's row order. The budget limits fetched relationship rows, not seed
matching or SQLite execution time. The schema indexes incoming relationships
by `target_id`; the relationship primary key already indexes outgoing ones.

SQLite filters substring candidates from names and aliases before returning
rows to Python. A connection-local `casefold` function preserves Unicode
matching, and the existing Python regex enforces word boundaries. SQLite still
scans the label columns; this reduces rows returned to Python rather than
providing an indexed search.

Retrieval opens the database read-only and uses one consistent snapshot during
concurrent graph updates. Exact phrase matching can miss paraphrases; fall back
to the wiki index when no nodes match and inspect supporting wiki pages for
details. Agents can invoke this command explicitly.

## Prompt-time graph recall

The shared [recall hook](../tools/recall_hook.py) reads the submitted `prompt`,
queries the graph through a read-only snapshot and formats source-backed facts
as reference data. The configured hooks use two hops and the default budget of
100 examined relationship rows. Context is capped at 6,000 characters, including
the omission notice. Missing databases, unmatched prompts and retrieval errors
allow submission to continue; errors go to stderr. Recall does not modify notes
or the queue and makes no model calls.

- [Claude settings](../.claude/settings.json) and [Codex hooks](../.codex/hooks.json)
  run on `UserPromptSubmit`, returning `hookSpecificOutput.additionalContext`.
- [Cursor hooks](../.cursor/hooks.json) run on `beforeSubmitPrompt`, returning
  `continue: true` and, when matches exist, `additional_context`.
- All three use [the portable bootstrap](../tools/run_hook.sh).

Codex requires review of new or changed hook definitions through `/hooks`
before they run; see [OpenAI's hook documentation](https://learn.chatgpt.com/docs/hooks#review-and-trust-hooks).
Cursor's [reference](https://cursor.com/docs/hooks#beforesubmitprompt) lists only
allow/block output, while an October 9, 2026
[staff reply](https://forum.cursor.com/t/agents-window-ignores-sessionstart-additional-context-claude-code-project-hooks-no-longer-load-3-24-9/174143/5)
describes `additional_context` on this event. Verify model visibility in a fresh
chat on the installed version; successful script output alone does not prove
client delivery. A temporary unique context marker can distinguish delivery
from information already in conversation history.

All 39 tests passed on 2026-10-27, including client output shapes, read-only
enforcement, snapshot consistency, partial results, context limits and failure
handling. Configured commands also returned context from the project graph,
and relocation tests covered nested directories, spaces and a minimal PATH.
Delivery into live Claude, Codex and Cursor model contexts has not been verified.

## Recall log

The shared [recall hook](../tools/recall_hook.py) appends one JSON record per
invocation to `.state/recall_runs.jsonl`, using
[the shared path definition](../tools/paths.py). Records contain a UTC timestamp,
client, hook event, session or conversation ID, optional turn ID, the full prompt,
hop and traversal settings, status, structured graph results, exact returned
context, context length and any retrieval error. Graph results preserve matched
nodes, descriptions, source paths, relationships and traversal metadata, including
information omitted from the capped text context.

Statuses are `matched`, `no_matches`, `no_prompt`, `missing_database` and `error`.
JSON escaping keeps multiline prompts and context in one record per line.
File locking prevents concurrent processes from interleaving records. Log write
failures are reported to stderr after emitting the normal hook response, so
logging failure does not block the prompt. The log is local runtime state and
is covered by the existing `.state/` Git ignore rule.

Watch new entries from the project root with:

```sh
tail -f .state/recall_runs.jsonl
```

For readable JSON when `jq` is installed, use
`tail -f .state/recall_runs.jsonl | jq .`. To print the most recent returned
context, use `tail -n 1 .state/recall_runs.jsonl | jq -r .context`.

The log records what the hook returned to the client, not confirmation that the
client delivered it to the model. All 42 tests passed on 2026-10-27, including
exact output correspondence, Unicode and multiline prompts, client/session
metadata, misses, missing databases, errors, log write failures, concurrent
processes and logging from relocated hook commands. Test records stay in
temporary projects rather than the real project log.
