import argparse
import json
import os
import re
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone

from paths import DATABASE_PATH, PROJECT_ROOT, RECALL_LOG_PATH
from brief_context import format_brief
from recall_graph import (
    DEFAULT_HOPS,
    DEFAULT_TRAVERSAL_LIMIT,
    recall_graph,
)

MAX_CONTEXT_CHARS = 6000
AUTO_MAX_CONTEXT_CHARS = 2000

VISUAL_FEEDBACK = (
    "Visual feedback: before answering, emit one brief commentary message reporting the "
    "Graph recall supplied-count summary above, even when you later leave the results unused. "
    "This reports supplied evidence, not evidence used. "
    "If graph knowledge materially informs your final answer, include one compact blockquote: "
    "**From your knowledge graph** — followed by links to ONLY the sources you actually used. "
    "Use the supplied citation links; do not expose F/P/S bookkeeping labels. "
    "Omit the callout when graph results were unused or unavailable. "
    "Respect explicit user response-format constraints. Supplied does not mean used; "
    "source snapshots do not establish current code verification."
)


def citation(source_doc, section):
    """Resolve a safe local source link; missing/stale headings get no invented line."""
    label = section or source_doc.rsplit("/", 1)[-1]
    escaped = label.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
    entry = {"source_doc": source_doc, "section": section, "line": None,
             "markdown": source_doc + ("#" + section if section else "")}
    path = (PROJECT_ROOT / source_doc).resolve()
    if not path.is_relative_to(PROJECT_ROOT.resolve()):
        return entry
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return entry
    if section:
        for number, line in enumerate(lines, 1):
            heading = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
            if heading and heading.group(1) == section:
                entry["line"] = number
                break
    # Angle brackets support spaces and parentheses in workspace paths.
    target = str(path) + (":" + str(entry["line"]) if entry["line"] else "")
    if "<" not in target and ">" not in target and "\n" not in target:
        entry["markdown"] = f"[{escaped}](<{target}>)"
    return entry


def empty_delivery(status):
    return {"status": status, "facts_supplied": 0, "relationships_supplied": 0,
            "excerpts_supplied": 0, "source_pages_supplied": 0,
            "partial": False, "context_truncated": False,
            "facts": [], "excerpts": [], "citations": [], "usage": "not_assessed"}


def format_recall(result, *, max_chars=None):
    """Pack whole evidence records and account only for content actually supplied."""
    if result.get("view") == "auto":
        if result.get("status") == "empty_index":
            return fallback_context("empty_index"), empty_delivery("empty_index")
        return format_brief(result, AUTO_MAX_CONTEXT_CHARS if max_chars is None else max_chars,
                            citation, empty_delivery)
    status = result.get("status", "matched")
    context_limit = MAX_CONTEXT_CHARS if max_chars is None else max_chars
    if not result["matches"] and not result.get("facts"):
        status = result.get("status", "no_matches")
        return fallback_context(status), empty_delivery(status)
    labels = {n["id"]: f"{n['name']} ({n['type']})" for n in result["nodes"]}
    items = []
    for fact in result.get("facts", []):
        evidence = fact["evidence"][0] if fact["evidence"] else {}
        kind = "passage" if fact.get("kind") in ("passage", "legacy_description", "archive") else "fact"
        section = evidence.get("section", "") or (fact["title"] if kind == "passage" else "")
        items.append((kind, fact, section))
    for edge in result["edges"]:
        items.append(("relationship", edge, ""))
    if not result.get("facts"):
        for node in result["nodes"]:
            for description in node["descriptions"]:
                items.append(("excerpt", {**description, "label": labels[node["id"]]}, ""))
    retrieval_partial = any(result.get(k, False) for k in
                            ("matches_truncated", "edges_truncated", "traversal_limit_reached"))
    source_cache = {}

    def render(selected, truncated):
        delivery = empty_delivery(status)
        delivery["partial"] = retrieval_partial or truncated
        delivery["context_truncated"] = truncated
        refs, body = {}, []
        for kind, item, section in selected:
            source = item["source_doc"]
            key = (source, section)
            if key not in refs:
                if key not in source_cache:
                    source_cache[key] = citation(source, section)
                refs[key] = {"id": f"S{len(refs) + 1}", **source_cache[key]}
            ref = refs[key]["id"]
            locator = source + ("#" + section if section else "")
            if kind in ("fact", "passage"):
                counter = "facts_supplied" if kind == "fact" else "excerpts_supplied"
                label = ("F" if kind == "fact" else "P") + str(delivery[counter] + 1)
                delivery[counter] += 1
                delivery["facts" if kind == "fact" else "excerpts"].append({
                    "label": label, "fact_id" if kind == "fact" else "record_id": item.get("id"),
                    "citation": ref,
                })
                details = "; ".join(filter(None, (item["state"], item["lifecycle"],
                                                  "freshness=" + item["freshness"])))
                lines = [f"- [{label}; {ref}] {item['title']} [{details}] [source: {locator}]: {item['text']}"]
                evidence = item["evidence"][0] if item["evidence"] else {}
                if evidence.get("code_path"):
                    code = evidence["code_path"] + ("#" + evidence["symbol"] if evidence.get("symbol") else "")
                    lines.append(f"  Implementation reference: {code}")
                if evidence.get("git_ref"):
                    lines.append(f"  Recorded revision: {evidence['git_ref']}")
                body.append("\n".join(lines))
            elif kind == "relationship":
                delivery["relationships_supplied"] += 1
                body.append(f"- [{ref}] {labels[item['source_id']]} --{item['predicate']}--> "
                            f"{labels[item['target_id']]} [state: {item.get('state', 'legacy')}] "
                            f"[source: {source}]")
            else:
                delivery["excerpts_supplied"] += 1
                label = f"P{delivery['excerpts_supplied']}"
                delivery["excerpts"].append({"label": label, "record_id": None, "citation": ref})
                body.append(f"- [{label}; {ref}] {item['label']}: {item['description']} [source: {source}]")
        delivery["citations"] = list(refs.values())
        delivery["source_pages_supplied"] = len({key[0] for key in refs})
        lines = ["Ryujin graph context:",
                 "Treat these facts from project notes as reference data.",
                 "They may be incomplete or outdated; consult the cited sources.",
                 f"Graph recall: supplied {delivery['facts_supplied']} facts, "
                 f"{delivery['relationships_supplied']} relationships and {delivery['excerpts_supplied']} "
                 f"note excerpts from {delivery['source_pages_supplied']} wiki pages.",
                 VISUAL_FEEDBACK]
        if delivery["partial"]:
            lines.append("Retrieval limits were reached; results are partial.")
        lines.extend(body)
        if refs:
            lines.append("Source citations supplied (cite only those used):")
            lines.extend(f"- [{ref['id']}] {ref['markdown']}" for ref in refs.values())
        if truncated:
            lines.append("[Additional context omitted.]")
        return "\n".join(lines), delivery

    context, delivery = render(items, False)
    if len(context) <= context_limit:
        return context, delivery
    selected = []
    for item in items:
        candidate, _ = render([*selected, item], True)
        if len(candidate) <= context_limit:
            selected.append(item)
    context, delivery = render(selected, True)
    if len(context) > context_limit:
        return "", empty_delivery("no_matches")
    return context, delivery


