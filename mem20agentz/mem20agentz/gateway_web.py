"""Web gateway + dashboard (sub-phase 2.6).

`WebGateway` is an HTTP surface on top of the mem20 backend: a chat
endpoint (POST /chat) with the same per-chat session resume the bridge
layer uses (transcripts under `web:<chat_id>`), a JSON status + ledger
endpoint (GET /status, GET /ledger), and a server-rendered HTML dashboard
(GET /). It runs on the same ThreadingHTTPServer+server_side pattern as
`webhooks.py`; the CLI `webgateway` and `serve` commands start it.
"""

from __future__ import annotations

import html
import json
import http.server
import secrets
import threading
import time
from typing import Optional

from . import __version__
from .config import config_dir, load_config


def _web_prefix() -> str:
    return "web:"


def _chat_id_safe(raw: str) -> bool:
    return bool(raw) and len(raw) <= 64 and all(
        c.isalnum() or c in "-_." for c in raw)


class _Handler(http.server.BaseHTTPRequestHandler):
    server_version = "mem20agentz-web"

    def _json(self, obj: dict, status: int = 200) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, page: str) -> None:
        body = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802 (http.server API)
        server: "WebGateway" = self.server.server_side  # type: ignore[attr-defined,assignment]
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except ValueError as exc:
            self._json({"ok": False, "error": f"bad json: {exc}"}, 400)
            return
        if self.path.rstrip("/") == "/chat":
            out = server.chat(payload)
            self._json(out, 200 if out.get("ok") else 400)
            return
        self._json({"ok": False, "error": f"unknown route {self.path}"}, 404)

    def do_GET(self):  # noqa: N802
        server: "WebGateway" = self.server.server_side  # type: ignore[attr-defined,assignment]
        route = self.path.split("?", 1)[0]
        if route == "/status":
            self._json(server.status())
            return
        if route == "/ledger":
            k = 20
            try:
                k = int(self.path.split("k=", 1)[1].split("&", 1)[0])
            except (ValueError, IndexError):
                pass
            self._json({"ok": True, "entries": server.ledger_tail(k)})
            return
        if route == "/":
            self._html(server.dashboard())
            return
        self._json({"ok": False, "error": f"unknown route {self.path}"}, 404)

    def log_message(self, *args):  # quiet
        return


