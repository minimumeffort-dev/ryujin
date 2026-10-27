# Wiki maintenance

## Purpose

Save useful codebase knowledge during normal work so later agents can explain
current behavior, locate implementation and recover recorded reasons and changes.
This is the host project's engineering record, including supported human and AI
attribution. Saved topic notes feed extraction; unsaved conversation knowledge
cannot be recovered by the watcher.

## Current behavior

### Capture at task boundaries

Before completing a substantive task, update affected topic pages after observing
the implementation and verification. Capture accepted decisions and useful findings
even when no code was changed. Search and read before writing. Use the applicable
sections of [the topic template](../tools/wiki/topic-template.md): purpose, current
behavior, code locations, constraints, decisions and reasoning, verification,
ownership, open questions and change history. Keep stable topic subheadings so
source-section links remain useful. Omit inapplicable sections and empty boilerplate.

Maintain [the architecture map](architecture.md) when entry points, component
boundaries, dependencies or data flow change. Bootstrap a bounded source-backed
map when adopting Ryujin in a new host project; inspect existing wiki coverage
for gaps. Record unknown historical reasons as unknown.

Describe current behavior separately from dated changes. Each meaningful change
records before/after behavior, the stated reason, affected code and observed
verification. Include a date and commit/issue references when available; for
uncommitted work identify the working tree. Preserve explanations of replaced
behavior and mark them historical. Acceptance, implementation, tests and deployment
are separate claims. Record verification commands or procedures, outcomes, dates,
revisions when available and material gaps. Never invent evidence or test results.

Keep [the index](index.md) as navigation with one-line descriptions and
[the log](log.md) as a concise dated, append-only ledger linking substantive updates.
Preserve original supplied material in `raw/`. Skip routine exchanges, duplicate
knowledge and writes prohibited by the user's instructions.

### Stop capture review

The first eligible Stop event requests a capture review even when the extraction
queue is empty. After capture, the current agent follows
[the extraction workflow](../tools/extraction/workflow.md), whose claim command
synchronously reconciles newly saved pages. Process jobs until empty; do not
edit source pages during extraction. When nothing needs capture and claim is
empty, finish without wiki changes. A missing workflow is reported without
claiming jobs. A queue-check failure is reported and still requests capture review.

For Codex and Claude, an active Stop continuation skips the hook; Cursor also skips
when loop_count is at least one or status is not completed. These checks occur
before logging and database access. Codex's [documented Stop contract](https://learn.chatgpt.com/docs/hooks#stop)
uses a block decision to request continuation and supplies stop_hook_active to
identify the continuation. Each original completion gets at most one
capture continuation. No transcript is read or stored by this hook and no extra
model process is launched. The review depends on the current agent following the
instructions; it does not guarantee complete capture or a fresh code audit.

## Code locations

- [AGENTS.md](../AGENTS.md): cross-project capture and extraction obligations.
- [Topic template](../tools/wiki/topic-template.md): reusable page sections outside
  the watched wiki, so placeholder text is not an extraction source.
- [queue_hook.py](../tools/queue_hook.py), `main`: loop guard, queue reconciliation
  and capture continuation for all three client adapters.
- [source_sync.py](../tools/source_sync.py), `synchronize_sources`, and
  [consume_queue.py](../tools/consume_queue.py): discover new saved notes at claim.
- [Stop-hook tests](../tools/tests/test_queue_hook.py): empty queue, guards, failures
  and isolated capture-to-recall flow.

## Constraints

An empty queue means no extraction is ready; it does not establish that all useful
knowledge was captured. The hook therefore asks for a bounded review on every
original completion, including routine ones where the agent should make no wiki
changes. It does not infer task scope from Git differences or scan transcripts.
Respect user restrictions on file changes. Preserve unrelated edits and original
accepted extraction files. Existing loop guards prevent repeated review; long or
failed extraction must follow the workflow's lease/retry rules.

## Decisions and reasoning

On 2026-10-28, Horia requested all four improvements: architecture mapping,
consistent pages, stronger AGENTS.md instructions and capture with an empty queue.
Previously the Stop hook returned immediately when no extraction job was ready;
that historical behavior could omit the reminder when no wiki page had been saved.
The replacement requests capture first and then extraction, without relying on
the presence of jobs. Keep the established client commands and loop guards.

## Verification

On 2026-10-28, `uv run --project tools --locked python -m unittest discover -s tools/tests -q`
passed all 63 tests for this working-tree change. New tests execute all three
Stop adapters with an empty queue, pending notes and protected continuation
states; verify that queue/log errors retain capture review; and distinguish
no-ready-work from delayed jobs. The isolated integration flow executes the
portable bootstrap, starts with zero jobs, receives the Stop capture reminder,
saves a topic note, claims and acknowledges its validated extraction, retrieves
its fact through the prompt hook and confirms an empty queue and valid database.
The test supplies the note as a fixture; actual model delivery is checked
separately below.

A live Codex CLI 0.159.2 test used a disposable project with the production Stop
and prompt-recall definitions and shared tool files unchanged. The wiki and queue
started empty. The model first replied READY without tools; the Stop hook logged
no ready jobs and delivered capture review. The same session then saved the
supplied accepted fixture decision and its stated rationale, claimed the note,
validated and acknowledged its extraction, and finished with an empty queue.
The guarded Stop did not request another review. A fresh model session answered
the retry-limit question from graph context without tools; its routine capture
review left wiki contents and accepted results unchanged. The graph distinguished
the named decision maker from unassigned implementation and ownership roles.
Normal workspace/hook trust was used without bypass flags; the three temporary
trust entries were removed afterward. Detailed event traces and the report are
in local `.state/verification/capture-flow/report.json`. This verifies actual Codex
model delivery; Claude and Cursor received adapter-level checks only.

## Ownership

Horia requested this change on 2026-10-28. Codex implemented the architecture map,
topic-page standardization, AGENTS.md instructions and queue-independent Stop
capture review in this working tree. No ongoing maintainer or additional reviewer
has been assigned by the source.

## Open questions

Claude and Cursor runtime delivery need independent client verification. Abrupt
termination before Stop and agent noncompliance can still leave knowledge unsaved;
automatic transcript capture remains deferred.

## Change history

- 2026-10-28: Replaced queue-dependent capture reminders with a first-Stop capture
  review even for an empty queue; retained client loop guards. Added the shared
  topic structure and architecture maintenance obligations at Horia's request.
