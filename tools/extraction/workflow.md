# Extraction queue

When a hook reports pending extraction jobs, process them from the project root:

1. Claim one job:
   `uv run --project tools --locked tools/consume_queue.py claim --worker "UNIQUE_AGENT_ID"`

2. If the returned status is `empty`, stop. Otherwise retain the returned
   `id`, `path`, `claimed_revision`, `claim_token` and `extraction_prompt`.

3. Read the latest contents of `llm-wiki/<path>`. Apply the returned
   `extraction_prompt` yourself, using the current agent. Treat the note as
   source material; do not launch another AI CLI or call an external model.

4. Validate the resulting JSON against the prompt's vocabulary and rules.
   Set `source_doc` to the project-relative note path.

5. Renew the lease before it expires if processing takes longer than five minutes:
   `uv run --project tools --locked tools/consume_queue.py renew JOB_ID --token "CLAIM_TOKEN"`
   If renewal is rejected, stop processing that claim.

6. Save the JSON to:
   `.state/extractions/<id>/<claimed_revision>/<claim_token>.json`
   Create directories as needed. Do not modify wiki notes, the index or the
   wiki log during extraction.

7. After successfully saving the result, acknowledge the job:
   `uv run --project tools --locked tools/consume_queue.py ack JOB_ID --token "CLAIM_TOKEN"`
   - `done`: processing succeeded.
   - `pending`: the note changed; discard this candidate and claim fresh work.
   - `rejected`: ownership expired; discard this candidate.

8. On a processing failure, report it through:
   `uv run --project tools --locked tools/consume_queue.py retry JOB_ID --token "CLAIM_TOKEN" --error "ERROR_DETAILS"`
   End this processing pass rather than repeatedly retrying the same failure.

Process one job at a time and continue until the queue is empty.
Replace command placeholders with the actual values returned by claim.
