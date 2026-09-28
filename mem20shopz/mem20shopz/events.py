"""Durable record of which Stripe events have already been handled.

Stripe redelivers. A webhook that succeeds and then gets retried - after a
timeout, a crash, or a deploy - must not provision a second account for one
payment. So the event id is recorded before the work runs, and a repeat is
refused.

SQLite rather than a dict on purpose: a redelivery usually arrives after a
restart, and an in-memory set would have forgotten. Writes are committed before
provisioning starts, so a crash mid-provision leaves the event marked and the
retry refused rather than double-charging the customer's downstream system.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

DEFAULT_DB = "/opt/mem20/store/shop/events.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_events (
    event_id     TEXT PRIMARY KEY,
    event_type   TEXT NOT NULL,
    processed_at REAL NOT NULL,
    outcome      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS processed_events_at ON processed_events (processed_at);
"""


class EventStore:
    def __init__(self, path: str = DEFAULT_DB) -> None:
        self.path = path
        self._lock = threading.Lock()
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        try:
            conn.row_factory = sqlite3.Row
            yield conn
            conn.commit()
        finally:
            conn.close()

    def already_processed(self, event_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT event_id, event_type, processed_at, outcome FROM processed_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return dict(row) if row else None

    def mark(self, event_id: str, event_type: str, outcome: str) -> bool:
        """Record an event as handled.

        Returns True if this call was the one that recorded it, False if another
        worker got there first. The primary key is what makes the check and the
        insert a single atomic step.
        """
        import time

        with self._lock, self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO processed_events (event_id, event_type, processed_at, outcome) VALUES (?, ?, ?, ?)",
                    (event_id, event_type, time.time(), outcome),
                )
            except sqlite3.IntegrityError:
                return False
        return True

    def count(self) -> int:
        with self._lock, self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM processed_events").fetchone()[0])

    def outcomes(self) -> dict[str, int]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT outcome, COUNT(*) FROM processed_events GROUP BY outcome").fetchall()
        return {row[0]: int(row[1]) for row in rows}