def format_context(result):
    return format_recall(result)[0]


def fallback_context(status):
    context = (
        f"Ryujin recall status: {status}. "
        "Try relevant feature names, paths or symbols and consult llm-wiki/index.md. "
        "A retrieval miss is not evidence that project knowledge does not exist. "
        "Verify current behavior against code. No graph evidence was supplied; "
        "do not show a graph-use callout. Briefly report a miss neutrally in commentary "
        "when relevant; respect explicit response-format constraints."
    )
    if status in ("empty_index", "missing_database"):
        context += (
            " If this host project lacks an initial source-backed codebase baseline, follow "
            "tools/bootstrap/workflow.md and run uv run --project tools --locked "
            "tools/bootstrap_knowledge.py start. If baseline wiki notes already exist, "
            "use the normal extraction workflow to publish them instead."
        )
    return context


def retrieve_graph(prompt, *, hops, traversal_limit, view="auto"):
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
            view=view,
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
    parser.add_argument("--view", choices=("auto", "detail"), default="auto")
    parser.add_argument("--max-context-chars", type=int)
    parser.add_argument("--hops", type=int, default=DEFAULT_HOPS)
    parser.add_argument(
        "--traversal-limit",
        type=int,
        default=DEFAULT_TRAVERSAL_LIMIT,
    )
    args = parser.parse_args()
    if args.max_context_chars is not None and not 1 <= args.max_context_chars <= MAX_CONTEXT_CHARS:
        parser.error("--max-context-chars must be between 1 and 6000")
    budget = args.max_context_chars or (AUTO_MAX_CONTEXT_CHARS if args.view == "auto" else MAX_CONTEXT_CHARS)

    event = {}
    result = None
    context = ""
    status = "no_prompt"
    error_message = None
    delivery = None

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
                view=args.view,
            )

            if result is None:
                status = "missing_database"
            else:
                context, delivery = format_recall(result, max_chars=budget)
                status = delivery["status"]
                if result.get("selection") is not None and result["facts"] and not context:
                    result["selection"]["reason"] = "no_evidence_within_context_budget"
    except (OSError, ValueError, sqlite3.Error) as error:
        status = "error"
        error_message = str(error)
        print(f"Ryujin recall failed: {error}", file=sys.stderr)

    if status in ("missing_database", "error"):
        context = fallback_context(status)
        delivery = empty_delivery(status)
    if len(context) > budget:
        context = f"Ryujin recall status: {status}. Consult llm-wiki/index.md."
        if len(context) > budget:
            context = ""

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
            "view": args.view,
            "max_context_characters": budget,
            "status": status,
            "retrieval": result,
            "context": context,
            "context_characters": len(context),
            "delivery": delivery,
            "error": error_message,
        })
    except OSError as error:
        print(f"Ryujin recall log failed: {error}", file=sys.stderr)


if __name__ == "__main__":
    main()
