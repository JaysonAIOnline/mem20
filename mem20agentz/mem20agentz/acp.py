"""ACP — peer-agent communication bridge (sub-phase 2.6).

`AcpServer` is a small HTTP JSON-RPC endpoint for external agents: POST
/acp with a `acp/message` request runs the mem20 agent and returns the
reply, persisting the exchange under `acp:<peer>` so peer conversations
resume exactly like bridge chats. A shared token (MEM20AGENTZ_ACP_TOKEN)
is honored when set; without one the endpoint binds to 127.0.0.1 only.
"""

from __future__ import annotations

import http.server
import json
import os
import threading
import time
from typing import Optional

from . import __version__


def _prefix() -> str:
    return "acp:"


def _safe_peer(raw: str) -> bool:
    return bool(raw) and len(raw) <= 64 and all(
        c.isalnum() or c in "-_." for c in raw)


class AcpError(RuntimeError):
    pass


class _Handler(http.server.BaseHTTPRequestHandler):
    server_version = "mem20agentz-acp"

    def _json(self, obj: dict, status: int = 200) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        server: "AcpServer" = self.server.server_side  # type: ignore[attr-defined,assignment]
        if self.path.rstrip("/") != "/acp":
            self._json({"ok": False, "error": "unknown route"}, 404)
            return
        if server.requires_token():
            got = self.headers.get("X-ACP-Token", "")
            if not server.check_token(got):
                self._json({"ok": False, "error": "token required"}, 401)
                return
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            envelope = json.loads(raw.decode("utf-8"))
        except ValueError as exc:
            self._json({"ok": False, "error": f"bad json: {exc}"}, 400)
            return
        out = server.dispatch(envelope)
        self._json(out, 200 if out.get("ok") else 400)

    def log_message(self, *args):  # quiet
        return


class AcpServer:
    def __init__(self, backend=None, agent_factory=None,
                 root: Optional[object] = None,
                 secrets: Optional[dict] = None) -> None:
        self.backend = backend
        self.agent_factory = agent_factory
        self.root = root
        self.secrets = secrets or {}
        self.served_url = ""
        self._httpd = None
        self._thread = None

    # ------------------------------------------------------------- tokens
    def token(self) -> str:
        return (self.secrets.get("acp_token")
                or os.environ.get("MEM20AGENTZ_ACP_TOKEN") or "")

    def requires_token(self) -> bool:
        return bool(self.token())

    def check_token(self, candidate: str) -> bool:
        return bool(candidate) and candidate == self.token()

    # ---------------------------------------------------------- dispatch
    def dispatch(self, envelope: dict) -> dict:
        params = envelope.get("params") or {}
        if envelope.get("method") == "acp/message":
            peer = str(params.get("peer") or "unknown")
            text = str(params.get("text") or "").strip()
            if not _safe_peer(peer):
                return {"ok": False, "error": "peer must be [A-Za-z0-9._-]"}
            if not text:
                return {"ok": False, "error": "text required"}
            try:
                reply = self._run(peer, text)
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": str(exc)}
            return {"ok": True, "reply": reply, "peer": peer,
                    "session_id": "acp:" + peer}
        if envelope.get("method") in ("acp/hello", "ping"):
            return {"ok": True, "service": "mem20agentz-acp",
                    "version": __version__}
        return {"ok": False, "error":
                f"unknown method {envelope.get('method')}"}

    def _run(self, peer: str, text: str) -> str:
        factory = self.agent_factory or build_acp_factory(self.backend)
        core = factory(peer)
        result = core.run(text)
        reply = result.text or "[acp] no reply produced"
        if result.blocked:
            reply = "[acp] run blocked by approvals"
        self._persist(peer, text, reply)
        return reply

    def _persist(self, peer: str, text: str, reply: str) -> None:
        if self.backend is None:
            return
        try:
            self.backend.session_append("gateway", _prefix() + peer,
                                        "user", text)
            self.backend.session_append("gateway", _prefix() + peer,
                                        "assistant", reply)
        except Exception as exc:  # noqa: BLE001
            import sys
            print(f"[acp] ledger write failed: {exc}", file=sys.stderr)

    # -------------------------------------------------------------- serve
    def serve(self, port: int = 0, host: str = "127.0.0.1") -> str:
        self._httpd = http.server.ThreadingHTTPServer((host, port), _Handler)
        self._httpd.server_side = self  # type: ignore[attr-defined]
        actual = self._httpd.server_address[1]
        self.served_url = f"http://{host}:{actual}"
        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                        daemon=True)
        self._thread.start()
        return self.served_url

    def serve_forever(self, port: int = 0, host: str = "127.0.0.1") -> None:
        self.serve(port=port, host=host)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None


def build_acp_factory(backend=None, profile="mem20", model=None):
    """Callable(peer) -> AgentCore resuming the acp:<peer> transcript."""
    from .gateway import build_agent_factory
    return build_agent_factory(backend=backend, profile=profile, model=model,
                               incarnation="acp", session_prefix=_prefix())