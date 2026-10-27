# Engineering knowledge model

## Purpose

Preserve the host project's features, code locations, changes, decisions, reasoning and supported attribution as human-readable wiki notes and derived SQLite retrieval structures.

## Current behavior

### Implemented extraction contract
[The prompt](../tools/extraction/prompt.md) and
[version-two validator](../tools/extraction/engineering.py) use FEATURE, COMPONENT,
CODE_ELEMENT, DECISION, CHANGE, CONSTRAINT, ISSUE, PERSON, TEAM and AGENT.
Legacy versionless extractions still use their original validator; they remain
readable and are never mechanically relabeled as the new entity types.

Canonical entity keys are separate from display names. Code identity is
code:project/relative/path#qualified_symbol, or the path alone for a file.
Same-named symbols in different files remain distinct. Relevant existing keys are
returned by claim for reuse.

Facts are independently retrievable assertions with kind, text, source-reported
state, optional lifecycle/rationale/supersession and exact source-section evidence.
States distinguish current, proposed, historical, superseded and disputed.
Acceptance, implementation, testing and deployment remain separate.
Source hashes, snapshots, prompt hashes and immutable accepted-result metadata are
recorded by the tools. A note reporting a test is source-reported evidence, not a
test independently observed by extraction.

Relationships include implements, part_of, depends_on, affects, governs, motivates,
constrains, resolves and supersedes. Each edge references supporting facts and
the validator checks endpoint types. Documents and URLs normally provide evidence
rather than becoming additional entity nodes.


### Capture policy
[AGENTS.md](../AGENTS.md) requires consulting recalled facts, retrying empty/stale/
partial retrieval with relevant features, paths or symbols, then consulting topic
pages and verifying code. At meaningful task boundaries, save behavior, code
locations, changes, accepted decisions and stated reasons, constraints, observed
verification, open questions and supported attribution.

For a new host project with an empty wiki, inspect code and tests and write a
bounded architecture and feature map. Do not reconstruct historical reasons by
guessing. Capture is agent work: the watcher cannot recover knowledge never saved.

Index and log pages remain navigation and historical ledger records. They no
longer generate primary extraction jobs. Their previously accepted results remain
preserved and explicitly searchable through history.



The [capture guidance](wiki-maintenance.md), [topic template](../tools/wiki/topic-template.md) and [architecture map](architecture.md) now make these obligations concrete. Capture happens before completion and before extraction; the first Stop requests review even with an empty queue.


### Retrieval and hook behavior
[Retrieval](../tools/recall_graph.py) combines exact names/aliases with
[bounded FTS5 search](../tools/search_knowledge.py) over facts and selected source
passages, then expands graph relationships. Facts appear before graph edges in
the compact hook context. Current facts rank ahead of proposed and historical
material; unclassified passages are labeled separately. Code references and
source/revision/freshness metadata accompany results.

