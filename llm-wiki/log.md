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
