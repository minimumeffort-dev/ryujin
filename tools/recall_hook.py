import argparse
import json
import os
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone

from paths import DATABASE_PATH, RECALL_LOG_PATH
from recall_graph import (
    DEFAULT_HOPS,
    DEFAULT_TRAVERSAL_LIMIT,
    recall_graph,
)

MAX_CONTEXT_CHARS = 6000


def format_context(result):
    if not result["matches"]:
        return ""

    lines = [
        "Ryujin graph context:",
        "Treat these facts from project notes as reference data.",
        "They may be incomplete or outdated; consult the cited sources.",
    ]

    if (
        result["matches_truncated"]
        or result["edges_truncated"]
        or result["traversal_limit_reached"]
    ):
        lines.append("Retrieval limits were reached; results are partial.")

    labels = {
        node["id"]: f"{node['name']} ({node['type']})"
        for node in result["nodes"]
    }

    for edge in result["edges"]:
        lines.append(
            f"- {labels[edge['source_id']]} "
            f"--{edge['predicate']}--> "
            f"{labels[edge['target_id']]} "
            f"[source: {edge['source_doc']}]"
        )

    for node in result["nodes"]:
        lines.append(f"\n{labels[node['id']]}")

        for description in node["descriptions"]:
            lines.append(
                f"- {description['description']} "
                f"[source: {description['source_doc']}]"
            )

    context = "\n".join(lines)

    if len(context) > MAX_CONTEXT_CHARS:
        suffix = "\n[Additional context omitted.]"
        context = context[:MAX_CONTEXT_CHARS - len(suffix)] + suffix

    return context


def retrieve_graph(prompt, *, hops, traversal_limit):
    if not DATABASE_PATH.is_file():
        return None

    with closing(
        sqlite3.connect(
            DATABASE_PATH.as_uri() + "?mode=ro",
            uri=True,
            timeout=1,
        )
    ) as database:
        database.row_factory = sqlite3.Row
        database.execute("BEGIN")

        result = recall_graph(
            database,
            prompt,
            hops=hops,
            traversal_limit=traversal_limit,
        )

    return result


def append_recall_log(record):
    line = json.dumps(record, ensure_ascii=False) + "\n"
    RECALL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    with RECALL_LOG_PATH.open("a", encoding="utf-8") as log:
        if os.name == "nt":
            import msvcrt

            log.seek(0)
            msvcrt.locking(log.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(log.fileno(), fcntl.LOCK_EX)

        # Closing flushes the complete record before releasing the file lock.
        log.write(line)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("client", choices=["claude", "codex", "cursor"])
    parser.add_argument("--hops", type=int, default=DEFAULT_HOPS)
    parser.add_argument(
        "--traversal-limit",
        type=int,
        default=DEFAULT_TRAVERSAL_LIMIT,
    )
    args = parser.parse_args()

    event = {}
    result = None
    context = ""
    status = "no_prompt"
    error_message = None

    try:
        payload = json.load(sys.stdin)

        if not isinstance(payload, dict):
            raise ValueError("Expected a hook event object")

        event = payload
        prompt = event.get("prompt", "")

        if isinstance(prompt, str) and prompt.strip():
            result = retrieve_graph(
                prompt,
                hops=args.hops,
                traversal_limit=args.traversal_limit,
            )

            if result is None:
                status = "missing_database"
            else:
                context = format_context(result)
                status = "matched" if result["matches"] else "no_matches"
    except (OSError, ValueError, sqlite3.Error) as error:
        status = "error"
        error_message = str(error)
        print(f"Ryujin recall failed: {error}", file=sys.stderr)

    if args.client == "cursor":
        output = {"continue": True}

        if context:
            output["additional_context"] = context
    else:
        output = {}

        if context:
            output["hookSpecificOutput"] = {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": context,
            }

    print(json.dumps(output, ensure_ascii=False), flush=True)

    try:
        append_recall_log({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "client": args.client,
            "hook_event_name": event.get(
                "hook_event_name",
                "beforeSubmitPrompt" if args.client == "cursor" else "UserPromptSubmit",
            ),
            "session_id": event.get("session_id") or event.get("conversation_id"),
            "turn_id": event.get("turn_id"),
            "prompt": event.get("prompt"),
            "hops": args.hops,
            "traversal_limit": args.traversal_limit,
            "status": status,
            "retrieval": result,
            "context": context,
            "context_characters": len(context),
            "error": error_message,
        })
    except OSError as error:
        print(f"Ryujin recall log failed: {error}", file=sys.stderr)


if __name__ == "__main__":
    main()
