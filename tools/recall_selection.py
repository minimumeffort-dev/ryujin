"""Conservative, deterministic selection for brief automatic graph recall."""
import re

from search_knowledge import query_terms

GENERIC = set("""okay ok yes solid plan ahead go continue proceed next step steps
improve improvement revision implement implemented implementation change changes
add update work working process processes currently entire successful following
really actually right now would could should need want thanks thank please""".split())
COMMON = set("""graph wiki knowledge project code codebase feature features file files
function functions context agent agents system implementation""".split())
COMMON.update(("existing", "extraction", "claim", "capture"))


def normalized_word(word):
    # Only inflection agreement, not semantic synonym matching.
    if len(word) > 5 and word.endswith("ies"):
        return word[:-3] + "y"
    for ending in ("ing", "ed", "s"):
        if len(word) > len(ending) + 3 and word.endswith(ending):
            return word[:-len(ending)]
    return word


def words(text):
    return {normalized_word(w.casefold()) for w in re.findall(r"[^\W_]+", text)}


def analyze_query(question):
    terms = [w for w in query_terms(question) if w not in GENERIC]
    locators = re.findall(r"(?<!\w)(?:[\w.-]+/)+[\w./()@-]+(?:#[\w.:]+)?", question)
    symbols = re.findall(r"\b\w+(?:[.#:]\w+)+\b", question)
    return {"terms": terms, "locators": list(dict.fromkeys(locators + symbols))[:8]}


def deduplicate(facts):
    """Group only identical assertions with compatible identity and source state."""
    groups = {}
    for fact in facts:
        # Preserve case in identifiers, numbers, punctuation and negation. Paraphrases
        # deliberately stay separate: similarity alone cannot establish equivalence.
        identity = fact.get("entity_key") or fact.get("node_id") or fact["source_doc"]
        locators = tuple(sorted((e.get("code_path") or "", e.get("symbol") or "",
                                 e.get("attribution_basis") or "") for e in fact["evidence"]))
        key = (identity, fact["kind"], fact["state"], fact["lifecycle"],
               " ".join(fact["text"].split()), fact.get("rationale", ""),
               repr(fact.get("code")), locators)
        source = {k: fact.get(k) for k in ("id", "source_doc", "source_hash", "extraction_id",
                                          "freshness", "evidence")}
        if key not in groups:
            groups[key] = {**fact, "sources": [source]}
        else:
            groups[key]["sources"].append(source)
    return list(groups.values())


def select_facts(facts, question, anchors, *, automatic=False, limit=10):
    analysis = analyze_query(question)
    terms = {normalized_word(t) for t in analysis["terms"]}
    anchor_ids = {node["id"] for node in anchors}
    anchor_lengths = {node["id"]: len(node["matched_as"]) for node in anchors}
    ownership = bool(re.search(r"\b(who|owner|ownership|maintain\w*|author|implemented|decided)\b", question, re.I))
    diagnostics = {"policy": "auto" if automatic else "detail", **analysis,
                   "candidate_count": len(facts), "rejected": [], "deduplicated": 0}
    ranked = []
    seen = set()
    for fact in facts:
        key = (fact["id"], fact["source_doc"])
        if key in seen:
            continue
        seen.add(key)
        matched = terms & words(fact["text"])
        specific = matched - COMMON
        anchor_node = fact.get("anchor_node_id", fact.get("node_id"))
        anchored = anchor_node in anchor_ids
        agreement = len(matched) / max(1, len(terms))
        reason = None
        if automatic and fact["freshness"] == "stale":
            reason = "stale_source"
        elif automatic and fact["kind"] == "passage" and len(words(fact["text"])) < 6:
            reason = "navigation_only_passage"
        elif automatic and not (anchored or (len(matched) >= 2 and specific and agreement >= 0.45)):
            reason = "insufficient_relevance"
        if reason:
            diagnostics["rejected"].append({"id": fact["id"], "reason": reason})
            continue
        signals = {"anchored": anchored, "matched_terms": sorted(matched),
                   "term_agreement": round(agreement, 3)}
        # Explicit locators and informative agreement precede lexical score. BM25
        # remains a rank signal, never a universal probability of relevance.
        rank = (-int(anchored), -anchor_lengths.get(anchor_node, 0),
                (fact["kind"] != "ownership") if ownership else (fact["kind"] == "ownership"),
                fact["kind"] in ("passage", "legacy_description", "archive"),
                -len(specific), -len(matched),
                fact["state"] != "current",
                fact["score"], fact["id"])
        ranked.append((rank, {**fact, "selection_signals": signals}))
    ranked.sort(key=lambda item: item[0])
    selected = deduplicate([f for _, f in ranked])
    diagnostics["deduplicated"] = len(ranked) - len(selected)
    diagnostics["duplicate_groups"] = [
        {"primary": f["id"], "sources": [s["id"] for s in f["sources"]],
         "reason": "identical_compatible_assertion"}
        for f in selected if len(f["sources"]) > 1]
    diagnostics.update(selected_count=min(limit, len(selected)),
                       more_available=len(selected) > limit,
                       reason="selected" if selected else "insufficient_relevance" if facts else "no_candidates")
    return selected[:limit], diagnostics
