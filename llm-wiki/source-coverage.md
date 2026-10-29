# Comprehensive source coverage

## Purpose

Make the 2026-10-29 codebase review inspectable: source scope, reviewed knowledge,
structural symbols, exclusions and publication checks. This snapshot is for revision
0a3793fcd191f5d3f562d9817f4523238d8885d0 plus the reviewed working tree; file hashes
identify the exact content. Later edits can invalidate its current-coverage claim.

## Current behavior

Codex reviewed all **42 eligible source files** in **53 chunks**, including all nine
test files and three client configurations. There are no scan-budget/unreadable gaps,
Python parse errors or intentionally omitted in-scope files. The static catalogue
contains **275 class/function identities and definition sites**, with **297 imported-name
entries across 29 Python files**. Imported names are syntactic observations, not
verified runtime dependencies. Each reviewed file maps to a substantive topic and
canonical semantic entity; that topic must link the source. The table below records
those review dispositions. The tool checks hashes and publication separately.

The durable [coverage and symbol catalogue](../raw/codebase-review-2026-10-29/coverage.json)
contains exact source/topic hashes, file-specific review reasons, topic/entity
mappings, nested/async symbol locators and line ranges, import scopes/aliases, and
excluded candidate paths with reasons. It preserves the inventory rather than
adding every syntax symbol as a graph node. Meaningful semantic entities and
relationships are extracted from the topics through the normal queue.

### Reviewed files

