# mem20api

A stable Python API over the mem20 memory engine.

## Why this exists

The engine (`memory_engine/memory.py`) resolves every store path at import time:

```python
STORE_DIR = os.environ.get("MEM20_STORE_PATH") or os.path.expanduser("~/.mem20/store")
LEDGER = os.path.join(STORE_DIR, "ledger.jsonl")
```

Callers therefore had to reassign a dozen module globals before every operation, and the MCP handlers were running `sys.path.insert(...)` plus a fresh `from memory import ...` inside each query. That is a lot of machinery to answer "what is in my memory".

This package is the supported way in.

## Install

```bash
pip install -e /opt/mem20/mem20api
```

Retrieval extras are optional. Without them `health()` reports that vector and BM25 are unavailable rather than pretending they ran:

```bash
pip install -e '/opt/mem20/mem20api[retrieval]'
```

## Use

```python
from mem20api import open_store

with open_store() as store:                 # $MEM20_STORE_PATH, else ~/.mem20/store
    store.remember("deploys", "Prod runs build 4127", tags=["prod"])

    r = store.semantic("what build is prod on", k=5)
    r["hits"]          # results
    r["healthy"]       # False if the index drifted from the ledger
    r["diagnostic"]    # exactly how many stale pointers exist

    store.graph("prod", hops=2)
    store.health()
```

## What it guarantees

**Reads never write.** `recall`, `semantic`, `hybrid`, `graph`, `health`, `contamination`, `stats`, and `entities` do not touch stored data. `rebuild()` rewrites derived indexes but never the ledger.

**Retrieval reports its own reliability.** Every result carries a diagnostic:

```python
r["diagnostic"]
# {'index': 'vector', 'indexed': 2705, 'resolvable': 379,
#  'missing_from_ledger': 2326, 'healthy': False, ...}
```

That field exists because of a real defect. Semantic retrieval on this
repository's live store returned **zero results and reported success**: the
FAISS index held 2,681 vectors against 371 ledger records, and every stale
entry was found by the search and then silently dropped when its content could
not be resolved. Nothing distinguished "nothing matches" from "your index is
stale".

**Hybrid search says which halves ran:**

```python
store.hybrid("query")["degraded_to"]   # 'both' | 'bm25_only' | 'vector_only' | 'neither'
```

A missing vector index previously degraded hybrid to keyword-only with no
signal at all.

**Graph traversal says when it has nothing.** It returns `found: False` with a
reason, not an empty list.

**Simulated content stays separate.** `remember_simulated` writes to a
different ledger that is never indexed. `promote` requires evidence.

## API

| Method | Kind | Notes |
|---|---|---|
| `health()` | read | Index/ledger agreement. `healthy` is False if anything drifted |
| `contamination()` | read | Grounded/simulated audit. Clean store reports `0.0` |
| `recall(topic, tags, k)` | read | Reverse-chronological |
| `recall_at(as_of)` | read | Point-in-time |
| `semantic(query, k, strict)` | read | Vector. `strict=True` raises `IndexDriftError` |
| `hybrid(query, k, alpha)` | read | RRF fusion + optional rerank |
| `graph(entity, hops)` | read | Multi-hop entity traversal |
| `entities(limit)` | read | Known entities, most connected first |
| `remember(topic, content, tags)` | **write** | Grounded only |
| `remember_simulated(topic, content)` | **write** | Simulated partition |
| `supersede(old_id, new)` | **write** | Marks the old fact superseded |
| `promote(sim_id, confirmation)` | **write** | Refuses without evidence |
| `rebuild(which)` | derived | Reindexes; never touches the ledger |
| `stats()` / `export(dest)` | read | Counts; ledger export |

## CLI

```bash
mem20-api-health health          # exits 1 if drifted
mem20-api-health rebuild         # reindex from the ledger
mem20-api-health contamination   # exits 1 if contamination_rate != 0
mem20-api-health stats
mem20-api-health query "what build is prod on" --mode hybrid
mem20-api-health query unity --mode graph -k 2
```

## A note on module resolution

`/opt/mem20` contains **two** `memory.py`: the repo root one and the engine at
`memory_engine/memory.py`. Under the repo's pytest configuration the root is
removed from `sys.path` while every project directory is added, so a bare
`import memory` can resolve to the wrong file — one that has none of the
retrieval API.

`open_store()` therefore verifies the module it loaded actually has the API it
is about to call, and raises `EngineNotFound` naming the file if not. That turns
a confusing `AttributeError` deep in a traceback into an immediate, accurate
error.

## Tests

```bash
cd /opt/mem20 && pytest tests/test_memory_api.py
```

Covers binding, cross-store isolation, read-only guarantees, drift detection,
simulated/grounded separation, and export.