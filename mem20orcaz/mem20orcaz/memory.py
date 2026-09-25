"""In-memory memory backend for mem20orcaz.

Pure-stdlib substitute for OrKa's Redis-based memory loggers. Provides the same
shaped interface (set/hset/get/hget/keys/scan/sadd/smembers/search-memories/
save-enhanced-trace/close) backed by plain Python dicts so every orchestration
feature is usable without a Redis server. An optional JSON snapshot export can
be attached for inspection.

Search is a deterministic keyword-scoring retrieval over stored values (BM25-lite
on token overlap), standing in for the RedisStack vector backend while keeping
the package dependency-free and hermetic in tests.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import uuid
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional

from .contracts import now_iso

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[a-zA-Z0-9]+")
_NS_SEP = "::"
_DEFAULT_NAMESPACE = "mem20orcaz"


class _RedisCompatBase:
    """Minimal dict-backed Redis-like store (subset used by OrKa)."""

    def __init__(self, host: str = "memory", port: int = 0, db: int = 0) -> None:
        self.host = host
        self.port = port
        self.db = db
        self._data: Dict[str, Any] = {}

    def set(self, name: str, value: Any, ex: Optional[int] = None) -> bool:
        self._data[name] = value
        return True

    def get(self, name: str) -> Any:
        return self._data.get(name)

    def hset(self, name: str, key: str, value: Any) -> int:
        bucket = self._data.setdefault(name, {})
        if not isinstance(bucket, dict):
            bucket = {}
            self._data[name] = bucket
        bucket[key] = value
        return 1

    def hget(self, name: str, key: str) -> Any:
        bucket = self._data.get(name)
        return bucket.get(key) if isinstance(bucket, dict) else None

    def hgetall(self, name: str) -> Dict[str, Any]:
        bucket = self._data.get(name)
        return dict(bucket) if isinstance(bucket, dict) else {}

    def hdel(self, name: str, key: str) -> int:
        bucket = self._data.get(name)
        if isinstance(bucket, dict) and key in bucket:
            del bucket[key]
            return 1
        return 0

    def exists(self, name: str) -> int:
        return 1 if name in self._data else 0

    def keys(self, pattern: str = "*") -> List[str]:
        if pattern in ("*", ""):
            return list(self._data.keys())
        # simple glob: translate * -> .*, ? -> .
        rx = "^" + re.escape(pattern).replace("\\*", ".*").replace("\\?", ".") + "$"
        return [k for k in self._data if re.match(rx, k)]

    def scan_iter(self, match: str = "*", count: int = 100) -> Iterable[str]:
        return iter(self.keys(match))

    def sadd(self, name: str, *members: Any) -> int:
        bucket = self._data.setdefault(name, set())
        if not isinstance(bucket, set):
            bucket = set(bucket)
            self._data[name] = bucket
        before = len(bucket)
        bucket.update(members)
        return len(bucket) - before

    def smembers(self, name: str) -> set:
        bucket = self._data.get(name)
        return set(bucket) if isinstance(bucket, (set, list, tuple)) else set()

    def incr(self, name: str) -> int:
        val = int(self._data.get(name, 0))
        val += 1
        self._data[name] = val
        return val

    def delete(self, *names: str) -> int:
        n = 0
        for name in names:
            if name in self._data:
                del self._data[name]
                n += 1
        return n

    def flushall(self) -> bool:
        self._data.clear()
        return True


class BaseMemoryLogger:
    """Interface for memory loggers (pure stdlib)."""

    def set(self, key: str, value: Any, **kwargs: Any) -> str:  # pragma: no cover
        raise NotImplementedError

    def get(self, key: str) -> Any:  # pragma: no cover
        raise NotImplementedError

    def search_memories(self, query: str, **kwargs: Any) -> List[Dict[str, Any]]:  # pragma: no cover
        raise NotImplementedError

    def log_memory(self, key: str, value: Any, namespace: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:  # pragma: no cover
        raise NotImplementedError

    def get_memory(self, key: str) -> Dict[str, Any]:  # pragma: no cover
        raise NotImplementedError


class MemoryLoggerError(Exception):
    """Raised for unsupported or misconfigured memory loggers."""


class InMemoryMemoryLogger(BaseMemoryLogger):
    """In-memory memory logger with Redis-stream-shaped log support.

    Maintains:
      * a flat ``memory_manager:key`` store of memory entries (blob dedup via blob
        id hashing),
      * hset-based per-namespace logs under ``mcaz:log:<namespace>``,
      * a ``mcaz:final_response`` head entry mirroring OrKa's pipeline.
    """

    def __init__(self, redis: Optional[_RedisCompatBase] = None, namespace: str = _DEFAULT_NAMESPACE, enable_stream: bool = True) -> None:
        self.redis = redis or _RedisCompatBase()
        self.namespace = namespace
        self.enable_stream = enable_stream
        self._last_id: Dict[str, int] = {}
        self.snapshot_path: Optional[str] = None

    # -- low-level key store -------------------------------------------------
    def set(self, key: str, value: Any, **kwargs: Any) -> str:
        self.redis.set(key, value)
        return key

    def get(self, key: str) -> Any:
        return self.redis.get(key)

    def hget(self, key: str, field: str) -> Any:
        return self.redis.hget(key, field)

    def hgetall(self, key: str) -> Dict[str, Any]:
        return self.redis.hgetall(key)

    def hkeys(self, key: str) -> List[str]:
        return list(self.redis.hgetall(key).keys())

    def scan(self, pattern: str = "*") -> Iterable[str]:
        return self.redis.scan_iter(match=pattern)

    def sadd(self, key: str, *members: Any) -> int:
        return self.redis.sadd(key, *members)

    def smembers(self, key: str) -> set:
        return self.redis.smembers(key)

    def hdel(self, key: str, field: str) -> int:
        return self.redis.hdel(key, field)

    def delete(self, key: str) -> int:
        return self.redis.delete(key)

    # -- stream-shaped log ----------------------------------------------------
    def log(self, namespace: str, data: Dict[str, Any]) -> str:
        """Append a blob-dedup entry to a stream and return a log id."""
        if not self.enable_stream:
            return "0"
        nxt = self._last_id.get(namespace, 0) + 1
        self._last_id[namespace] = nxt
        msg_id = f"{nxt:016d}-0"
        # blob dedup: store under a content-stable blob id, keep pointer in stream
        blob_id = _blob_id(data)
        self.redis.hset(f"blob:{namespace}", blob_id, _json(data))
        stream_key = f"{namespace}"
        entry = {"id": msg_id, "blob_id": blob_id, "data": data, "list": stream_key}
        self.redis.hset(stream_key, msg_id, _json(entry))
        return msg_id

    def xrange(self, namespace: str, start: str = "-", end: str = "+") -> List[Dict[str, Any]]:
        entries = self.redis.hgetall(namespace)
        ids = sorted(entries.keys())
        result = []
        for mid in ids:
            if _id_gte(mid, start) and _id_lte(mid, end):
                try:
                    entry = json.loads(entries[mid])
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                result.append({"id": mid, "blob_id": entry.get("blob_id"), "data": entry.get("data", {})})
        return result

    def xlen(self, namespace: str) -> int:
        return len(self.redis.hgetall(namespace))

    xadd = log

    # -- memory manager ---------------------------------------------------------
    def set_memory(self, key: str, value: Any) -> None:
        self.redis.set(f"memory_manager:{key}", value)

    def get_memory_by_key(self, key: str) -> Any:
        return self.redis.get(f"memory_manager:{key}")

    def get_memories(self) -> List[Any]:
        prefix = "memory_manager:"
        return [self.redis.get(i) for i in self.redis.keys(pattern=f"{prefix}*")]

    def search_memories(self, query: str, k: int = 5, threshold: float = 0.15, **_: Any) -> List[Dict[str, Any]]:
        """Deterministic keyword search over stored memory values.

        Relevance is query-term *coverage* (fraction of query terms present in a
        stored document), scored additionally by term frequency. Only documents
        with at least one matching term are returned.
        """
        q_terms = Counter(_WORD_RE.findall(query.lower()))
        if not q_terms:
            return []
        total_q = sum(q_terms.values())
        n_docs = max(1, len(self.redis.keys(pattern="memory_manager:*")))
        scored: List[Dict[str, Any]] = []
        for key in sorted(self.redis.keys(pattern="memory_manager:*")):
            raw = self.redis.get(key)
            key_label = key.split(":", 1)[-1] if ":" in key else key
            text = _to_text(raw)
            words = _WORD_RE.findall((key_label + " " + text).lower())
            if not words:
                continue
            counts = Counter(words)
            matched = sum(cnt for term, qcnt in q_terms.items()
                          if (cnt := counts.get(term)))
            coverage = matched / total_q
            if coverage <= 0:
                continue
            idf = math.log1p(n_docs) / max(1.0, math.log1p(len(words)))
            tf = sum(qcnt * counts.get(term, 0) for term, qcnt in q_terms.items()) / len(words)
            if coverage >= threshold:
                scored.append({"key": key, "value": raw,
                               "relevance": round(coverage, 4),
                               "score": round(tf * idf, 4)})
        scored.sort(key=lambda r: (r["relevance"], r["score"]), reverse=True)
        return scored[:k]

    def log_memory(self, key: str, value: Any, namespace: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        ns = namespace or self.namespace
        self.redis.set(f"memory_manager:{key}", value)
        entry = {
            "key": key,
            "value": value,
            "namespace": ns,
            "timestamp": now_iso(),
            "metadata": metadata or {},
        }
        self.log(f"mcaz:log:{ns}", entry)
        return entry

    def get_memory(self, key: str) -> Dict[str, Any]:
        raw = self.redis.get(f"memory_manager:{key}")
        val: Dict[str, Any] = {"key": key, "value": raw}
        return val

    # -- final response + trace --------------------------------------------------
    def set_final_response(self, response: Any) -> str:
        self.redis.set("mcaz:final_response", response)
        return "mcaz:final_response"

    def get_final_response(self) -> Any:
        return self.redis.get("mcaz:final_response")

    def save_enhanced_trace(self, trace: Dict[str, Any]) -> str:
        key = f"mcaz:trace:{trace.get('trace_id') or trace.get('run_id') or str(uuid.uuid4())[:8]}"
        self.redis.set(key, trace)
        return key

    def get_trace(self, key: str) -> Any:
        return self.redis.get(key)

    def close(self) -> None:
        if self.snapshot_path:
            self.export_snapshot(self.snapshot_path)
        logger.debug("InMemoryMemoryLogger closed (host=%s)", self.redis.host)

    def export_snapshot(self, path: str) -> str:
        payload = {k: self.redis._data.get(k) for k in sorted(self.redis._data.keys())}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)
        self.snapshot_path = path
        return path


def _id_gte(mid: str, bound: str) -> bool:
    return bound in ("-", "") or mid >= bound


def _id_lte(mid: str, bound: str) -> bool:
    return bound in ("+", "") or mid <= bound


def _blob_id(data: Dict[str, Any]) -> str:
    import hashlib

    return hashlib.sha1(_json(data).encode("utf-8")).hexdigest()


def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str, separators=(",", ":"))


def _to_text(raw: Any) -> str:
    if isinstance(raw, dict):
        for f in ("response", "result", "text", "value"):
            if raw.get(f):
                return str(raw[f])
        return " ".join(str(v) for v in raw.values())
    if isinstance(raw, (list, tuple)):
        return " ".join(_to_text(x) for x in raw)
    return str(raw or "")


def create_memory_logger(backend: str = "memory", **kwargs: Any) -> BaseMemoryLogger:
    """Factory matching OrKa's create_memory_logger; only the stdlib backend exists."""
    backend = (backend or "memory").lower()
    if backend in ("memory", "inmemory", "simple", "none"):
        return InMemoryMemoryLogger(**kwargs)
    raise MemoryLoggerError(
        f"unsupported memory backend {backend!r}: mem20orcaz ships 'memory' only "
        "(Redis/RedisStack backends are intentionally not ported)"
    )