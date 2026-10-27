"""Version two engineering vocabulary and evidence validation."""
from pathlib import PurePosixPath
import re

SCHEMA_VERSION = 2
ACTORS = {"PERSON", "TEAM", "AGENT"}
SOFTWARE = {"FEATURE", "COMPONENT", "CODE_ELEMENT"}
TYPES = SOFTWARE | ACTORS | {"DECISION", "CHANGE", "CONSTRAINT", "ISSUE"}
RELATIONS = {
    "member_of": (ACTORS, {"TEAM"}),
    "implements": ({"CODE_ELEMENT", "COMPONENT", "CHANGE"}, {"FEATURE", "DECISION", "CONSTRAINT"}),
    "part_of": (TYPES - ACTORS, TYPES - ACTORS),
    "depends_on": (SOFTWARE, SOFTWARE),
    "affects": ({"CHANGE", "DECISION", "ISSUE"}, SOFTWARE),
    "governs": ({"DECISION"}, SOFTWARE),
    "motivates": ({"CONSTRAINT", "ISSUE"}, {"DECISION", "CHANGE"}),
    "constrains": ({"CONSTRAINT"}, SOFTWARE),
    "resolves": ({"CHANGE", "DECISION"}, {"ISSUE"}),
    "supersedes": ({"DECISION", "CHANGE"}, {"DECISION", "CHANGE"}),
    "authored_by": ({"CHANGE", "CODE_ELEMENT"}, ACTORS),
    "committed_by": ({"CHANGE"}, ACTORS),
    "implemented_by": (SOFTWARE | {"CHANGE"}, ACTORS),
    "decided_by": ({"DECISION"}, ACTORS),
    "approved_by": ({"DECISION", "CHANGE"}, ACTORS),
    "requested_by": ({"FEATURE", "CHANGE", "DECISION"}, ACTORS),
    "reviewed_by": (SOFTWARE | {"CHANGE", "DECISION"}, ACTORS),
    "owned_by": (SOFTWARE, ACTORS),
    "maintained_by": (SOFTWARE, ACTORS),
}
KINDS = {"behavior", "rationale", "constraint", "change", "verification",
         "open_question", "decision", "ownership"}
STATES = {"current", "proposed", "historical", "superseded", "disputed"}


def text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def fields(item, required, optional, name):
    if not isinstance(item, dict) or not required <= item.keys() or item.keys() - required - optional:
        raise ValueError(f"{name} requires {sorted(required)}; optional {sorted(optional)}")


