# Engineering extraction contract

## Purpose

Turn saved engineering notes into evidence-backed semantic entities, assertions
and relationships. Structural symbol enumeration is a separate
[coverage checklist](source-coverage.md); extraction selects meaningful knowledge.

## Current behavior

### Versioned validation

The current-agent [prompt](../tools/extraction/prompt.md) returns schema_version 2
with exactly source_doc, nodes, facts, edges and aliases beside that version.
[engineering.py](../tools/extraction/engineering.py), `validate_engineering`, checks
ten entity types, eight fact kinds, five fact states, canonical key prefixes,
unique keys and allowed relationship endpoint types. A CODE_ELEMENT key is
`code:project/relative/path#qualified_symbol`, or the path alone for a file.
Paths must be normalized and project-relative; symbols with the same name in
different files stay distinct. Every node needs a fact or supported relationship;
every edge cites a fact concerning one endpoint.

[validate.py](../tools/extraction/validate.py), `validate_extraction`, dispatches
version-two records to that contract and keeps the original versionless validator
for legacy records. Legacy types are not mechanically relabeled. The standalone
CLI needs --source-file to check excerpts against note contents; queue acceptance
always supplies the saved source snapshot.

### Evidence and attribution

Evidence names an exact Markdown heading and a verbatim excerpt, allowing
whitespace wrapping differences. `section_text` includes descendant headings until
the next heading of the same or higher level; duplicate heading names select the
first occurrence. Preserve distinct headings for durable citations.

Validation establishes structural consistency and literal evidence containment.
It does not independently prove semantic entailment, correct engineering claims,
current code behavior or execution of a reported test. The current agent must
review meaning and verify implementation before capture.

Attribution edges distinguish implementer, decision maker, approver, requester,
reviewer, author, committer, owner and maintainer, with PERSON, TEAM and AGENT kept
separate. The validator requires the named actor in supporting evidence and an
allowed attribution_basis. git_author supports authored_by only; git_committer
supports committed_by only. Other attribution requires explicit_statement.
The agent must still check that the quoted statement supports the specific role.
Unknown historical attribution stays unknown.

### Queue handoff

Follow [the workflow](../tools/extraction/workflow.md): claim, read the returned
prompt and note, write the candidate, validate, then acknowledge. Claim supplies
at most 100 existing canonical keys, not an exhaustive entity catalogue. Reuse
known identities and explicitly query when identity is unclear. No external model
is launched. Capture finishes first and wiki inputs stay unchanged during extraction.
[Queue publication](extraction-queue.md) checks hashes, evidence, lease and source
revision and archives an immutable source snapshot and accepted JSON.

## Code locations

- [Prompt](../tools/extraction/prompt.md): semantic vocabulary, evidence and roles.
- [Workflow](../tools/extraction/workflow.md): current-agent execution and leases.
- [engineering.py](../tools/extraction/engineering.py): validate_engineering,
  relative_path, section_text and source evidence validation.
- [validate.py](../tools/extraction/validate.py): legacy/version-two dispatch and CLI.
- [Engineering tests](../tools/tests/test_engineering_knowledge.py): invalid excerpts,
  endpoint types, same-named symbols, implementation versus Git authorship, and
  separate decision-maker/maintainer roles.
- [Completion tests](../tools/tests/test_queue_completion.py): invalid candidates
  leave claims intact and cannot replace accepted results.

## Verification

On 2026-10-29, Codex reviewed the prompt, both validators, queue handoff and their
tests against revision 0a3793f plus working-tree changes. All 100 tests passed with
`uv run --project tools --locked python -m unittest discover -s tools/tests -q`.
These tests check literal/structural contracts; they do not measure extraction
recall or prove that every meaningful assertion was selected.

## Ownership

Codex wrote this source-review topic on 2026-10-29 for Horia's comprehensive
coverage request. Original implementation/decision attribution remains as recorded
in [the engineering model](engineering-knowledge-model.md#ownership). No ongoing
owner or maintainer is assigned here.

## Open questions

Semantic completeness and supported role entailment still require agent judgment.
The first-100 key list may omit relevant existing identities in larger graphs.

## Change history

- 2026-10-29: Added the source-backed validator/evidence boundary and its limitations;
  preserved the extraction vocabulary, existing results and graph schema.
