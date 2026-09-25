from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import DEFAULT_CONFIG
from .util import datetime_from_iso, utcnow


@dataclass
class MemoryEntry:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    content: str = ""
    author: str = ""
    timestamp: Any = field(default_factory=utcnow)
    metadata: dict = field(default_factory=dict)
    embedding: list[float] | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "author": self.author,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "embedding": self.embedding,
        }

    @classmethod
    def from_dict(cls, data: dict) -> MemoryEntry:
        timestamp = data.get("timestamp")
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex),
            content=str(data.get("content", "")),
            author=str(data.get("author", "")),
            timestamp=datetime_from_iso(timestamp) if timestamp else utcnow(),
            metadata=dict(data.get("metadata") or {}),
            embedding=data.get("embedding"),
        )


class BaseMemoryService:
    async def add_memory(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
        entry: MemoryEntry,
    ) -> None:
        raise TypeError(f"{type(self).__name__} must implement add_memory")

    async def search_memory(
        self,
        app_name: str,
        user_id: str,
        query: str,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        raise TypeError(f"{type(self).__name__} must implement search_memory")

    async def get_memory(
        self,
        app_name: str,
        user_id: str,
        memory_id: str,
    ) -> MemoryEntry | None:
        raise TypeError(f"{type(self).__name__} must implement get_memory")

    async def list_memories(
        self,
        app_name: str,
        user_id: str,
        session_id: str | None = None,
        limit: int = 100,
    ) -> list[MemoryEntry]:
        raise TypeError(f"{type(self).__name__} must implement list_memories")

    async def delete_memory(
        self,
        app_name: str,
        user_id: str,
        memory_id: str,
    ) -> bool:
        raise TypeError(f"{type(self).__name__} must implement delete_memory")


class InMemoryMemoryService(BaseMemoryService):
    def __init__(self):
        self._memories: dict[tuple[str, str, str, str], MemoryEntry] = {}

    @staticmethod
    def _key(app_name: str, user_id: str, session_id: str, memory_id: str) -> tuple[str, str, str, str]:
        return app_name, user_id, session_id, memory_id

    async def add_memory(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
        entry: MemoryEntry,
    ) -> None:
        self._memories[self._key(app_name, user_id, session_id, entry.id)] = entry

    async def search_memory(
        self,
        app_name: str,
        user_id: str,
        query: str,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        query_text = query.casefold()
        matches = [
            entry
            for (app, user, _, _), entry in self._memories.items()
            if app == app_name and user == user_id and query_text in entry.content.casefold()
        ]
        matches.sort(key=lambda entry: entry.timestamp, reverse=True)
        return matches[: max(0, limit)]

    async def get_memory(
        self,
        app_name: str,
        user_id: str,
        memory_id: str,
    ) -> MemoryEntry | None:
        for (app, user, _, identifier), entry in self._memories.items():
            if app == app_name and user == user_id and identifier == memory_id:
                return entry
        return None

    async def list_memories(
        self,
        app_name: str,
        user_id: str,
        session_id: str | None = None,
        limit: int = 100,
    ) -> list[MemoryEntry]:
        entries = [
            entry
            for (app, user, stored_session, _), entry in self._memories.items()
            if app == app_name
            and user == user_id
            and (session_id is None or stored_session == session_id)
        ]
        entries.sort(key=lambda entry: entry.timestamp, reverse=True)
        return entries[: max(0, limit)]

    async def delete_memory(
        self,
        app_name: str,
        user_id: str,
        memory_id: str,
    ) -> bool:
        for key, entry in list(self._memories.items()):
            if key[0] == app_name and key[1] == user_id and key[3] == memory_id:
                del self._memories[key]
                return True
        return False


class FileMemoryService(BaseMemoryService):
    def __init__(self, memory_dir: str | None = None):
        self.memory_dir = Path(memory_dir or DEFAULT_CONFIG.memory_dir)
        self._lock = threading.RLock()

    @staticmethod
    def _safe_component(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", value) or "_"

    def _path_for(self, app_name: str, user_id: str) -> Path:
        return self.memory_dir / self._safe_component(app_name) / f"{self._safe_component(user_id)}.json"

    def _load(self, app_name: str, user_id: str) -> list[MemoryEntry]:
        path = self._path_for(app_name, user_id)
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
        if not isinstance(data, list):
            raise TypeError(f"memory store {path} is not a JSON list")
        return [MemoryEntry.from_dict(item) for item in data]

    def _save(self, app_name: str, user_id: str, entries: list[MemoryEntry]) -> None:
        path = self._path_for(app_name, user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=".memory-", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump([entry.to_dict() for entry in entries], stream, indent=2, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    async def add_memory(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
        entry: MemoryEntry,
    ) -> None:
        with self._lock:
            entry.metadata = dict(entry.metadata)
            entry.metadata.setdefault("session_id", session_id)
            entries = self._load(app_name, user_id)
            entries = [existing for existing in entries if existing.id != entry.id]
            entries.append(entry)
            self._save(app_name, user_id, entries)

    async def search_memory(
        self,
        app_name: str,
        user_id: str,
        query: str,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        with self._lock:
            entries = self._load(app_name, user_id)
        query_text = query.casefold()
        results = [entry for entry in entries if query_text in entry.content.casefold()]
        results.sort(key=lambda entry: entry.timestamp, reverse=True)
        return results[: max(0, limit)]

    async def get_memory(
        self,
        app_name: str,
        user_id: str,
        memory_id: str,
    ) -> MemoryEntry | None:
        with self._lock:
            return next(
                (entry for entry in self._load(app_name, user_id) if entry.id == memory_id),
                None,
            )

    async def list_memories(
        self,
        app_name: str,
        user_id: str,
        session_id: str | None = None,
        limit: int = 100,
    ) -> list[MemoryEntry]:
        with self._lock:
            entries = self._load(app_name, user_id)
        if session_id is not None:
            entries = [entry for entry in entries if entry.metadata.get("session_id") == session_id]
        entries.sort(key=lambda entry: entry.timestamp, reverse=True)
        return entries[: max(0, limit)]

    async def delete_memory(
        self,
        app_name: str,
        user_id: str,
        memory_id: str,
    ) -> bool:
        with self._lock:
            entries = self._load(app_name, user_id)
            remaining = [entry for entry in entries if entry.id != memory_id]
            if len(remaining) == len(entries):
                return False
            self._save(app_name, user_id, remaining)
            return True
