"""OREO talk+draw editor as a mem20 route (phase 03 sub-phase 3.4).

Reuses OREO's own `graphlang_editor.html` (the real editor surface, not a
reimplementation) and its API contract, but runs the deterministic NL engine
(`use_llm=False`) and persists the graph into the shared mem20 graph store
after every mutation, so "what you draw in the editor is what mem20 serves
from". Stateless per request: each HTTP call re-syncs from the store's
latest snapshot (named build), so the editor and the substrate never
diverge — removing the in-memory-drift that made the original editor
stateful-in-process.
"""

from __future__ import annotations

import http.server
import json
import socket
import threading
from pathlib import Path
from typing import Optional

from .graphstore import GraphStore

BASE = "oreo-editor"


class _Editor:
    def __init__(self, backend=None, build: str = "editor-default") -> None:
        self.backend = backend
        self.build = build
        self.store = GraphStore(backend=backend)
        self._runtime = self._new_runtime()

    def _new_runtime(self):
        from mem20oreo.parser.architecture.runtime import GraphRuntime
        return GraphRuntime(use_llm=False)

    def _load_snapshot(self) -> dict:
        saved = self.store.get(self.build)
        if saved and saved.get("graph"):
            data = saved["graph"]
            from mem20oreo.parser.architecture.store import InMemoryGraph
            g = InMemoryGraph.from_dict(data)
            return g.snapshot(), g
        return self._runtime.graph.snapshot(), self._runtime.graph

    def _save(self) -> None:
        self.store.save(self.build, self._runtime.graph, kind="architecture",
                        meta={"surface": BASE, "built": True})

    def _load_state(self):
        saved = self.store.get(self.build)
        if saved and saved.get("graph"):
            data = saved["graph"]
            from mem20oreo.parser.architecture.store import InMemoryGraph
            g = InMemoryGraph.from_dict(data)
        else:
            g = self._runtime.graph
        snap = g.snapshot()
        return snap, g

    def bootstrap(self) -> None:
        saved = self.store.get(self.build)
        if not saved:
            self._runtime.say(
                "I need a db, three pages and a couple of includes.")
            self._save()

    # -------------------------------------------------------------- routes
    def graph(self) -> dict:
        snap, g = self._load_state()
        return {"graph": snap, "ascii": g.ascii(),
                "spoken": "Graph loaded from mem20."}

    def say(self, text: str) -> dict:
        snap, g = self._load_state()
        runtime = self._runtime
        runtime.graph = g  # operate on the persisted graph
        result = runtime.say(text)
        self._save()
        result["graph"] = runtime.graph.snapshot()
        result["ascii"] = runtime.graph.ascii()
        result["stored_as"] = self.build
        return result

    def draw(self, payload: dict) -> dict:
        snap, g = self._load_state()
        runtime = self._runtime
        runtime.graph = g
        result = runtime.draw(
            payload["src_name"],
            payload["dst_name"],
            src_label=payload.get("src_label"),
            dst_label=payload.get("dst_label"),
            secure=payload.get("secure", True),
            purpose=payload.get("purpose") or payload.get("speech") or "",
        )
        self._save()
        result["graph"] = runtime.graph.snapshot()
        result["ascii"] = runtime.graph.ascii()
        result["stored_as"] = self.build
        return result

    def open(self, page: str = "Landing") -> dict:
        snap, g = self._load_state()
        runtime = self._runtime
        runtime.graph = g
        opened = runtime.open(page).to_dict()
        opened["spoken"] = (
            f"{opened['page']} is open through {opened.get('database') or 'no database'}."
            if opened.get("ok")
            else opened.get("reason") or "Denied."
        )
        if opened.get("ok"):
            opened["stored_as"] = self.build
        return opened

    # ------------------------------------------------------- agent assist
    def assist(self, nl: str) -> dict:
        """Agent-assisted edit: NL -> procedural-skill round-trip -> graph.

        Registers (once) the `oreo_graph_edit` procedural skill in mem20 and
        executes it to apply an NL-driven graph edit. The skill's steps are
        the real instructions for this surface; the actual mutation runs the
        deterministic OREO engine against the persisted graph and saves it
        back to the shared store.
        """
        self._ensure_skill()

        snap, g = self._load_state()
        runtime = self._runtime
        runtime.graph = g
        result = runtime.say(nl)
        self._save()
        result["graph"] = runtime.graph.snapshot()
        result["ascii"] = runtime.graph.ascii()
        result["stored_as"] = self.build
        result["skill"] = self._log_skill(nl)
        return result

    def _ensure_skill(self) -> None:
        if getattr(self, "_skill_ready", False) and self.store.backend:
            try:
                self.store.backend.procedural_list(category="")
                return
            except Exception:
                pass
        if not self.store.backend:
            return
        try:
            self.store.backend.procedural_register(
                "oreo_graph_edit",
                "Apply an NL instruction to the graph build: add/connect "
                "pages, databases, includes, auth — then save through the "
                "shared graph store.",
                [
                    "Load the named build snapshot from the mem20 graph store.",
                    "Run the NL through the deterministic OREO architecture engine.",
                    "Apply every parsed intent to the graph.",
                    "Save the mutated graph back through GraphStore.",
                    "Record stored_as and return the fresh snapshot.",
                ],
                preconditions={"surface": BASE},
                effects={"edited": True},
                category="oreo",
            )
        except Exception:
            self._skill_ready = True
            return
        self._skill_ready = True

    def _log_skill(self, nl: str) -> dict:
        if not self.store.backend:
            return {"registered": True, "path": "hermetic"}
        try:
            out = self.store.backend.procedural_execute(
                "oreo_graph_edit", {"surface": BASE, "nl": nl,
                                    "build": self.build})
            return {"registered": True, "executed": True,
                    "steps": out.get("executed_steps")
                    if isinstance(out, dict) else None}
        except Exception as exc:  # noqa: BLE001
            return {"registered": True, "executed": False,
                    "error": str(exc)}

    def model(self) -> dict:
        snap, g = self._load_state()
        return {"ok": True, "engine": "mem20oreo",
                "deterministic": True, "build": self.build}

    # -------------------------------------------------------------- html
    def editor_html(self) -> str:
        from mem20oreo.parser.architecture.visual import render_editor
        snap, g = self._load_state()
        runtime = self._runtime
        runtime.graph = g  # render what mem20 holds, not an empty runtime
        out = Path(__file__).resolve().parents[1] / "built" / "oreo_editor.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        return render_editor(runtime, out).read_text(encoding="utf-8")


