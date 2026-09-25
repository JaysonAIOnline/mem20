"""mem20 agentz auth layer: key ring, rotation pool, key-hiding proxy.

Rules (2.8):
  * KeyRing never returns/prints secret values in reports — presence + source
    only. get() returns the value in-memory for the transport seam.
  * AuthPool rotates numbered keys on 401 so a dead key never bricks a provider.
  * AuthProxy is an OpenAI-compatible HTTP front that hides provider keys from
    clients: the proxy resolves credentials server-side from KeyRing.
"""

from __future__ import annotations

import dataclasses
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

_SECRET_PREFIX = "secret:"


def _norm(name: str) -> str:
    return name.strip().upper().replace("-", "_").replace(".", "_")


class KeyRing:
    """Resolve a provider API key without ever exposing it in reports.

    Order per provider `name`:
      1. env  MEM20AGENTZ_<NAME>_API_KEY
      2. explicit api_key value passed by caller (config; "secret:<vault>"
         refs resolved against the vault)
      3. env provider convention (e.g. NVIDIA_API_KEY for name "nvidia")
      4. vault keys: <name>_api_key and api:<name>
    """

    def __init__(self, secrets: Any = None, env: Optional[dict] = None) -> None:
        self.secrets = secrets
        self._env = dict(env) if env is not None else dict(os.environ)

    def get(self, name: str, api_key: Optional[str] = None
            ) -> tuple[Optional[str], Optional[str]]:
        n = _norm(name)
        env_key = self._env.get(f"MEM20AGENTZ_{n}_API_KEY")
        if env_key:
            return env_key, f"env:MEM20AGENTZ_{n}_API_KEY"
        if isinstance(api_key, str) and api_key:
            if api_key.startswith(_SECRET_PREFIX):
                vault_name = api_key[len(_SECRET_PREFIX):].strip()
                val = self._vault("get", vault_name)
                if val:
                    return val, f"vault:{vault_name}"
                return None, f"vault:{vault_name} (missing)"
            return api_key, "config"
        known_env = self._known_env(name)
        if known_env and known_env in self._env:
            return self._env[known_env], f"env:{known_env}"
        for vault_name in (f"{name.lower()}_api_key", f"api:{name.lower()}"):
            val = self._vault("get", vault_name)
            if val:
                return val, f"vault:{vault_name}"
        return None, None

    def rotate(self, name: str) -> Optional[str]:
        """Rotate to the next numbered key; returns the new source or None."""
        n = _norm(name)
        for suffix in ("_API_KEY_2", "_API_KEY_3", "_API_KEY_4"):
            env_key = self._env.get(f"MEM20AGENTZ_{n}{suffix}")
            if env_key:
                src = f"env:MEM20AGENTZ_{n}{suffix}"
                self._env[f"MEM20AGENTZ_{n}_API_KEY"] = env_key
                return src
        return None

    def status(self, names: list[str], api_keys: Optional[dict] = None
               ) -> list[dict]:
        rows = []
        for name in names:
            val, source = self.get(name, (api_keys or {}).get(name))
            rows.append({"name": name, "present": bool(val), "source": source})
        return rows

    def redact(self, text: str) -> str:
        if self.secrets is not None:
            return self.secrets.redact(text)
        for name, _ in [("mem20agentz", None)]:
            pass
        return text

    def _known_env(self, name: str) -> Optional[str]:
        from .llm import KNOWN_PROVIDERS
        entry = KNOWN_PROVIDERS.get(name.lower())
        return (entry or {}).get("key_env")

    def _vault(self, op: str, name: str):
        if self.secrets is None:
            return None
        try:
            return getattr(self.secrets, op)(name)
        except Exception:  # noqa: BLE001
            return None


