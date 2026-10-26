# AGENTS.md

## Python tools

- Keep Python tools in `tools/`, managed as a standalone uv project.
- Run commands from the project root.
- Set up the environment with `uv sync --project tools --locked`.
- Run scripts with `uv run --project tools --locked tools/<script>.py`.
- Manage dependencies with `uv add --project tools <package>` and keep `tools/pyproject.toml` and `tools/uv.lock` together.
