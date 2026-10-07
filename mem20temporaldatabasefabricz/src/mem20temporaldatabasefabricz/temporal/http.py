"""HTTP surface for the bi-temporal store.

Adds temporal questions to mem20. It does not take over recall: the `/recall/*`
routes are read-only proxies onto the retrieval functions that are already
live (ledger recall, hybrid search, as-of recall), so nothing is displaced.

Writes go through the same engine the CLI uses, so the invariants hold
regardless of entry point.
"""

from __future__ import annotations

import os
import sys
from typing import Any

from fastapi import FastAPI, HTTPException, Query

from .engine import BiTemporalEngine, InvariantError, event_time_coverage
from .ledger_adapter import TEMPORAL_DIAGNOSTICS, build_engine
from .store import ChainError, TemporalStore

DB_PATH = os.environ.get(
    "MEM20_TEMPORAL_DB", os.path.expanduser("~/.mem20/temporal/temporal.db"))
MEM20_ROOT = os.environ.get("MEM20_ROOT", "/opt/mem20")


def _memory():
    """Import memory_engine lazily.

    The temporal service must start even if the memory engine's optional
    vector dependencies are unavailable; failing at import would take the
    temporal endpoints down with them.
    """
    path = os.path.join(MEM20_ROOT, "memory_engine")
    if path not in sys.path:
        sys.path.insert(0, path)
    import memory  # noqa: PLC0415
    return memory


