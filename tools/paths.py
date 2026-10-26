from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

NOTES_DIR = PROJECT_ROOT / "llm-wiki"
QUEUE_DIR = PROJECT_ROOT / ".state" / "extraction-queue"
