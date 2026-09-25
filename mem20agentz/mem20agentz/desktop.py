"""Unified office frontend + web app (sub-phase 2.9).

`Frontend` is the ONE office-style surface over the mem20 backend. It is a
thin client: every panel (chat, status, ledger, cron, projects) is fed by the
same endpoints the wire/desktop clients consume (`/chat`, `/status`,
`/ledger`) plus one composed bundle (`/office`). Chat transports and
transcripts are shared with `gateway_web.WebGateway` under the same `web:`
session prefix, so desktop/webgateway/office/CLI hold no divergent state.

The HTML app renders a dependency-free CSS-3D office room: bridges are desks,
projects are shelves, cron jobs are wall slots, the ledger is the floor. All
state is fetched live from `/office`.
"""

from __future__ import annotations

import html
import http.server
import json
import os
import pathlib
import subprocess
import sys
import threading
import time
import uuid
from typing import Optional

from . import __version__
from .config import load_config

FRONTEND_DIR = pathlib.Path(__file__).parent / "frontend"
CREWZ_ROOT = "/opt/mem20/mem20crewz"
GAMEZ_ROOT = "/opt/mem20/mem20gamez"
RUNTIME_ROOT = pathlib.Path(os.path.expanduser(
    os.environ.get("MEM20_RUNTIME", "/root/.mem20agentz")))


def _sys_python() -> str:
    return sys.executable


