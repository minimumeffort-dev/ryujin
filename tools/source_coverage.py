"""Auditable source review: static Python symbols, file dispositions and publication checks."""
import argparse
import ast
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3

import bootstrap_knowledge as bootstrap
from watcher_lock import file_lock

VERSION = 1


def ledger_path():
    return bootstrap.STATE_DIR / "bootstrap" / "coverage.json"


def write_json(path, data):
    # Reuse atomic replace without changing the bootstrap manifest or database.
    import os
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.stem + "-", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def symbols(relative, text):
    """Parse definitions/imports, including nested scopes, without importing source."""
    tree = ast.parse(text.lstrip("\ufeff"), filename=relative)
    definitions, imports, scope = {}, [], []

    class Visitor(ast.NodeVisitor):
        def definition(self, node, kind):
            qualified = ".".join([*scope, node.name])
            key = "code:" + relative + "#" + qualified
            entry = definitions.setdefault(key, {"key": key, "symbol": qualified,
                                                  "kind": kind, "definitions": []})
            entry["definitions"].append({"line": node.lineno, "end_line": node.end_lineno,
                                           "kind": kind})
            scope.append(node.name)
            self.generic_visit(node)
            scope.pop()

        def visit_ClassDef(self, node):
            self.definition(node, "class")

        def visit_FunctionDef(self, node):
            self.definition(node, "function")

        def visit_AsyncFunctionDef(self, node):
            self.definition(node, "async_function")

        def visit_Import(self, node):
            for alias in node.names:
                imports.append({"module": alias.name, "name": None, "alias": alias.asname,
                                "level": 0, "line": node.lineno, "scope": ".".join(scope)})

        def visit_ImportFrom(self, node):
            for alias in node.names:
                imports.append({"module": node.module, "name": alias.name, "alias": alias.asname,
                                "level": node.level, "line": node.lineno, "scope": ".".join(scope)})

    Visitor().visit(tree)
    return {"symbols": list(definitions.values()), "imports": imports}


def current_bootstrap():
    state = bootstrap.load_state()
    if state is None:
        raise ValueError("Run bootstrap_knowledge.py start --refresh first")
    if bootstrap.inventory(state["options"])["signature"] != state["inventory"]["signature"]:
        raise ValueError("Source inventory changed; refresh bootstrap before reviewing")
    return state


def load_ledger():
    data = json.loads(ledger_path().read_text(encoding="utf-8"))
    if data.get("version") != VERSION or data.get("project_root") != str(bootstrap.PROJECT_ROOT.resolve()):
        raise ValueError("Unsupported coverage ledger or different project")
    return data


def initialize():
    state = current_bootstrap()
    old = load_ledger() if ledger_path().exists() else None
    old_files = {f["path"]: f for f in old["files"]} if old else {}
    files = []
    for file in state["inventory"]["files"]:
        path = bootstrap.PROJECT_ROOT / file["path"]
        text = path.read_bytes().decode("utf-8")
        if bootstrap.digest(text) != file["hash"]:
            raise ValueError("Source changed during inventory; refresh and retry")
        entry = {**file, "status": "unresolved", "topics": [], "entities": [], "reason": "",
                 "symbols": [], "imports": [], "parse_error": None}
        if path.suffix == ".py":
            try:
                entry.update(symbols(file["path"], text))
            except (SyntaxError, ValueError, RecursionError) as error:
                entry["parse_error"] = str(error)
        previous = old_files.get(file["path"])
        if previous and previous["hash"] == file["hash"]:
            for key in ("status", "topics", "entities", "reason", "reviewed_at"):
                if key in previous:
                    entry[key] = previous[key]
        files.append(entry)
    eligible = {f["path"] for f in files}
    gaps = {g["path"] for g in state["inventory"]["gaps"]}
    candidates, _ = bootstrap.candidate_paths()
    excluded = [{"path": p, "reason": "Configured inventory exclusion or non-UTF-8/binary file"}
                for p in candidates if p not in eligible and p not in gaps]
    data = {"version": VERSION, "project_root": str(bootstrap.PROJECT_ROOT.resolve()),
            "revision": state["git_revision"], "inventory_signature": state["inventory"]["signature"],
            "created_at": bootstrap.timestamp(), "files": files,
            "scan_gaps": state["inventory"]["gaps"], "excluded": excluded,
            "scope": "Eligible first-party text files; Python class/function definitions and imported-name entries."
                     " Symbols are structural observations, not proof of semantic completeness or ownership."}
    write_json(ledger_path(), data)
    return data


