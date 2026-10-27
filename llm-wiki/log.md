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
