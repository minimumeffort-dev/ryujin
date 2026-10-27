# Engineering knowledge model

## Purpose and status

On 2026-10-27, the user clarified that Ryujin is a reusable template for coding
projects. Its knowledge map should preserve understanding of the host codebase:
features, implementation, changes, decisions and their reasons. The design below
is a proposal, not an accepted contract or implemented migration.

The wiki remains the human-readable engineering record; the graph and search
index are derived retrieval structures. Verify current behavior against current
code. Recorded decisions preserve reasons that code alone cannot explain.

## Verified starting point

- The [prompt](../tools/extraction/prompt.md) and
  [validator](../tools/extraction/validate.py) allow only PERSON, ROLE, POLICY,
  PROCESS and DOCUMENT, with approved_by, held_by, delegates_to, part_of and
  references relationships. Features, decisions and code elements cannot be
  represented directly.
- A read-only database inspection found 72 nodes: 36 DOCUMENT, 35 PROCESS and
  one POLICY. Relationships were 109 references and 17 part_of. These counts are
  a snapshot of this repository, not expectations for every host project.
- The watcher queues all Markdown notes, including index and log pages, which
  repeat topic summaries and give navigation documents many graph connections.
- The [retriever](../tools/recall_graph.py) seeds traversal using complete entity
  names and aliases appearing in a prompt. It does not search descriptions.
- This chat's recall log recorded no_matches and zero context for
  "how often do we rebuild our knowledge graph?". The graph nevertheless contained
  the answer in Automatic graph updates. A read-only CLI lookup using
  tools/build_graph.py also returned relevant descriptions.
- A temporary in-memory FTS5 index over existing names and descriptions retrieved
  the rebuild rule with `graph AND rebuild`. This tests a reduced lexical query,
  not a natural-language query planner or semantic search. No persistent index
  was created.
- The recall hook ran automatically in this Codex chat. The current user turn also
  supplied a graph-context message to the model. This establishes delivery here,
  not in Claude or Cursor.
- [The builder](../tools/build_graph.py) identifies nodes by type and display name
  and rebuilds the whole graph per accepted extraction. The
  [schema](../tools/schema.sql) has source-specific descriptions but lacks
  structured facts, evidence locators, source hashes and extraction versions.

## Capture policy

Changing extraction cannot recover knowledge never saved in notes. In each new
host project, an initial agent pass should inspect the code and tests and write
a bounded set of architecture and feature pages. Do not infer historical decisions
or their reasons from implementation alone.

During normal work, update topic pages at meaningful task boundaries with behavior,
implementation locations, meaningful changes, accepted decisions and stated reasons,
constraints, observed verification and open questions. Keep implementation, tests
and deployment distinct. Record commits when available and identify uncommitted work.

Use the index for navigation and the append-only log as a ledger. Exclude index.md
and log.md from primary extraction by default. Review existing history recorded only
in the log and transfer useful knowledge to topic pages before retiring its graph
contributions. Repository-specific domain extensions can supplement the shared model.

## Proposed extraction contract

| Type | Meaning |
| --- | --- |
| FEATURE | User-visible or internal capability and its behavior |
| COMPONENT | Subsystem, service, package or architectural boundary |
| CODE_ELEMENT | Relevant file, function, type, API, schema, configuration or test |
| DECISION | A choice with status, rationale and alternatives when stated |
| CHANGE | A meaningful behavior or implementation change, with revision when known |
| CONSTRAINT | An invariant, compatibility requirement or operating limit |
| ISSUE | A known failure, limitation or unresolved engineering question |

Documents, URLs, commits and test results normally supply evidence. Make them
entities only when the host project's subject requires it. Do not create a node
for every heading, mention or file.

Separate canonical identity from display names. A code key includes its relative
path and qualified symbol, such as `code:tools/queue_store.py#acknowledge`.
Same-named functions in different files must not merge. Reuse keys for the same
identity, preserve supported aliases and handle renames explicitly. The database
already belongs to one host project; global project IDs are unnecessary here.

Suggested relationships: implements, part_of, depends_on, affects, governs,
motivates, constrains, resolves and supersedes. Define legal endpoint types in the
validator. Edges use canonical keys and require supporting facts. For example,
code implements a feature, a decision governs a component, a constraint motivates
a decision, and a change resolves an issue.

Extract small, independently retrievable facts with:

- A local key, subject key, kind and concise text. Kinds include behavior,
  rationale, constraint, change, verification and open_question.
- Assertion state: current, proposed, historical, superseded or disputed. Current
  means reported as current by the source at that revision, not verified forever.
- Separate lifecycle when stated, such as an accepted decision or implemented
  feature. Acceptance does not establish implementation or verification.
- Supporting source section and exact excerpt; retain referenced code paths,
  symbols, revision IDs and verification results only when present.
- Explicit supersession when the source replaces an earlier decision or fact.

The surrounding tool records hashes, versions and capture times. The model must
not invent metadata, dates, reasons, aliases or test results. A note quoting an old
test result is not a test observed by the extracting agent.

Proposed prompt opening:

> Extract durable engineering knowledge about this host project. Preserve what a
> future coding agent needs to locate a feature, understand current behavior,
> explain a recorded decision, respect constraints and understand meaningful
> changes. Extract supported facts and their evidence, then connect the relevant
> entities. Preserve proposals, history and uncertainty explicitly.

