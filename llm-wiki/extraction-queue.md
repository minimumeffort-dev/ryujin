# Extraction queue and publication

## Purpose

Coordinate saved-page extraction without stale, unvalidated or partial graph
publication. Initial [bootstrap](codebase-bootstrap.md) reuses this queue.

## Current behavior

### Source revisions and claims

One job exists per normalized note path. Enqueue coalesces the latest payload and
increments revision; edits during processing retain the active claim until
reconciliation. Unchanged source/prompt hashes do not create revisions.

Claim first synchronizes topic pages and recovers expired claims. BEGIN IMMEDIATE
selects the oldest available pending job by available_at then id, records a random
token and claimed revision, increments attempts and sets a 300-second default lease.
The current agent uses the returned extraction prompt and canonical keys;
claim does not launch a model. Index/log are not primary extraction jobs.

### Evidence and publication

Candidates live at `.state/extractions/<id>/<claimed_revision>/<claim_token>.json`.
Acknowledge requires the active token, processing state and unexpired lease. It
checks source hash, schema version and exact evidence, then rechecks source after
rebuilding. Changed sources/newer revisions return to pending without stale publication.

Every successful extraction acknowledgment archives the result and source snapshot,
updates the accepted pointer, rebuilds the entire graph and FTS5 index, and completes
the job in one SQLite transaction. There is no timed graph rebuild schedule.
Validation/rebuild failure or lease expiry cannot publish a partial update.
Earlier accepted results remain immutable history.

### Retry, recovery and renewal

Retry and expired-claim recovery default to five-second delay and five attempts
before failure. New revisions reset attempts and return to pending. Renewal needs
an active unexpired token and extends without shortening the existing deadline.
Stop work on rejected claims; follow workflow rules rather than retrying repeatedly.

## Code locations

- [queue_store.py](../tools/queue_store.py): enqueue, claim, acknowledge, retry,
  renew, recover_expired and database configuration.
- [consume_queue.py](../tools/consume_queue.py): CLI and synchronous reconciliation.
- [source_sync.py](../tools/source_sync.py): source/prompt hashes and topic filtering.
- [Workflow](../tools/extraction/workflow.md), [prompt](../tools/extraction/prompt.md),
  [validator](../tools/extraction/engineering.py): current-agent evidence contract.
- [build_graph.py](../tools/build_graph.py),
  [engineering_graph.py](../tools/engineering_graph.py): graph/search publication.
- [Completion tests](../tools/tests/test_queue_completion.py) and
  [engineering tests](../tools/tests/test_engineering_knowledge.py): leases,
  revisions, evidence, concurrency, rollback, snapshots and history.

## Constraints

Connections enforce WAL, synchronous FULL and foreign keys. Source paths must be
normalized/project-relative; workers nonempty and leases finite/positive. Candidate
paths include tokens to separate concurrent workers. Capture precedes extraction;
wiki stays unchanged during extraction. No ready work can coexist with delayed,
processing or failed jobs. Full rebuild cost grows with latest accepted results.

## Decisions and reasoning

Existing source makes validation, history, graph/search state and completion succeed
or fail together. Bootstrap reuses that consistency boundary to avoid a second
publisher. Historical decision makers and unstated reasons for defaults are unknown.

## Verification

On 2026-10-29, Codex revisited all queue/CLI/synchronization source and completion
tests for the comprehensive pass. The full 100-test suite passed, including wrong
tokens, expiry during validation/rebuild, changed source revisions, registration
and graph rollback, concurrent acknowledgments and concurrent distinct jobs.
This review retained queue behavior and schema.

On 2026-10-28, source review checked queue, CLI, synchronization, builders and tests
at revision `0a3793fcd191f5d3f562d9817f4523238d8885d0` plus working-tree changes.
`uv run --project tools --locked python -m unittest discover -s tools/tests -q`
passed 77 tests, including concurrency/rollback and bootstrap-to-normal-change flow.
Reading test source alone does not establish execution. Earlier publication history
remains in [graph building](session-capture.md#graph-building).

## Ownership

Codex wrote this queue baseline on 2026-10-28 for Horia's bootstrap request.
Documentation authorship does not identify original queue implementers, decision
makers or maintainers; those roles stay unknown without explicit evidence.

## Open questions

Incremental publication remains deferred. Full-rebuild scale limits are unmeasured.
Native Windows execution was not verified by the macOS tests.

## Change history

- 2026-10-28: Documented source-backed queue baseline: leases, revisions, stale
  source rejection and transactional publication. Bootstrap reuses existing schema.
