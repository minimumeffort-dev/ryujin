import argparse
import json
import sqlite3
import sys
from contextlib import closing

from paths import DATABASE_PATH
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


def retrieve_context(prompt, *, hops, traversal_limit):
    if not DATABASE_PATH.is_file():
        return ""

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

    return format_context(result)


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

    context = ""

    try:
        event = json.load(sys.stdin)

        if not isinstance(event, dict):
            raise ValueError("Expected a hook event object")

        prompt = event.get("prompt", "")

        if isinstance(prompt, str) and prompt.strip():
            context = retrieve_context(
                prompt,
                hops=args.hops,
                traversal_limit=args.traversal_limit,
            )
    except (OSError, ValueError, sqlite3.Error) as error:
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

    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
