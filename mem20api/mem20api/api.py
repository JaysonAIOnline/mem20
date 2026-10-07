"""A stable Python API over the mem20 memory engine.

The engine (`memory_engine/memory.py`) is a 3,600-line module that reads
`MEM20_STORE_PATH` at import time and resolves its own paths as module globals.
Callers therefore have to mutate `M.LEDGER`, `M.STORE_DIR` and eight other
globals before every operation, and the MCP handlers were doing
`sys.path.insert(...)` plus `from memory import ...` inside each call. This
module is the supported entry point: one `open_store()` that binds a store, and
methods that return plain dicts.

Design rules:

- **Read-only by default.** Nothing here mutates stored data unless you call a
  method whose name says so (`remember`, `promote`, `rebuild_*`, `supersede`).
- **Trustworthy reporting.** `health()` exposes index/ledger drift. Retrieval
  results carry diagnostics rather than silently shrinking.
- **Honest errors.** A method that cannot do its job raises or returns an
  explicit error field; it never returns an empty list to mean "broken".

Example:

    from mem20api import open_store

    store = open_store("~/.mem20/store")
    store.remember("deploys", "Prod is on build 4127", tags=["prod"])

    hits = store.semantic("what build is prod on", k=5)
    if not hits["healthy"]:
        print("index drifted:", hits["diagnostic"])

    for e in store.graph("prod", hops=2)["entities"]:
        print(e["entity"], e["hop"])
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable

__all__ = ["open_store", "health", "MemoryStore", "EngineNotFound", "StoreError"]

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_ENGINE = _REPO_ROOT / "memory_engine"
_ENGINE_FILE = _ENGINE / "memory.py"


class EngineNotFound(RuntimeError):
    """The memory engine module could not be located."""


class StoreError(RuntimeError):
    """The store could not be opened or is unusable."""


def _load_engine():
    """Import the engine module, verifying it is the real one.

    The engine is not an installed package. It lives at
    `memory_engine/memory.py` in the repo, and deployments that copy it into the
    store dir expect it to be importable from `MEM20_STORE_PATH`.

    The verification is not paranoia. `/opt/mem20` also contains a top-level
    `memory.py`, and under the repo's pytest configuration the repo root is
    removed from `sys.path` while every project directory is added, so a bare
    `import memory` can resolve to `/opt/mem20/memory.py` instead of
    `memory_engine/memory.py`. That module has none of the retrieval API, so the
    store bound cleanly and then every call failed with AttributeError while
    pointing at a file that looks correct in a traceback.

    So: put the engine directory at the front of `sys.path`, import by file
    location, and assert the module has the API we are about to call.
    """
    if str(_ENGINE) not in sys.path:
        sys.path.insert(0, str(_ENGINE))
    else:
        sys.path.remove(str(_ENGINE))
        sys.path.insert(0, str(_ENGINE))

    existing = sys.modules.get("memory")
    if existing is not None:
        got = getattr(existing, "__file__", None) or ""
        if Path(got).resolve() == _ENGINE_FILE.resolve():
            _verify_engine_api(existing)
            return existing
        # A different `memory` module is already loaded. Do not disturb the
        # caller's binding; load ours under a private name instead.
        return _load_engine_by_path()

    try:
        import memory as m  # noqa: PLC0415
    except ImportError:
        return _load_engine_by_path()
    _verify_engine_api(m)
    return m


def _load_engine_by_path():
    """Load the engine straight from its file, bypassing sys.path entirely."""
    import importlib.util  # noqa: PLC0415

    engine_file = _ENGINE_FILE
    if not engine_file.is_file():
        store_dir = os.environ.get("MEM20_STORE_PATH")
        alt = Path(store_dir) / "memory.py" if store_dir else None
        if alt and alt.is_file():
            engine_file = alt
        else:
            raise EngineNotFound(
                f"memory engine not found at {_ENGINE_FILE}"
                + (f" or {alt}" if alt else " or $MEM20_STORE_PATH/memory.py"))

    spec = importlib.util.spec_from_file_location("mem20_engine_memory",
                                                  engine_file)
    if spec is None or spec.loader is None:
        raise EngineNotFound(f"could not load a module spec from {engine_file}")
    m = importlib.util.module_from_spec(spec)
    sys.modules["mem20_engine_memory"] = m
    spec.loader.exec_module(m)
    _verify_engine_api(m)
    return m


#: Names this API depends on. If a module resolves to something else, say so
#: plainly instead of failing later with a confusing AttributeError.
_REQUIRED_ENGINE_API = (
    "remember", "recall", "recall_semantic", "recall_hybrid", "recall_graph",
    "index_health", "audit_contamination", "rebuild_vectors", "rebuild_bm25",
    "rebuild_graph", "STORE_DIR", "LEDGER",
)


def _verify_engine_api(m) -> None:
    missing = [n for n in _REQUIRED_ENGINE_API if not hasattr(m, n)]
    if missing:
        got = getattr(m, "__file__", "<unknown>")
        raise EngineNotFound(
            f"module {got!r} is not the mem20 memory engine; it is missing "
            f"{', '.join(missing)}. Expected {_ENGINE_FILE}.")


class MemoryStore:
    """A bound view of one mem20 store."""

    def __init__(self, store_path: str | os.PathLike[str]):
        self._path = str(Path(store_path).expanduser())
        self._engine = _load_engine()
        self._previous_env = os.environ.get("MEM20_STORE_PATH")
        os.environ["MEM20_STORE_PATH"] = self._path
        try:
            self._rebind()
        except Exception as e:
            raise StoreError(f"could not bind store {self._path}: {e}") from e

    def _rebind(self) -> None:
        """Point the engine's path globals at this store.

        The engine resolves every path at import time, so binding a different
        store means reassigning them. Doing it here, once, is why callers no
        longer have to.
        """
        m = self._engine
        d = self._path
        m.STORE_DIR = d
        m.MEM_DIR = str(Path(d).parent)
        m.ENTRIES = os.path.join(d, "entries")
        m.BACKUP_DIR = os.path.join(d, "backups")

        # Every path the engine derives from STORE_DIR. These are module
        # globals computed once at import, so binding a different store has to
        # reassign all of them. Missing one means a write lands in the previous
        # store, which is silent and is exactly the bug this module exists to
        # prevent.
        for attr, name in (
            ("LEDGER", "ledger.jsonl"),
            ("INDEX", "INDEX.md"),
            ("VECTOR_INDEX", "vector_index.faiss"),
            ("VECTOR_META", "vector_meta.jsonl"),
            ("BM25_INDEX", "bm25_index.pkl"),
            ("BM25_CORPUS", "bm25_corpus.jsonl"),
            ("GRAPH_INDEX", "memory_graph.json"),
            ("SIMULATED_LEDGER", "simulated_ledger.jsonl"),
            ("PREDICTIONS_LEDGER", "predictions_ledger.jsonl"),
            ("PINNED_FILE", "pinned_blocks.json"),
            ("AFFECTIVE_FILE", "affective_state.json"),
            ("PROCEDURAL_FILE", "procedural_memory.json"),
            ("WORLD_MODEL_FILE", "world_model.json"),
        ):
            setattr(m, attr, os.path.join(d, name))

    def __enter__(self) -> "MemoryStore":
        return self

    def __exit__(self, *exc) -> None:
        if self._previous_env is None:
            os.environ.pop("MEM20_STORE_PATH", None)
        else:
            os.environ["MEM20_STORE_PATH"] = self._previous_env

    # -- trust -----------------------------------------------------------

    def health(self) -> dict:
        """Index/ledger agreement. `healthy` is False if any index drifted."""
        return self._engine.index_health()

    def contamination(self) -> dict:
        """Grounded/simulated separation audit. A clean store reports 0.0."""
        return self._engine.audit_contamination()

    # -- writes (explicit) ----------------------------------------------

    def remember(self, topic: str, content: str, tags: Iterable[str] | None = None,
                 priority: str = "normal", **kw) -> dict:
        return self._engine.remember(topic, content, tags=list(tags or []),
                                     priority=priority, **kw)

    def remember_simulated(self, topic: str, content: str, **kw) -> dict:
        """Write to the SIMULATED partition. Never indexed, never retrievable
        by default. Use for counterfactuals and hypotheses."""
        return self._engine.remember_simulated(topic, content, **kw)

    def supersede(self, old_id: str, new_content: str, **kw) -> dict:
        return self._engine.supersede(old_id, new_content, **kw)

    def promote(self, sim_id: str, confirmation: str = "", **kw) -> dict:
        """Promote a simulated fact to grounded. Requires evidence: an explicit
        confirmation string or a resolved prediction error. Refused otherwise."""
        return self._engine.promote_simulated_to_grounded(
            sim_id, confirmation=confirmation, **kw)

    def rebuild(self, which: str = "all") -> dict:
        """Rebuild derived indexes from the ledger.

        `which` is any of 'vector', 'bm25', 'graph', or 'all'. The ledger is the
        source of truth and is never touched here.
        """
        wanted = ("vector", "bm25", "graph") if which == "all" else (which,)
        out = {}
        if "vector" in wanted:
            out["vector"] = self._engine.rebuild_vectors()
        if "bm25" in wanted:
            out["bm25"] = self._engine.rebuild_bm25()
        if "graph" in wanted:
            out["graph"] = self._engine.rebuild_graph()
        return out

    # -- reads -----------------------------------------------------------

    def recall(self, topic: str | None = None, tags: Iterable[str] | None = None,
               k: int = 5, include_simulated: bool = False) -> list[dict]:
        return self._engine.recall(topic=topic, tags=list(tags or []), k=k,
                                   include_simulated=include_simulated)

    def recall_at(self, as_of: str, **kw) -> list[dict]:
        """Point-in-time recall: what was true at `as_of`."""
        return self._engine.recall_at(as_of=as_of, **kw)

    def semantic(self, query: str, k: int = 5, topic: str | None = None,
                 tags: Iterable[str] | None = None,
                 strict: bool = False) -> dict:
        """Vector retrieval.

        Returns `{"hits": [...], "diagnostic": {...}, "healthy": bool}`. The
        diagnostic reports how many index entries point at records that no
        longer exist, because a silently shortened result list is
        indistinguishable from a store with no matches.
        """
        hits = self._engine.recall_semantic(query, k=k, topic=topic,
                                            tags=list(tags or []), strict=strict)
        diag: dict[str, Any] = {}
        if hits and "_index_drift" in hits[0]:
            diag = hits[0]["_index_drift"]
        return {
            "hits": hits,
            "diagnostic": diag,
            "healthy": bool(diag.get("healthy", True)) if diag else True,
        }

    def hybrid(self, query: str, k: int = 5, topic: str | None = None,
               tags: Iterable[str] | None = None,
               alpha: float = 0.5) -> dict:
        """RRF fusion of vector + BM25, with optional cross-encoder rerank.

        `diagnostic.degraded_to` says which halves actually contributed. It was
        previously impossible to tell a working hybrid search from one that had
        silently fallen back to keywords only.
        """
        hits = self._engine.recall_hybrid(query, k=k, topic=topic,
                                          tags=list(tags or []), alpha=alpha)
        diag: dict[str, Any] = {}
        if hits and "_retrieval" in hits[0]:
            diag = hits[0]["_retrieval"]
        return {"hits": hits, "diagnostic": diag,
                "degraded_to": diag.get("degraded_to", "unknown")}

    def graph(self, entity: str, hops: int = 2, max_results: int = 20,
              min_facts: int = 1, topic: str | None = None) -> dict:
        """Multi-hop entity traversal over the persisted graph index."""
        return self._engine.recall_graph(entity, hops=hops,
                                         max_results=max_results,
                                         min_facts=min_facts, topic=topic)

    def entities(self, limit: int = 50) -> list[dict]:
        """Entity names known to the graph index, most connected first."""
        g = self._engine._load_graph()
        deg = {k: sum(1 for e in g["edges"].values() if e["a"] == k)
               for k in g["nodes"]}
        out = []
        for k in sorted(deg, key=lambda x: (-deg[x], x))[:limit]:
            n = g["nodes"][k]
            out.append({"entity": n["name"], "degree": deg[k],
                        "facts": len(n["facts"]), "topics": sorted(n["topics"])})
        return out

    def ledger(self, k: int = 20) -> list[dict]:
        return self._engine._load_ledger()[-k:]

    # -- introspection ---------------------------------------------------

    @property
    def path(self) -> str:
        return self._path

    def stats(self) -> dict:
        recs = self._engine._load_ledger()
        remembered = [r for r in recs if r.get("action") == "remember"]
        topics: dict[str, int] = {}
        for r in remembered:
            topics[r.get("topic", "unknown")] = topics.get(
                r.get("topic", "unknown"), 0) + 1
        return {
            "path": self._path,
            "ledger_events": len(recs),
            "grounded_facts": len(remembered),
            "topics": len(topics),
            "vector_available": self._engine.VECTOR_AVAILABLE,
            "bm25_available": self._engine.BM25_AVAILABLE,
            "health": self.health(),
        }

    def export(self, dest: str | os.PathLike[str], fmt: str = "json") -> str:
        """Export the ledger. Read-only with respect to the store."""
        dest = str(Path(dest))
        recs = self._engine._load_ledger()
        if fmt == "json":
            with open(dest, "w", encoding="utf-8") as f:
                json.dump(recs, f, ensure_ascii=False, indent=2)
        elif fmt == "jsonl":
            with open(dest, "w", encoding="utf-8") as f:
                for r in recs:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
        else:
            raise ValueError(f"unsupported format: {fmt}")
        return dest


def open_store(path: str | os.PathLike[str] | None = None) -> MemoryStore:
    """Open a mem20 store.

    Defaults to `$MEM20_STORE_PATH`, then `~/.mem20/store`.
    """
    if path is None:
        path = os.environ.get("MEM20_STORE_PATH") or "~/.mem20/store"
    return MemoryStore(path)


def health(path: str | os.PathLike[str] | None = None) -> dict:
    """One-shot health check, for callers that only need the verdict."""
    return open_store(path).health()