def relative_path(value):
    text(value, "path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value or path.as_posix() != value:
        raise ValueError("Path must be normalized and project-relative")


def section_text(source, heading):
    lines = source.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if match and match[2].strip() == heading:
            end = index + 1
            while end < len(lines):
                boundary = re.match(r"^(#{1,6})\s+", lines[end])
                if boundary and len(boundary[1]) <= len(match[1]):
                    break
                end += 1
            return "\n".join(lines[index:end])
    raise ValueError(f"Evidence section not found: {heading!r}")


def validate_engineering(data, expected_source, *, source_text=None):
    fields(data, {"schema_version", "source_doc", "nodes", "facts", "edges", "aliases"}, set(), "extraction")
    if type(data["schema_version"]) is not int or data["schema_version"] != SCHEMA_VERSION:
        raise ValueError("Unsupported extraction schema_version")
    relative_path(data["source_doc"])
    if data["source_doc"] != expected_source:
        raise ValueError("source_doc must match the claimed source")
    for key in ("nodes", "facts", "edges", "aliases"):
        if not isinstance(data[key], list):
            raise ValueError(f"{key} must be an array")
    nodes = {}
    for node in data["nodes"]:
        fields(node, {"key", "name", "type", "description"}, {"code"}, "node")
        for key in ("key", "name", "type", "description"):
            text(node[key], "node." + key)
        if node["type"] not in TYPES:
            raise ValueError("Unsupported engineering entity type")
        prefix = "code" if node["type"] == "CODE_ELEMENT" else node["type"].lower()
        if not node["key"].startswith(prefix + ":") or node["key"] == prefix + ":" or node["key"] in nodes:
            raise ValueError("Entity keys must be unique and use the type prefix")
        if node["type"] == "CODE_ELEMENT":
            code = node.get("code")
            fields(code, {"path", "kind"}, {"symbol"}, "node.code")
            relative_path(code["path"])
            text(code["kind"], "code.kind")
            if "symbol" in code:
                text(code["symbol"], "code.symbol")
            key = "code:" + code["path"] + ("#" + code["symbol"] if code.get("symbol") else "")
            if node["key"] != key:
                raise ValueError("Code identity must equal code:path[#qualified-symbol]")
        elif "code" in node:
            raise ValueError("Only code entities can carry code metadata")
        nodes[node["key"]] = node
    facts = {}
    for fact in data["facts"]:
        fields(fact, {"key", "subject", "kind", "text", "state", "evidence"},
               {"lifecycle", "rationale", "supersedes"}, "fact")
        for key in ("key", "subject", "kind", "text", "state"):
            text(fact[key], "fact." + key)
        if not fact["key"].startswith("fact:") or fact["key"] in facts:
            raise ValueError("Facts require unique fact: keys")
        if fact["subject"] not in nodes or fact["kind"] not in KINDS or fact["state"] not in STATES:
            raise ValueError("Unsupported fact kind/state or missing subject")
        for key in ("lifecycle", "rationale"):
            if key in fact:
                text(fact[key], "fact." + key)
        replaced = fact.get("supersedes", [])
        if not isinstance(replaced, list) or any(
            not isinstance(key, str) or not key.startswith("fact:") or key == fact["key"]
            for key in replaced
        ):
            raise ValueError("Invalid supersession keys")
        if not isinstance(fact["evidence"], list) or not fact["evidence"]:
            raise ValueError("Every fact needs evidence")
        for evidence in fact["evidence"]:
            fields(evidence, {"section", "excerpt"},
                   {"code_path", "symbol", "git_ref", "attribution_basis"}, "evidence")
            for key, value in evidence.items():
                text(value, "evidence." + key)
            if "code_path" in evidence:
                relative_path(evidence["code_path"])
            if evidence.get("attribution_basis") not in (None, "explicit_statement", "git_author", "git_committer"):
                raise ValueError("Unsupported attribution basis")
            if source_text is not None:
                section = section_text(source_text, evidence["section"])
                if " ".join(evidence["excerpt"].split()) not in " ".join(section.split()):
                    raise ValueError("Evidence excerpt is not present in its source section")
        facts[fact["key"]] = fact
    for edge in data["edges"]:
        fields(edge, {"source", "predicate", "target", "facts"}, set(), "edge")
        for key in ("source", "predicate", "target"):
            text(edge[key], "edge." + key)
        if edge["source"] not in nodes or edge["target"] not in nodes or edge["predicate"] not in RELATIONS:
            raise ValueError("Unknown relationship or canonical endpoint")
        left, right = RELATIONS[edge["predicate"]]
        if nodes[edge["source"]]["type"] not in left or nodes[edge["target"]]["type"] not in right:
            raise ValueError("Relationship endpoint types violate its contract")
        if not isinstance(edge["facts"], list) or not edge["facts"] or any(
            not isinstance(key,str) or key not in facts for key in edge["facts"]
        ):
            raise ValueError("Relationships require existing supporting facts")
        if any(facts[key]["subject"] not in (edge["source"], edge["target"]) for key in edge["facts"]):
            raise ValueError("Supporting facts must concern a relationship endpoint")
        if edge["predicate"].endswith("_by"):
            allowed = {"explicit_statement"}
            if edge["predicate"] == "authored_by":
                allowed.add("git_author")
            if edge["predicate"] == "committed_by":
                allowed.add("git_committer")
            actor = nodes[edge["target"]]["name"].casefold()
            if not any(e.get("attribution_basis") in allowed and actor in e["excerpt"].casefold()
                       for key in edge["facts"] for e in facts[key]["evidence"]):
                raise ValueError("Named, role-specific attribution evidence is required; authorship is not ownership")
    for alias in data["aliases"]:
        fields(alias, {"entity", "alias"}, set(), "alias")
        text(alias["alias"], "alias.alias")
        if not isinstance(alias["entity"], str) or alias["entity"] not in nodes:
            raise ValueError("Alias must reference a canonical node key")
    supported = {f["subject"] for f in facts.values()} | {
        e[key] for e in data["edges"] for key in ("source", "target")
    }
    if set(nodes) - supported:
        raise ValueError("Entities need facts or supported relationships")
    return data