| Source | Substantive topic | Mapped canonical entity | Python identities |
| --- | --- | --- | ---: |
| [tools/pyproject.toml](../tools/pyproject.toml) | [watcher-startup](watcher-startup.md) | `feature:shared-watcher-startup` | 0 |
| [.claude/settings.json](../.claude/settings.json) | [watcher-startup](watcher-startup.md) | `feature:shared-watcher-startup` | 0 |
| [.codex/hooks.json](../.codex/hooks.json) | [watcher-startup](watcher-startup.md) | `feature:shared-watcher-startup` | 0 |
| [.cursor/hooks.json](../.cursor/hooks.json) | [watcher-startup](watcher-startup.md) | `feature:shared-watcher-startup` | 0 |
| [.gitignore](../.gitignore) | [watcher-startup](watcher-startup.md) | `feature:shared-watcher-startup` | 0 |
| [tools/ensure_watcher.py](../tools/ensure_watcher.py) | [watcher-startup](watcher-startup.md) | `feature:shared-watcher-startup` | 1 |
| [tools/watch_llm_wiki.py](../tools/watch_llm_wiki.py) | [watcher-startup](watcher-startup.md) | `feature:shared-watcher-startup` | 3 |
| [tools/watcher_lock.py](../tools/watcher_lock.py) | [watcher-startup](watcher-startup.md) | `feature:shared-watcher-startup` | 3 |
| [tools/run_hook.sh](../tools/run_hook.sh) | [watcher-startup](watcher-startup.md) | `feature:shared-watcher-startup` | 0 |
| [tools/tests/test_watcher_startup.py](../tools/tests/test_watcher_startup.py) | [watcher-startup](watcher-startup.md) | `feature:shared-watcher-startup` | 14 |
| [AGENTS.md](../AGENTS.md) | [wiki-maintenance](wiki-maintenance.md) | `feature:task-boundary-wiki-capture` | 0 |
| [tools/wiki/topic-template.md](../tools/wiki/topic-template.md) | [wiki-maintenance](wiki-maintenance.md) | `feature:task-boundary-wiki-capture` | 0 |
| [tools/queue_hook.py](../tools/queue_hook.py) | [wiki-maintenance](wiki-maintenance.md) | `feature:task-boundary-wiki-capture` | 2 |
| [tools/source_sync.py](../tools/source_sync.py) | [wiki-maintenance](wiki-maintenance.md) | `feature:task-boundary-wiki-capture` | 1 |
| [tools/tests/test_queue_hook.py](../tools/tests/test_queue_hook.py) | [wiki-maintenance](wiki-maintenance.md) | `feature:task-boundary-wiki-capture` | 13 |
| [tools/bootstrap/prompt.md](../tools/bootstrap/prompt.md) | [codebase-bootstrap](codebase-bootstrap.md) | `feature:existing-codebase-bootstrap` | 0 |
| [tools/bootstrap/workflow.md](../tools/bootstrap/workflow.md) | [codebase-bootstrap](codebase-bootstrap.md) | `feature:existing-codebase-bootstrap` | 0 |
| [tools/bootstrap_knowledge.py](../tools/bootstrap_knowledge.py) | [codebase-bootstrap](codebase-bootstrap.md) | `feature:existing-codebase-bootstrap` | 16 |
| [tools/tests/test_bootstrap_knowledge.py](../tools/tests/test_bootstrap_knowledge.py) | [codebase-bootstrap](codebase-bootstrap.md) | `feature:existing-codebase-bootstrap` | 18 |
| [tools/source_coverage.py](../tools/source_coverage.py) | [codebase-bootstrap](codebase-bootstrap.md) | `feature:source-review-coverage` | 18 |
| [tools/tests/test_source_coverage.py](../tools/tests/test_source_coverage.py) | [codebase-bootstrap](codebase-bootstrap.md) | `feature:source-review-coverage` | 14 |
| [tools/extraction/prompt.md](../tools/extraction/prompt.md) | [extraction-contract](extraction-contract.md) | `feature:engineering-knowledge-extraction` | 0 |
| [tools/extraction/workflow.md](../tools/extraction/workflow.md) | [extraction-contract](extraction-contract.md) | `feature:engineering-knowledge-extraction` | 0 |
| [tools/extraction/engineering.py](../tools/extraction/engineering.py) | [extraction-contract](extraction-contract.md) | `feature:engineering-knowledge-extraction` | 5 |
| [tools/extraction/validate.py](../tools/extraction/validate.py) | [extraction-contract](extraction-contract.md) | `feature:engineering-knowledge-extraction` | 4 |
| [tools/tests/test_engineering_knowledge.py](../tools/tests/test_engineering_knowledge.py) | [extraction-contract](extraction-contract.md) | `feature:engineering-knowledge-extraction` | 21 |
| [tools/queue_store.py](../tools/queue_store.py) | [extraction-queue](extraction-queue.md) | `component:extraction-queue` | 7 |
| [tools/consume_queue.py](../tools/consume_queue.py) | [extraction-queue](extraction-queue.md) | `component:extraction-queue` | 1 |
| [tools/tests/test_queue_completion.py](../tools/tests/test_queue_completion.py) | [extraction-queue](extraction-queue.md) | `component:extraction-queue` | 23 |
| [tools/paths.py](../tools/paths.py) | [engineering-knowledge-model](engineering-knowledge-model.md) | `component:engineering-knowledge-store` | 0 |
| [tools/migrations.py](../tools/migrations.py) | [engineering-knowledge-model](engineering-knowledge-model.md) | `component:engineering-knowledge-store` | 5 |
| [tools/build_graph.py](../tools/build_graph.py) | [engineering-knowledge-model](engineering-knowledge-model.md) | `component:engineering-knowledge-store` | 4 |
| [tools/engineering_graph.py](../tools/engineering_graph.py) | [engineering-knowledge-model](engineering-knowledge-model.md) | `component:engineering-knowledge-store` | 5 |
| [tools/schema.sql](../tools/schema.sql) | [engineering-knowledge-model](engineering-knowledge-model.md) | `component:engineering-knowledge-store` | 0 |
| [tools/recall_graph.py](../tools/recall_graph.py) | [graph-retrieval-comparison](graph-retrieval-comparison.md) | `feature:selective-graph-recall` | 7 |
| [tools/search_knowledge.py](../tools/search_knowledge.py) | [graph-retrieval-comparison](graph-retrieval-comparison.md) | `feature:selective-graph-recall` | 3 |
| [tools/recall_selection.py](../tools/recall_selection.py) | [graph-retrieval-comparison](graph-retrieval-comparison.md) | `feature:selective-graph-recall` | 5 |
| [tools/brief_context.py](../tools/brief_context.py) | [graph-retrieval-comparison](graph-retrieval-comparison.md) | `feature:selective-graph-recall` | 3 |
| [tools/recall_hook.py](../tools/recall_hook.py) | [graph-retrieval-comparison](graph-retrieval-comparison.md) | `feature:selective-graph-recall` | 9 |
| [tools/tests/test_graph_recall.py](../tools/tests/test_graph_recall.py) | [graph-retrieval-comparison](graph-retrieval-comparison.md) | `feature:selective-graph-recall` | 20 |
| [tools/tests/test_recall_hook.py](../tools/tests/test_recall_hook.py) | [graph-retrieval-comparison](graph-retrieval-comparison.md) | `feature:selective-graph-recall` | 30 |
| [tools/tests/test_selective_recall.py](../tools/tests/test_selective_recall.py) | [graph-retrieval-comparison](graph-retrieval-comparison.md) | `feature:selective-graph-recall` | 20 |