_FALLBACK_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>mem20</title></head>
<body><h1>mem20</h1>
<p>frontend template missing at
<code>mem20agentz/frontend/index.html</code> — reinstall the package.</p>
<div id="office"></div>
<div id="t-office"></div><div id="t-kanban"></div>
<div id="t-production"></div><div id="t-settings"></div><div id="t-chat"></div>
<script>window.MEM20_READY = "mem20 client ready.";/* /office */</script>
</body></html>
"""


class _Handler(http.server.BaseHTTPRequestHandler):
    server_version = "mem20agentz-office"

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
        frontend: "Frontend" = self.server.server_side  # type: ignore[attr-defined,assignment]
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except ValueError as exc:
            self._json({"ok": False, "error": f"bad json: {exc}"}, 400)
            return
        if self.path.rstrip("/") == "/chat":
            out = frontend.chat(payload)
            self._json(out, 200 if out.get("ok") else 400)
            return
        if self.path.rstrip("/") == "/production/run":
            name = str(payload.get("name") or "").strip()
            if not name:
                self._json({"ok": False, "error": "name required"}, 400)
                return
            try:
                bid = frontend.production_run(name)
                self._json({"ok": True, "build_id": bid})
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": str(exc)}, 500)
            return
        if self.path.rstrip("/") == "/settings":
            out = frontend.save_settings(payload)
            self._json(out, 200 if out.get("ok") else 400)
            return
        if self.path.rstrip("/") == "/kanban/move":
            out = frontend.kanban_move(payload)
            self._json(out, 200 if out.get("ok") else 400)
            return
        if self.path.rstrip("/") == "/kanban/boards":
            out = frontend.kanban_board_create(payload)
            self._json(out, 200 if out.get("ok") else 400)
            return
        if self.path.rstrip("/") == "/kanban/tasks":
            out = frontend.kanban_task_add(payload)
            self._json(out, 200 if out.get("ok") else 400)
            return
        if self.path.rstrip("/") == "/kanban/boards/delete":
            out = frontend.kanban_board_delete(payload)
            self._json(out, 200 if out.get("ok") else 400)
            return
        if self.path.rstrip("/") == "/crewz/run":
            out = frontend.crewz_run(payload)
            self._json(out, 200 if out.get("ok") else 400)
            return
        if self.path.rstrip("/") == "/gamez/train":
            out = frontend.gamez_train(payload)
            self._json(out, 200 if out.get("ok") else 400)
            return
        if self.path.rstrip("/") == "/cron/run":
            out = frontend.cron_run(payload)
            self._json(out, 200 if out.get("ok") else 400)
            return
        if self.path.rstrip("/") == "/webhooks/fire":
            out = frontend.webhooks_fire(payload)
            self._json(out, 200 if out.get("ok") else 400)
            return
        if self.path.rstrip("/") == "/pause":
            out = frontend.set_paused(payload)
            self._json(out, 200 if out.get("ok") else 400)
            return
        self._json({"ok": False, "error": f"unknown route {self.path}"}, 404)

    def do_GET(self):  # noqa: N802
        frontend: "Frontend" = self.server.server_side  # type: ignore[attr-defined,assignment]
        route = self.path.split("?", 1)[0]
        query = self.path.split("?", 1)[1] if "?" in self.path else ""
        if route == "/office":
            self._json(frontend.office())
            return
        if route == "/ledger":
            k = 20
            try:
                k = int(query.split("k=", 1)[1].split("&", 1)[0])
            except (ValueError, IndexError):
                pass
            self._json({"ok": True, "entries": frontend.ledger_tail(k)})
            return
        if route == "/status":
            self._json(frontend.status())
            return
        if route == "/kanban":
            self._json(frontend.kanban_view())
            return
        if route == "/production":
            self._json(frontend.production_view(query))
            return
        if route == "/specs":
            self._json(frontend.specs_view())
            return
        if route == "/crewz":
            self._json(frontend.crewz_view())
            return
        if route == "/gamez":
            self._json(frontend.gamez_view())
            return
        if route == "/systems":
            self._json(frontend.systems_view())
            return
        if route == "/fleet":
            self._json(frontend.fleet_view())
            return
        if route.startswith("/fleet/"):
            self._json(frontend.fleet_view(route[len("/fleet/"):]))
            return
        if route == "/sessions":
            self._json(frontend.sessions_view())
            return
        if route == "/cron":
            self._json(frontend.cron_view())
            return
        if route == "/webhooks":
            self._json(frontend.webhooks_view())
            return
        if route == "/settings":
            self._json(frontend.settings())
            return
        if route == "/dashboard":
            self._json(frontend.dashboard())
            return
        if route == "/health":
            self._json({"ok": True, "service": "mem office",
                        "version": __version__})
            return
        if route == "/":
            if getattr(frontend, "mode", "desktop") == "dashboard":
                self._html(frontend.dashboard_html())
            else:
                self._html(frontend.html())
            return
        self._json({"ok": False, "error": f"unknown route {self.path}"}, 404)

    def log_message(self, *args):  # quiet
        return


class Frontend:
    """Unified office web frontend over the mem20 backend surface."""

    def __init__(self, backend=None, root: Optional[object] = None,
                 agent_factory=None) -> None:
        self.backend = backend
        self.root = root
        self.agent_factory = agent_factory
        self.served_url = ""
        self.started_at = time.time()
        self._httpd = None
        self._thread = None
        self._web = None
        self.mode = "desktop"
        self._runs: dict[str, dict] = {}

    @staticmethod
    def _run_dir(kind: str) -> pathlib.Path:
        base = RUNTIME_ROOT / kind / "runs"
        base.mkdir(parents=True, exist_ok=True)
        return base

    def _spawn(self, kind: str, cmd: list[str], cwd: str,
               env_extra: Optional[dict] = None) -> str:
        """Start a background run (crewz crew, gamez training…), streaming
        stdout+stderr to a log under the runtime dir."""
        run_id = uuid.uuid4().hex[:10]
        log = self._run_dir(kind) / f"{run_id}.log"
        with log.open("a", encoding="utf-8") as fh:
            fh.write(f"$ {' '.join(cmd)}\n")
        env = dict(os.environ)
        if env_extra:
            env.update(env_extra)
        proc = subprocess.Popen(
            cmd, cwd=cwd, env=env,
            stdout=log.open("ab"), stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL)
        self._runs[run_id] = {
            "run_id": run_id, "kind": kind, "status": "running",
            "started": time.time(), "log": str(log),
            "cmd": list(cmd), "pid": proc.pid,
        }

        def _monitor():
            rc = proc.wait()
            summary = {"rc": rc, "finished": time.time(),
                       "duration_s": round(time.time() - self._runs[run_id]["started"], 1)}
            if rc == 0:
                self._runs[run_id]["status"] = "done"
            else:
                self._runs[run_id]["status"] = "failed"
            self._runs[run_id]["rc"] = rc
            try:
                summary["tail"] = self._tail(str(log), 200)
            except OSError:
                pass
            summary_path = self._run_dir(kind) / f"{run_id}.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            self._runs[run_id]["summary"] = summary

        threading.Thread(target=_monitor, daemon=True).start()
        return run_id

    @staticmethod
    def _tail(path: str, n: int = 200) -> list[str]:
        try:
            lines = pathlib.Path(path).read_text(encoding="utf-8",
                                                 errors="replace").splitlines()
        except OSError:
            return []
        return lines[-n:]

    def _gateway(self) -> object:
        if self._web is None:
            from .gateway_web import WebGateway
            self._web = WebGateway(backend=self.backend, root=self.root,
                                   agent_factory=self.agent_factory)
        return self._web

    def chat(self, payload: dict) -> dict:
        return self._gateway().chat(payload)

    def status(self) -> dict:
        return self._gateway().status()

    def ledger_tail(self, k: int = 20) -> list[dict]:
        return self._gateway().ledger_tail(k)

    # ------------------------------------------------------------ kanban
    def kanban_view(self) -> dict:
        from .kanban import Kanban, KanbanDoorError
        try:
            kanban = Kanban()
            boards = []
            for b in kanban.board_names():
                try:
                    board = kanban.board(b)
                except Exception:  # noqa: BLE001
                    continue
                cards = []
                for c in (board.cards if board else []):
                    cards.append({
                        "id": c.get("id", ""),
                        "title": c.get("title", ""),
                        "status": c.get("status", ""),
                        "assignee": c.get("assignee", ""),
                        "tags": c.get("tags", []),
                    })
                boards.append({"name": b, "cards": cards})
            return {"ok": True, "boards": boards}
        except KanbanDoorError as exc:
            return {"ok": False, "error": f"door unavailable: {exc}"}

    def kanban_move(self, payload: dict) -> dict:
        from .kanban import Kanban, KanbanDoorError
        board = payload.get("board")
        task_id = payload.get("task_id")
        target = payload.get("target") or payload.get("status")
        if not board or not task_id or not target:
            return {"ok": False, "error": "board, task_id, target required"}
        try:
            kanban = Kanban()
            kanban.move_card(board, task_id, target)
            return {"ok": True, "board": board, "task_id": task_id,
                    "target": target}
        except (KanbanDoorError, Exception) as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    # --------------------------------------------------------- production
    def production_view(self, query: str = "") -> dict:
        from . import production
        params = {}
        if query:
            for part in query.split("&"):
                if "=" in part:
                    k, _, v = part.partition("=")
                    params[k] = v
        build = params.get("build") or None
        phase = params.get("phase") or None
        try:
            tail = int(params.get("tail", 60))
        except ValueError:
            tail = 60
        view = production.peek(build, phase, tail)
        build_ids = []
        if production.RUNS_DIR.exists():
            build_ids = sorted(
                (d.name for d in production.RUNS_DIR.iterdir()
                 if d.is_dir() and (d / "state.json").exists()),
                key=lambda n: (production.RUNS_DIR / n).stat().st_mtime,
                reverse=True)[:20]
        view["builds"] = build_ids
        return view

    def production_run(self, name: str) -> str:
        from . import production
        return production.run(name)

    def specs_view(self) -> dict:
        """Launchable pipeline specs (name -> phases) for the production
        page."""
        try:
            from . import production
            specs = []
            for spec_file in sorted(production.SPECS_DIR.glob("*.json")):
                try:
                    spec = json.loads(spec_file.read_text(encoding="utf-8"))
                except (ValueError, OSError):
                    continue
                name = str(spec.get("name") or spec_file.stem)
                phases = [str(p.get("id") or p.get("name") or p)
                          for p in spec.get("phases", [])]
                specs.append({
                    "name": name,
                    "start": str(spec.get("start") or ""),
                    "phases": phases,
                    "path": str(spec_file),
                })
            return {"ok": True, "specs": specs}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    # -------------------------------------------------------------- crewz
    def _crewz_roadmaps(self) -> list[dict]:
        base = os.path.join(CREWZ_ROOT, "runtime", "roadmaps")
        out = []
        if not os.path.isdir(base):
            return out
        for fn in sorted(os.listdir(base)):
            if not fn.endswith(".jsonl"):
                continue
            p = os.path.join(base, fn)
            events = []
            try:
                for line in open(p, encoding="utf-8"):
                    line = line.strip()
                    if line:
                        events.append(json.loads(line))
            except (ValueError, OSError):
                continue
            statuses = {}
            for ev in events:
                statuses[ev.get("status", "planned")] = \
                    statuses.get(ev.get("status", "planned"), 0) + 1
            try:
                updated = os.path.getmtime(p)
            except OSError:
                updated = 0
            out.append({"name": fn[: -len(".jsonl")], "phases": events,
                        "statuses": statuses, "updated": updated})
        out.sort(key=lambda r: r["updated"], reverse=True)
        return out

    def crewz_view(self) -> dict:
        peers = []
        try:
            import sys
            sys.path.insert(0, CREWZ_ROOT)
            from mem20crewz.a2a import A2AClient  # type: ignore[import-not-found]
            client = A2AClient()
            for name in client.peer_names():
                peers.append({"name": name,
                              "url": client.peers()[name].get("url", "")})
        except Exception:  # noqa: BLE001
            peers = []
        runs = []
        for v in self._runs.values():
            if v["kind"] != "crewz":
                continue
            run = dict(v)
            run["tail"] = self._tail(str(v["log"]), 80)
            runs.append(run)
        runs.sort(key=lambda r: r["started"], reverse=True)
        return {"ok": True, "roadmaps": self._crewz_roadmaps(),
                "peers": peers, "runs": runs,
                "root": CREWZ_ROOT}

    def crewz_run(self, payload: dict) -> dict:
        topic = str(payload.get("topic") or "mem20 command center").strip()
        real = bool(payload.get("real", True))
        if not topic:
            return {"ok": False, "error": "topic required"}
        python = _sys_python()
        cmd = [python, "-m", "mem20crewz", "demo"]
        if real:
            cmd.append("--real")
        cmd += ["--topic", topic]
        run_id = self._spawn("crewz", cmd, cwd="/opt/mem20")
        return {"ok": True, "run_id": run_id}

    # -------------------------------------------------------------- gamez
    def gamez_view(self) -> dict:
        runs = []
        base = self._run_dir("gamez")
        for log_p in sorted(base.glob("*.log"), reverse=True)[:12]:
            run_id = log_p.stem
            summary = None
            sfile = base / f"{run_id}.json"
            if sfile.exists():
                try:
                    summary = json.loads(sfile.read_text(encoding="utf-8"))
                except ValueError:
                    summary = None
            active = self._runs.get(run_id)
            status = (active or {}).get("status", "done" if summary else "?")
            runs.append({"run_id": run_id, "summary": summary,
                         "status": status,
                         "tail": self._tail(str(log_p), 40),
                         "log": str(log_p)})
        envs = ["CartPole-v1"]
        try:
            import gymnasium
            envs = sorted(
                (e for e in gymnasium.envs.registry  # type: ignore[attr-defined]
                 if " -v" in e or e.endswith("-v0") or e.endswith("-v1")),
                key=str)[:40] or envs
        except Exception:  # noqa: BLE001
            pass
        return {"ok": True, "environments": envs,
                "agent_types": ["dqn", "random"],
                "runs": runs, "active": [dict(v) for v in self._runs.values()
                                         if v["kind"] == "gamez"]}

    def gamez_train(self, payload: dict) -> dict:
        env = str(payload.get("env") or "CartPole-v1").strip()
        agent = str(payload.get("agent") or "dqn").strip()
        try:
            episodes = max(1, min(int(payload.get("episodes", 20)), 500))
            max_steps = max(1, min(int(payload.get("max_steps", 1000)), 10000))
            batch_size = max(1, min(int(payload.get("batch_size", 64)), 4096))
        except (TypeError, ValueError):
            episodes, max_steps, batch_size = 20, 1000, 64
        python = _sys_python()
        cmd = [python, "-m", "mem20gamez", "train", "--env", env,
               "--agent", agent, "--episodes", str(episodes),
               "--max-steps", str(max_steps), "--batch-size", str(batch_size)]
        run_id = self._spawn("gamez", cmd, cwd=GAMEZ_ROOT)
        return {"ok": True, "run_id": run_id, "env": env, "agent": agent}

    # ------------------------------------------------------------ systems
    def systems_view(self) -> dict:
        fleet = []
        try:
            from . import production
            fleet = production.fleet()
        except Exception:  # noqa: BLE001
            fleet = []
        services = []
        for unit in ["mem20-agentz-desktop", "mem20-agentz-web",
                     "mem20-agentz-gateway", "mem20-kanban", "mem20-chat",
                     "mem20-gateway", "mem20-messenger", "mcp-server"]:
            state = "?"
            try:
                r = subprocess.run(["systemctl", "is-active", unit],
                                   capture_output=True, text=True, timeout=5)
                state = r.stdout.strip() or "inactive"
            except Exception:  # noqa: BLE001
                state = "unknown"
            services.append({"unit": unit, "state": state})
        companions = [
            {"name": "chat web ui", "url": "http://127.0.0.1:3000", "port": 3000},
            {"name": "native model gateway", "url": "http://127.0.0.1:4000", "port": 4000},
            {"name": "platform mcp", "url": "http://127.0.0.1:8080/health", "port": 8080},
            {"name": "kanban door", "url": "http://127.0.0.1:8221", "port": 8221},
            {"name": "messenger", "url": "http://127.0.0.1:8000", "port": 8000},
            {"name": "webgateway", "url": "http://127.0.0.1:18779", "port": 18779},
            {"name": "dashboard", "url": "http://127.0.0.1:18778", "port": 18778},
        ]
        for c in companions:
            c["up"] = self._port_open(c["port"])
        return {"ok": True, "fleet": fleet, "services": services,
                "companions": companions}

    @staticmethod
    def _port_open(port: int) -> bool:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.4)
        try:
            return s.connect_ex(("127.0.0.1", port)) == 0
        finally:
            s.close()

    # ------------------------------------------------------------- fleet
    FLEET_ROOTS = ["/opt/mem20"]

    @classmethod
    def _scan_fleet(cls) -> list[dict]:
        """Real on-disk inventory of the fleet: every mem20* package plus the
        braid (Rust subsystem). Metadata is read from the tree itself."""
        import re
        base = pathlib.Path("/opt/mem20")
        roots = sorted(base.glob("mem20*"))
        if (base / "braid").is_dir():
            roots.append(base / "braid")
        out = []
        for d in roots:
                if not d.is_dir() or d.name == "mem20.egg-info":
                    continue
                py = d / "pyproject.toml"
                cargo = d / "Cargo.toml"
                meta_name = version = desc = ""
                kind = "python"
                if py.exists():
                    try:
                        with open(py, "rb") as fh:
                            import tomllib
                            table = tomllib.load(fh)
                        proj = table.get("project", {})
                        meta_name = proj.get("name", "")
                        version = proj.get("version", "")
                        desc = proj.get("description", "") or ""
                    except Exception:  # noqa: BLE001
                        pass
                elif any(c is not None for c in
                         [c for c in d.rglob("Cargo.toml") if "target" not in str(c)][:1]):
                    kind = "rust"
                    cargo = next((c for c in d.rglob("Cargo.toml")
                                  if "target" not in str(c)), cargo)
                    try:
                        t = cargo.read_text(encoding="utf-8", errors="replace")
                        m = re.search(r'^\[package\]\r?\n(?:[^[]*?)name\s*=\s*"([^"]+)"', t, re.M)
                        if not m:
                            m = re.search(r'name\s*=\s*"([^"]+)"', t)
                        if m:
                            meta_name = m.group(1)
                        for v in re.finditer(r'^(?:version|workspace)\.?p?ackage?\.?version?\s*(?:=)\s*"([^"]+)"', t, re.M):
                            pass
                        v = re.search(r'^version\s*=\s*"([^"]+)"', t, re.M)
                        if v and v.group(1) != "workspace":
                            version = v.group(1)
                        else:
                            wv = re.search(r'\[workspace\.package\]\r?\n(?:[^[]*?)version\s*=\s*"([^"]+)"', t, re.M)
                            if wv:
                                version = wv.group(1)
                        dm = re.search(r'^description\s*=\s*"([^"]+)"', t, re.M)
                        if dm:
                            desc = dm.group(1)
                    except Exception:  # noqa: BLE001
                        pass
                else:
                    continue
                name = meta_name or d.name
                if kind == "python":
                    sub = d / name
                    src_dirs = [sub] if sub.is_dir() else [d]
                    pat = "*.py"
                else:
                    src_dirs = [d]
                    pat = "*.rs"
                files = []
                for sd in src_dirs:
                    files += [f for f in sd.rglob(pat)
                              if "__pycache__" not in str(f) and "/target/" not in str(f)
                              and "Cargo.lock" not in str(f)]
                files = sorted(set(files))
                if not files and kind == "other":
                    kind = "python"
                    files = sorted(set([f for f in d.rglob("*.py")
                                        if "__pycache__" not in str(f)]))
                loc = 0
                for f in files:
                    try:
                        loc += len(f.read_text(encoding="utf-8", errors="replace").splitlines())
                    except OSError:
                        pass
                doc = ""
                if kind == "python":
                    initp = (d / name / "__init__.py") if (d / name).is_dir() else (d / "__init__.py")
                    if initp.exists():
                        t = initp.read_text(encoding="utf-8", errors="replace")
                        m = re.search(r'"""(.*?)"""', t, re.S)
                        if m:
                            doc = re.sub(r"\s+", " ", m.group(1)).strip()[:240]
                if not doc and desc:
                    doc = desc
                modules = []
                for f in files:
                    rel = str(f.relative_to(d))
                    try:
                        t = f.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        continue
                    if not t.lstrip():
                        continue
                    if kind == "python":
                        if re.search(r"^\s*(class|def)\s+\w+", t, re.M):
                            modules.append(rel)
                    elif re.search(r"\bpub\s+(fn|struct|enum|trait|mod|impl)\b", t):
                        modules.append(rel)
                commands = []
                if kind == "python":
                    clif = (d / name / "cli.py") if (d / name).is_dir() else (d / "cli.py")
                    if clif.exists():
                        t = clif.read_text(encoding="utf-8", errors="replace")
                        for m in re.finditer(r'add_parser\(\s*["\']([\w-]+)', t):
                            if m.group(1) not in commands:
                                commands.append(m.group(1))
                else:
                    for ex in sorted(d.rglob("examples/*.rs")):
                        if "/target/" in str(ex):
                            continue
                        commands.append(ex.stem)
                    cmdds = (d / "braid_cli" / "src" / "main.rs")
                    if cmdds.exists() and not commands:
                        t = cmdds.read_text(encoding="utf-8", errors="replace")
                        for m in re.finditer(r'^\s*["\']([\w-]+)["\']\s*=>', t, re.M):
                            commands.append(m.group(1))
                if kind == "rust" and not version:
                    for c in d.rglob("Cargo.toml"):
                        if "/target/" in str(c):
                            continue
                        try:
                            t = c.read_text(encoding="utf-8", errors="replace")
                            v = re.search(r'^version\s*=\s*"([^"]+)"', t, re.M)
                            if v and v.group(1) != "workspace":
                                version = v.group(1)
                                break
                        except OSError:
                            continue
                if kind == "rust" and not desc:
                    for c in d.rglob("Cargo.toml"):
                        if "/target/" in str(c):
                            continue
                        try:
                            t = c.read_text(encoding="utf-8", errors="replace")
                            dm = re.search(r'^description\s*=\s*"([^"]+)"', t, re.M)
                            if dm:
                                desc = dm.group(1)
                                break
                        except OSError:
                            continue
                out.append({
                    "name": name,
                    "package_dir": str(d),
                    "kind": kind,
                    "version": version,
                    "description": desc or doc,
                    "modules": modules[:60],
                    "commands": commands,
                    "loc": loc,
                    "languages": ["Rust"] if kind == "rust" else ["Python"],
                })
        return out

    def _fleet_state_map(self) -> dict:
        live = {}
        try:
            st = self.status()
            for s in (st.get("fleet") or []):
                if isinstance(s, dict) and s.get("name"):
                    live[s["name"]] = s
        except Exception:  # noqa: BLE001
            pass
        return live

    def fleet_view(self, name: str = "") -> dict:
        items = self._scan_fleet()
        live = self._fleet_state_map()
        for it in items:
            st = live.get(it["name"]) or {}
            enabled = st.get("enabled")
            active = st.get("active")
            it["state"] = "active" if (active or enabled) else "idle"
            it["online"] = self._port_open(4000) if it["name"] in ("mem20gateway", "gateway") else None
        if name:
            found = next((i for i in items
                          if i["name"] == name or i["name"].endswith(name)
                          or name in i["package_dir"]), None)
            if not found:
                return {"ok": False, "error": f"unknown fleet member: {name}"}
            return {"ok": True, "fleet": [found], "total": len(items)}
        return {"ok": True, "fleet": items, "total": len(items)}

    # ----------------------------------------------------------- sessions
    def sessions_view(self) -> dict:
        try:
            from .sessions import Sessions
            return {"ok": True,
                    "sessions": Sessions(backend=self.backend).list()}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    # -------------------------------------------------------------- cron
    def cron_view(self) -> dict:
        try:
            from .cron import Cron
            cron = Cron(backend=self.backend, root=self.root)
            jobs = []
            for j in cron.list_jobs():
                job = dict(j)
                try:
                    job["next_run"] = cron.next_run(str(job.get("name")))
                except Exception:  # noqa: BLE001
                    job["next_run"] = ""
                jobs.append(job)
            return {"ok": True, "jobs": jobs}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    def cron_run(self, payload: dict) -> dict:
        name = str(payload.get("name") or "").strip()
        if not name:
            return {"ok": False, "error": "name required"}
        try:
            from .cron import Cron
            result = Cron(backend=self.backend, root=self.root).run(
                name, backend=self.backend)
            return {"ok": True, "name": name, "result": str(result)[:400]}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    # ---------------------------------------------------------- webhooks
    def webhooks_view(self) -> dict:
        try:
            from .webhooks import WebhookServer
            server = WebhookServer(ledger=self.backend)
            return {"ok": True, "routes": server.routes()}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    def webhooks_fire(self, payload: dict) -> dict:
        route = str(payload.get("route") or "").strip()
        try:
            body = json.dumps(payload.get("body", {}) or {}).encode("utf-8")
        except (TypeError, ValueError):
            return {"ok": False, "error": "bad body"}
        from .webhooks import WebhookServer
        server = WebhookServer(ledger=self.backend)
        status, out = server.dispatch(route, body)
        return {"ok": out.get("ok", False), "status": status,
                "route": route, "error": out.get("error", ""),
                "out": out.get("out", "")}

    # ------------------------------------------------------- kanban write
    def kanban_board_create(self, payload: dict) -> dict:
        name = str(payload.get("name") or "").strip()
        columns = payload.get("columns") or None
        if not name:
            return {"ok": False, "error": "name required"}
        try:
            from .kanban import Kanban, KanbanDoorError
            kanban = Kanban()
            board = kanban.create_board(name, columns=columns)
            return {"ok": True, "board": getattr(board, "name", name)}
        except (KanbanDoorError, Exception) as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    def kanban_task_add(self, payload: dict) -> dict:
        board = str(payload.get("board") or "").strip()
        title = str(payload.get("title") or "").strip()
        assignee = str(payload.get("assignee") or "").strip()
        if not board or not title:
            return {"ok": False, "error": "board and title required"}
        try:
            from .kanban import Kanban, KanbanDoorError
            kanban = Kanban()
            card = kanban.add_card(board, title, assignee=assignee)
            return {"ok": True, "board": board,
                    "card": getattr(card, "to_dict", lambda: card)()
                    if hasattr(card, "to_dict") else {"title": title}}
        except (KanbanDoorError, Exception) as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    def kanban_board_delete(self, payload: dict) -> dict:
        name = str(payload.get("name") or "").strip()
        if not name:
            return {"ok": False, "error": "name required"}
        try:
            from .kanban import Kanban, KanbanDoorError
            Kanban().delete_board(name)
            return {"ok": True, "board": name}
        except (KanbanDoorError, Exception) as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    # ------------------------------------------------------------- pause
    def set_paused(self, payload: dict) -> dict:
        try:
            paused = bool(payload.get("paused", True))
            pausefile = RUNTIME_ROOT / "PAUSED"
            if paused:
                pausefile.write_text("paused\n", encoding="utf-8")
            elif pausefile.exists():
                pausefile.unlink()
            return {"ok": True, "paused": paused}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    # ---------------------------------------------------------- settings
    def settings(self) -> dict:
        cfg = load_config()
        data = cfg.data
        subs = dict(data.get("subsystems", {}))
        try:
            from . import production
            names = [f["name"] for f in production.fleet()]
        except Exception:  # noqa: BLE001
            names = []
        if not subs:
            for n in names:
                subs.setdefault(n, {"enabled": True, "note": ""})
        braid = dict(data.get("braid", {"enabled": True, "note": ""}))
        return {
            "ok": True,
            "subsystems": subs,
            "fleet": names,
            "braid": braid,
            "model": data.get("model", {}),
            "default_profile": data.get("default_profile", "mem20"),
        }

    def save_settings(self, payload: dict) -> dict:
        cfg = load_config()
        updated = {}
        if isinstance(payload.get("subsystems"), dict):
            updated["subsystems"] = payload["subsystems"]
        if isinstance(payload.get("braid"), dict):
            updated["braid"] = payload["braid"]
        if updated:
            cfg.update_file(updated)
        return {"ok": True, "updated": list(updated)}

    # ---------------------------------------------------------- dashboard
    def dashboard(self) -> dict:
        """Compact status bundle for the :18778 dashboard surface."""
        view = self.production_view("")
        b = {}
        try:
            from .kanban import Kanban
            b = self.kanban_view()
        except Exception:  # noqa: BLE001
            b = {}
        return {
            "service": "mem20",
            "version": __version__,
            "now_unix": int(time.time()),
            "status": {
                "service": "mem office",
                "production": {
                    "latest_build": view.get("build_id"),
                    "status": view.get("status"),
                    "phases": [{"id": p["id"], "name": p["name"],
                                "status": p["status"],
                                "gate": p.get("gate", "")}
                               for p in view.get("phases", [])],
                },
                "kanban": {
                    "boards": b.get("boards") if b.get("ok") else [],
                },
                "settings": self.settings(),
            },
        }

    def office(self) -> dict:
        """The single bundle consumed by the office web app (and thin
        clients): status + ledger + cron + projects, all read from the same
        backend surface the webgateway uses."""
        cron = []
        projects = []
        try:
            from .cron import Cron
            jobs = Cron(backend=self.backend, root=self.root).list_jobs()
            cron = [{"schedule": str(j.get("schedule", "")),
                     "command": str(j.get("command") or j.get("prompt") or "")}
                    for j in jobs if isinstance(j, dict)]
        except Exception:  # noqa: BLE001
            cron = []
        try:
            from .projects import Projects
            projects = [{"name": str(p.get("name", p))}
                        for p in Projects(backend=self.backend,
                                          root=self.root).list_projects()]
        except Exception:  # noqa: BLE001
            projects = []
        return {
            "service": "mem office",
            "version": __version__,
            "status": self.status(),
            "ledger": self.ledger_tail(12),
            "cron": cron,
            "projects": projects,
            "now_unix": int(time.time()),
        }

    # ------------------------------------------------------------------ html
    def html(self) -> str:
        """Unified mem20 command center. The SPA shell lives in
        frontend/index.html and is read at serve-time so the frontend can be
        edited without touching server code."""
        try:
            page = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
        except OSError:
            page = _FALLBACK_HTML
        return page.replace("@VERSION@", __version__).replace(
            "@STARTED_UNIX@", str(int(self.started_at)))

    def dashboard_html(self) -> str:
        """Compact auto-refreshing surface for the :18778 mem20 dashboard."""
        return """<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>mem20 dashboard</title>
