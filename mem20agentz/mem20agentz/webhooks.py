"""Webhooks — small webhook engine (sub-phase 2.4).

Incoming webhooks: a threaded HTTPServer on <config>.webhooks.port accepts
POST /webhook/<route> and dispatches to a registered handler (a callable
installed via `register`). If no handler is registered for the route, the
delivery is logged to ledger (tag `mem20agentz,webhook`) instead of dropped.
Listeners can also repost to a target URL. `WebhookServer` on port 0 is the
hermetic-testable primitive.
"""

from __future__ import annotations

import http.server
import json
import pathlib
import threading
import time
from typing import Callable, Optional

from .config import config_dir

WEBHOOKS_DIR = "webhooks"


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 (http.server API)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        server: "WebhookServer" = self.server.server_side  # type: ignore[attr-defined,assignment]
        route = self.path.split("/webhook/")[-1] if "/webhook/" in self.path \
            else self.path
        status, out = server.dispatch(route, body)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(out).encode("utf-8"))

    def log_message(self, *args):  # quiet
        return


class WebhookServer:
    def __init__(self, hook_registry=None, ledger=None,
                 root: Optional[pathlib.Path] = None) -> None:
        self.hook_registry = hook_registry
        self.ledger = ledger
        self.root = root or config_dir() / WEBHOOKS_DIR
        self.handlers: dict[str, Callable[[bytes], str]] = {}
        self.lock = threading.Lock()
        self.served_url = ""
        self._httpd = None
        self._thread = None

    # ---------------------------------------------------------- registry
    def register(self, route: str, handler) -> None:
        with self.lock:
            self.handlers[route] = handler

    def unregister(self, route: str) -> bool:
        with self.lock:
            return self.handlers.pop(route, None) is not None

    def routes(self) -> list[str]:
        with self.lock:
            return sorted(self.handlers.keys())

    # --------------------------------------------------------- dispatch
    def dispatch(self, route: str, body: bytes) -> tuple[int, dict]:
        with self.lock:
            handler = self.handlers.get(route)
        if handler is not None:
            try:
                out = handler(body)
                return 200, {"ok": True, "route": route, "out": str(out)[:400]}
            except Exception as exc:  # noqa: BLE001
                return 500, {"ok": False, "route": route, "error": str(exc)}
        self._log_undelivered(route, body)
        return 404, {"ok": False, "route": route, "error": "no handler"}

    # -------------------------------------------------------------- serve
    def serve(self, port: int = 0) -> str:
        """Start the listener thread; returns http://host:port."""
        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port),
                                                      _Handler)
        self._httpd.server_side = self  # type: ignore[attr-defined]
        actual = self._httpd.server_address[1]
        self.served_url = f"http://127.0.0.1:{actual}"
        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                        daemon=True)
        self._thread.start()
        return self.served_url

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    # ----------------------------------------------------------- helpers
    def _log_undelivered(self, route: str, body: bytes) -> None:
        if self.ledger is None:
            return
        try:
            self.ledger.session_append(
                "webhooks", "webhooks", "system",
                json.dumps({"route": route,
                            "body": body[:400].decode("utf-8", "replace")}))
        except Exception as exc:  # noqa: BLE001
            import sys
            print(f"[webhooks] ledger write failed: {exc}", file=sys.stderr)