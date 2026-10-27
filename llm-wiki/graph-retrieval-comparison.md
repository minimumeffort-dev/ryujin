# Graph retrieval comparison

Reviewed on 2026-10-27 against graph-memory-starter commit
`496a6e9d9b9578943ec5ed34c2780de5a0fa5510`:
[recall.py](https://github.com/Glitch-Cat-Club/graph-memory-starter/blob/496a6e9d9b9578943ec5ed34c2780de5a0fa5510/src/recall.py)
and [its prompt hook](https://github.com/Glitch-Cat-Club/graph-memory-starter/blob/496a6e9d9b9578943ec5ed34c2780de5a0fa5510/src/recall_hook.py).

## Verified differences

Both implementations match entity names and aliases without a model call.
Graph-memory-starter walks a configurable neighborhood using recursive SQL,
defaulting to three hops, then returns up to eight relationships ordered by proximity.
Ryujin's [retriever](../tools/recall_graph.py) now supports configurable hops
using breadth-first traversal, defaulting to one hop. It ranks relationships
by distance and then word overlap with the question. Ryujin limits seed matches
to five, returns up to eight relationships and reports truncation.

Ryujin also limits traversal to 100 examined relationship rows by default,
including repeated rows. It prevents repeated node expansion and reports
budget consumption. This bounds rows fetched during traversal, not SQLite
execution time or seed matching. See [retrieval options](session-capture.md#graph-retrieval).

Their seed matching fetches every name and alias into Python. Ryujin filters
substring candidates in SQLite, although the database still scans labels.
Ryujin preserves Unicode case folding and punctuation-aware boundaries.

Ryujin returns JSON with node IDs and source-specific descriptions. Their compact
text formatter includes descriptions selected by name, which can mix unrelated
same-named entities. Ryujin's CLI uses a read-only snapshot; their separate Claude
hook emits recalled text as prompt context. Ryujin's recall hook remains
unimplemented.

At the initial comparison, Ryujin followed only one hop. In-memory checks
confirmed that difference on a policy-to-role-to-person chain, their same-name
description ambiguity, and a punctuation-boundary mismatch. Subsequent Ryujin
tests cover configurable hops, cycles and traversal limits. These checks are
not performance benchmarks.

## Proposed next steps

Configurable, bounded multi-hop retrieval with source tracking and distance
ranking was implemented on 2026-10-27. Compact text output for prompt injection
and connecting the shared retriever to client hooks remain proposals.