<style>
 body{margin:0;font-family:system-ui,sans-serif;background:#0d1017;color:#e8e8e8}
 header{padding:12px 20px;border-bottom:1px solid #232a34;display:flex;
   gap:14px;align-items:baseline}
 header h1{margin:0;font-size:1rem}
 header span{color:#8ca0b8;font-size:.8rem}
 #app{padding:16px 20px;display:flex;flex-direction:column;gap:16px}
 h2{font-size:.82rem;color:#93a7c0;text-transform:uppercase;
   letter-spacing:.1em;margin:0 0 8px}
 .card{background:#151b25;border:1px solid #232a34;border-radius:12px;padding:14px}
 table{width:100%;border-collapse:collapse;font-size:.84rem}
 th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #222b36}
 th{color:#93a7c0;font-size:.72rem;text-transform:uppercase}
 .badge{display:inline-block;border-radius:6px;padding:1px 8px;font-size:.72rem}
 .ok{background:#123c26;color:#7fdca0} .run{background:#3a2d10;color:#ffd479}
 .fail{background:#43191d;color:#ff8d92} .pill{background:#1e2733;
   border:1px solid #2c3644;border-radius:20px;padding:2px 10px;font-size:.72rem}
 .statusline{font-size:.78rem;color:#8ca0b8}
</style></head><body>
<header><h1>mem20 dashboard</h1><span id="meta">…</span></header>
<div id="app">
  <div class="card"><h2>production</h2><div id="prod">…</div></div>
  <div class="card"><h2>kanban board</h2><div id="kanban">…</div></div>
  <div class="card"><h2>subsystems</h2><div id="subs">…</div></div>
</div>
<script>
const el=id=>document.getElementById(id);
const esc=t=>String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
async function refresh(){
  try{
    const d=await (await fetch('/dashboard')).json();
    el('meta').textContent='v'+d.version+' · '+new Date(d.now_unix*1000)
      .toISOString();
    const p=d.status.production||{};
    const st=p.status||'?';
    const badge=st==='complete'?'ok':(st==='running'?'run':'fail');
    el('prod').innerHTML='<span class="badge '+badge+'">'+st+'</span> '+
      '<b>'+esc(p.latest_build||'—')+'</b>'+
      '<table><tr><th>phase</th><th>role</th><th>status</th><th>gate</th></tr>'+
      (p.phases||[]).map(x=>'<tr><td>'+esc(x.id)+'</td><td>'+esc(x.name)+
      '</td><td>'+esc(x.status)+'</td><td class="statusline">'+
      esc(x.gate||'')+'</td></tr>').join('')+'</table>';
    const boards=d.status.kanban.boards||[];
    el('kanban').innerHTML=boards.length?boards.map(b=>
      '<b>'+esc(b.name)+'</b><br>'+(b.cards||[]).map(c=>
      '<span class="pill">'+esc(c.title)+'</span>').join('')).join('<br>')
      :'<span class="statusline">no boards</span>';
    const s=d.status.settings||{};
    const rows=Object.entries(s.subsystems||{}).filter(([n])=>
      (s.fleet||[]).includes(n)).slice(0,16);
    el('subs').innerHTML=(rows.map(([n,v])=>'<span class="pill">'+(v&&v.enabled
      ?'✔':'✘')+' '+esc(n)+'</span>').join('')||'<span class="statusline">—</span>')
      +' — braid '+(s.braid&&s.braid.enabled?'enabled':'disabled');
  }catch(e){el('meta').textContent='offline: '+e;}
}
refresh();setInterval(refresh,5000);
</script>
</body></html>
"""

    # ----------------------------------------------------------------- serve
    def serve(self, port: int = 0, host: str = "127.0.0.1") -> str:
        self._httpd = http.server.ThreadingHTTPServer((host, port), _Handler)
        self._httpd.server_side = self  # type: ignore[attr-defined]
        actual = self._httpd.server_address[1]
        self.served_url = f"http://{host}:{actual}"
        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                        daemon=True)
        self._thread.start()
        return self.served_url

    def serve_dashboard(self, port: int = 18778,
                        host: str = "127.0.0.1") -> str:
        """Second surface for `mem20 dashboard` (:18778)."""
        self.mode = "dashboard"
        return self.serve(port=port, host=host)

    def serve_both(self, desktop_port: int = 18785,
                   dashboard_port: int = 18778,
                   host: str = "127.0.0.1") -> tuple[str, str]:
        """Serve the unified desktop (:18785) and dashboard (:18778)."""
        self.serve(port=desktop_port, host=host)
        self.mode = "desktop"
        dash = Frontend(self.backend, self.root, self.agent_factory)
        dash.mode = "dashboard"
        dash_url = dash.serve(port=dashboard_port, host=host)
        return self.served_url, dash_url

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

    @staticmethod
    def _esc(text: str) -> str:
        return html.escape(str(text))


def build_office_factory(backend=None, profile="mem20", model=None):
    """Callable(chat_id) -> AgentCore resuming the web:<chat_id> transcript
    (identical to the webgateway factory — single source, no divergent
    session state)."""
    from .gateway_web import build_web_factory
    return build_web_factory(backend=backend, profile=profile, model=model)


def default_office_port() -> int:
    try:
        cfg = load_config()
        return int(cfg.get("gateway", {}).get("office", {}).get(
            "port", 18785))
    except Exception:  # noqa: BLE001
        return 18785


def default_dashboard_port() -> int:
    try:
        cfg = load_config()
        return int(cfg.get("gateway", {}).get("office", {}).get(
            "dashboard_port", 18778))
    except Exception:  # noqa: BLE001
        return 18778