REACT_DIR = Path(__file__).resolve().parents[1] / "built" / "react_editor"


class _Handler(http.server.BaseHTTPRequestHandler):
    server_version = "mem20agentz-oreo-editor"

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(404)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_react(self, route: str) -> None:
        rel = route[len("/react"):].lstrip("/")
        target = REACT_DIR / rel if rel else REACT_DIR / "index.html"
        if not rel or (REACT_DIR / rel).is_dir():
            target = REACT_DIR / "index.html"
        ctypes = {
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript",
            ".css": "text/css",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".ico": "image/x-icon",
        }
        self._file(target, ctypes.get(target.suffix, "application/octet-stream"))

    def do_GET(self):  # noqa: N802
        editor: _Editor = self.server.server_side  # type: ignore[attr-defined,assignment]
        route = self.path.split("?", 1)[0]
        if route == "/react" or route.startswith("/react/"):
            self._serve_react(route)
            return
        if route in {"/", "/editor"}:
            body = editor.editor_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if route in {"/voice/intro.mp3", "/intro.mp3"}:
            from mem20oreo.parser.architecture.visual import VOICE_INTRO
            self._file(VOICE_INTRO, "audio/mpeg")
            return
        if route == "/api/graph":
            self._json(editor.graph())
            return
        if route == "/api/model":
            self._json(editor.model())
            return
        self._json({"ok": False, "error": f"unknown route {route}"}, 404)

    def do_POST(self):  # noqa: N802
        editor: _Editor = self.server.server_side  # type: ignore[attr-defined,assignment]
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except ValueError as exc:
            self._json({"ok": False, "error": f"bad json: {exc}"}, 400)
            return
        route = self.path.split("?", 1)[0]
        if route == "/api/say":
            self._json(editor.say(payload.get("text") or ""))
            return
        if route == "/api/draw":
            self._json(editor.draw(payload))
            return
        if route == "/api/open":
            self._json(editor.open(payload.get("page") or "Landing"))
            return
        if route == "/api/yes":
            self._json(editor.say("yes, make it right"))
            return
        if route == "/api/assist":
            self._json(editor.assist(payload.get("text") or ""))
            return
        self._json({"ok": False, "error": f"unknown route {route}"}, 404)

    def log_message(self, *args):  # quiet
        return


class OreoEditor:
    def __init__(self, backend=None, build: str = "editor-default",
                 host: str = "127.0.0.1", port: int = 0) -> None:
        self.backend = backend
        self.build = build
        self.editor = _Editor(backend=backend, build=build)
        self.host = host
        self.port = port
        self.server: Optional[http.server.ThreadingHTTPServer] = None

    def serve(self, port: int = 0, host: str = "127.0.0.1") -> str:
        self.editor.bootstrap()
        self.host = host
        self.port = port or self._pick_port()
        self.server = http.server.ThreadingHTTPServer(
            (host, self.port), _Handler)
        self.server.server_side = self.editor  # type: ignore[attr-defined]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return f"http://{host}:{self.port}/editor"

    def serve_forever(self, port: int = 0, host: str = "127.0.0.1") -> None:
        self.editor.bootstrap()
        self.port = port or self._pick_port()
        self.server = http.server.ThreadingHTTPServer(
            (host, self.port), _Handler)
        self.server.server_side = self.editor  # type: ignore[attr-defined]
        print(f"OREO editor at http://{host}:{self.port}/editor")
        self.server.serve_forever()

    def stop(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()

    @staticmethod
    def _pick_port() -> int:
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        return port