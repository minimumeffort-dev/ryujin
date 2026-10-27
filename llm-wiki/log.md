# Wiki log

## [2026-10-27] research | Watcher startup

Created [Watcher startup](watcher-startup.md) with documentation for the three clients, current implementation facts, and a proposed startup design. Added the wiki index. The startup design remains a proposal.

## [2026-10-27] research | Watcher supervision

Expanded [Watcher startup](watcher-startup.md) with operating-system supervisor options, their ownership of the foreground watcher, and the limits of crash recovery. Updated the index. Supervision remains optional and has not been implemented.

## [2026-10-27] implementation | Shared watcher startup

Implemented a shared startup helper, lifetime watcher lock, startup reconciliation and startup hooks for Claude Code, Codex and Cursor. Four integration tests passed on macOS. Updated [Watcher startup](watcher-startup.md) and the index with implementation details, verification limits and the decision to defer a supervisor. Codex's new startup hook requires trust review.

## [2026-10-27] implementation | Portable hook commands

Replaced machine-specific startup and Stop commands with a shared shell bootstrap that resolves the host project and locates `uv`. Added a relocation test covering all configured commands, nested working directories, spaces and a minimal `PATH`; all five integration tests passed. Updated [Watcher startup](watcher-startup.md) with the portability prerequisites and Codex's required review of the modified hooks.

## [2026-10-27] maintenance | Concise agent instructions

Reduced [AGENTS.md](../AGENTS.md) from 77 to 22 lines. Kept essential wiki and Python rules in the entry point and moved the extraction instructions unchanged to [the extraction workflow](../tools/extraction/workflow.md). Added its link to the index.

## [2026-10-27] maintenance | Group extraction documents

Grouped [the prompt](../tools/extraction/prompt.md) and [the workflow](../tools/extraction/workflow.md) in `tools/extraction/`, preserving their contents. Updated the code path and Markdown links, including the historical workflow link above.

## [2026-10-27] decision | Defer session capture

Recorded [session capture](session-capture.md) as deferred work: bounded transcript staging, later agent review and reuse of the queue's concurrency controls. Documented graph construction from accepted extraction results as the next proposed milestone. No capture or graph code was added.

## [2026-10-27] implementation | Validate and register completed extractions

Connected JSON validation to queue acknowledgment and recorded accepted result paths with job completion in one SQLite transaction. Updated [the workflow](../tools/extraction/workflow.md) and [the graph milestone](session-capture.md) with the implemented behavior. Added nine completion tests covering validation failures, accepted-result replacement, claim and revision checks, concurrency and rollback; all 14 completion and watcher startup tests passed. Previously completed jobs are not backfilled; graph construction remains future work.

## [2026-10-27] implementation | Graph schema

Added the four graph tables and enabled foreign-key checks in the database helper. Applied the schema while preserving existing queue and accepted-result records. All 14 existing tests and isolated foreign-key and source-contribution checks passed. Updated [the graph milestone](session-capture.md): the tables exist, while importing accepted JSON and retrieval remain unimplemented.

## [2026-10-27] implementation | Build graph from accepted extractions

The [graph builder](../tools/build_graph.py) rebuilds the graph from accepted JSON in one SQLite transaction, identifies nodes by exact type and name, and preserves source-specific information. Reprocessed `index.md` and `watcher-startup.md`, which predated accepted-result tracking, and rebuilt the graph from all four wiki notes. Updated [graph-building guidance](session-capture.md).

## [2026-10-27] implementation | Automatic graph updates

Connected successful extraction acknowledgment to graph rebuilding in the same SQLite transaction. Rebuild failure or lease expiry rolls back the accepted result, job completion and graph changes. Updated [the workflow](../tools/extraction/workflow.md) and [graph guidance](session-capture.md). All 18 tests passed, including automatic rebuilding, concurrent jobs, rollback and lease expiry.

## [2026-10-27] implementation | Graph retrieval command

Completed [recall_graph.py](../tools/recall_graph.py) with name and alias matching, one-hop relationships, source-specific descriptions and truncation flags. Retrieval uses a read-only database snapshot. Updated [retrieval guidance](session-capture.md) and the index. All 25 tests passed, including alias matching, source provenance, limits, read-only enforcement and concurrent-update consistency. Automatic prompt-hook integration remains future work.

## [2026-10-27] implementation | SQLite retrieval candidate filtering

Updated [recall_graph.py](../tools/recall_graph.py) to filter substring candidates in SQLite before fetching rows into Python. Preserved Unicode case folding and the existing word-boundary checks. Added tests for Unicode names and aliases and for avoiding unrelated row materialization; all 27 tests passed. Updated [retrieval guidance](session-capture.md) to distinguish reduced Python row loading from indexed search.

## [2026-10-27] research | Graph retrieval comparison

Compared Ryujin with graph-memory-starter's current recall implementation and checked traversal, same-name descriptions and punctuation handling in memory. Recorded [the comparison](graph-retrieval-comparison.md), including proposed bounded multi-hop retrieval and compact prompt output. Updated the index. Runtime code was not changed.

## [2026-10-27] implementation | Bounded multi-hop retrieval

