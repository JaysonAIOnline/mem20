"""sense API HTTP server (localhost:8784). Routes:
  GET  /health            -> service + UCG + braid status
  GET  /.well-known/card  -> capability cards (gap/replan/twin/accel/enroll)
  POST /gap               -> {goal}                        -> gap report
  POST /replan            -> {goal, phases?, journal?}     -> replan plan
  POST /twin              -> {}                            -> workflow digest
  POST /exec              -> {steps?, initial?, journal?}  -> exec plan
  POST /accelerate        -> {action, human, ...}          -> RM-150 human trust bridge
  POST /enroll            -> {action, device, ...}         -> RM-151 device trust bridge
"""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from . import braid_hook
from .descriptor import all_descriptors, TWIN_ID
from .service import SenseError, SenseService

DEFAULT_PORT = 8784


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        return

    def _send(self, code: int, body: Any):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/health", "/healthz"):
            self._send(200, SenseService().health())
        elif self.path == "/.well-known/card":
            self._send(200, {"services": [d["id"] for d in all_descriptors()]})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        route = self.path.split("?")[0]
        if route not in ("/gap", "/replan", "/twin", "/exec", "/accelerate", "/enroll"):
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception as e:
            self._send(400, {"error": f"invalid JSON: {e}"})
            return
        svc = SenseService()
        try:
            if route == "/gap":
                self._send(200, svc.gap(body.get("goal")))
            elif route == "/replan":
                self._send(200, svc.replan(body.get("goal"), body.get("phases"),
                                           bool(body.get("journal", False))))
            elif route == "/twin":
                self._send(200, svc.twin())
            elif route == "/accelerate":
                self._send(200, svc.accelerate(
                    body.get("action", "summary"), body.get("human", "human-1"),
                    public_key=body.get("public_key"), goal=body.get("goal"),
                    signature=body.get("signature"), metric=body.get("metric"),
                    delta=body.get("delta"), name=body.get("name"),
                    max_devices=body.get("max", 3)))
            elif route == "/enroll":
                self._send(200, svc.enroll(
                    body.get("action", "list"), body.get("device", "device-1"),
                    public_key=body.get("public_key"), signature=body.get("signature"),
                    nonce=body.get("nonce"), hostname=body.get("hostname"),
                    platform=body.get("platform"), max_devices=body.get("max", 3)))
            else:  # /exec
                self._send(200, svc.exec(body.get("steps"), body.get("initial"),
                                         bool(body.get("journal", False))))
        except SenseError as e:
            self._send(400, {"error": str(e)})
        except Exception as e:
            self._send(500, {"error": str(e)})


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    port = DEFAULT_PORT
    if argv and argv[0] == "--port":
        port = int(argv[1])
    srv = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    print(f"mem20sensez serving on {port}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())