"""Rooms, membership, messages (sqlite)."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Optional


class StoreError(RuntimeError):
    pass


_SCHEMA = """
CREATE TABLE IF NOT EXISTS rooms(
  name TEXT PRIMARY KEY,
  topic TEXT NOT NULL DEFAULT '',
  created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS members(
  room TEXT NOT NULL,
  profile TEXT NOT NULL,
  kind TEXT NOT NULL,
  joined REAL NOT NULL,
  PRIMARY KEY(room, profile)
);
CREATE TABLE IF NOT EXISTS messages(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  room TEXT NOT NULL,
  sender TEXT NOT NULL,
  text TEXT NOT NULL,
  ts REAL NOT NULL
);
"""


class Store:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(str(self.path), timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def create_room(self, name: str, topic: str = "") -> dict:
        if not name or not name.replace("-", "").replace("_", "").isalnum():
            raise StoreError(f"bad room name {name!r}")
        try:
            with self._connect() as db:
                db.execute("INSERT INTO rooms(name,topic,created) VALUES(?,?,?)",
                           (name, topic, time.time()))
        except sqlite3.IntegrityError as exc:
            raise StoreError(f"room {name!r} exists") from exc
        return {"name": name, "topic": topic}

    def rooms(self) -> list[dict]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM rooms ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    def join(self, room: str, profile: str, kind: str = "agent") -> dict:
        if kind not in ("human", "agent"):
            raise StoreError(f"kind must be human|agent, got {kind!r}")
        with self._connect() as db:
            exists = db.execute("SELECT 1 FROM rooms WHERE name=?",
                                (room,)).fetchone()
            if not exists:
                raise StoreError(f"unknown room {room!r}")
            db.execute("INSERT OR IGNORE INTO members(room,profile,kind,joined)"
                       " VALUES(?,?,?,?)", (room, profile, kind, time.time()))
        return {"room": room, "profile": profile, "kind": kind}

    def members(self, room: str) -> list[dict]:
        with self._connect() as db:
            rows = db.execute("SELECT profile,kind FROM members WHERE room=?",
                              (room,)).fetchall()
        return [dict(r) for r in rows]

    def post(self, room: str, sender: str, text: str) -> dict:
        if not text.strip():
            raise StoreError("empty message refused")
        with self._connect() as db:
            exists = db.execute("SELECT 1 FROM rooms WHERE name=?",
                                (room,)).fetchone()
            if not exists:
                raise StoreError(f"unknown room {room!r}")
            cur = db.execute("INSERT INTO messages(room,sender,text,ts)"
                             " VALUES(?,?,?,?)",
                             (room, sender, text, time.time()))
            rowid = cur.lastrowid
        return {"id": rowid, "room": room, "sender": sender, "text": text}

    def history(self, room: str, limit: int = 50) -> list[dict]:
        with self._connect() as db:
            rows = db.execute("SELECT id,sender,text,ts FROM messages"
                              " WHERE room=? ORDER BY id DESC LIMIT ?",
                              (room, limit)).fetchall()
        return [dict(r) for r in reversed(rows)]

    def find_profile(self, room: str, name: str) -> Optional[dict]:
        lowered = name.lower()
        for member in self.members(room):
            if member["profile"].lower() == lowered:
                return member
        return None