class AuthPool:
    """Multiple keys per provider with 401-triggered rotation (pool + health)."""

    def __init__(self, keys: list[str], provider: str = "") -> None:
        self.provider = provider
        self.keys = keys
        self._index = 0
        self._lock = threading.Lock()
        self.rotations = 0

    @classmethod
    def from_env(cls, name: str, env: Optional[dict] = None) -> "AuthPool":
        e = dict(env) if env is not None else dict(os.environ)
        n = _norm(name)
        prefix = f"MEM20AGENTZ_{n}_API_KEY"
        keys: list[str] = []
        for k, v in e.items():
            if not k.startswith(prefix):
                continue
            suffix = k[len(prefix):]
            if suffix == "" or suffix in ("_2", "_3", "_4", "_5"):
                keys.append(v)
        return cls([k for k in keys if k], provider=name)

    def next(self) -> Optional[str]:
        with self._lock:
            if not self.keys:
                return None
            key = self.keys[self._index % len(self.keys)]
            self._index = (self._index + 1) % len(self.keys)
            return key

    def mark_failed(self) -> int:
        with self._lock:
            self.rotations += 1
        return self.rotations


@dataclasses.dataclass
class AuthProxyConfig:
    host: str = "127.0.0.1"
    port: int = 18784
    token: Optional[str] = None


class AuthProxy:
    """OpenAI-compatible /v1/chat/completions front that keeps keys server-side.

    Client sends NO provider key. Optional X-Auth-Proxy-Token gates access.
    """

    def __init__(self, router: Any, keyring: Optional[KeyRing] = None,
                 config: Optional[AuthProxyConfig] = None,
                 token: Optional[str] = None) -> None:
        self.router = router
        self.keyring = keyring
        self.config = config or AuthProxyConfig()
        if token:
            self.config.token = token
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def serve(self) -> str:
        handler = self._make_handler()
        self._server = ThreadingHTTPServer((self.config.host, self.config.port),
                                           handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        daemon=True)
        self._thread.start()
        return f"http://{self.config.host}:{self._server.server_address[1]}"

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def _json(self, code: int, payload: dict) -> tuple[bytes, int]:
        body = json.dumps(payload).encode("utf-8")
        return body, code

    def _handle_completions(self, req: BaseHTTPRequestHandler, body: dict
                            ) -> tuple[bytes, int]:
        messages = body.get("messages")
        if not isinstance(messages, list) or not messages:
            return self._json(400, {"error": "messages required"})
        try:
            result = self.router.complete(
                messages, model=body.get("model"),
                temperature=float(body.get("temperature", 0.7)),
                max_tokens=int(body.get("max_tokens", 1200)))
        except Exception as exc:  # noqa: BLE001
            return self._json(502, {"error": str(exc)})
        created = int(__import__("time").time())
        payload = {"id": "chatcmpl-mem20agentz", "object": "chat.completion",
                   "created": created, "model": result.get("model"),
                   "choices": [{"index": 0,
                                "message": {"role": "assistant",
                                            "content": result.get("text")},
                                "finish_reason": "stop"}]}
        return self._json(200, payload)

    def _handle_models(self) -> tuple[bytes, int]:
        models = []
        for p in self.router.providers:
            models.append({"id": p.model, "owned_by": p.name})
        return self._json(200, {"object": "list", "data": models})

    def _make_handler(self):
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            def _check(self) -> bool:
                if proxy.config.token:
                    got = self.headers.get("X-Auth-Proxy-Token", "")
                    if got != proxy.config.token:
                        self._write_json(403, {"error": "token rejected"})
                        return False
                return True

            def _write_json(self, code: int, payload: dict) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):  # noqa: N802
                if not self._check():
                    return
                if self.path.rstrip("/") == "/v1/models":
                    body, code = proxy._handle_models()
                else:
                    body, code = proxy._json(
                        404, {"error": f"unknown path {self.path}"})
                self._write_json(code, json.loads(body.decode("utf-8")))

            def do_POST(self):  # noqa: N802
                if not self._check():
                    return
                if self.path.rstrip("/") != "/v1/chat/completions":
                    self._write_json(404, {"error": "unknown path"})
                    return
                try:
                    raw = self.rfile.read(
                        int(self.headers.get("Content-Length", "0")) or 0)
                    body = json.loads(raw.decode("utf-8"))
                except (ValueError, TypeError):
                    self._write_json(400, {"error": "invalid json body"})
                    return
                payload, code = proxy._handle_completions(self, body)
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):  # noqa: D102
                pass

        return Handler