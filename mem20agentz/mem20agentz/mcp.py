"""MCP: a clean JSON-RPC Model Context Protocol client and server (2.6).

The server exposes mem20 procedural skills as `tools/*` capabilities over
HTTP JSON-RPC (initialize, tools/list, tools/call). The client talks to any
MCP HTTP or streamable-HTTP endpoint that speaks the same envelope. Both
sides are hermetic-testable: the client is driven against the real server
over loopback HTTP in the test suite.
"""

from __future__ import annotations

import http.server
import json
import threading
import time
from typing import Optional

import httpx

from . import __version__

PROTOCOL_VERSION = "2024-11-05"
JSONRPC = "2.0"


class McpError(RuntimeError):
    """Raised by the client when a server returns a JSON-RPC error."""


def _envelope(mid: int, method: str, params: Optional[dict] = None) -> dict:
    body = {"jsonrpc": JSONRPC, "id": mid, "method": method}
    if params is not None:
        body["params"] = params
    return body


def _result(mid, result) -> dict:
    return {"jsonrpc": JSONRPC, "id": mid, "result": result}


def _rpc_error(mid, code: int, message: str) -> dict:
    return {"jsonrpc": JSONRPC, "id": mid,
            "error": {"code": code, "message": message}}


# ------------------------------------------------------------------ server
class McpServer:
    """HTTP JSON-RPC server exposing procedural skills as MCP tools."""

    def __init__(self, backend=None, root: Optional[object] = None) -> None:
        self.backend = backend
        self.root = root
        self.served_url = ""
        self._httpd = None
        self._thread = None

    # ------------------------------------------------------------- methods
    def initialize(self, params: Optional[dict]) -> dict:
        return {"protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "mem20agentz",
                               "version": __version__}}

    @staticmethod
    def _tool_schema(skill: dict) -> dict:
        return {
            "name": str(skill.get("name") or skill.get("skill") or "skill"),
            "description": str(skill.get("description") or "")[:300],
            "inputSchema": {"type": "object",
                            "properties": {"arg": {"type": "string"}}},
        }

    def list_tools(self) -> list[dict]:
        if self.backend is None:
            return []
        try:
            skills = self.backend.procedural_list(category=None) or []
        except Exception:  # noqa: BLE001
            return []
        return [self._tool_schema(s) for s in skills]

    def call_tool(self, name: str, args: Optional[dict] = None) -> str:
        if self.backend is None:
            raise McpError("server has no backend (sealed)")
        args = args or {}
        context = {"arg": args.get("arg", ""), "raw": json.dumps(args)[:400]}
        try:
            result = self.backend.procedural_execute(name, context)
        except Exception as exc:  # noqa: BLE001
            raise McpError(f"tool '{name}' failed: {exc}") from exc
        if result is None:
            return ""
        if isinstance(result, dict):
            return str(result.get("output") or
                       result.get("ok") or json.dumps(result))[:4000]
        return str(result)[:4000]

    # --------------------------------------------------------- dispatch
    def dispatch(self, envelope: dict) -> dict:
        if not isinstance(envelope, dict) or envelope.get("jsonrpc") != JSONRPC:
            return _rpc_error(None, -32700, "parse error / not jsonrpc 2.0")
        mid = envelope.get("id")
        method = envelope.get("method")
        params = envelope.get("params") or {}
        try:
            if method == "initialize":
                return _result(mid, self.initialize(params))
            if method in ("tools/list", "tools/list_changed"):
                return _result(mid, {"tools": self.list_tools()})
            if method == "tools/call":
                name = str((params or {}).get("name") or "")
                if not name:
                    return _rpc_error(mid, -32602, "name required")
                args = params.get("arguments")
                if args is not None and not isinstance(args, dict):
                    return _rpc_error(mid, -32602, "arguments must be object")
                return _result(
                    mid, {"content": [{"type": "text",
                                       "text": self.call_tool(name, args)}]})
            if method in ("ping", "notifications/initialized"):
                return _result(mid, {})
            return _rpc_error(mid, -32601, f"method not found: {method}")
        except McpError as exc:
            return _rpc_error(mid, -32602, str(exc))
        except Exception as exc:  # noqa: BLE001
            return _rpc_error(mid, -32603, f"internal error: {exc}")

    # -------------------------------------------------------------- serve
    def serve(self, port: int = 0, host: str = "127.0.0.1") -> str:
        self._httpd = http.server.ThreadingHTTPServer((host, port),
                                                      _McpHttpHandler)
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


class _McpHttpHandler(http.server.BaseHTTPRequestHandler):
    server_version = "mem20agentz-mcp"

    def do_POST(self):  # noqa: N802
        server: "McpServer" = self.server.server_side  # type: ignore[attr-defined,assignment]
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            envelope = json.loads(raw.decode("utf-8"))
            out = server.dispatch(envelope)
        except ValueError:
            out = _rpc_error(None, -32700, "parse error")
        body = json.dumps(out).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # quiet
        return


# ------------------------------------------------------------------ client
class McpClient:
    """Minimal MCP client (initialize, tools/list, tools/call) over HTTP."""

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)
        self._mid = 0

    def _request(self, method: str, params: Optional[dict] = None) -> dict:
        self._mid += 1
        payload = _envelope(self._mid, method, params)
        try:
            resp = self._client.post(self.base_url + "/mcp", json=payload)
            resp.raise_for_status()
            body = resp.json()
        except httpx.HTTPError as exc:
            raise McpError(f"transport error: {exc}") from exc
        except ValueError as exc:
            raise McpError("server returned non-json response") from exc
        if not isinstance(body, dict):
            raise McpError("server returned non-object response")
        if "error" in body and body["error"] is not None:
            err = body["error"]
            raise McpError(f"rpc error {err.get('code')}: "
                           f"{err.get('message')}")
        return body.get("result") or {}

    def initialize(self) -> dict:
        return self._request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "clientInfo": {"name": "mem20agentz-client",
                           "version": __version__},
            "capabilities": {}})

    def list_tools(self) -> list[dict]:
        result = self._request("tools/list")
        return result.get("tools") or []

    def call_tool(self, name: str, args: Optional[dict] = None) -> str:
        result = self._request("tools/call",
                               {"name": name,
                                "arguments": args or {}})
        content = result.get("content") or []
        return "\n".join(
            str(c.get("text", "")) for c in content if isinstance(c, dict))

    def ping(self) -> bool:
        return bool(self._request("ping"))

    def close(self) -> None:
        self._client.close()