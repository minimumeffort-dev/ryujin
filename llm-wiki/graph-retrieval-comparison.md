# Graph retrieval comparison

## Purpose

Compare retrieval behavior using pinned upstream source and distinguish configured hook output from actual model delivery.

Reviewed on 2026-10-27 against graph-memory-starter commit
`496a6e9d9b9578943ec5ed34c2780de5a0fa5510`:
[recall.py](https://github.com/Glitch-Cat-Club/graph-memory-starter/blob/496a6e9d9b9578943ec5ed34c2780de5a0fa5510/src/recall.py)
and [its prompt hook](https://github.com/Glitch-Cat-Club/graph-memory-starter/blob/496a6e9d9b9578943ec5ed34c2780de5a0fa5510/src/recall_hook.py).

## Current behavior

Automatic recall now uses selective, brief output; explicit detail retrieval retains
bounded neighborhood expansion. See [implemented selective recall](#implemented-selective-recall).
The comparison below describes detailed retrieval and its earlier evolution.

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

### Recall visibility proposal

On 2026-10-28, Horia requested visible feedback when graph recall finds relevant
knowledge and when that knowledge informs an answer. The paragraphs below record
the historical proposal from that initial review; implementation follows below.

Source inspection found that `.codex/hooks.json` already sets the recall progress
label to "Recalling wiki knowledge". `tools/recall_hook.py` injects source-backed
reference context and logs results, but emits no `systemMessage` result notice.
The [official hook contract](https://learn.chatgpt.com/docs/hooks#common-output-fields)
supports a progress label and a systemMessage rendered as a warning. It does not
document a custom-card output field. The
[MCP UI guide](https://developers.openai.com/plugins/build/chatgpt-ui)
documents iframe components in ChatGPT and compatible hosts; this does not verify
custom component rendering in the installed Codex app.

Proposed first step: retain automatic recall, include a compact retrieval summary
and citation identifiers in the model context, and instruct the assistant to show
a small source-linked callout when recalled facts materially inform its answer.
Count only facts and sources actually delivered within the context budget. Keep
"found and supplied" separate from "used in this answer": a pre-answer hook can
report retrieval, while usage is assistant-reported attribution supported by its
citations. This does not prove causal use of every supplied fact.

Use neutral feedback for ordinary misses and identify partial results. Avoid
presenting routine successful retrieval as a warning. An optional detailed viewer
could inspect existing recall logs; a custom interactive card would require a
separate integration and verification of host rendering. These are proposals.

The existing hook fields and helper output were inspected and the official docs
read on 2026-10-28. No new client UI or rendering behavior was tested in this review.

### Implemented recall feedback

On 2026-10-28, Horia accepted the progress-message and source-linked answer-callout
proposal and requested both stages. Codex implemented them in `.codex/hooks.json`,
`tools/recall_hook.py` and `AGENTS.md` in this working tree. This implementation
replaces the earlier source-linked callout proposal. The optional detailed viewer
and custom interactive MCP component remain proposals.

The Codex recall hook configures "Searching your project graph..." as its native
progress label. Because a fast hook may finish before a visible progress frame,
the context also instructs the assistant to emit one persistent commentary summary
of supplied evidence before answering. The summary reports delivered facts,
relationships, note excerpts and distinct wiki pages. It reports supply, not use.
Normal misses receive neutral commentary when relevant.

If graph knowledge materially informs an answer, the assistant includes one compact
blockquote labeled **From your knowledge graph** and links only to the source
sections it used. Unused results and misses get no graph-use callout. Explicit
response-format requests take precedence. This is assistant-reported attribution,
not proof of causal use of every supplied record. Ordinary successes do not emit
warning-style `systemMessage` notices.

The formatter packs whole evidence records and their citations within the existing
6,000-character cap. Oversized records are omitted rather than cut into incomplete
claims. FTS passages and legacy descriptions count as note excerpts, not extracted
facts. Only supplied records and their distinct source pages count in the receipt;
output omissions and retrieval limits are marked partial. Local citation links
resolve to existing source files and heading lines when present; missing headings
do not receive invented line numbers. Paths outside the project are not read.

The recall log retains the full retrieved result and adds a `delivery` receipt
with supplied counts, local fact/passage/citation identifiers and source links.
Its `usage` value is `not_assessed`: the pre-answer hook does not observe the
eventual answer. No database migration or separate model is required for feedback.

### Agent efficiency assessment

Historical assessment before selective recall: the priorities below were proposals
then. Paired task-efficiency measurement remains proposed.

On 2026-10-28, Horia clarified that the wiki should save tokens and make subsequent
agents faster. A published baseline and successful context delivery do not establish
either outcome. Code coverage, semantic coverage, retrieval relevance and task
efficiency are separate measures. Exhaustively listing functions is not itself a
success criterion; a useful baseline should help an agent locate the relevant
implementation and tests and recover constraints, recorded reasons and pitfalls.

Proposed priorities: capture task-oriented architecture and feature knowledge with
precise code/test references; supply a small relevant starting context and expand
on demand; avoid injecting weak matches merely because the budget has space;
and verify code freshness before acting on saved notes. These are recommendations,
not accepted or implemented retrieval changes. Complete source delivery does not
establish that notes contain all important engineering knowledge.

Proposed evaluation: run representative questions and coding tasks in paired fresh
sessions with the same source revision, model, prompt and tool permissions, with
recall enabled and disabled. Compare correctness, model-reported token usage,
wall-clock task time, search/file reads and retrieved-context relevance. Include
bootstrap, capture and extraction costs when measuring net savings across later
tasks. Character counts are not token measurements. No paired efficiency benchmark
or net savings result is currently recorded.

### Selective recall implementation proposal

Historical design, subsequently accepted by Horia and implemented below. The original
proposal is retained to explain the change and its constraints.

On 2026-10-28, Horia asked how to implement relevance filtering and smaller initial
context with expansion on demand. The design below is proposed, not accepted or
implemented. It changes retrieval policy and response selection while preserving
the stored knowledge and existing evidence/history contracts.

Separate automatic and explicit recall policies. Automatic recall should require
a specific code path, qualified symbol or feature/alias anchor, or sufficient
agreement across informative query terms in the candidate assertion. Generic
follow-ups such as "what next?" can return no reference context. The hook currently
receives the submitted prompt, not the conversation's resolved task; do not invent
that missing intent. The agent can make an explicit query using the topic from
its conversation. Missing databases and errors remain distinct from weak matches.

In search_knowledge.py, retain bounded FTS candidate generation and add a query
analysis/reranking stage. Preserve code paths and qualified symbols before general
word tokenization. Weight explicit code/feature anchors and phrase or informative
term agreement above incidental words; use BM25 within that selection rather than
one universal raw-score confidence threshold. Calibrate automatic acceptance on
representative positive and negative queries. Apply source-state eligibility to
exact and full-text candidates consistently. A source snapshot's freshness does
not prove that the current implementation still matches it.

Collapse duplicate presentation across source pages using compatible canonical
subject/fact identity or normalized assertion text, while retaining all supporting
source references. Keep differing state, attribution, numbers, negation or code
identity separate. Do not automatically merge arbitrary paraphrases or remove
stored facts. Deduplication happens before the brief context budget is filled.

In recall_graph.py, add policy-controlled fact limits and entity-focused expansion.
The automatic view should omit a generic relationship neighborhood; selected
facts can carry supported implementation/test locators from evidence or explicit
code relationships. Do not guess missing test paths. Proposed explicit options
--entity KEY and --view detail would return relevant entity facts and bounded
relationships with the existing hop/row controls. These options do not exist yet.

In recall_hook.py, initially try at most three facts and a configurable 2,000-character
total automatic-context cap including short instructions, receipt and citations.
These are starting settings to evaluate, not measured optimums or token counts.
Keep whole claims and source links, compress repeated feedback instructions, and
offer the agent the stable entity key for explicit expansion. An ordinary weak
match can emit no additionalContext while its local log records the skip reason.
Keep existing client allow/failure behavior and separate supplied evidence from
assistant-reported answer use. Detail retrieval remains an explicit agent action.

Record local selection diagnostics: policy, candidate/selected counts, anchor and
term-agreement signals, rejection/deduplication reasons and delivered characters.
Update AGENTS.md to prefer a brief result followed by focused code verification,
with explicit detail recall when evidence is insufficient. First verify exact
path/symbol lookup, cross-page duplicates with retained provenance, contradictory
facts, vague/unrelated prompts, missing test references, budget/receipt correctness,
detail expansion and the original rebuild question. Then measure paired task
correctness, actual token usage, file reads and elapsed time before claiming savings.

### Implemented selective recall

On 2026-10-28, Horia approved selective recall and requested implementation. Codex
implemented it in this working tree, preserving schema, accepted JSON and archived
results. No ongoing retrieval owner or maintainer was assigned.

[recall_selection.py](../tools/recall_selection.py) requires a specific entity anchor
or at least two matching assertion terms, including a non-generic term, with 45
percent query-term agreement for automatic recall. Paths and qualified symbols are
preserved; code anchors can retrieve facts explicitly supporting their implements
relationships. Ranking favors anchors, question intent, facts and informative
agreement. BM25 ranks candidates without becoming a confidence probability.

Vague follow-ups/approvals can abstain before FTS search. Weak results and stale
source snapshots are suppressed automatically; deleted aliases cannot seed an
active entity through another source. Detail mode retains broader discovery.
Identical normalized assertions with compatible canonical subject, kind, state,
lifecycle, code and attribution evidence collapse across pages while retaining all
source records/citations. Different numbers, negation, actors, code identities and
states stay separate. Paraphrases are not merged and stored facts are not deleted.

[brief_context.py](../tools/brief_context.py) and [recall_hook.py](../tools/recall_hook.py)
default to three evidence records and 2,000 characters total, including instructions,
receipt, citations and expansion guidance. Only whole records fit; oversized records
can be skipped without hiding later fitting ones. Passages/legacy text count as
excerpts. Automatic recall examines no general relationship neighborhood. Explicit
evidence and supported code relationships supply up to two distinct code locators
per record; missing test references are not guessed.

Weak automatic matches inject no reference context. Missing databases, empty indexes
and errors retain bounded guidance and allow submission. Logs retain selection
signals, candidate/selected counts, rejection reasons, duplicate groups and available
detail; delivery counts separately describe what actually fit. Existing client
hook commands and the distinction between supplied and used evidence are preserved.

Expand with `uv run --project tools --locked tools/recall_graph.py --entity feature:automatic-graph-updates --view detail --hops 2`.
The CLI defaults to detail mode; --entity works without a question, and --limit
controls 1 to 50 facts, default 10. Auto still caps at three. Explicit hook detail
retains the 6,000-character ceiling; --max-context-chars configures a hook budget
within that ceiling. AGENTS.md directs focused code verification and expansion
when brief evidence is insufficient. Source freshness concerns saved wiki hashes,
not continuing code verification. The limits/heuristics remain tunable.

## Verification

### Comprehensive source review and same-page state fix

On 2026-10-29, Codex reviewed [recall_graph.py](../tools/recall_graph.py),
[search_knowledge.py](../tools/search_knowledge.py),
[recall_selection.py](../tools/recall_selection.py),
[brief_context.py](../tools/brief_context.py) and
[recall_hook.py](../tools/recall_hook.py) with their tests for Horia's comprehensive
coverage request. The candidate loader previously deduplicated by source page plus
body text. Distinct same-page assertions with identical text but different states
could disappear before compatible-state-aware selection. Codex changed this to
source page plus record ID; select_facts remains responsible for compatible
assertion grouping. Current and proposed assertions now survive candidate loading
separately. Stored knowledge and schema are unchanged.

[test_selective_recall.py](../tools/tests/test_selective_recall.py) adds the same-page
current/proposed regression. [test_graph_recall.py](../tools/tests/test_graph_recall.py)
checks Unicode/literal matching, bounded traversal, cycles and read-only snapshots;
[test_recall_hook.py](../tools/tests/test_recall_hook.py) checks adapters, concurrent
logs, budgets and truthful citations/counts. All 100 tests passed with the standard
unittest discovery command. These are source, CLI and adapter checks; they do not
extend earlier live-client proofs or establish token/task-time savings.

### Selective recall checks

On 2026-10-28, `uv run --project tools --locked python -m unittest discover -s tools/tests -q`
passed all 91 tests at revision 0a3793fcd191f5d3f562d9817f4523238d8885d0 plus working-tree
changes. Fourteen new tests cover anchors, references, silent client misses,
duplicate provenance, conflicting claims, stale/deleted/superseded sources,
inactive aliases, heading passages, entity expansion, absent tests, budgets and
read-only CLI behavior. Existing queue/migration/concurrency/relocation checks passed.

A local 12-prompt set retained context for six specific questions and supplied none
for six vague/unrelated prompts. Rebuild, bootstrap-command and 300-second lease
answers ranked first. Injected context fell from 49,441 to 9,553 characters, an
80.7 percent reduction in this sample. These are character counts, not model tokens,
net task cost or speed; this is not a held-out benchmark.

All three actual configured client commands passed positive/negative adapter checks
with their project environment variables set. CLI entity expansion returned ten
facts/eight relationships. These are adapter/CLI checks, not fresh live-model proof.
Prior live Codex evidence remains below; Claude/Cursor model delivery is still
unverified. Evidence is local at `.state/verification/selective-recall/`.

### Verified recall feedback

On 2026-10-28, all 69 tests passed with
`uv run --project tools --locked python -m unittest discover -s tools/tests -q`.
Checks cover delivered counts, fact/excerpt separation, source-section links in
paths with spaces, omitted oversized records, partial results, misses, safe source
resolution and the existing client, queue, migration and watcher contracts.

Fresh Codex CLI 0.159.2 sessions with the configured GPT-6.1-Sol model and unchanged
production recall handler/helper passed three read-only probes without tools:
matched knowledge produced a supplied-count commentary and a final callout linking
only the relevant section; matched but unused knowledge produced the receipt and
no callout; a miss produced neutral feedback and no callout. Counts distinguished
two extracted facts from two fallback note excerpts across two pages. An interactive
terminal session also displayed the source-linked callout. The brief native progress
label was not captured, so persistent commentary provides the observed feedback.

The changed production hook definition was reviewed through normal client trust.
Temporary fixture trust was removed; the shared background server was not restarted.
Evidence is local at `.state/verification/recall-ui/report.json`. These observations
verify Codex model output and terminal presentation, not a custom desktop component
or Claude/Cursor model delivery.

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

### Observed retrieval overhead

On 2026-10-28, the automatic recall record for Horia's question about token savings
and faster subsequent agents supplied 5,936 context characters: 10 facts and four
relationships from six pages, marked partial. Its early facts included Cursor
context delivery and queue/capture details. Inspection of `.state/recall_runs.jsonl`
confirmed these were actually supplied. This is evidence of weakly relevant context
on this prompt, not proof that recall increases cost on every task. The current
formatter caps characters, while lexical search uses OR terms and ranks bounded
hits without a task-utility acceptance threshold. See
[search_knowledge.py](../tools/search_knowledge.py) and
[recall_hook.py](../tools/recall_hook.py). Existing verification reports cover
publication, preservation and client delivery; none measures paired task efficiency.

## Ownership

Codex performed the documented comparison and standardized this page on 2026-10-28 at Horia's request. No ongoing retrieval maintainer, additional reviewer or upstream author identity is assigned by this source.

Horia requested both recall-feedback stages on 2026-10-28. Codex implemented the
progress label, bounded delivery receipt, source citations and answer-callout
instructions. This attribution assigns no ongoing owner or maintainer.

## Open questions

Claude and Cursor model delivery remain unverified. No retrieval performance or
paired agent-efficiency benchmark has been recorded. Whether avoided investigation
outweighs recalled context and ongoing capture/extraction overhead remains unknown.

## Change history

- 2026-10-27: Recorded the pinned-source comparison; bounded traversal and shared prompt hooks followed.
- 2026-10-28: Recorded the implemented engineering/FTS model and controlled Codex delivery test. Standardized the page and retained its comparison, next-step and verification anchors.
- 2026-10-28: Recorded the visual-recall request, documented hook UI limits and a
  proposed distinction between retrieved context and cited use. Recall behavior
  is unchanged; custom UI rendering remains unverified.
- 2026-10-28: Implemented the accepted two-stage feedback and delivery receipt;
  verified 69 tests and fresh Codex used/unused/miss responses. Retained the
  original proposal as historical context; custom interactive UI remains proposed.
- 2026-10-28: Recorded Horia's token-saving and subsequent-agent speed goal,
  observed weakly relevant context on that question, and proposed task-oriented
  capture, selective retrieval and a paired efficiency evaluation. No savings
  claim or retrieval change was made.
- 2026-10-28: Added a proposed implementation for separate automatic/explicit recall,
  anchor and term-agreement filtering, conservative cross-page deduplication,
  supported code/test references, brief-context settings and entity-focused
  expansion. Runtime behavior remains unchanged.
- 2026-10-28: Horia accepted selective recall; Codex implemented the automatic/detail
  policies, filtering, conservative deduplication, brief context, entity expansion
  and diagnostics. All 91 tests and 12 local prompt cases passed; character savings
  do not establish net token savings or faster task completion.
- 2026-10-29: Fixed same-page candidate collapse across states during comprehensive
  review and added its regression; all 100 tests passed.
