from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable

from .models import Capability, Job, JobState
from . import braid_hook


class StateStore:
    """Owned SQLite state plane with event history and snapshot support."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS capabilities (
                    id TEXT PRIMARY KEY,
                    body TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS edges (
                    src TEXT NOT NULL,
                    dst TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY (src, dst, relation)
                );
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    kind TEXT NOT NULL,
                    entity_id TEXT,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    body TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS feedback (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    plan_id TEXT NOT NULL,
                    outcome REAL NOT NULL,
                    correction TEXT,
                    metadata TEXT NOT NULL
                );
                """
            )

    def emit(self, kind: str, entity_id: str | None, payload: dict[str, Any]) -> int:
        braid_meta: dict[str, Any] = {}
        if kind in ("capability.upserted", "capability.deleted", "edge.upserted"):
            try:
                receipt = braid_hook.journal_event(kind, entity_id, payload)
                braid_meta = {"_braid_cid": receipt["cid"], "_braid_depth": receipt["depth"], "_braid_proof_hops": receipt["proof_hops"]}
            except braid_hook.BraidUnavailable as e:  # honest: ledger down is recorded, never faked
                braid_meta = {"_braid": "unavailable", "_braid_reason": str(e)}
        stored_payload = {**payload, **braid_meta}
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO events(ts,kind,entity_id,payload) VALUES(?,?,?,?)",
                (time.time(), kind, entity_id, json.dumps(stored_payload, sort_keys=True, default=str)),
            )
            return int(cur.lastrowid)

    def events_since(self, seq: int = 0, limit: int = 500) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT seq,ts,kind,entity_id,payload FROM events WHERE seq>? ORDER BY seq LIMIT ?",
            (seq, limit),
        ).fetchall()
        return [
            {
                "seq": r["seq"],
                "ts": r["ts"],
                "kind": r["kind"],
                "entity_id": r["entity_id"],
                "payload": json.loads(r["payload"]),
            }
            for r in rows
        ]

    def put_capability(self, capability: Capability) -> None:
        capability.validate()
        body = json.dumps(capability.to_dict(), sort_keys=True, default=str)
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO capabilities(id,body,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET body=excluded.body,updated_at=excluded.updated_at",
                (capability.id, body, capability.updated_at),
            )
        self.emit("capability.upserted", capability.id, capability.to_dict())

    def get_capability(self, capability_id: str) -> Capability | None:
        row = self._conn.execute("SELECT body FROM capabilities WHERE id=?", (capability_id,)).fetchone()
        return Capability.from_dict(json.loads(row["body"])) if row else None

    def all_capabilities(self) -> list[Capability]:
        rows = self._conn.execute("SELECT body FROM capabilities ORDER BY id").fetchall()
        return [Capability.from_dict(json.loads(r["body"])) for r in rows]

    def delete_capability(self, capability_id: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM capabilities WHERE id=?", (capability_id,))
            self._conn.execute("DELETE FROM edges WHERE src=? OR dst=?", (capability_id, capability_id))
        if cur.rowcount:
            self.emit("capability.deleted", capability_id, {})
            return True
        return False

    def put_edge(self, src: str, dst: str, relation: str, metadata: dict[str, Any] | None = None) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO edges(src,dst,relation,metadata) VALUES(?,?,?,?)",
                (src, dst, relation, json.dumps(metadata or {}, sort_keys=True)),
            )
        self.emit("edge.upserted", src, {"src": src, "dst": dst, "relation": relation})

    def edges(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT src,dst,relation,metadata FROM edges ORDER BY src,dst,relation").fetchall()
        return [dict(src=r["src"], dst=r["dst"], relation=r["relation"], metadata=json.loads(r["metadata"])) for r in rows]

    def put_job(self, job: Job) -> None:
        job.updated_at = time.time()
        body = json.dumps(job.to_dict(), sort_keys=True, default=str)
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO jobs(id,idempotency_key,body,updated_at) VALUES(?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET body=excluded.body,updated_at=excluded.updated_at",
                (job.id, job.idempotency_key, body, job.updated_at),
            )
        self.emit("job.updated", job.id, job.to_dict())

    def get_job_by_key(self, key: str) -> Job | None:
        row = self._conn.execute("SELECT body FROM jobs WHERE idempotency_key=?", (key,)).fetchone()
        if not row:
            return None
        d = json.loads(row["body"])
        d["state"] = JobState(d["state"])
        return Job(**d)

    def add_feedback(self, plan_id: str, outcome: float, correction: str | None = None, metadata: dict[str, Any] | None = None) -> None:
        if not -1.0 <= outcome <= 1.0:
            raise ValueError("feedback outcome must be between -1 and 1")
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO feedback(ts,plan_id,outcome,correction,metadata) VALUES(?,?,?,?,?)",
                (time.time(), plan_id, outcome, correction, json.dumps(metadata or {}, sort_keys=True)),
            )
        self.emit("feedback.recorded", plan_id, {"outcome": outcome, "correction": correction})

    def feedback_weight(self) -> float:
        row = self._conn.execute("SELECT AVG(outcome) AS avg_outcome FROM feedback").fetchone()
        return float(row["avg_outcome"] or 0.0)

    def snapshot(self) -> dict[str, Any]:
        return {
            "capabilities": [c.to_dict() for c in self.all_capabilities()],
            "edges": self.edges(),
            "events": self.events_since(0, 100000),
        }

    def close(self) -> None:
        self._conn.close()
