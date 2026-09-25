"""A2AClient — delegation = A2A fan-out to the mem20 peer fleet.

Spec-compliant A2A v1.0 client (JSON-RPC over HTTP), matching the mem20
a2a wire contract:
  - discovery:  GET /.well-known/agent-card.json (fallback /.well-known/agent.json)
  - task send:  POST {jsonrpc, id, method:"SendMessage", params:{message:{role,
                parts:[{text,mediaType}], messageId, contextId}}}
  - reply:      unwrap {"task":{...}} / {"message":{...}}, text from
                artifacts -> status.message -> bare text.

Peers come from the mem20 peer config (MEM20CREWZ_A2A_CONFIG override,
or /opt/mem20/mem20crewz/peers.yaml), or an explicit peers table (used by
hermetic tests with a loopback server).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import yaml

DEFAULT_TIMEOUT = 30
PROFILE_ENV = "MEM20_PROFILE"
CONFIG_OVERRIDE_ENV = "MEM20CREWZ_A2A_CONFIG"
DEFAULT_PEERS_FILE = "/opt/mem20/mem20crewz/peers.yaml"
MEMBER_PEERS_FILE = os.path.expanduser("~/.mem20/peers.yaml")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _text_part(text: str) -> dict:
    return {"text": text, "mediaType": "text/plain"}


def _text_message(role: str, text: str, context_id: str) -> dict:
    return {"role": role, "parts": [_text_part(text)],
            "messageId": uuid.uuid4().hex,
            "contextId": context_id}


def _extract_text(payload: Any) -> str:
    """v1.0 + legacy part extraction (mirrors the mem20 a2a wire text extraction)."""
    if not isinstance(payload, dict):
        return str(payload)
    for artifact in payload.get("artifacts", []) or []:
        txt = _extract_parts(artifact.get("parts", []))
        if txt:
            return txt
    status = payload.get("status", {}) or {}
    msg = status.get("message")
    if msg:
        txt = _extract_parts(msg.get("parts", []))
        if txt:
            return txt
    return _extract_parts(payload.get("parts", []))


def _extract_parts(parts: Any) -> str:
    chunks = []
    for part in parts or []:
        if not isinstance(part, dict):
            continue
        t = part.get("text")
        if isinstance(t, str):
            chunks.append(t)
        elif part.get("kind") == "text" and isinstance(part.get("text"), str):
            chunks.append(part["text"])
        elif part.get("kind") == "data" and part.get("data") is not None:
            chunks.append(json.dumps(part["data"], default=str))
        elif part.get("data") is not None:
            chunks.append(json.dumps(part["data"], default=str))
    return "\n".join(chunks).strip()


def _unwrap(result: Any) -> Any:
    if isinstance(result, dict):
        if isinstance(result.get("task"), dict):
            return result["task"]
        if isinstance(result.get("message"), dict):
            return result["message"]
    return result


def _short_state(state: str) -> str:
    return state.replace("TASK_STATE_", "").replace("_", "-").lower() if state else ""


class A2AError(RuntimeError):
    pass


class A2AClient:
    """Synchronous A2A client (call/fan_out) over the mem20 peer config."""

    def __init__(self, peers: Optional[dict] = None,
                 timeout: int = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout
        self._peers = peers if peers is not None else self._load_peers_config()

    # ------------------------------------------------------------ peer config
    @classmethod
    def _config_path(cls) -> Optional[str]:
        override = os.environ.get(CONFIG_OVERRIDE_ENV)
        if override:
            return override
        for candidate in (DEFAULT_PEERS_FILE, MEMBER_PEERS_FILE):
            if os.path.exists(candidate):
                return candidate
        return None

    @classmethod
    def _load_peers_config(cls) -> dict:
        path = cls._config_path()
        if not path:
            return {}
        with open(path, "r", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
        agents = cfg.get("a2a_agents", {}) or {}
        if not isinstance(agents, dict):
            agents = {}
        peers: dict[str, dict] = {}
        for name, entry in agents.items():
            if isinstance(entry, dict) and entry.get("url"):
                peers[str(name)] = {
                    "url": str(entry["url"]),
                    "timeout": int(entry.get("timeout", DEFAULT_TIMEOUT)),
                    "capabilities": list(entry.get("capabilities", []) or []),
                }
        return peers

    def peers(self) -> dict:
        return dict(self._peers)

    def peer_names(self) -> list:
        return sorted(self._peers)

    def matched_peers(self, capability: str = "") -> list[str]:
        if not capability:
            return self.peer_names()
        out = []
        low = capability.lower()
        for name, entry in self._peers.items():
            caps = [str(c).lower() for c in entry.get("capabilities", [])]
            for c in caps:
                # fuzzy prefix / substring match both directions
                if c == low or low.startswith(c) or c.startswith(low) \
                        or low in c or c in low:
                    out.append(name)
                    break
        return sorted(out)

    # ------------------------------------------------------------ discovery
    def discover(self, name: str, timeout: Optional[int] = None) -> dict:
        entry = self._peers.get(name)
        if not entry:
            raise A2AError(f"no peer named '{name}'")
        base = entry["url"].rstrip("/")
        t = timeout or entry.get("timeout") or self.timeout
        card = self._http_get(f"{base}/.well-known/agent-card.json", t)
        if card is None:
            card = self._http_get(f"{base}/.well-known/agent.json", t)
        if card is None:
            raise A2AError(f"discovery failed for '{name}' at {base}")
        return card

    # --------------------------------------------------------------- calls
    def call(self, name: str, message: str, context_id: str = "",
             timeout: Optional[int] = None) -> dict:
        """SendMessage to one peer. Returns {reply, context_id, state, agent}."""
        entry = self._peers.get(name)
        if not entry:
            raise A2AError(f"no peer named '{name}'")
        base = entry["url"].rstrip("/")
        t = timeout or entry.get("timeout") or self.timeout
        envelope = {
            "jsonrpc": "2.0",
            "id": "mem20crewz-" + uuid.uuid4().hex[:12],
            "method": "SendMessage",
            "params": {"message": _text_message(
                "ROLE_USER", message, context_id or ("ctx-" + uuid.uuid4().hex[:12]))},
        }
        resp = self._http_post(base, envelope, t)
        if resp is None:
            raise A2AError(f"no response from '{name}' at {base}")
        if "error" in resp:
            err = resp.get("error", {})
            raise A2AError(f"peer '{name}' error: {err.get('message', err)}")
        payload = _unwrap(resp.get("result", {}))
        reply = _extract_text(payload)
        ctx = context_id
        state = ""
        if isinstance(payload, dict):
            ctx = payload.get("contextId", ctx)
            state = _short_state((payload.get("status") or {}).get("state", ""))
        return {"agent": name, "reply": reply, "context_id": ctx, "state": state}

    def fan_out(self, capability: str = "", message: str = "",
                mode: str = "parallel", max_peers: Optional[int] = None) -> dict:
        """Delegation fan-out. Parallel via asyncio over aiohttp, sequential
        otherwise (no dependency on an event loop already running)."""
        targets = self.matched_peers(capability)
        if max_peers:
            targets = targets[:max_peers]
        results: list[dict] = []
        if not targets:
            return {"matched": [], "results": [], "capability": capability}
        if mode == "parallel":
            results = self._parallel(targets, message)
        else:
            for name in targets:
                results.append(self._one(name, message))
        return {"matched": targets, "results": results, "capability": capability}

    # ------------------------------------------------------------ transport
    @staticmethod
    def _http_post(base: str, body: dict, timeout: int) -> Optional[dict]:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(base, data=data,
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                return json.loads(resp.read().decode("utf-8"))
        except (OSError, urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            return None

    @staticmethod
    def _http_get(url: str, timeout: int) -> Optional[dict]:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
                return json.loads(resp.read().decode("utf-8"))
        except (OSError, urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            return None

    def _one(self, name: str, message: str) -> dict:
        try:
            return self.call(name, message)
        except A2AError as exc:
            return {"agent": name, "reply": "", "context_id": "", "state": "",
                    "error": str(exc)}

    def _parallel(self, targets: list[str], message: str) -> list[dict]:
        async def run():
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async def one(name: str) -> dict:
                    entry = self._peers.get(name, {})
                    base = entry.get("url", "").rstrip("/")
                    t = entry.get("timeout") or self.timeout
                    try:
                        async with session.post(
                                base, json=self._rpc_body(message),
                                timeout=aiohttp.ClientTimeout(total=t)) as resp:
                            raw = await resp.json(content_type=None)
                    except Exception as exc:  # noqa: BLE001
                        return {"agent": name, "reply": "", "state": "",
                                "context_id": "", "error": str(exc)}
                    if "error" in raw:
                        return {"agent": name, "reply": "", "state": "",
                                "context_id": "",
                                "error": raw.get("error", {}).get("message", "rpc error")}
                    payload = _unwrap(raw.get("result", {}))
                    return {"agent": name, "reply": _extract_text(payload),
                            "context_id": context_id_of(payload),
                            "state": state_of(payload)}
                return await asyncio.gather(*(one(n) for n in targets))

        return asyncio.run(run())

    def _rpc_body(self, message: str) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": "mem20crewz-" + uuid.uuid4().hex[:12],
            "method": "SendMessage",
            "params": {"message": _text_message(
                "ROLE_USER", message, "ctx-" + uuid.uuid4().hex[:12])},
        }
        # note: per-peer context_id differs; acceptable for fan-out delegation


def context_id_of(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(payload.get("contextId", ""))
    return ""


def state_of(payload: Any) -> str:
    if isinstance(payload, dict):
        return _short_state((payload.get("status") or {}).get("state", ""))
    return ""