# Graph retrieval comparison

## Purpose

Compare retrieval behavior using pinned upstream source and distinguish configured hook output from actual model delivery.

Reviewed on 2026-10-27 against graph-memory-starter commit
`496a6e9d9b9578943ec5ed34c2780de5a0fa5510`:
[recall.py](https://github.com/Glitch-Cat-Club/graph-memory-starter/blob/496a6e9d9b9578943ec5ed34c2780de5a0fa5510/src/recall.py)
and [its prompt hook](https://github.com/Glitch-Cat-Club/graph-memory-starter/blob/496a6e9d9b9578943ec5ed34c2780de5a0fa5510/src/recall_hook.py).

## Current behavior

### Verified differences
Both implementations match entity names and aliases without a model call.
Since 2026-10-28, Ryujin additionally searches engineering facts and selected
source passages with ranked FTS5 retrieval, so a full entity name is no longer
required to seed retrieval. Exact matching remains a separate channel for code.
Graph-memory-starter walks a configurable neighborhood using recursive SQL,
defaulting to three hops, then returns up to eight relationships ordered by proximity.
Ryujin's [retriever](../tools/recall_graph.py) now supports configurable hops
using breadth-first traversal, defaulting to one hop. It ranks relationships
by distance and then word overlap with the question. Ryujin limits seed matches
to five, returns up to eight relationships and reports truncation.

Ryujin also limits traversal to 100 examined relationship rows by default,
including repeated rows. It prevents repeated node expansion and reports
budget consumption. This bounds rows fetched during traversal, not SQLite
execution time or seed matching. See [retrieval options](session-capture.md#graph-retrieval).

Their seed matching fetches every name and alias into Python. Ryujin filters
substring candidates in SQLite, although the database still scans labels.
Ryujin preserves Unicode case folding and punctuation-aware boundaries.

Ryujin returns JSON with node IDs and source-specific descriptions. Their compact
text formatter includes descriptions selected by name, which can mix unrelated
same-named entities. Ryujin's CLI and shared hook use a read-only snapshot.
Graph-memory-starter has a separate Claude context hook. Ryujin now configures
prompt hooks for Claude, Codex and Cursor through [one shared helper](../tools/recall_hook.py),
which emits compact text capped at 6,000 characters. See
[client activation and verification limits](session-capture.md#prompt-time-graph-recall).

At the initial comparison, Ryujin followed only one hop. In-memory checks
confirmed that difference on a policy-to-role-to-person chain, their same-name
description ambiguity, and a punctuation-boundary mismatch. Subsequent Ryujin
tests cover configurable hops, cycles and traversal limits. These checks are
not performance benchmarks.

## Code locations

[recall_graph.py](../tools/recall_graph.py) handles matching and traversal; [search_knowledge.py](../tools/search_knowledge.py) ranks full-text hits; [recall_hook.py](../tools/recall_hook.py) formats and logs client context. Client definitions are linked from [prompt-time recall](session-capture.md#prompt-time-graph-recall).

## Constraints

The upstream comparison applies to the pinned commit, not an assertion about later upstream versions. In-memory checks are not performance benchmarks. Valid hook JSON or a recall log alone does not prove model delivery. FTS5 is lexical retrieval; results are bounded and may be partial.

## Decisions and reasoning

### Proposed next steps
Configurable, bounded multi-hop retrieval with source tracking and distance
ranking, compact text output and shared prompt-hook wiring were implemented
on 2026-10-27. A subsequent Codex chat demonstrated automatic hook execution and
delivery of graph context to the model. Claude and Cursor delivery remain
unverified, including Cursor's version-dependent prompt-hook behavior. The
[engineering knowledge model](engineering-knowledge-model.md) records the
observed exact-name retrieval miss and implemented extraction/search changes,
including evidence-backed attribution, canonical identity, versioned results and
explicit retrieval-status feedback.

## Verification

### Verified Codex model delivery
On 2026-10-28, Codex CLI 0.159.2 passed a controlled model-response check using
the configured default model, GPT-6.1-Sol. An isolated graph held a random probe
value absent from the user prompt and ordinary workspace files. The production
UserPromptSubmit definition and retrieval/bootstrap files were copied unchanged.

After establishing normal workspace and hook trust in the test project, a fresh
interactive session returned the exact value. Two subsequent fresh ephemeral
sessions used the same question and database: hooks enabled returned the exact
value, and hooks disabled returned UNKNOWN. Neither session made tool calls;
the hook's matched context and model responses were checked against the test
controller's expected value. This verifies delivery into the model, beyond valid
hook JSON. Temporary trust entries were removed afterward.

Initial untrusted-project attempts returned UNKNOWN without invoking the hook;
those runs did not test context injection. Final paired runs used normal trust
and no trust-bypass flag. Evidence is saved in local runtime state at
`.state/verification/live-context-delivery/report.json`, with model event traces
and the on/off responses alongside it. This result applies to the tested Codex
client and configuration; Claude and Cursor remain unverified.

## Ownership

Codex performed the documented comparison and standardized this page on 2026-10-28 at Horia's request. No ongoing retrieval maintainer, additional reviewer or upstream author identity is assigned by this source.

## Open questions

Claude and Cursor model delivery remain unverified. No retrieval performance benchmark has been recorded.

## Change history

- 2026-10-27: Recorded the pinned-source comparison; bounded traversal and shared prompt hooks followed.
- 2026-10-28: Recorded the implemented engineering/FTS model and controlled Codex delivery test. Standardized the page and retained its comparison, next-step and verification anchors.
