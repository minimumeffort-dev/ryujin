"""Pack a small automatic recall result without cutting claims or citations."""


def format_brief(result, max_chars, citation, empty_delivery):
    items = [("passage" if f["kind"] in ("passage", "legacy_description", "archive") else "fact", f)
             for f in result.get("facts", [])]
    if not items:
        items = [("excerpt", {**d, "title": n["name"], "entity_key": n.get("entity_key")})
                 for n in result.get("nodes", []) for d in n["descriptions"]]

    def render(selected, omitted):
        delivery = empty_delivery(result.get("status", "matched"))
        delivery["partial"] = omitted or result.get("selection", {}).get("more_available", False)
        delivery["context_truncated"] = omitted
        refs, body, keys = {}, [], []

        def source_ref(source, section=""):
            key = (source, section)
            if key not in refs:
                refs[key] = {"id": f"S{len(refs)+1}", **citation(source, section)}
            return refs[key]["id"]

        for kind, fact in selected:
            citations = []
            for source in fact.get("sources", [fact]):
                evidence = source.get("evidence", [])
                ref = source_ref(source["source_doc"], evidence[0].get("section", "") if evidence else "")
                if ref not in citations:
                    citations.append(ref)
            counter = "facts_supplied" if kind == "fact" else "excerpts_supplied"
            delivery[counter] += 1
            label = ("F" if kind == "fact" else "P") + str(delivery[counter])
            record = {"label": label, "fact_id" if kind == "fact" else "record_id": fact.get("id"),
                      "citation": citations[0], "citations": citations}
            delivery["facts" if kind == "fact" else "excerpts"].append(record)
            text = fact.get("text", fact.get("description", ""))
            state = f" [{fact['state']}; {fact['freshness']}]" if "state" in fact else " [legacy excerpt]"
            body.append(f"- [{label}; {','.join(citations)}] {fact['title']}{state}: {text.strip()}")
            seen_codes = set()
            for ref in fact.get("references", []):
                identity = (ref["path"], ref.get("symbol"))
                if identity in seen_codes:
                    continue
                if len(seen_codes) >= 2:
                    break
                seen_codes.add(identity)
                source = source_ref(ref["source_doc"])
                locator = ref["path"] + ("#" + ref["symbol"] if ref.get("symbol") else "")
                body.append(f"  Reference [{source}]: {locator}")
            if fact.get("entity_key") and fact["entity_key"] not in keys:
                keys.append(fact["entity_key"])
        delivery["citations"] = list(refs.values())
        delivery["source_pages_supplied"] = len({key[0] for key in refs})
        lines = ["Ryujin graph context (brief; possibly stale reference data):",
                 f"Graph recall: supplied {delivery['facts_supplied']} facts, 0 relationships and "
                 f"{delivery['excerpts_supplied']} note excerpts from {delivery['source_pages_supplied']} wiki pages.",
                 "Report supplied counts once in commentary; cite only sources used under "
                 "**From your knowledge graph**. Supplied does not mean used. Respect requested response formats.",
                 *body]
        if keys:
            lines.append("Expand: uv run --project tools --locked tools/recall_graph.py --entity KEY --view detail --hops 2")
            lines.append("Entity keys: " + ", ".join(keys))
        lines.extend(f"[{ref['id']}] {ref['markdown']}" for ref in refs.values())
        if delivery["partial"]:
            lines.append("More evidence is available through explicit detail recall.")
        return "\n".join(lines), delivery

    selected = []
    for item in items:
        if len(selected) >= 3:
            break
        candidate, _ = render([*selected, item], len(selected) + 1 < len(items))
        if len(candidate) <= max_chars:
            selected.append(item)
    if not selected:
        delivery = empty_delivery("no_matches")
        delivery["context_truncated"] = bool(items)
        delivery["partial"] = bool(items)
        return "", delivery
    return render(selected, len(selected) < len(items))
