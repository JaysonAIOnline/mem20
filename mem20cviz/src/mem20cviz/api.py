"""cv.infer HTTP server (localhost). Routes:
  GET  /health            -> capability + engine status
  GET  /.well-known/card  -> capability card
  POST /infer             -> JSON request {mode, image_path|frame_blob_b64, options}
"""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from . import braid_hook
from .descriptor import CAPABILITY_ID, CAPABILITY_NAME, CAPABILITY_VERSION, descriptor
from .service import InferenceError, run_inference

DEFAULT_PORT = 8783


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence default noise
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
            self._send(200, {
                "ok": True,
                "capability": CAPABILITY_ID,
                "name": CAPABILITY_NAME,
                "version": CAPABILITY_VERSION,
                "engines": ["classical"],
                "braid": braid_hook.braid_ok(),
            })
        elif self.path == "/.well-known/card":
            self._send(200, descriptor())
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/infer":
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception as e:  # noqa: BLE001
            self._send(400, {"error": f"invalid JSON: {e}"})
            return
        try:
            start = __import__("time").monotonic()
            result = run_inference(payload)
            result.setdefault("metadata", {})["server_ms"] = int(
                (__import__("time").monotonic() - start) * 1000)
            self._send(200, result)
        except InferenceError as e:
            self._send(400, {"error": str(e)})
        except PermissionError as e:
            self._send(503, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            self._send(500, {"error": str(e)})


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    port = DEFAULT_PORT
    if argv and argv[0] == "--port":
        port = int(argv[1])
    srv = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    print(f"mem20cviz cv.infer serving on {port}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())