"""state_plane — owned persistent state layer for trust-bridge entities.

JSON files under the mem20 store (MEM20_STORE_PATH or ~/.mem20/store). Every
write is atomic (temp file + rename) and appends to an event history, so
snapshots and rollback are possible. Versioned entities with validation at the
boundary. Exposes create / query / update / subscribe / delete.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable

MEM20_STORE = os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store"))

SCHEMA_VERSION = 1


class StatePlaneError(RuntimeError):
    pass


class StatePlane:
    """Persistent, versioned, atomic JSON state plane for one entity type.

    Layout:
      <store>/<name>.json                 entity records by id
      <store>/<name>.history.jsonl        append-only event history
    """

    def __init__(self, name: str, store: str | None = None,
                 validator: Callable[[str, dict[str, Any]], None] | None = None) -> None:
        self.name = name
        self.store_dir = Path(store or MEM20_STORE)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._data_file = self.store_dir / f"{name}.json"
        self._history_file = self.store_dir / f"{name}.history.jsonl"
        self._validator = validator
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self._data_file.exists():
            return {}
        with open(self._data_file) as f:
            return json.load(f)

    def _save(self) -> None:
        tmp = self._data_file.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(self._data, f, indent=2)
        os.replace(tmp, self._data_file)

    def _record(self, op: str, entity_id: str, payload: dict[str, Any]) -> None:
        with open(self._history_file, "a") as f:
            f.write(json.dumps({
                "ts": time.time(),
                "schema_version": SCHEMA_VERSION,
                "op": op,
                "entity": entity_id,
                "payload": payload,
            }) + "\n")

    def _validate(self, entity_id: str, entity: dict[str, Any]) -> None:
        if self._validator is not None:
            self._validator(entity_id, entity)

    # --- CRUD ---------------------------------------------------------
    def put(self, entity_id: str, entity: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._validate(entity_id, entity)
            prev = self._data.get(entity_id)
            stored = dict(entity)
            stored.setdefault("entity_id", entity_id)
            self._data[entity_id] = stored
            self._save()
            self._record("put", entity_id, {
                "entity": stored,
                "previous": prev,
            })
            return dict(stored)

    def get(self, entity_id: str, default: Any = None) -> Any:
        with self._lock:
            found = self._data.get(entity_id)
            return dict(found) if isinstance(found, dict) else (default if found is None else found)

    def all(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(v) for v in self._data.values()]

    def query(self, **filters: Any) -> list[dict[str, Any]]:
        with self._lock:
            out = []
            for v in self._data.values():
                if all(v.get(k) == val for k, val in filters.items()):
                    out.append(dict(v))
            return out

    def delete(self, entity_id: str) -> bool:
        with self._lock:
            if entity_id not in self._data:
                return False
            removed = self._data.pop(entity_id)
            self._save()
            self._record("delete", entity_id, {"removed": removed})
            return True

    def subscribe_ids(self, pattern: str = "") -> list[str]:
        with self._lock:
            ids = sorted(self._data.keys())
            if not pattern:
                return ids
            import fnmatch
            return [i for i in ids if fnmatch.fnmatch(i, pattern)]

    def history(self, entity_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if not self._history_file.exists():
            return []
        out = []
        with open(self._history_file) as f:
            for line in f:
                if not line.strip():
                    continue
                ev = json.loads(line)
                if entity_id is None or ev.get("entity") == entity_id:
                    out.append(ev)
        return out[-limit:]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "schema_version": SCHEMA_VERSION,
                "name": self.name,
                "entities": dict(self._data),
            }