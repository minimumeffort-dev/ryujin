# AGENTS.md

## LLM wiki

- Maintain `llm-wiki/` as lasting project knowledge. Consult its index and relevant pages before substantive work.
- Capture useful source material, verified findings, accepted decisions and their reasoning, reusable explanations and open questions.
- Search first; prefer updating existing pages. Read current contents before editing and preserve unrelated changes.
- Write concise Markdown understandable without the conversation. Link sources, relevant code and related pages.
- Distinguish facts, decisions, proposals and uncertainties. Flag contradictions, revise stale claims and repair broken links.
- Preserve originals in `raw/`. Use descriptive wiki filenames and subfolders when useful; create missing files as needed.
- Keep `llm-wiki/index.md` current with links and one-line descriptions. Record substantive wiki updates in the dated, append-only `llm-wiki/log.md`.
- Skip routine exchanges, duplicate information and updates when the user requests no file changes.

## Python tools

- Keep Python tools in `tools/` as a standalone uv project. Run commands from the project root.
- Set up with `uv sync --project tools --locked`; run scripts with `uv run --project tools --locked tools/<script>.py`.
- Add dependencies with `uv add --project tools <package>`. Keep `tools/pyproject.toml` and `tools/uv.lock` together.

## Extraction queue

When a hook reports pending jobs, read and follow [the extraction workflow](tools/extraction/workflow.md) before claiming any work.
