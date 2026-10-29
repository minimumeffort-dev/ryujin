# Existing-codebase knowledge bootstrap

## Purpose

Create a source-backed engineering baseline when adding Ryujin to existing code.
The current agent reviews source and writes architecture/feature wiki notes;
the ordinary extraction queue publishes them to the graph.

## Current behavior

Run `uv run --project tools --locked tools/bootstrap_knowledge.py start` from the
host root. Follow the returned prompt and [workflow](../tools/bootstrap/workflow.md).
`read` delivers the next chunk with path, hash, offsets and starting line;
`read PATH --chunk N` revisits it. The agent reviews manifests, documentation,
implementation and tests together. Filenames are inventory, not semantic facts.
No separate model is launched. Delivery does not prove understanding or tests.

After writing notes, `finish --notes llm-wiki/architecture.md llm-wiki/FEATURE.md`
rejects source drift and incomplete delivery. Each topic must link to inventoried
source, including an architecture topic. Finish synchronizes saved notes into
normal extraction without claiming jobs; the current agent follows the extraction
workflow until empty. Existing wiki, accepted JSON and graph history are preserved.

`status` reports not_started, reviewing, ready_for_notes, extraction_pending or
complete. Complete requires every baseline note hash in immutable accepted runs.
Deliberate partial handoff requires `--allow-partial --gaps-note PATH`, an included
topic with a nonempty Open questions section, and ends as complete_partial.

Later features use ordinary capture, reconciliation, extraction and recall without
another bootstrap. Archived runs preserve baseline completion after later note
revisions. Plain start resumes; start --refresh rescans and retains delivered
chunks only for identical content and chunk boundaries.

## Code locations

### Comprehensive coverage tooling

[source_coverage.py](../tools/source_coverage.py) adds an auditable source-review
ledger to the bootstrap workflow. Run init after start --refresh; its Python AST
visitor enumerates classes, functions, async functions, nested qualified identities,
definition sites and imported names without executing source. Repeated definitions
share a logical key with separate sites. Imports are syntax observations, not
proof of runtime dependency behavior. Non-Python source needs manual review.

After reading and writing substantive topics, record each file as reviewed with
topic links, canonical entities and a review reason, omitted with a reason, or
unresolved. Reviewed files require all chunks delivered, no parse errors and a
source link from a substantive topic. The coverage summary cannot be its own review
evidence. Unchanged source hashes preserve records; source/topic drift invalidates
completion. Parse errors and scan gaps remain explicit.

Runtime state is .state/bootstrap/coverage.json with atomic writes and a dedicated
OS lock. verify checks dispositions and current source/topic hashes without creating
a database. verify --published additionally opens SQLite read-only and requires
current accepted topic hashes plus source-specific graph contributions for every
mapped entity. export --output raw/REVIEW/coverage.json writes the catalogue and
ledger without the machine-specific project root. These checks verify recorded
review and publication, not exhaustive semantic understanding.

[Coverage tests](../tools/tests/test_source_coverage.py) check nested/async/repeated
definitions, no source execution, dispositions, source/topic drift, parse/budget
gaps, source links, exact publication/entity support and relocated CLI behavior.

- [bootstrap_knowledge.py](../tools/bootstrap_knowledge.py): inventory, delivery,
  drift checks, handoff and publication status.
- [Prompt](../tools/bootstrap/prompt.md), [workflow](../tools/bootstrap/workflow.md)
  and [AGENTS.md](../AGENTS.md): current-agent review and capture guidance.
- [recall_hook.py](../tools/recall_hook.py), `fallback_context`: empty/missing graph
  guidance recommends bootstrap when a source-backed baseline is absent, normal
  extraction when one exists. Generic misses do not request rescanning.
- [watcher_lock.py](../tools/watcher_lock.py), `file_lock`: reusable OS locking;
  bootstrap has its own operation lock, separate from watcher lifetime locking.
- [Tests](../tools/tests/test_bootstrap_knowledge.py): relocated end-to-end flow.

## Constraints

Defaults: 2,000 UTF-8 text files, 8 MiB total, 512 KiB/file, 12,000 characters/chunk.
Start accepts limit overrides and repeated --exclude GLOB. Git discovery honors
ignored untracked files; filesystem fallback uses standard exclusions. Generated
output, dependencies, wiki/raw/state, binaries, symlinks, outside-root paths and
common credential files are excluded. Exclusions are not a general secret detector.
Budget/unreadable gaps stay visible. Source changes require refresh before handoff.

`.state/bootstrap/manifest.json` stores hashes, metadata and progress using atomic
replacement and a dedicated OS lock. Bootstrap creates no source copies or database
backup. Graph schema remains unchanged. Do not edit wiki during extraction.

## Decisions and reasoning

On 2026-10-28, Horia requested an existing-codebase baseline followed by normal
flows for later changes. Review source into the wiki first because it is the
durable engineering record. Reuse validated transactional publication and history
instead of adding a second graph writer. Keep large-repository coverage explicit.