Added configurable breadth-first traversal to [recall_graph.py](../tools/recall_graph.py), defaulting to one hop and 100 examined relationship rows. Results include distance, budget consumption and a budget flag; cycles cannot repeatedly expand nodes. Added the incoming-edge index to [the schema](../tools/schema.sql) and applied it while preserving existing table contents. All 30 tests passed, and the project CLI confirmed two-hop retrieval and budget exhaustion. Updated [retrieval guidance](session-capture.md#graph-retrieval) and [the comparison](graph-retrieval-comparison.md); compact prompt output and recall hooks remain future work.

## [2026-10-27] implementation | Shared prompt-time graph recall

Added [recall_hook.py](../tools/recall_hook.py) and connected Claude, Codex and Cursor prompt events through the existing portable bootstrap. Hooks use two hops, a 100-row traversal budget and a 6,000-character text cap. Recall reads one snapshot and allows prompts to proceed when no context is available or retrieval fails. All 39 tests passed, including client formats, failure handling, snapshot consistency and relocated hook commands; each configured command also returned context from the project graph. Updated [recall guidance](session-capture.md#prompt-time-graph-recall), [the comparison](graph-retrieval-comparison.md) and the index. Live client context delivery remains unverified; Codex requires trust review, and Cursor's prompt context field has conflicting reference and staff documentation.

## [2026-10-27] implementation | Shared recall log

Added `.state/recall_runs.jsonl` logging to [the shared recall hook](../tools/recall_hook.py). Each record includes the client/session, prompt, retrieval settings, structured graph results, exact returned context, status and errors. Concurrent writes are locked and log failures preserve normal hook output. All 42 tests passed, including session metadata, multiline and Unicode input, misses and failures, exact context correspondence, concurrent processes and relocated commands. Tests use temporary logs; the real log was prepared empty for subsequent prompts. Updated [recall log guidance](session-capture.md#recall-log) and the index, including the distinction between returned context and verified model delivery.

## [2026-10-27] proposal | Engineering knowledge for host projects

Recorded the user's clarified purpose for Ryujin and a [proposed engineering knowledge model](engineering-knowledge-model.md). Inspected the prompt, validator, schema and current graph; verified that an automatically invoked Codex hook missed a natural-language question whose answer existed in graph descriptions. An in-memory FTS5 experiment retrieved that fact with `graph AND rebuild`. Proposed software entities, supported facts, capture and hook changes, broader retrieval and a versioned migration preserving existing results. The current user turn supplied graph context to this Codex model; other client delivery remains unverified. These are documentation changes and a proposal; no runtime or schema migration was applied.

## [2026-10-28] implementation | Engineering knowledge and attribution

Implemented the [engineering knowledge model](engineering-knowledge-model.md): version-two extraction and evidence validation, canonical code identities, supported facts, distinct person/team/agent attribution, source-hash reconciliation, explicit recall statuses and ranked FTS5 retrieval. Preserved version-one readers and original results; the migration made a consistent SQLite backup and archived accepted metadata. Refreshed all four topic pages, retaining the six original accepted results and ten archived runs; the extraction queue is empty. All 56 tests passed, including natural-language retrieval, attribution separation, same-named symbols, source edits/deletion, supersession, archived provenance, migration and rollback. The original rebuild question returned Automatic graph updates first from session-capture.md, with tools/queue_store.py#acknowledge as its implementation reference. Shared helper output for Claude, Codex and Cursor returned the answer against the project database using isolated verification logs; live Claude/Cursor model delivery remains unverified. Database integrity and foreign-key checks passed. Preserved the original proposal in raw/engineering-knowledge-proposal-2026-10-27.md. Verification details are in local runtime state at .state/verification/engineering-knowledge-v2.json.

## [2026-10-28] verification | Codex model-visible graph context

Verified actual model delivery in Codex CLI 0.159.2 using a random graph probe in an isolated project. A fresh interactive session and a fresh hook-enabled exec session returned the exact value; the paired hook-disabled exec session returned UNKNOWN. The prompt did not contain the value and neither paired session used tools. The production recall hook definition and relevant helper files matched the fixture byte-for-byte. Initial untrusted-project runs did not invoke the hook; final paired runs used normal workspace/hook trust without a bypass flag. Removed the temporary trust entries. Recorded scope and evidence in [the retrieval comparison](graph-retrieval-comparison.md); the detailed report is local runtime state at .state/verification/live-context-delivery/report.json. The user narrowed verification to Codex; Claude and Cursor remain unverified.

## [2026-10-28] implementation | Architecture and task-boundary capture

At Horia's request, Codex added [the architecture map](architecture.md), [capture guidance](wiki-maintenance.md) and [the topic template](../tools/wiki/topic-template.md); standardized all six topic pages while retaining existing section anchors and historical explanations; and updated [AGENTS.md](../AGENTS.md) with completion-time capture, dated changes and architecture maintenance. The shared Stop hook now requests capture review independently of ready extraction jobs, retains the original continuation guards, respects no-file-change requests and reports queue/log errors without suppressing review. Existing hook definitions and database schema remain unchanged. All 63 tests passed, including a relocated empty-queue capture-to-recall flow. A live Codex test with matching production handlers/tools captured and extracted a decision after an empty-queue Stop; a fresh model retrieved it without tools and its routine review left the wiki and accepted results unchanged. Claude/Cursor model delivery remains unverified. Evidence is in local .state/verification/capture-flow/report.json.

## [2026-10-28] verification | Refreshed capture knowledge and original question

Re-extracted all six current topic pages after standardization, retaining all 67 previous supported fact texts, all original accepted JSON files and the four previous extraction runs. The project graph now contains 51 entities, 108 facts and 67 relationships across six latest accepted results and ten archived runs; the queue is empty. Current source snapshots/hashes, accepted-result hashes, database integrity and foreign keys passed verification. The original question, "how often do we rebuild our knowledge graph?", still retrieves successful extraction acknowledgment as the first answer. Empty-queue capture, implementation attribution and architecture-maintenance questions also retrieve the new source-backed facts. No ongoing owner or maintainer was invented. Details are in local .state/verification/capture-flow/report.json.
