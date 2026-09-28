"""ucg_client — query the Universal Capability Graph from sense-organs.

Two transports: direct (in-process UCGService) and HTTP (the live UCG server
on 8781). Both return plain capability dicts so the rest of mem20sensez is
transport-agnostic and hermetically testable.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Any

DEFAULT_UCG_URL = "http://127.0.0.1:8781"

STOPWORDS = {
    "who", "what", "which", "provides", "provide", "providing", "can", "any",
    "the", "a", "an", "i", "have", "need", "list", "me", "for", "of", "to",
    "on", "at", "is", "are", "and", "or", "with", "from", "by", "in",
}


def tokenize(text: str) -> list[str]:
    cleaned = text.lower().replace("-", " ").replace("/", " ").replace(".", " ").replace("_", " ")
    tokens = [t.strip("?.!,;:'\"()") for t in cleaned.split()]
    return [t for t in tokens if t and t not in STOPWORDS]


class UcgClient:
    """Query capabilities from the UCG (direct or HTTP)."""

    def __init__(self, service: Any = None, base_url: str = DEFAULT_UCG_URL) -> None:
        self._service = service
        self.base_url = base_url.rstrip("/")

    def query(self, text: str, active_only: bool = True) -> list[dict[str, Any]]:
        if self._service is not None:
            body = {"text": text, "active_only": active_only}
            return self._service.query(body)
        req = urllib.request.Request(
            f"{self.base_url}/query",
            data=json.dumps({"text": text, "active_only": active_only}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    def all(self, active_only: bool = True) -> list[dict[str, Any]]:
        if self._service is not None:
            return [self._normalize(c) for c in self._service.store.all_capabilities()
                    if (not active_only or self._state(c) == "active")]
        req = urllib.request.Request(
            f"{self.base_url}/query",
            data=json.dumps({"text": "", "active_only": active_only}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    @staticmethod
    def _state(cap: Any) -> str:
        val = getattr(cap, "state", None)
        if isinstance(val, str):
            return val
        return getattr(val, "value", "active")

    @staticmethod
    def _normalize(cap: Any) -> dict[str, Any]:
        """Accept store objects (state machine enums) or plain dicts."""
        if isinstance(cap, dict):
            return cap
        out: dict[str, Any] = {}
        for name in ("id", "name", "provider", "endpoint", "invocation",
                     "signed", "latency_ms", "cost_units", "energy_units"):
            if hasattr(cap, name):
                out[name] = getattr(cap, name)
        for name in ("inputs", "outputs", "requires", "conflicts", "platforms"):
            if hasattr(cap, name):
                out[name] = list(getattr(cap, name))
        meta = getattr(cap, "metadata", None)
        if isinstance(meta, dict):
            out["metadata"] = meta
        else:
            out["metadata"] = getattr(meta, "__dict__", {}) if meta else {}
        out["state"] = UcgClient._state(cap)
        return out

    def capability(self, capability_id: str) -> dict[str, Any] | None:
        for c in self.all(active_only=False):
            if c["id"] == capability_id:
                return c
        return None