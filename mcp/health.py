"""Operational HTTP endpoint for the mem20 MCP server.

Exposes /health, /ready, and /metrics for liveness/readiness probes and basic
observability. Implemented with the standard-library http.server so it adds no
new dependency, and runs in a daemon thread so it can never block the stdio
JSON-RPC transport.
"""
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional

logger = logging.getLogger("mem20.mcp")


class _HealthHandler(BaseHTTPRequestHandler):
    server_version = "mem20-health/1.0"

    def _json(self, obj: Dict[str, Any], code: int = 200) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split("?")[0].rstrip("/")
        srv = self.server.mem20_server  # type: ignore[attr-defined]
        if path in ("", "/health"):
            self._json({
                "status": "ok",
                "service": "mem20-mcp",
                "uptime_seconds": round(time.time() - srv._start_time, 3),
            })
        elif path == "/ready":
            ready = bool(getattr(srv, "tools", None)) and len(getattr(srv, "tools", {})) > 0
            self._json({"ready": ready, "tools": len(getattr(srv, "tools", {}))})
        elif path == "/metrics":
            self._json(srv.metrics())
        else:
            self._json({"error": "not found", "path": path}, code=404)

    def log_message(self, *args: Any) -> None:  # silence default stderr logging
        return


def start_health_server(server: Any, port: int) -> Optional[ThreadingHTTPServer]:
    """Start the health HTTP server in a background daemon thread.

    Returns the server object, or None if it could not bind (the MCP server
    continues to run regardless). Bind failures are non-fatal so enabling the
    endpoint can never break stdio transport.
    """
    try:
        httpd = ThreadingHTTPServer(("0.0.0.0", port), _HealthHandler)
    except OSError as e:
        logger.warning("health endpoint disabled (could not bind :%s): %s", port, e)
        return None
    httpd.mem20_server = server  # type: ignore[attr-defined]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    logger.info("health endpoint listening on :%s (/health /ready /metrics)", port)
    return httpd
