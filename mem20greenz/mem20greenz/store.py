"""Clone target registry (sqlite, per-workspace).

Statuses: staged -> captured -> baselined -> verified -> promoted.
`dropped` is terminal. Every transition is validated; illegal jumps
raise instead of silently passing.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS targets(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL,
  kind TEXT NOT NULL,
  source TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'staged',
  created REAL NOT NULL,
  updated REAL NOT NULL
);
"""

_ORDER = ["staged", "captured", "baselined", "verified", "promoted"]
_TERMINAL = {"dropped"}


class RegistryError(RuntimeError):
    pass


class Registry:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(str(self.path), timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def add(self, name: str, kind: str, source: str) -> dict:
        if kind not in ("software", "website"):
            raise RegistryError(f"kind must be software|website, got {kind!r}")
        now = time.time()
        try:
            with self._connect() as db:
                cur = db.execute(
                    "INSERT INTO targets(name,kind,source,status,created,updated)"
                    " VALUES(?,?,?,?,?,?)",
                    (name, kind, source, "staged", now, now),
                )
                rowid = cur.lastrowid
        except sqlite3.IntegrityError as exc:
            raise RegistryError(f"target {name!r} already registered") from exc
        created = self.get(name)
        if created is None:
            raise RegistryError(f"target {name!r} vanished after insert")
        return created

    def get(self, name: str) -> Optional[dict]:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM targets WHERE name=?", (name,)).fetchone()
        return dict(row) if row else None

    def list(self, status: Optional[str] = None) -> list[dict]:
        with self._connect() as db:
            if status:
                rows = db.execute(
                    "SELECT * FROM targets WHERE status=? ORDER BY id",
                    (status,)).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM targets ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def advance(self, name: str, to: str) -> dict:
        current = self.get(name)
        if current is None:
            raise RegistryError(f"unknown target {name!r}")
        if current["status"] in _TERMINAL:
            raise RegistryError(f"target {name!r} is dropped (terminal)")
        if to == "dropped":
            pass
        elif to not in _ORDER:
            raise RegistryError(f"unknown status {to!r}")
        elif _ORDER.index(to) != _ORDER.index(current["status"]) + 1:
            raise RegistryError(
                f"illegal transition {current['status']!r} -> {to!r}")
        with self._connect() as db:
            db.execute("UPDATE targets SET status=?, updated=? WHERE name=?",
                       (to, time.time(), name))
        updated = self.get(name)
        if updated is None:
            raise RegistryError(f"target {name!r} vanished after update")
        return updated

    def drop(self, name: str) -> dict:
        return self.advance(name, "dropped")
