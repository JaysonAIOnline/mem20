from __future__ import annotations

import argparse
import json
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .service import UCGService


AGENT_CARD = {
    "name": "mem20ucgz",
    "description": "Universal Capability Graph (RM-001) — register capabilities, query providers, compose plans.",
    "version": "1.0.0",
    "capabilities": ["capability-graph", "capability-register", "capability-query", "capability-compose"],
    "endpoints": {"message": "https://mem20.local/a2a"},
}


class Handler(BaseHTTPRequestHandler):
    service: UCGService

    def _json_body(self) -> dict:
        size = int(self.headers.get("Content-Length", "0"))
        if size > 1_000_000:
            raise ValueError("request too large")
        return json.loads(self.rfile.read(size) or b"{}")

    def _send(self, status: int, payload, content_type: str = "application/json") -> None:
        if content_type == "application/json":
            data = json.dumps(payload, sort_keys=True, default=str).encode()
        else:
            data = payload.encode() if isinstance(payload, str) else payload
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:
        try:
            url = urlparse(self.path)
            if url.path in ("/.well-known/agent-card.json", "/.well-known/agent.json"):
                return self._send(200, AGENT_CARD)
            if url.path == "/health":
                return self._send(200, {"ok": True})
            if url.path == "/graph":
                return self._send(200, self.service.graph.graph())
            if url.path.startswith("/capabilities/"):
                cap_id = url.path.split("/", 2)[2]
                cap = self.service.graph.get(cap_id)
                return self._send(200 if cap else 404, cap.to_dict() if cap else {"error": "not found"})
            if url.path == "/events":
                qs = parse_qs(url.query)
                since = int(qs.get("since", ["0"])[0])
                return self._send(200, self.service.store.events_since(since))
            if url.path == "/metrics":
                return self._send(200, self.service.metrics.prometheus(), "text/plain; version=0.0.4")
            return self._send(404, {"error": "not found"})
        except Exception as e:
            return self._send(400, {"error": f"{type(e).__name__}: {e}"})

    def _handle_a2a_send(self, body: dict) -> dict:
        """A2A message/send + SendMessage: 'who provides X?' -> ranked capability list."""
        msg = (body.get("message") or body.get("params", {}).get("message") or {})
        text = ""
        for part in (msg.get("parts") or []) or []:
            if isinstance(part, dict) and part.get("text"):
                text += str(part.get("text")) + " "
        text = text.strip() or "list"
        results = self.service.query({"text": text})
        if not results:
            summary = f"No capabilities match '{text}'."
        else:
            ranked = sorted(results, key=lambda c: (c["latency_ms"], c["cost_units"]))
            lines = [f"- {c['id']} (provider={c['provider']}, latency={c['latency_ms']}ms, cost={c['cost_units']})" for c in ranked]
            summary = f"{len(ranked)} capabilities match '{text}':\n" + "\n".join(lines)
        return {
            "jsonrpc": "2.0",
            "id": body.get("id", f"mem2a-{int(time.time())}"),
            "result": {
                "task": {
                    "status": {"state": "TASK_STATE_COMPLETED"},
                    "artifacts": [{"parts": [{"kind": "text", "text": summary}]}],
                }
            },
        }

    def do_POST(self) -> None:
        try:
            body = self._json_body()
            if self.path in ("/message/send", "/"):
                return self._send(200, self._handle_a2a_send(body))
            if self.path == "/a2a":
                return self._send(200, self._handle_a2a_send(body))
            if self.path == "/capabilities":
                return self._send(201, self.service.register(body))
            if self.path == "/query":
                return self._send(200, self.service.query(body))
            if self.path == "/compose":
                return self._send(200, self.service.compose(body))
            if self.path == "/feedback":
                self.service.store.add_feedback(body["plan_id"], float(body["outcome"]), body.get("correction"), body.get("metadata"))
                return self._send(201, {"ok": True})
            return self._send(404, {"error": "not found"})
        except Exception as e:
            return self._send(400, {"error": f"{type(e).__name__}: {e}"})

    def do_PUT(self) -> None:
        try:
            if not self.path.startswith("/capabilities/"):
                return self._send(404, {"error": "not found"})
            cap_id = self.path.split("/", 2)[2]
            body = self._json_body()
            body["id"] = cap_id
            cap = self.service.graph.update(__import__("mem20ucgz.models", fromlist=["Capability"]).Capability.from_dict(body))
            return self._send(200, cap.to_dict())
        except Exception as e:
            return self._send(400, {"error": f"{type(e).__name__}: {e}"})

    def do_DELETE(self) -> None:
        if not self.path.startswith("/capabilities/"):
            return self._send(404, {"error": "not found"})
        cap_id = self.path.split("/", 2)[2]
        ok = self.service.graph.delete(cap_id)
        return self._send(200 if ok else 404, {"deleted": ok})


def serve(host: str, port: int, db: str) -> None:
    service = UCGService(db)
    Handler.service = service
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"RM-001 Universal Capability Graph listening on http://{host}:{port}")
    server.serve_forever()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8781)
    p.add_argument("--db", default="ucg.sqlite3")
    a = p.parse_args()
    serve(a.host, a.port, a.db)


if __name__ == "__main__":
    main()