For the earlier question, extract a FEATURE named Automatic graph updates, a
behavior fact stating that successful extraction acknowledgment rebuilds the graph
atomically with acceptance and completion, and a CODE_ELEMENT for
tools/queue_store.py#acknowledge linked with implements. Cite the Graph building
section of [session-capture.md](session-capture.md), retaining its code reference.
Reclassification must not manufacture a newly accepted design decision.

## Retrieval, hooks and shared instructions

Keep one shared retrieval implementation behind the existing client adapters.
Use exact path/symbol and alias matches as strong signals, then ranked full-text
search over facts, names, aliases and selected topic-page passages. Expand a bounded
neighborhood to obtain connected implementation, decisions and constraints. Rank
relevant facts before navigation links; avoid letting high-degree sources consume
the context budget.

[SQLite FTS5](https://www.sqlite.org/fts5.html) supplies full-text search and BM25
ranking. English stemming can connect rebuild with rebuilds/rebuilding. Preserve a
separate exact-match channel for code paths and symbols. FTS does not understand
semantic paraphrases. Evaluate real questions before adding embeddings or other
retrieval dependencies. Construct bounded, safely quoted queries from user text;
do not forward unchecked prompts as FTS syntax.

Prompt hooks should return relevant facts, sources/revisions and a small retrieval
status envelope even for empty or stale results. A miss should tell the agent to
reformulate its query or consult the wiki, not imply the knowledge does not exist.
Allow prompts to proceed on failure; distinguish empty index, miss, stale data and
retrieval error.

Retain SessionStart watcher startup. Add source-hash reconciliation for unchanged
notes and deleted sources. Stop continuation should ask the current agent to save
missing substantive knowledge first, then process extraction jobs. Preserve loop
guards and atomic leases. Hooks coordinate work; they do not perform semantic
extraction themselves or start another model process. The
[official OpenAI hook documentation](https://learn.chatgpt.com/docs/hooks) describes
UserPromptSubmit context injection and Stop continuation. Other clients retain
their adapters and need independent delivery checks.

Suggested concise addition to the shared AGENTS.md policy:

> Consult recalled project knowledge before substantive work. If recall is empty,
> incomplete or stale, query with relevant features, paths or symbols and consult
> the wiki. Verify current behavior against code. At meaningful task boundaries,
> update topic pages with changed behavior, implementation locations, accepted
> decisions and stated reasons, constraints, observed verification and open
> questions. Keep proposals and history distinct from current behavior. Missing
> recall is a retrieval result, not evidence that knowledge is absent.

## Proposed SQLite changes

| Area | Change |
| --- | --- |
| graph_nodes | Add unique entity_key and optional code kind/path/symbol. Retain display name/type; remove identity dependence on UNIQUE(type, name). |
| graph_facts | Add subject, fact key/kind, text, assertion state, optional lifecycle/rationale and supersession. Facts become primary retrieval records. |
| graph_fact_sources | Replace unstructured graph_node_sources contributions with fact evidence linked to accepted extraction runs, section/excerpt and optional code/revision/verification references. |
| graph_edges | Link canonical nodes with supporting fact IDs. Derive assertion state from support instead of treating every edge as unconditional. |
| graph_aliases | Retain source-supported aliases for lookup, without automatic identity merging. |
| knowledge_sources | Track source path/kind, hash and active/deleted state. |
| extraction_runs | Preserve immutable accepted results with source hash/revision, schema/ontology versions, prompt hash and result path. Keep extraction_results as the current accepted-result pointer. |
| knowledge_search | Add FTS5 records for facts and selected passages, with record IDs and weighted names/aliases/text/path fields. Publish search and graph changes atomically. |
| schema_migrations | Add numbered migrations; CREATE TABLE IF NOT EXISTS cannot change existing table definitions. |

Avoid replacing evidence with a confidence number. Verification records state what
was checked, at which revision, with which result and scope. Preserve conflicting
claims for review. Replacing or deleting one source retires its current contributions
without deleting support from other sources. Preserve old accepted JSON for audit;
default retrieval uses current contributions and makes historical claims explicit.

## Migration and evaluation

1. Back up state and add version-aware readers/validators before changing the
   prompt. Preserve queue leases and accepted-result pointers. The current builder
   revalidates all accepted JSON; an in-place vocabulary change would break rebuilds
   against old-format results.
2. Add tables/indexes beside the current graph. Re-extract eligible topic pages into
   a versioned staging generation. Do not mechanically rename every PROCESS to
   FEATURE or DOCUMENT to CODE_ELEMENT.
3. Validate facts, endpoints, source support, states and retrieval, then publish a
   compatible graph/search generation atomically. Keep originals recoverable.
4. Enable revised capture and hook output. Skip unchanged hashes and reconcile
   deletions. Full rebuilding can remain initially while semantics and retrieval
   change; incremental source replacement is a separate optimization.
5. Test real questions: when rebuilding runs, where a feature is implemented, why
   a recorded decision was made, what a change affected, which constraints apply
   and what remains unverified. Missing reasons must remain missing. Include another
   small host project to test the template beyond Ryujin.

Retain tests for leases, concurrent acceptance, stale revisions, rollback, read-only
retrieval and client output. Add migration compatibility, hash idempotency, deletion,
same-named symbols, supersession, unrelated-question misses and the natural-language
regression from this chat.

Related: [graph building and recall](session-capture.md),
[retrieval comparison](graph-retrieval-comparison.md),
[extraction workflow](../tools/extraction/workflow.md).