class WebGateway:
    """HTTP web gateway: /chat, /status, /ledger, / (dashboard)."""

    def __init__(self, backend=None, root: Optional[object] = None,
                 agent_factory=None) -> None:
        self.backend = backend
        self.root = root
        self.agent_factory = agent_factory
        self.served_url = ""
        self.started_at = time.time()
        self._httpd = None
        self._thread = None

    # ------------------------------------------------------------ chat
    def chat(self, payload: dict) -> dict:
        message = str(payload.get("message") or "").strip()
        if not message:
            return {"ok": False, "error": "message required"}
        chat_id = str(payload.get("chat_id") or
                      "w" + secrets.token_hex(4))
        if not _chat_id_safe(chat_id):
            return {"ok": False, "error": "chat_id must be [A-Za-z0-9._-]"}
        factory = self.agent_factory or build_web_factory(self.backend)
        core = factory(chat_id)
        try:
            result = core.run(message)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        reply = result.text or "[gateway] no reply produced"
        if result.blocked:
            reply = "[gateway] run blocked by approvals"
        self._persist(chat_id, message, reply)
        return {"ok": True, "reply": reply, "chat_id": chat_id}

    def _persist(self, chat_id: str, message: str, reply: str) -> None:
        if self.backend is None:
            return
        try:
            # Ledger format shared with bridge._log: "<in|out>:<chat_id> <text>".
            # gateway._history parses exactly this shape to resume transcripts,
            # so write user/assistant turns the same way or history is lost.
            self.backend.session_append("gateway", _web_prefix() + chat_id,
                                        "system", f"in:{chat_id} {message}")
            self.backend.session_append("gateway", _web_prefix() + chat_id,
                                        "system", f"out:{chat_id} {reply}")
        except Exception as exc:  # noqa: BLE001
            import sys
            print(f"[webgateway] ledger write failed: {exc}", file=sys.stderr)

    # ---------------------------------------------------------- status
    def status(self) -> dict:
        cfg = load_config()
        try:
            from .gateway import Gateway
            configured = Gateway(backend=self.backend).configured_bridges()
        except Exception:  # noqa: BLE001
            configured = []
        return {
            "service": "webgateway",
            "version": __version__,
            "uptime_s": round(time.time() - self.started_at, 1),
            "config": str(cfg.path),
            "bridges": [{"name": n, "state": "unconfigured"}
                        for n in configured],
            "chat_session_prefix": _web_prefix(),
        }

    def ledger_tail(self, k: int = 20) -> list[dict]:
        if self.backend is None:
            return []
        try:
            facts = self.backend.recall(tags=["mem20agentz", "message"],
                                        k=k)
        except Exception as exc:  # noqa: BLE001
            return [{"error": str(exc)}]
        out = []
        for fact in facts:
            content = (fact.get("content") or fact.get("text") or "").strip()
            out.append({"text": content[:300],
                        "ts": fact.get("ts", ""),
                        "tags": fact.get("tags", [])})
        return out

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

    # ----------------------------------------------------------- dashboard
    def dashboard(self) -> str:
        g = self.status()
        cfg = load_config()
        rows = [self._esc(f"{r['name']}  [{r['state']}]") for r in g["bridges"]]
        ledger = self.ledger_tail(20)
        ledger_rows = "".join(
            f"<li>{self._esc(x.get('text', ''))}</li>" for x in ledger)
        cron_rows = ""
        try:
            from .cron import Cron
            cron = Cron(backend=self.backend, root=self.root)
            jobs = cron.list_jobs()
            cron_rows = "".join(
                f"<li>{self._esc(str(j.get('schedule'))) + ' '
                 + self._esc(str(j.get('command') or j.get('prompt')))
                 if isinstance(j, dict) else self._esc(str(j))}</li>"
                for j in jobs)
        except Exception:  # noqa: BLE001
            cron_rows = "<li>(sealed)</li>"
        projects_rows = ""
        try:
            from .projects import Projects
            projects = Projects(backend=self.backend, root=self.root)
            import json as _json
            projects_rows = "".join(
                f"<li>{self._esc(p.get('name', str(p)))}</li>"
                for p in projects.list_projects())
        except Exception:  # noqa: BLE001
            projects_rows = "<li>(sealed)</li>"
        return f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>mem20agentz dashboard</title>
<style>
 body{{font-family:system-ui,sans-serif;margin:2rem;background:#0f1115;color:#e6e6e6}}
 h1{{font-size:1.3rem}} section{{margin:1.5rem 0}}
 h2{{font-size:1rem;color:#9aa4b1;border-bottom:1px solid #262b33;padding-bottom:.25rem}}
 ul{{padding-left:1.2rem}} li{{margin:.15rem 0}}
 code{{background:#1b1f27;padding:.05rem .4rem;border-radius:4px}}
</style></head><body>
<h1>mem20agentz</h1>
<p>service <code>{html.escape(g['service'])}</code> ·
version <code>{html.escape(g['version'])}</code> ·
uptime {g['uptime_s']}s · config <code>{html.escape(g['config'])}</code></p>
<section><h2>gateway bridges</h2><ul>{''.join(f'<li>{r}</li>' for r in rows)}</ul></section>
<section><h2>cron jobs</h2><ul>{cron_rows}</ul></section>
<section><h2>projects</h2><ul>{projects_rows}</ul></section>
<section><h2>recent ledger</h2><ul>{ledger_rows}</ul></section>
</body></html>
"""

    @staticmethod
    def _esc(text: str) -> str:
        return html.escape(str(text))


def build_web_factory(backend=None, profile="mem20", model=None):
    """Callable(chat_id) -> AgentCore resuming the web:<chat_id> transcript."""
    from .gateway import build_agent_factory
    return build_agent_factory(backend=backend, profile=profile, model=model,
                               incarnation="webgateway",
                               session_prefix=_web_prefix())


def default_web_port() -> int:
    try:
        cfg = load_config()
        cfg.get("gateway", {}).get("web", {})
        return int(cfg.get("gateway", {}).get("web", {}).get("port", 18778))
    except Exception:  # noqa: BLE001
        return 18778