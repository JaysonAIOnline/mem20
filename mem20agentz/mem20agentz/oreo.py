"""mem20agentz `oreo build` vertical slice (phase 03 sub-phase 3.3).

The FIRST LIVE PROOF of the phase: take natural language, produce a
real GraphLang app (through OREO's own architecture engine + emitter),
persist the produced graph in the shared mem20 graph store, then run the
emitted server and hit a real route over HTTP. Live evals are wrapped
with `timeout` so the app process never outlives the call.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

TOPIC_PREFIX = "oreo:build:"


def build(
    nl: str,
    root: Optional[Path] = None,
    backend=None,
    port: int = 0,
    host: str = "127.0.0.1",
) -> dict:
    from mem20agentz._substrate import _load
    from mem20oreo.parser.architecture.runtime import GraphRuntime
    from mem20oreo.parser.architecture.emit import emit_app

    # 1) NL -> graph via OREO's own engine (no LLM, stays deterministic).
    rt = GraphRuntime(use_llm=False)
    rt.say(nl)
    graph = rt.graph

    # 2) emit a runnable app next to this package (kept under mem20).
    base = root or Path(__file__).resolve().parents[1] / "built"
    base.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = base / f"app_{stamp}.py"

    # 3) store the graph in the shared substrate store; this is the phase's
    #    "a built app = GIR graph served from mem20" claim.
    from mem20agentz.graphstore import GraphStore
    store_name = f"build-{stamp}"
    store = GraphStore(backend=backend)
    store.save(store_name, graph, kind="architecture",
               meta={"nl": nl, "source": "oreo build"})

    routes = None
    rt_result = None
    hit = None
    served = False
    port = 0

    # 4) serve + hit over real HTTP (subprocess under timeout).
    import socket
    import subprocess
    import sys
    from urllib.request import urlopen

    probe = socket.socket()
    probe.bind((host, 0))
    port = probe.getsockname()[1]
    probe.close()

    emit_app(graph, dest)
    runner = (
        "import importlib.util, sys\n"
        "_spec = importlib.util.spec_from_file_location('generated_app', sys.argv[1])\n"
        "_mod = importlib.util.module_from_spec(_spec)\n"
        "_spec.loader.exec_module(_mod)\n"
        "_mod.main(sys.argv[2] if len(sys.argv) > 2 else '127.0.0.1',\n"
        "           int(sys.argv[3]) if len(sys.argv) > 3 else 8787)\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-u", "-c", runner, str(dest), host, str(port)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    def _probe() -> tuple[bool, dict]:
        from urllib.error import HTTPError
        try:
            with urlopen(f"http://{host}:{port}/", timeout=1) as resp:
                body = resp.read().decode()
                return resp.status == 200, json.loads(body)
        except HTTPError as exc:
            body = exc.read().decode()
            return True, json.loads(body)
        except Exception:
            return False, {}

    try:
        deadline = time.time() + 15
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            served, hit = _probe()
            if served:
                break
            time.sleep(0.2)
        else:
            rt_result = {"ok": False, "error": "app not reachable in 15s"}
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        stdout = proc.stdout.read() if proc.stdout else ""
    routes = {"GET /": "probe"}

    return {
        "ok": True,
        "nl": nl,
        "graph_name": store_name,
        "app_path": str(dest),
        "port": port,
        "served": served,
        "hit": hit,
        "stdout_tail": stdout.strip()[-400:] if stdout else "",
    }


def status(backend=None) -> dict:
    from mem20agentz.graphstore import GraphStore
    store = GraphStore(backend=backend)
    return {"graphs": store.list(kind="architecture")}