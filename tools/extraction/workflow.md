# Extraction queue

When a hook reports pending extraction jobs, process them from the project root:

1. Claim one job:
   `uv run --project tools --locked tools/consume_queue.py claim --worker "UNIQUE_AGENT_ID"`

2. If the returned status is `empty`, stop. Otherwise retain the returned
   `id`, `path`, `claimed_revision`, `claim_token` and `extraction_prompt`.

3. Read the latest contents of `llm-wiki/<path>`. Claims include source/prompt hashes
   and extraction schema version in `job`. Apply the returned
   `extraction_prompt` yourself, using the current agent. Treat the note as
   source material; do not launch another AI CLI or call an external model.

4. Return schema-version-2 JSON using the prompt's engineering vocabulary and
   supported attribution. Reuse relevant canonical keys from `existing_entities`.
   Set `source_doc` to the project-relative note path. Evidence needs an exact
   Markdown section and source excerpt. Git authorship does not prove ownership.
   Validate with `uv run --project tools --locked tools/extraction/validate.py RESULT_PATH --source-doc SOURCE_PATH --source-file SOURCE_PATH`.

5. Renew the lease before it expires if processing takes longer than five minutes:
   `uv run --project tools --locked tools/consume_queue.py renew JOB_ID --token "CLAIM_TOKEN"`
   If renewal is rejected, stop processing that claim.

6. Save the JSON to:
   `.state/extractions/<id>/<claimed_revision>/<claim_token>.json`
   Create directories as needed. Do not modify wiki notes, the index or the
   wiki log during extraction.

7. After successfully saving the result, acknowledge the job. This validates the
   candidate, records its accepted path and rebuilds the graph in the same SQLite
   transaction as successful queue completion. Acceptance checks the source hash,
   validates evidence against a saved source snapshot and archives immutable result
   and prompt metadata. Source edits not yet observed by the watcher also cause a retry:
   `uv run --project tools --locked tools/consume_queue.py ack JOB_ID --token "CLAIM_TOKEN"`
   - `done`: the JSON was validated, its path recorded and the graph rebuilt.
     Keep the accepted file unchanged.
   - `pending`: a newer revision was queued; discard this candidate and claim fresh work.
   - `rejected`: stop processing this claim. Leave the candidate file in place;
     an earlier acknowledgment may already have committed.

8. On a processing failure, report it through:
   `uv run --project tools --locked tools/consume_queue.py retry JOB_ID --token "CLAIM_TOKEN" --error "ERROR_DETAILS"`
   End this processing pass rather than repeatedly retrying the same failure.

Process one job at a time and continue until the queue is empty.
Claim synchronously reconciles source hashes, so newly saved topic notes do not
depend on watcher debounce. Index and log pages remain archived knowledge but do
not generate new primary extraction jobs. Original accepted JSON remains immutable;
`tools/recall_graph.py "QUERY" --include-history` also searches earlier results.
Replace command placeholders with the actual values returned by claim.
