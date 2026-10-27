# AGENTS.md

## LLM wiki

Maintain `llm-wiki/` as the project's persistent, interlinked knowledge base.
Keep it current as useful knowledge emerges from our work.

### Structure

- `raw/`: original source material supplied for ingestion. Preserve it unchanged.
- `llm-wiki/index.md`: links to wiki pages with one-line descriptions.
- `llm-wiki/log.md`: append-only, dated record of substantive wiki updates.
- `llm-wiki/*.md`: topic pages, source summaries, decisions, comparisons and syntheses.
  Use descriptive filenames; introduce subfolders when useful.

### Workflow

- Consult the index and relevant pages before substantive work.
- Capture useful information from sources and conversations: verified findings,
  accepted decisions and their reasoning, reusable explanations and open questions.
- Search before creating pages. Prefer updating existing pages. Read their current
  contents before editing and preserve unrelated changes.
- Write concise Markdown understandable without the original conversation.
  Link supporting sources, relevant code and related pages.
- Distinguish verified facts, accepted decisions, proposals and uncertainties.
  Flag contradictions, revise outdated claims and repair broken links.
- Update the index when adding or reorganizing pages. Append a brief log entry
  describing substantive updates and linking to affected pages.
- Create missing wiki files when first needed. Skip routine exchanges, duplicate
  information and updates when the user explicitly requests no file changes.

## Python tools

- Keep Python tools in `tools/`, managed as a standalone uv project.
- Run commands from the project root.
- Set up the environment with `uv sync --project tools --locked`.
- Run scripts with `uv run --project tools --locked tools/<script>.py`.
- Manage dependencies with `uv add --project tools <package>` and keep `tools/pyproject.toml` and `tools/uv.lock` together.