The original question, "how often do we rebuild our knowledge graph?", must retrieve
the behavior that every successful extraction acknowledgment rebuilds the graph
atomically with acceptance and job completion. That behavior is documented in
[Graph building](session-capture.md#graph-building) and implemented by
tools/queue_store.py#acknowledge.

Prompt hooks now supply an explicit status on a miss, missing database, empty
index or retrieval error, with a suggestion to retry or consult the wiki. Failure
still allows prompt submission. Shared client adapters retain their existing
commands, hop/row budgets and 6000-character context cap. This Codex chat has
demonstrated automatic hook execution and model-visible context; Claude and
Cursor model delivery need independent verification.

[Source reconciliation](../tools/source_sync.py) tracks content hashes, ignores
unchanged source/prompt combinations, excludes index/log from primary jobs and
marks deletions inactive. Claim and Stop synchronously reconcile sources, so they
do not rely on watcher debounce. Stop asks the current agent to save missing
substantive knowledge before extraction while preserving the loop guard. No
additional model process is launched. The watcher needs restart after a code
upgrade; startup scanning reconciles edits made while it was stopped.

FTS is lexical search, not semantic paraphrase understanding. It uses safely
constructed, bounded queries and English stemming. Exact code lookup remains a
separate channel. Freshness is source-snapshot metadata, not proof that current
code or production behavior matches the note.


### Schema and migration
The [schema](../tools/schema.sql) retains the queue and existing graph tables.
Canonical keys/code locators live in graph_entity_keys. New tables store
graph_facts, graph_fact_sources, graph_edge_facts, graph_fact_supersession,
knowledge_sources, extraction_runs and schema_migrations. knowledge_search is the
derived FTS5 index. Display names no longer determine entity uniqueness.

The [migration](../tools/migrations.py) takes a consistent SQLite backup before
upgrading an existing database, preserves jobs/leases and accepted pointers,
archives immutable result JSON and hashes, retains original files and builds a
searchable compatibility representation of existing graph descriptions. It does
not invent source snapshots or source hashes for old accepted results.

New acceptance saves its exact source snapshot, verifies evidence and rejects
changed sources even before the watcher notices the edit. Result acceptance,
archive insertion, graph replacement, search publication and job completion share
one transaction. Failure or lease expiry rolls them back.

The graph still rebuilds from all latest accepted results after each successful
acknowledgment. Earlier accepted versions remain in extraction_runs and can be
searched with --include-history. Deleted, navigation, ledger, historical and
superseded material is excluded from ordinary search. Removing one source does
not remove facts supported by another active source. Full rebuilding remains
the initial publication method; incremental graph updates are deferred.

## Code locations

[prompt.md](../tools/extraction/prompt.md) defines extraction; [engineering.py](../tools/extraction/engineering.py) validates it; [engineering_graph.py](../tools/engineering_graph.py) publishes facts and indexes; [migrations.py](../tools/migrations.py) preserves legacy data. [queue_store.py](../tools/queue_store.py), `acknowledge`, connects validation, snapshots, publication and completion. See [the architecture map](architecture.md).

## Constraints

Extraction requires exact source-section evidence and canonical identities. Unknown ownership and reasoning stay unknown. Legacy records retain their original vocabulary. Current source claims, observed verification, acceptance and deployment remain distinct. Full rebuilding continues after successful acknowledgment; incremental publication remains deferred.

## Decisions and reasoning

### Purpose and decision
On 2026-10-27, the user defined Ryujin as a reusable coding-project template whose
knowledge map preserves features, implementation, changes, decisions and reasoning.
On 2026-10-28, the user requested implementation and added attribution for who
implemented code, made a decision and owns or maintains it.

The wiki is the human-readable engineering record. SQLite graph and full-text
search are derived retrieval structures. Verify current behavior against code.
The original proposal is preserved in
[raw/engineering-knowledge-proposal-2026-10-27.md](../raw/engineering-knowledge-proposal-2026-10-27.md).

## Verification

On 2026-10-28, 55 tests passed before the project migration, including the original
natural-language question, source evidence, ownership roles, two same-named symbols,
source-hash idempotency, stale claims, deletion with shared support, history,
version-one migration/backup, rollback, concurrency, read-only snapshots and
portable hook commands. These checks include a temporary host project. Test
records are isolated from the real recall log.

Useful question checks include where a feature is implemented, who explicitly
implemented it, who made a decision, which team maintains code, what changed,
which constraints apply and what remains unverified. Missing reasons and ownership
must remain missing.

Related: [graph building and recall](session-capture.md),
[retrieval comparison](graph-retrieval-comparison.md),
[extraction workflow](../tools/extraction/workflow.md).

Sources: [SQLite FTS5](https://www.sqlite.org/fts5.html),
[OpenAI hook documentation](https://learn.chatgpt.com/docs/hooks).


The later capture-workflow checks are recorded in [wiki maintenance](wiki-maintenance.md#verification).

## Ownership

### Attribution and ownership
The user requested separate attribution for implementation, decision making and
ownership. The contract distinguishes PERSON, TEAM and AGENT, and supports
authored_by, committed_by, implemented_by, decided_by, approved_by, requested_by,
reviewed_by, owned_by, maintained_by and member_of.

Git author metadata supports authored_by; Git committer metadata supports
committed_by. Neither proves who implemented code, made a decision, approved it
or maintains it. Other *_by relationships require explicit named statements in
their supporting excerpts. Review assignments do not establish completed review
or ongoing ownership. Preserve dates, revision and scope; unknown attribution
stays unknown.

Codex implemented the version-two engineering knowledge code in this working tree
at the user's request. This statement identifies the AI implementer, not a human
Git author or ongoing owner. The user approved implementing the engineering model
and requested ownership support; the source does not assign an ongoing maintainer
or identify historical decision makers for existing code.


On 2026-10-28, Horia requested the architecture map, standardized pages, stronger AGENTS.md instructions and empty-queue Stop review; Codex implemented that follow-up in this working tree. No ongoing owner or maintainer was assigned.

## Open questions

Historical decision makers and ongoing ownership remain unidentified where no explicit source exists. Claude and Cursor runtime model delivery remain unverified. FTS5 paraphrase limits and full-rebuild costs remain known limitations.

## Change history

- 2026-10-27: Recorded the engineering-knowledge proposal; the original remains preserved in raw/.
- 2026-10-28: Implemented version-two extraction, canonical keys, evidence-backed attribution, snapshots/history, migration and FTS5 retrieval.
- 2026-10-28: Standardized topic pages and connected capture obligations to the architecture map and queue-independent Stop review. Existing graph schema and accepted extraction files were preserved.
