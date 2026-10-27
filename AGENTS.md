# AGENTS.md

## LLM wiki

- Maintain `llm-wiki/` as lasting project knowledge. Consult recalled facts before substantive work; retry empty, stale or partial recall with feature names, paths or symbols using `uv run --project tools --locked tools/recall_graph.py "QUERY"`, then consult the index and relevant pages. Verify current behavior against code.
- Capture useful source material, verified findings, accepted decisions and their reasoning, reusable explanations and open questions.
- Before completing a substantive task and before extraction, update affected topic pages using [the capture guidance](llm-wiki/wiki-maintenance.md) and [page structure](tools/wiki/topic-template.md). Record current behavior, relevant paths/symbols, changes, decisions and stated reasons, constraints, observed verification and open questions; omit inapplicable sections.
- Maintain [the architecture map](llm-wiki/architecture.md) when component boundaries, entry points, dependencies or data flow change. Bootstrap a bounded, source-backed map for a new host project; identify gaps in existing coverage and never invent historical reasons.
- Record explicit implementation, decision, approval and maintenance attribution, separating people, teams and AI agents. Git author/committer metadata does not establish who implemented, decided or owns code. Leave unsupported attribution unknown.
- Search first; prefer updating existing pages. Read current contents before editing and preserve unrelated changes.
- Write concise Markdown understandable without the conversation. Link sources, relevant code and related pages.
- Distinguish facts, decisions, proposals and uncertainties. Date meaningful changes, include revision references when available, and mark replaced behavior as historical while retaining its explanation. Flag contradictions, revise stale claims and repair broken links.
- Preserve originals in `raw/`. Use descriptive wiki filenames and subfolders when useful; create missing files as needed.
- Keep `llm-wiki/index.md` current with links and one-line descriptions. Record substantive wiki updates in the dated, append-only `llm-wiki/log.md`.
- Skip routine exchanges, duplicate information and updates when the user requests no file changes.

## Python tools

- Keep Python tools in `tools/` as a standalone uv project. Run commands from the project root.
- Set up with `uv sync --project tools --locked`; run scripts with `uv run --project tools --locked tools/<script>.py`.
- Add dependencies with `uv add --project tools <package>`. Keep `tools/pyproject.toml` and `tools/uv.lock` together.

## Extraction queue

The first Stop hook requests a capture review even with an empty queue. Save missing substantive knowledge first, then read and follow [the extraction workflow](tools/extraction/workflow.md) before claiming any work. Keep wiki pages unchanged during extraction; finish when capture is unnecessary and the queue is empty.
