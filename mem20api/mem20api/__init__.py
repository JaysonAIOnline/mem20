"""mem20api — a stable, trustworthy Python API over the mem20 memory engine.

The engine is a large module that resolves its store paths at import time.
Calling it directly means mutating module globals, and the MCP handlers were
doing `sys.path.insert` plus a fresh import on every single query. This package
is the supported way in:

    from mem20api import open_store

    with open_store() as store:
        store.remember("deploys", "Prod runs build 4127", tags=["prod"])
        hits = store.semantic("what build does prod run")
        hits["healthy"]   # False if the vector index has drifted from the ledger

## What it guarantees

- **Reads never write.** `recall`, `semantic`, `hybrid`, `graph`, `health`,
  `contamination` and `stats` are read-only. `rebuild` rewrites derived
  indexes but never the ledger.
- **Retrieval reports its own reliability.** Every result carries a diagnostic
  saying how many index entries point at records that no longer exist and which
  halves of a hybrid search actually ran. A short result list is never the only
  signal you get.
- **The simulated partition stays separate.** `remember_simulated` writes to a
  different ledger that is never indexed, and promotion to grounded requires
  evidence.
"""
from .api import (  # noqa: F401
    EngineNotFound,
    MemoryStore,
    StoreError,
    health,
    open_store,
)

__all__ = [
    "open_store",
    "health",
    "MemoryStore",
    "EngineNotFound",
    "StoreError",
]
__version__ = "0.1.0"