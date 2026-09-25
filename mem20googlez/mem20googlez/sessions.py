from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import DEFAULT_CONFIG
from .events import Event
from .util import datetime_from_iso as parse_datetime
from .util import utcnow


@dataclass
class State:
    data: dict = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def update(self, data: dict) -> None:
        self.data.update(data)

    def to_dict(self) -> dict:
        return dict(self.data)


@dataclass
class Session:
    id: str
    app_name: str
    user_id: str
    state: State = field(default_factory=State)
    events: list[Event] = field(default_factory=list)
    created_at: Any = field(default_factory=utcnow)
    updated_at: Any = field(default_factory=utcnow)

    def add_event(self, event: Event) -> None:
        self.events.append(event)
        self.updated_at = utcnow()

    def get_last_output(self) -> str | None:
        for event in reversed(self.events):
            if event.text():
                return event.text()
        return None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "app_name": self.app_name,
            "user_id": self.user_id,
            "state": self.state.to_dict(),
            "events": [event.to_dict() for event in self.events],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class BaseSessionService:
    async def create_session(
        self,
        app_name: str,
        user_id: str,
        session_id: str | None = None,
        state: dict | None = None,
    ) -> Session:
        raise TypeError(f"{type(self).__name__} must implement create_session")

    async def get_session(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> Session | None:
        raise TypeError(f"{type(self).__name__} must implement get_session")

    async def list_sessions(
        self,
        app_name: str | None = None,
        user_id: str | None = None,
    ) -> list[Session]:
        raise TypeError(f"{type(self).__name__} must implement list_sessions")

    async def delete_session(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> bool:
        raise TypeError(f"{type(self).__name__} must implement delete_session")

    async def append_event(self, session: Session, event: Event) -> None:
        raise TypeError(f"{type(self).__name__} must implement append_event")

    async def update_state(self, session: Session, delta: dict) -> None:
        session.state.update(delta)
        raise TypeError(f"{type(self).__name__} must implement update_state")

    async def get_session_by_id(
        self,
        session_id: str,
        app_name: str | None = None,
        user_id: str | None = None,
    ) -> Session | None:
        raise TypeError(f"{type(self).__name__} must implement get_session_by_id")


class InMemorySessionService(BaseSessionService):
    def __init__(self):
        self._sessions: dict[tuple[str, str, str], Session] = {}

    @staticmethod
    def _key(app_name: str, user_id: str, session_id: str) -> tuple[str, str, str]:
        return app_name, user_id, session_id

    async def create_session(
        self,
        app_name: str,
        user_id: str,
        session_id: str | None = None,
        state: dict | None = None,
    ) -> Session:
        requested_id = session_id or uuid.uuid4().hex
        key = self._key(app_name, user_id, requested_id)
        if key in self._sessions:
            return self._sessions[key]
        now = utcnow()
        session = Session(
            id=requested_id,
            app_name=app_name,
            user_id=user_id,
            state=State(dict(state or {})),
            created_at=now,
            updated_at=now,
        )
        self._sessions[key] = session
        return session

    async def get_session(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> Session | None:
        return self._sessions.get(self._key(app_name, user_id, session_id))

    async def list_sessions(
        self,
        app_name: str | None = None,
        user_id: str | None = None,
    ) -> list[Session]:
        return [
            session
            for (stored_app, stored_user, _), session in self._sessions.items()
            if (app_name is None or stored_app == app_name)
            and (user_id is None or stored_user == user_id)
        ]

    async def delete_session(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> bool:
        return self._sessions.pop(self._key(app_name, user_id, session_id), None) is not None

    async def append_event(self, session: Session, event: Event) -> None:
        session.add_event(event)

    async def update_state(self, session: Session, delta: dict) -> None:
        session.state.update(delta)

    async def get_session_by_id(
        self,
        session_id: str,
        app_name: str | None = None,
        user_id: str | None = None,
    ) -> Session | None:
        for session in await self.list_sessions(app_name, user_id):
            if session.id == session_id:
                return session
        return None


class DatabaseSessionService(BaseSessionService):
    def __init__(self, db_path: str | None = None):
        self.db_path = str(db_path or DEFAULT_CONFIG.session_db_path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30.0)
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _init_db(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    app_name TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    events TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_app_user ON sessions(app_name, user_id)"
            )

    @staticmethod
    def _row_to_session(row: sqlite3.Row | tuple) -> Session:
        return Session(
            id=row[0],
            app_name=row[1],
            user_id=row[2],
            state=State(json.loads(row[3])),
            events=[Event.from_dict(item) for item in json.loads(row[4])],
            created_at=parse_datetime(row[5]),
            updated_at=parse_datetime(row[6]),
        )

    async def create_session(
        self,
        app_name: str,
        user_id: str,
        session_id: str | None = None,
        state: dict | None = None,
    ) -> Session:
        requested_id = session_id or uuid.uuid4().hex
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM sessions WHERE id=?", (requested_id,)
            ).fetchone()
            if existing is not None:
                if existing[1] != app_name or existing[2] != user_id:
                    raise ValueError(f"session id '{requested_id}' belongs to another user")
                restored = self._row_to_session(existing)
                if state:
                    restored.state.update(state)
                    self._save(connection, restored)
                return restored
            now = utcnow()
            connection.execute(
                "INSERT INTO sessions(id, app_name, user_id, state, events, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    requested_id,
                    app_name,
                    user_id,
                    json.dumps(dict(state or {})),
                    "[]",
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
        return Session(
            id=requested_id,
            app_name=app_name,
            user_id=user_id,
            state=State(dict(state or {})),
            created_at=now,
            updated_at=now,
        )

    async def get_session(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> Session | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE id=? AND app_name=? AND user_id=?",
                (session_id, app_name, user_id),
            ).fetchone()
        return self._row_to_session(row) if row else None

    async def get_session_by_id(
        self,
        session_id: str,
        app_name: str | None = None,
        user_id: str | None = None,
    ) -> Session | None:
        clauses = ["id=?"]
        values: list[str] = [session_id]
        if app_name is not None:
            clauses.append("app_name=?")
            values.append(app_name)
        if user_id is not None:
            clauses.append("user_id=?")
            values.append(user_id)
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT * FROM sessions WHERE {' AND '.join(clauses)}", values
            ).fetchone()
        return self._row_to_session(row) if row else None

    async def list_sessions(
        self,
        app_name: str | None = None,
        user_id: str | None = None,
    ) -> list[Session]:
        clauses: list[str] = []
        values: list[str] = []
        if app_name is not None:
            clauses.append("app_name=?")
            values.append(app_name)
        if user_id is not None:
            clauses.append("user_id=?")
            values.append(user_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM sessions{where} ORDER BY updated_at DESC", values
            ).fetchall()
        return [self._row_to_session(row) for row in rows]

    async def delete_session(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM sessions WHERE id=? AND app_name=? AND user_id=?",
                (session_id, app_name, user_id),
            )
            return cursor.rowcount > 0

    @staticmethod
    def _save(connection: sqlite3.Connection, session: Session) -> None:
        connection.execute(
            "UPDATE sessions SET state=?, events=?, updated_at=? WHERE id=? AND app_name=? AND user_id=?",
            (
                json.dumps(session.state.to_dict()),
                json.dumps([event.to_dict() for event in session.events]),
                session.updated_at.isoformat(),
                session.id,
                session.app_name,
                session.user_id,
            ),
        )

    async def append_event(self, session: Session, event: Event) -> None:
        session.add_event(event)
        with self._connect() as connection:
            self._save(connection, session)

    async def update_state(self, session: Session, delta: dict) -> None:
        session.state.update(delta)
        session.updated_at = utcnow()
        with self._connect() as connection:
            self._save(connection, session)


def datetime_from_iso(value: str):
    return parse_datetime(value)