def topic_path(relative):
    path = (bootstrap.PROJECT_ROOT / relative).resolve()
    if (not path.is_relative_to(bootstrap.NOTES_DIR.resolve()) or path.suffix.lower() != ".md"
        or path.name.casefold() in ("index.md", "log.md", "source-coverage.md")):
        raise ValueError("Review evidence must be a substantive topic inside llm-wiki")
    return path


def linked_sources(path, text):
    result = set()
    for link in re.findall(r"\]\((<[^>\n]+>|[^)\n]+)\)", text):
        link = link.strip("<>")
        if "://" in link or link.startswith("#"):
            continue
        address = re.sub(r":\d+$", "", link.split("#", 1)[0])
        target = (path.parent / address).resolve()
        if target.is_relative_to(bootstrap.PROJECT_ROOT.resolve()):
            result.add(target.relative_to(bootstrap.PROJECT_ROOT.resolve()).as_posix())
    return result


def record(paths, status, topics, entities, reason):
    state = current_bootstrap()
    data = load_ledger()
    if data["inventory_signature"] != state["inventory"]["signature"]:
        raise ValueError("Coverage snapshot differs from bootstrap; run init")
    if status not in ("reviewed", "omitted", "unresolved") or not reason.strip():
        raise ValueError("Use a valid disposition and a substantive reason")
    if status == "reviewed" and (not topics or not entities):
        raise ValueError("Reviewed files need substantive topics and canonical entities")
    if any(not re.match(r"^(feature|component|code|decision|change|constraint|issue|person|team|agent):\S", e) for e in entities):
        raise ValueError("Entities must use canonical engineering keys")
    evidence, linked = [], set()
    for relative in dict.fromkeys(topics):
        path = topic_path(relative)
        text = path.read_text(encoding="utf-8")
        evidence.append({"path": path.relative_to(bootstrap.PROJECT_ROOT.resolve()).as_posix(),
                         "hash": bootstrap.digest(text)})
        linked.update(linked_sources(path, text))
    selected = {f["path"]: f for f in data["files"]}
    # Validate the whole request before modifying any file disposition.
    for relative in paths:
        if relative not in selected:
            raise ValueError("Path is outside the coverage inventory")
        entry = selected[relative]
        if status == "reviewed":
            delivered = state["delivered"].get(relative, [])
            if any(chunk not in delivered for chunk in range(1, entry["chunks"] + 1)):
                raise ValueError("Deliver all source chunks before recording review")
            if relative not in linked:
                raise ValueError(f"{relative} needs a source link from its review topics")
            if entry["parse_error"]:
                raise ValueError("Resolve Python parse errors before marking reviewed")
    for relative in paths:
        selected[relative].update(status=status, topics=evidence, entities=list(dict.fromkeys(entities)),
                                  reason=reason.strip(), reviewed_at=bootstrap.timestamp())
    write_json(ledger_path(), data)
    return data


