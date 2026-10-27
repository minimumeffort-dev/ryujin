import argparse
import json

from pathlib import Path

ENTITY_TYPES = {"PERSON", "ROLE", "POLICY", "PROCESS", "DOCUMENT"}

RELATIONSHIPS = {"approved_by", "held_by", "delegates_to", "part_of", "references"}

FIELDS = {
    "nodes": {"name", "type", "description"},
    "edges": {"source", "predicate", "target"},
    "aliases": {"entity", "alias"},
}


def validate_extraction(data, expected_source):
    required = {"source_doc", "nodes", "edges", "aliases"}

    if not isinstance(data, dict) or set(data) != required:
        raise ValueError(f"Expected exactly these top-level fields: {sorted(required)}")

    source = data["source_doc"]

    if not isinstance(source, str) or not source.strip():
        raise ValueError("source_doc must be a non-empty string")

    if source != expected_source:
        raise ValueError(f"source_doc must equal {expected_source!r}")

    # Check each collection and its object fields.
    for section, fields in FIELDS.items():
        if not isinstance(data[section], list):
            raise ValueError(f"{section} must be an array")

        for index, item in enumerate(data[section]):
            location = f"{section}[{index}]"

            if not isinstance(item, dict) or set(item) != fields:
                raise ValueError(f"{location} must have exactly {sorted(fields)}")

            for field in fields:
                value = item[field]

                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{location}.{field} must be a non-empty string")

    # Check node types and build a lookup of unique names.
    names = set()

    for index, node in enumerate(data["nodes"]):
        if node["type"] not in ENTITY_TYPES:
            raise ValueError(f"nodes[{index}].type is unsupported: {node['type']!r}")

        if node["name"] in names:
            raise ValueError(f"Duplicate node name: {node['name']!r}")

        names.add(node["name"])

    # Check predicates and ensure both endpoints exist.
    for index, edge in enumerate(data["edges"]):
        if edge["predicate"] not in RELATIONSHIPS:
            raise ValueError(f"edges[{index}].predicate is unsupported")

        for endpoint in ("source", "target"):
            if edge[endpoint] not in names:
                raise ValueError(
                    f"edges[{index}].{endpoint} has no node: " f"{edge[endpoint]!r}"
                )

    # Check that aliases point to existing nodes.
    for index, alias in enumerate(data["aliases"]):
        if alias["entity"] not in names:
            raise ValueError(
                f"aliases[{index}].entity has no node: " f"{alias['entity']!r}"
            )

    return data


def load_extraction(path, expected_source):
    text = Path(path).read_text(encoding="utf-8")
    data = json.loads(text)
    return validate_extraction(data, expected_source)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--source-doc", required=True)
    args = parser.parse_args()

    try:
        load_extraction(args.path, args.source_doc)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    print("Extraction JSON is valid")


if __name__ == "__main__":
    main()