### Scope exclusions

The inventory excludes wiki/raw/state, generated/dependency/virtualenv/cache output,
lockfiles, binaries, symlinks and common credential paths. Git-ignored untracked
paths are outside Git discovery. Editor settings are outside the selected source
scope. See the catalogue for discovered excluded paths. The lockfile remains the dependency resolver's
record, not a semantically reviewed source file. Existing wiki evidence was read
and preserved separately. Exclusions are not a general secret detector.

## Code locations

[source_coverage.py](../tools/source_coverage.py) implements the catalogue, review
ledger and verification. [The workflow](../tools/bootstrap/workflow.md) and
[bootstrap topic](codebase-bootstrap.md#comprehensive-coverage-tooling) document
repeating or refreshing this pass. Runtime state is .state/bootstrap/coverage.json;
the durable raw snapshot can be inspected without that local state.

## Decisions and reasoning

Horia requested this comprehensive pass on 2026-10-29. Record file dispositions
and structural inventory so missing review is visible; preserve curated semantic
knowledge with implementation/test references so later agents can locate code.
The catalogue does not infer historical reasons, ownership or semantic completeness.
The existing engineering schema supports the topic extraction; no migration,
database wipe or database backup is needed.

## Verification

All 100 tests passed using
`uv run --project tools --locked python -m unittest discover -s tools/tests -q`.
Eight coverage tests exercise inventory, drift, evidence and publication contracts.
Source review also found and fixed [same-page recall state collapse](graph-retrieval-comparison.md#comprehensive-source-review-and-same-page-state-fix)
with a regression test. Tests use isolated fixture state where appropriate.

After normal extraction, run
`uv run --project tools --locked tools/source_coverage.py verify --published`
and `uv run --project tools --locked tools/bootstrap_knowledge.py status`.
The first requires exact accepted topic hashes and each mapped entity's support
from its mapped topic; the second checks baseline publication. Final runtime
checks, original-question recall and immutable-knowledge preservation are saved
in .state/verification/comprehensive-review/report.json. A publication check does
not establish exhaustive semantic extraction, live-client delivery or token savings.

The first publication pass on 2026-10-29 reported published coverage for all 42
files, complete bootstrap for all ten baseline topics and an empty unfinished queue.
All 27 prior accepted JSON files and 27 archived runs remained unchanged. Source
hashes, SQLite integrity and foreign keys passed. The original rebuild question
ranked successful extraction acknowledgment first; vague approval/follow-up and
unrelated prompts supplied no automatic context. Ownership recall initially found
only the implementation capability, so the precise code-level attribution below
was added for explicit path questions.

## Ownership

Horia requested the pass; Codex implemented the coverage tool and tests, performed
this source review and wrote the catalogue/topic updates on 2026-10-29. These are
explicit scoped attributions, not inferred Git roles. Original code implementers,
historical decision makers and ongoing owners remain unknown where unsupported.

Specifically, Codex implemented tools/source_coverage.py and
tools/tests/test_source_coverage.py on 2026-10-29 at Horia's request. This identifies
the AI implementer of these files for this pass; no ongoing owner or maintainer
was assigned.

## Open questions

This is comprehensive review of the eligible scope, not a proof that all possible
engineering knowledge or every symbol is in the graph. The raw catalogue enumerates
syntax; the graph holds selected supported semantic facts. Future source drift,
excluded/generated files, lexical-recall limits, unrecorded historical rationale
and ownership, and unmeasured task/token savings remain visible limitations.

## Change history

- 2026-10-29: Recorded the comprehensive file dispositions and static catalogue,
  linked substantive subsystem knowledge and normal publication checks, and
  preserved the existing wiki/graph/history without a schema change.