def verify(data=None, *, published=False):
    data = data or load_ledger()
    issues = []
    try:
        state = current_bootstrap()
        if state["inventory"]["signature"] != data["inventory_signature"]:
            issues.append("Coverage inventory is stale")
    except (OSError, ValueError) as error:
        issues.append(str(error))
    for file in data["files"]:
        if file["status"] == "unresolved":
            issues.append(file["path"] + ": unresolved")
        if file["parse_error"]:
            issues.append(file["path"] + ": Python parse error")
        for topic in file["topics"]:
            try:
                text = topic_path(topic["path"]).read_text(encoding="utf-8")
                if bootstrap.digest(text) != topic["hash"]:
                    issues.append(file["path"] + ": changed topic " + topic["path"])
            except (OSError, ValueError) as error:
                issues.append(str(error))
    issues.extend(g["path"] + ": " + g["reason"] for g in data["scan_gaps"])
    if published:
        if not bootstrap.DATABASE_PATH.exists():
            issues.append("Knowledge database is missing")
        else:
            with closing(sqlite3.connect(bootstrap.DATABASE_PATH.as_uri() + "?mode=ro", uri=True)) as database:
                for file in data["files"]:
                    if file["status"] != "reviewed":
                        continue
                    for topic in file["topics"]:
                        row = database.execute("SELECT source_hash FROM extraction_results WHERE source_doc=?",
                                               (topic["path"],)).fetchone()
                        if not row or row[0] != topic["hash"]:
                            issues.append(file["path"] + ": unpublished topic " + topic["path"])
                    for entity in file["entities"]:
                        sources = {row[0] for row in database.execute(
                            """SELECT s.source_doc FROM graph_entity_keys k JOIN graph_node_sources s
                               ON s.node_id=k.node_id WHERE k.entity_key=?""", (entity,))}
                        if not sources.intersection(t["path"] for t in file["topics"]):
                            issues.append(file["path"] + ": unmapped entity " + entity)
    return {"status": "incomplete" if issues else "published" if published else "notes_ready",
            "files": len(data["files"]), "reviewed": sum(f["status"] == "reviewed" for f in data["files"]),
            "omitted": sum(f["status"] == "omitted" for f in data["files"]),
            "unresolved": sum(f["status"] == "unresolved" for f in data["files"]),
            "python_files": sum(f["path"].endswith(".py") for f in data["files"]),
            "symbols": sum(len(f["symbols"]) for f in data["files"]),
            "definition_sites": sum(len(s["definitions"]) for f in data["files"] for s in f["symbols"]),
            "imports": sum(len(f["imports"]) for f in data["files"]),
            "excluded": len(data["excluded"]), "issues": issues,
            "notice": "Recorded agent review and published mappings, not proof of exhaustive semantic understanding."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("init", help="Inventory symbols and initialize/resume file dispositions")
    mark = commands.add_parser("record", help="Record current-agent review evidence")
    mark.add_argument("paths", nargs="+")
    mark.add_argument("--status", choices=("reviewed", "omitted", "unresolved"), default="reviewed")
    mark.add_argument("--topic", action="append", default=[])
    mark.add_argument("--entity", action="append", default=[])
    mark.add_argument("--reason", required=True)
    check = commands.add_parser("verify", help="Verify dispositions, hashes and optional graph publication")
    check.add_argument("--published", action="store_true")
    export = commands.add_parser("export", help="Save a project-relative symbol/coverage snapshot")
    export.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.action in ("init", "record"):
            with file_lock(bootstrap.STATE_DIR / "bootstrap" / "coverage.lock") as acquired:
                if not acquired:
                    raise ValueError("Another coverage update is running")
                data = initialize() if args.action == "init" else record(args.paths, args.status, args.topic, args.entity, args.reason)
            output = verify(data)
        elif args.action == "export":
            data = load_ledger()
            # The export is durable project evidence and contains no machine-specific root.
            data = {k: v for k, v in data.items() if k != "project_root"}
            write_json(args.output, data)
            output = {"output": str(args.output), "files": len(data["files"])}
        else:
            output = verify(published=args.published)
        print(json.dumps(output, indent=2, ensure_ascii=False))
        if args.action == "verify" and output["issues"]:
            raise SystemExit(1)
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f"Coverage failed: {error}\n")


if __name__ == "__main__":
    main()
