"""Durable, verifiable storage for bi-temporal versions.

SQLite only - no dependency, one file, WAL mode. Two tables:

  versions  the queryable bi-temporal intervals
  events    an append-only, hash-chained log of everything that happened

The event log is the authority. `versions` is derived state that can be dropped
and rebuilt from the log at any time, and `verify_chain()` proves the log has
not been edited. This is what makes "why did the system believe that?" a
question with an answer rather than an assertion.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from typing import Any, Iterable

GENESIS = "0" * 64

__all__ = ["TemporalStore", "ChainError", "canonical", "version_id_for"]


class ChainError(RuntimeError):
    """Raised when the event log does not hash to its recorded chain."""


def canonical(obj: Any) -> str:
    """Stable JSON: same structure always yields the same bytes."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str)


def _sha(prev_hash: str, payload: str) -> str:
    return hashlib.sha256(f"{prev_hash}|{payload}".encode()).hexdigest()


def version_id_for(subject: str, attribute: str, known_from: str, value_ref: str) -> str:
    """Content-addressed version id.

    Derived from the inputs rather than a counter or a random string, so
    replaying the same sequence of assertions produces the same ids. That is
    what lets an ingest be idempotent without a separate dedup table.
    """
    return hashlib.sha256(
        canonical({"s": subject, "a": attribute, "k": known_from, "v": value_ref})
        .encode()
    ).hexdigest()[:20]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS versions (
    version_id TEXT PRIMARY KEY,
    subject    TEXT NOT NULL,
    attribute  TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to   TEXT,
    known_from TEXT NOT NULL,
    known_to   TEXT,
    value_ref  TEXT NOT NULL DEFAULT '',
    provenance TEXT NOT NULL DEFAULT '{}',
    seq        INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_versions_subject
    ON versions(subject, attribute);
CREATE INDEX IF NOT EXISTS idx_versions_valid
    ON versions(valid_from, valid_to);
CREATE INDEX IF NOT EXISTS idx_versions_known
    ON versions(known_from, known_to);

CREATE TABLE IF NOT EXISTS events (
    seq       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT NOT NULL,
    kind      TEXT NOT NULL,
    payload   TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    hash      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind);
"""


class TemporalStore:
    """SQLite-backed version store with a tamper-evident event chain."""

    def __init__(self, path: str | os.PathLike[str]):
        self.path = str(path)
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "TemporalStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- event chain ----------------------------------------------------

    def head_hash(self) -> str:
        row = self._conn.execute("SELECT hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        return row["hash"] if row else GENESIS

    def append_event(self, ts: str, kind: str, payload: dict) -> str:
        """Append one event and chain it onto the current head."""
        prev = self.head_hash()
        body = canonical({"ts": ts, "kind": kind, "payload": payload})
        digest = _sha(prev, body)
        self._conn.execute(
            "INSERT INTO events(ts, kind, payload, prev_hash, hash) VALUES(?,?,?,?,?)",
            (ts, kind, body, prev, digest),
        )
        self._conn.commit()
        return digest

    def events(self, limit: int | None = None, kind: str | None = None) -> list[dict]:
        sql = "SELECT seq, ts, kind, payload, prev_hash, hash FROM events"
        args: list[Any] = []
        if kind:
            sql += " WHERE kind = ?"
            args.append(kind)
        sql += " ORDER BY seq"
        if limit:
            sql += " LIMIT ?"
            args.append(limit)
        return [dict(r) for r in self._conn.execute(sql, args).fetchall()]

    def verify_chain(self) -> dict:
        """Recompute every hash. Any edited event breaks the chain at that point."""
        prev = GENESIS
        checked = 0
        for row in self._conn.execute(
            "SELECT seq, ts, kind, payload, prev_hash, hash FROM events ORDER BY seq"
        ):
            if row["prev_hash"] != prev:
                raise ChainError(
                    f"event {row['seq']} expects prev_hash {prev[:12]}... "
                    f"but records {row['prev_hash'][:12]}...")
            expected = _sha(prev, row["payload"])
            if expected != row["hash"]:
                raise ChainError(f"event {row['seq']} hash mismatch: content was altered")
            prev = row["hash"]
            checked += 1
        return {"ok": True, "events_checked": checked, "head": prev}

    # -- versions -------------------------------------------------------

    def put_version(self, row: dict, seq: int = 0) -> bool:
        """Insert a version. Returns False if this exact version already exists.

        Idempotent by construction: a replayed ingest is a no-op rather than a
        duplicate, so replaying history twice cannot change an answer.
        """
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO versions"
            "(version_id, subject, attribute, valid_from, valid_to,"
            " known_from, known_to, value_ref, provenance, seq)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (row["version_id"], row["subject"], row["attribute"],
             row["valid_from"], row.get("valid_to"), row["known_from"],
             row.get("known_to"), row.get("value_ref", ""),
             canonical(row.get("provenance", {})), seq),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def close_version(self, version_id: str, known_to: str, seq: int = 0) -> bool:
        """Close a version's KNOWN interval. Never touches valid_to.

        This is the whole point of the known axis: retiring a belief does not
        rewrite what was true in the world, it only records that we stopped
        holding the belief.
        """
        cur = self._conn.execute(
            "UPDATE versions SET known_to = ? WHERE version_id = ? AND known_to IS NULL",
            (known_to, version_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def close_validity(self, version_id: str, valid_to: str) -> bool:
        """Close a version's VALID interval: the claim itself stopped being true."""
        cur = self._conn.execute(
            "UPDATE versions SET valid_to = ? WHERE version_id = ? AND valid_to IS NULL",
            (valid_to, version_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def versions_for(self, subject: str | None = None,
                     attribute: str | None = None) -> list[dict]:
        sql = "SELECT * FROM versions"
        clauses, args = [], []
        if subject is not None:
            clauses.append("subject = ?")
            args.append(subject)
        if attribute is not None:
            clauses.append("attribute = ?")
            args.append(attribute)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY seq, known_from, valid_from, version_id"
        return [dict(r) for r in self._conn.execute(sql, args).fetchall()]

    def all_versions(self) -> list[dict]:
        return [dict(r) for r in self._conn.execute("SELECT * FROM versions").fetchall()]

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM versions").fetchone()[0])

    def count_events(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])