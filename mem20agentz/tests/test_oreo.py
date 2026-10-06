"""Hermetic test for `oreo build` vertical slice.

The build must run its full path without touching the shared substrate:
architecture NL engine (deterministic, no LLM), graph persistence through
injected hooks, emitted app file, and a real loopback HTTP round-trip in a
(promptly-terminated) subprocess. The sealed backend makes any unexpected
substrate call explode.
"""

from __future__ import annotations

import json
import pathlib

from mem20agentz import _substrate
from mem20agentz.oreo import build, status


def _sealed_backend() -> _substrate.Backend:
    backend = _substrate.Backend(use_substrate=False)
    memory: dict[str, list[dict]] = {}
    order: list[str] = []

    def remember(topic, content, tags=None, actor="agent",
                 epistemic_status="observed"):
        memory.setdefault(topic, [])
        memory[topic].insert(0, {
            "topic": topic,
            "content": content,
            "tags": tags or [],
            "actor": actor,
        })
        order.append(topic)
        return {"ok": True}

    def recall(topic=None, tags=None, k=10, **kw):
        hits = []
        for topic_key in sorted(memory, reverse=True):
            if topic and not topic_key.startswith(topic):
                continue
            for h in memory[topic_key]:
                if tags and not all(t in (h["tags"] or []) for t in tags):
                    continue
                hits.append(h)
        return hits[:k]

    backend.hooks["remember"] = remember
    backend.hooks["recall"] = recall
    return backend


def test_oreo_build_full_slice(tmp_path: pathlib.Path):
    backend = _sealed_backend()
    res = build(
        "I need a db, a landing page and a dashboard. "
        "Connect the db to the landing page with a secure auth.",
        backend=backend, root=tmp_path,
    )
    assert res["ok"] is True
    assert res["served"] is True
    assert res["hit"]["status"] == 200
    assert res["hit"]["page"] == "Landing"
    assert res["hit"]["database"] == "MainDB"
    assert res["hit"]["secure"] is True
    assert pathlib.Path(res["app_path"]).exists()

    graphs = status(backend=backend)["graphs"]
    assert any(g["name"] == res["graph_name"] for g in graphs)


def test_oreo_build_app_file_is_runnable():
    backend = _sealed_backend()
    res = build("I need a db and one landing page.",
                backend=backend, root=None)
    import importlib.util
    spec = importlib.util.spec_from_file_location("built_app", res["app_path"])
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    routes = {p: n for p, n in mod.ROUTES.items()}
    assert "/" in routes
    assert res["served"] is True