def create_app(db_path: str | None = None) -> FastAPI:
    app = FastAPI(
        title="mem20 bi-temporal memory",
        version="1.1.0",
        description=("Separates when a claim was true (valid) from when the "
                     "system knew it (known). Read and query over mem20's "
                     "existing ledger; nothing existing is replaced."))

    ledger_path = os.environ.get(
        "MEM20_LEDGER_PATH", os.path.expanduser("~/.mem20/store/ledger.jsonl"))
    sync_state: dict[str, Any] = {"stamp": None}

    def ledger_stamp() -> tuple:
        try:
            st = os.stat(ledger_path)
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return (0, 0)

    def engine_for(memory=None) -> BiTemporalEngine:
        """Open the engine, re-syncing the ledger only when it has changed.

        Deriving intervals is O(ledger). Doing that on every request would make
        each call cost more as the store grows, for no change in the answer -
        the intervals are already durable. The mtime+size stamp means the sync
        runs when the ledger actually moves, and never otherwise.
        """
        store = TemporalStore(db_path or DB_PATH)
        stamp = ledger_stamp()
        rows = memory._load_ledger() if memory else []
        if stamp == sync_state["stamp"] and rows:
            return BiTemporalEngine(store)
        engine = build_engine(store, rows)
        sync_state["stamp"] = stamp
        return engine

    @app.exception_handler(InvariantError)
    def _invariant(_request, exc: InvariantError):
        raise HTTPException(status_code=409, detail=str(exc))

    @app.exception_handler(ChainError)
    def _chain(_request, exc: ChainError):
        raise HTTPException(status_code=500, detail=str(exc))

    @app.get("/healthz")
    def healthz() -> dict:
        store = TemporalStore(db_path or DB_PATH)
        try:
            return {"ok": True, "db": db_path or DB_PATH,
                    "versions": store.count(), "events": store.count_events()}
        finally:
            store.close()

    # -- temporal reads ------------------------------------------------

    @app.get("/temporal/query/{subject}")
    def temporal_query(subject: str, valid_at: str | None = Query(None),
                       known_at: str | None = Query(None),
                       attribute: str | None = Query(None)) -> dict:
        """One bi-temporal slice. Omit an axis to mean 'now'."""
        return engine_for().query(subject, valid_at=valid_at, known_at=known_at,
                                  attribute=attribute).to_dict()

    @app.get("/temporal/slices/{subject}")
    def temporal_slices(subject: str, instant: str = Query(...),
                        attribute: str | None = Query(None)) -> dict:
        """All four slices at one instant - the diagnostic view."""
        return engine_for().four_slices(subject, instant, attribute)

    @app.get("/temporal/history/{subject}")
    def temporal_history(subject: str,
                         attribute: str | None = Query(None)) -> dict:
        """Every version, oldest first, including superseded ones."""
        chain = engine_for().history(subject, attribute)
        return {"subject": subject, "count": len(chain),
                "versions": [v.to_dict() for v in chain]}

    @app.get("/temporal/explain/{subject}")
    def temporal_explain(subject: str, valid_at: str | None = Query(None),
                         known_at: str | None = Query(None),
                         attribute: str | None = Query(None)) -> dict:
        """Why the engine answers what it answers."""
        return engine_for().explain(subject, valid_at=valid_at,
                                    known_at=known_at, attribute=attribute)

    @app.get("/temporal/subjects")
    def temporal_subjects(limit: int = Query(50, ge=1, le=1000)) -> dict:
        store = TemporalStore(db_path or DB_PATH)
        try:
            rows = store._conn.execute(
                "SELECT subject, COUNT(*) n FROM versions "
                "GROUP BY subject ORDER BY n DESC LIMIT ?", (limit,)).fetchall()
            return {"subjects": [{"subject": r[0], "versions": r[1]} for r in rows]}
        finally:
            store.close()

    @app.get("/temporal/verify")
    def temporal_verify() -> dict:
        store = TemporalStore(db_path or DB_PATH)
        try:
            return store.verify_chain()
        finally:
            store.close()

    @app.get("/temporal/export")
    def temporal_export(subject: str | None = Query(None)) -> dict:
        return engine_for().export(subject)

    @app.get("/temporal/diagnostics")
    def temporal_diagnostics() -> dict:
        """Measured, not asserted: how much of the valid axis is real event time."""
        store = TemporalStore(db_path or DB_PATH)
        try:
            coverage = event_time_coverage(store.all_versions())
        finally:
            store.close()
        return {**TEMPORAL_DIAGNOSTICS, "event_time_coverage": coverage,
                "remedy": TEMPORAL_DIAGNOSTICS["remedy"]}

    @app.get("/temporal/event-time-coverage")
    def temporal_event_time_coverage() -> dict:
        store = TemporalStore(db_path or DB_PATH)
        try:
            return event_time_coverage(store.all_versions())
        finally:
            store.close()

    # -- temporal writes ------------------------------------------------

    @app.post("/temporal/assert")
    def temporal_assert(body: dict[str, Any]) -> dict:
        """Assert a belief. Refused if one is already open for that attribute."""
        engine = engine_for()
        interval = engine.assert_belief(
            body["subject"], body.get("attribute", "value"), body["value"],
            valid_from=body.get("valid_from"), known_at=body.get("known_at"),
            provenance=body.get("provenance"))
        return {"recorded": interval.to_dict()}

    @app.post("/temporal/correct")
    def temporal_correct(body: dict[str, Any]) -> dict:
        """Supersede the open belief. The old version stays queryable."""
        engine = engine_for()
        interval = engine.correct(
            body["subject"], body.get("attribute", "value"), body["value"],
            known_at=body.get("known_at"), valid_from=body.get("valid_from"),
            provenance=body.get("provenance"))
        return {"corrected": interval.to_dict()}

    @app.post("/temporal/retract")
    def temporal_retract(body: dict[str, Any]) -> dict:
        """Stop believing. Asserts no replacement and edits no valid time."""
        engine = engine_for()
        closed = engine.retract(body["subject"], body.get("attribute", "value"),
                                known_at=body.get("known_at"),
                                reason=body.get("reason", "retracted"))
        return {"retracted": len(closed), "closed": [v.to_dict() for v in closed]}

    @app.post("/temporal/expire")
    def temporal_expire(body: dict[str, Any]) -> dict:
        """Record that the claim itself stopped being true."""
        engine = engine_for()
        interval = engine.expire(body["subject"], body.get("attribute", "value"),
                                 body["valid_to"], reason=body.get("reason", "no_longer_true"))
        return {"expired": interval.to_dict()}

    # -- existing retrieval, read-only ----------------------------------

    @app.get("/recall/topic")
    def recall_topic(topic: str | None = Query(None), k: int = Query(20, ge=1, le=500)):
        memory = _memory()
        return {"recall": memory.recall(topic=topic, k=k)}

    @app.get("/recall/as-of")
    def recall_as_of(as_of: str | None = Query(None),
                     topic: str | None = Query(None),
                     k: int = Query(20, ge=1, le=500)):
        """The corrected as-of recall. Historical answers now survive corrections."""
        memory = _memory()
        return {"as_of": as_of, "slice": engine_for(memory).query(
            topic or "").slice_name,
            "records": memory.recall_at(as_of=as_of, topic=topic, k=k)}

    @app.get("/recall/hybrid")
    def recall_hybrid(q: str = Query(..., min_length=1),
                      k: int = Query(10, ge=1, le=100)):
        memory = _memory()
        return {"query": q, "results": memory.recall_hybrid(q, k=k)}

    @app.get("/recall/graph")
    def recall_graph(entity: str = Query(...), hops: int = Query(2, ge=1, le=5),
                     max_results: int = Query(20, ge=1, le=200)):
        memory = _memory()
        return memory.recall_graph(entity, hops=hops, max_results=max_results)

    @app.get("/recall/contamination")
    def recall_contamination() -> dict:
        """Step 7.4 audit. Includes pinned-block and graph surfaces."""
        return _memory().audit_contamination()

    return app


app = create_app()


def serve(host: str = "127.0.0.1", port: int = 8791) -> None:
    import uvicorn  # noqa: PLC0415
    uvicorn.run(app, host=host, port=port, log_level="info")