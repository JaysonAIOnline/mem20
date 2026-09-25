"""mem20langz — checkpointers.

BaseCheckpointSaver defines the storage contract. InMemorySaver stores
per-thread state snapshots in memory (thread_id keyed, newest last); it also
DRAMAtes the ``interrupt`` flag and a pending-task list so a run paused by
interrupt() can resume at the same node.

Mirrors mem20 graph substrate.checkpoint.memory semantics at a minimal level.
"""

from __future__ import annotations

import copy
import threading
import time
import uuid
from typing import Any, Optional


class Checkpoint:
    __slots__ = ("checkpoint_id", "state", "interrupt", "created")

    def __init__(self, state: dict[str, Any], checkpoint_id: Optional[str] = None, interrupt: bool = False) -> None:
        self.checkpoint_id = checkpoint_id or str(uuid.uuid4())
        self.state = copy.deepcopy(state)
        self.interrupt = interrupt
        self.created = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "state": copy.deepcopy(self.state),
            "interrupt": self.interrupt,
            "created": self.created,
        }


class BaseCheckpointSaver:
    """Storage contract used by the Pregel runtime."""

    def put(self, thread_id: str, state: dict[str, Any], checkpoint_id: Optional[str] = None, interrupt: bool = False) -> str:
        raise NotImplementedError

    def get(self, thread_id: str) -> Optional[dict[str, Any]]:
        raise NotImplementedError

    def list(self, thread_id: str, limit: int = 50) -> list[dict[str, Any]]:
        raise NotImplementedError

    def get_pending(self, thread_id: str) -> Optional[list[str]]:
        raise NotImplementedError

    def get_pending_writes(self, thread_id: str) -> Optional[list[Any]]:
        return None

    def clear(self, thread_id: str) -> None:
        raise NotImplementedError


class InMemorySaver(BaseCheckpointSaver):
    """Thread-safe in-memory checkpointer keyed by thread_id."""

    def __init__(self) -> None:
        self._store: dict[str, list[Checkpoint]] = {}
        self._lock = threading.Lock()

    def put(self, thread_id: str, state: dict[str, Any], checkpoint_id: Optional[str] = None, interrupt: bool = False) -> str:
        cp = Checkpoint(state, checkpoint_id=checkpoint_id, interrupt=interrupt)
        with self._lock:
            self._store.setdefault(thread_id, []).append(cp)
        return cp.checkpoint_id

    def get(self, thread_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            items = self._store.get(thread_id)
            if not items:
                return None
            last = items[-1]
        return last.to_dict()

    def list(self, thread_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            items = self._store.get(thread_id) or []
            return [cp.to_dict() for cp in items[-limit:]]

    def get_pending(self, thread_id: str) -> Optional[list[str]]:
        cp = self.get(thread_id)
        if cp and cp["interrupt"] and cp["state"].get("_pending"):
            return list(cp["state"]["_pending"])
        return None

    def get_pending_writes(self, thread_id: str) -> Optional[list[Any]]:
        return None

    def clear(self, thread_id: str) -> None:
        with self._lock:
            self._store.pop(thread_id, None)

    @property
    def threads(self) -> list[str]:
        with self._lock:
            return list(self._store.keys())