## Verification

### Comprehensive review proposal

Historical proposal from 2026-10-28; Horia authorized implementation on 2026-10-29.
The ledger and comprehensive pass described below are now implemented; this dated
proposal is retained as history. See [the current coverage record](source-coverage.md).

On 2026-10-28, Horia asked how to traverse the codebase and extract all entities.
Proposed follow-up: refresh the source inventory, review each subsystem's code,
tests and configuration, update substantive wiki topics, then use normal validated
extraction/publication. Re-extracting existing wiki pages alone cannot recover
knowledge missing from those pages. No new comprehensive pass was performed for
this clarification, and a coverage ledger is not implemented by the current tool.

Track every in-scope file's disposition: reviewed with topic links and canonical
entities, intentionally omitted with a reason, or unresolved. A deterministic
symbol inventory can enumerate Python functions/classes for the review checklist;
it cannot establish features, historical reasoning or ownership. Record those
semantic entities/relationships from supported source review and explicit statements.
Do not infer implementers or owners from Git authorship. If every syntactic symbol
must itself become a graph node, that needs an explicit catalog ingestion contract;
the current extraction prompt deliberately selects meaningful engineering entities.

Review bootstrap, watcher/client lifecycle, capture/synchronization, extraction and
validation, queue/leases, graph publication/schema/history, and recall/selection/
formatting with their tests. Verify that files have dispositions, important features
have implementation references, test references are supported or unknown, accepted
note hashes are published, and representative questions retrieve the expected facts.
File/chunk delivery counts alone do not establish semantic completeness.

### Baseline verification

On 2026-10-28, `uv run --project tools --locked python -m unittest discover -s tools/tests -q`
passed all 77 tests at revision `0a3793fcd191f5d3f562d9817f4523238d8885d0` plus
working-tree changes. The relocated CLI test preserves prior accepted knowledge,
reviews existing code, hands fixture notes to normal extraction and reaches complete.
It then changes retry limit 3 to 4 through ordinary capture/extraction, retrieves 4,
and retains complete baseline status, original JSON and database/FK integrity.
Fixture note writing tests handoff, not independent model review.

Ryujin's actual baseline review covered 37 source files in 45 chunks with zero
scan-budget/unreadable gaps. Codex read the delivered source and combined existing
topic coverage with this page, [architecture](architecture.md) and
[queue details](extraction-queue.md). Publication is checked separately through
status and graph recall after acknowledgment.

Normal publication accepted all eight baseline pages and status reported complete
with no unfinished extraction jobs. Recall returned the initialization command,
ordinary flow for later features, lease/retry defaults and the correct original
rebuild answer first. All 127 previous supported fact texts, 61 existing result
files and 14 archived runs were preserved unchanged. Accepted source hashes,
database integrity and foreign keys passed. Detailed evidence is local runtime
state at `.state/verification/bootstrap-knowledge/report.json`.

## Ownership

On 2026-10-29, Horia requested the comprehensive pass. Codex implemented
source_coverage.py, its eight tests and workflow/AGENTS.md guidance, reviewed all
42 eligible source files and wrote the topic updates and coverage catalogue in
this working tree. This assigns implementation/review for this pass, not historical
code ownership or an ongoing maintainer.

Horia requested the existing-codebase bootstrap on 2026-10-28. Codex implemented
the tool, prompt/workflow, guidance, tests and baseline notes in this working tree.
No ongoing owner or maintainer was assigned. Unknown historical attribution stays unknown.

## Open questions

Native Windows execution is untested. Large projects may need budget overrides
or explicit scope exclusions. Source delivery does not establish semantic completeness.
Historical reasons and owners need explicit evidence. Transcript capture and
incremental graph publication remain deferred.

A read-only inventory check after selective recall on 2026-10-28 found 40 eligible
files, no scan-budget/unreadable gaps, three new source files and seven changed
files relative to the original 37-file baseline. The new files are brief_context.py,
recall_selection.py and test_selective_recall.py. Original baseline completion tracks
its historical accepted notes; it does not assert current comprehensive coverage.

## Change history

- 2026-10-28: Replaced informal initial source review with resumable bootstrap and
  normal-queue handoff at Horia's request; preserved schema, knowledge and later
  capture flow. All 77 tests passed.
- 2026-10-28: Recorded the proposed component-by-component coverage pass and its
  missing file/entity disposition ledger; distinguished structural symbol inventory
  from curated semantic extraction. No new bootstrap run was started.
- 2026-10-29: Implemented the coverage ledger/static catalogue, refreshed and read
  all 42 files in 53 chunks with zero scan gaps; catalogued 275 Python identities
  and 297 imported-name entries across 29 Python files. All 100 tests passed.
  Current publication is independently checked with verify --published and status;
  [the coverage record](source-coverage.md) links the durable snapshot and limits.
