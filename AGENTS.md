# AGENTS.md

## LLM wiki

- Maintain `llm-wiki/` as lasting project knowledge. Consult recalled facts before substantive work; retry empty, stale or partial recall with feature names, paths or symbols using `uv run --project tools --locked tools/recall_graph.py "QUERY"`, then consult the index and relevant pages. Verify current behavior against code.
- Automatic recall is deliberately brief and can abstain on weak or vague prompts. Use focused source checks first; when supplied evidence is insufficient, expand a supplied canonical key with `uv run --project tools --locked tools/recall_graph.py --entity KEY --view detail --hops 2`. Missing recall does not establish missing knowledge. Never infer absent test references or code freshness from a wiki snapshot.
- When recall supplies evidence, report its supplied-count summary once in commentary before answering, even if those results are later unused. If graph knowledge materially informs the final answer, include one compact blockquote labeled **From your knowledge graph** with links to only the source sections used. Use the hook's citation links; distinguish supplied evidence from assistant-reported use, omit the callout for unused/missing results, and respect explicit response-format requests.
- Capture useful source material, verified findings, accepted decisions and their reasoning, reusable explanations and open questions.
- Before completing a substantive task and before extraction, update affected topic pages using [the capture guidance](llm-wiki/wiki-maintenance.md) and [page structure](tools/wiki/topic-template.md). Record current behavior, relevant paths/symbols, changes, decisions and stated reasons, constraints, observed verification and open questions; omit inapplicable sections.
- Maintain [the architecture map](llm-wiki/architecture.md) when component boundaries, entry points, dependencies or data flow change. Bootstrap a bounded, source-backed map for a new host project; identify gaps in existing coverage and never invent historical reasons.
- For first adoption into an existing codebase or a missing host-project baseline, follow [the bootstrap workflow](tools/bootstrap/workflow.md). The current agent reviews sources and writes wiki notes; hand them to normal extraction and verify publication before calling bootstrap complete. Later changes use ordinary capture; refresh bootstrap only when requested or coverage needs it.
- For a requested comprehensive source pass, use the workflow's symbol inventory and per-file coverage ledger. Record reviewed, omitted-with-reason or unresolved dispositions; verify current topic hashes and graph mappings with `tools/source_coverage.py verify --published`. Symbol enumeration and recorded review do not prove exhaustive semantic understanding.
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
