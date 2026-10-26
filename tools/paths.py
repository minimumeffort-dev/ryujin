from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

NOTES_DIR = PROJECT_ROOT / "llm-wiki"
STATE_DIR = PROJECT_ROOT / ".state"
DATABASE_PATH = STATE_DIR / "ryujin.sqlite3"
SCHEMA_PATH = PROJECT_ROOT / "tools" / "schema.sql"
EXTRACTION_PROMPT_PATH = PROJECT_ROOT / "tools" / "extraction_prompt.md"
