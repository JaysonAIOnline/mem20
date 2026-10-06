"""Test the OREO talk+draw editor as a mem20 surface (phase 03 sub-phase 3.4).

The editor must (1) bootstrap a real architecture graph into the shared
graph store, (2) serve the OREO editor HTML (not a stub), (3) round-trip a
`say` and a `draw` so every mutation is persisted to the store, and (4)
reload the persisted snapshot so a cold instance sees the same graph. All
through the sealed-substrate seam — no live substrate touched.
"""

from __future__ import annotations

import urllib.request

from mem20agentz import _substrate
from mem20agentz.oreditor import _Editor, OreoEditor


def _sealed_backend() -> _substrate.Backend:
    backend = _substrate.Backend(use_substrate=False)
    memory: dict[str, list[dict]] = {}
    order: list[str] = []

    def remember(topic, content, tags=None, actor="agent",
                 epistemic_status="observed"):
        key = (topic + "|" + str(len(order)))
        memory.setdefault(topic, [])
        memory[topic].insert(0, {
            "topic": topic,
            "content": content,
            "tags": tags or [],
            "actor": actor,
        })
        order.append(key)
        return {"ok": True, "topic": topic}

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


def test_editor_bootstrap_persists_graph():
    backend = _sealed_backend()
    editor = _Editor(backend=backend, build="ed-boot")
    editor.bootstrap()

    graph = editor.graph()
    assert graph["graph"]["nodes"]
    assert any(n["label"] == "Database" for n in graph["graph"]["nodes"])
    stored = editor.store.get("ed-boot")
    assert stored is not None
    assert stored["kind"] == "architecture"


def test_editor_serves_real_html():
    backend = _sealed_backend()
    editor = _Editor(backend=backend, build="ed-html")
    editor.bootstrap()
    html = editor.editor_html()
    assert html.startswith("<!doctype html>")
    assert "GraphLang" in html
    assert "listenBtn" in html


def test_editor_say_persists_and_reloads():
    backend = _sealed_backend()
    editor = _Editor(backend=backend, build="ed-say")
    editor.bootstrap()
    before = editor.store.get("ed-say")

    result = editor.say(
        "Connect the db to the settings page with a secure auth.")
    assert result["applied"]
    assert result["stored_as"] == "ed-say"

    after = editor.store.get("ed-say")
    assert after is not None
    assert len(after["graph"]["rels"]) > len(before["graph"]["rels"])
    assert any(r["type"] == "CONNECTS_TO" for r in after["graph"]["rels"])
    assert any(r["type"] == "AUTHENTICATES_WITH"
               for r in after["graph"]["rels"])

    cold = _Editor(backend=backend, build="ed-say")
    cold_graph = cold.graph()
    assert len(cold_graph["graph"]["relationships"]) == len(
        after["graph"]["rels"])


def test_editor_draw_persists_relationship():
    backend = _sealed_backend()
    editor = _Editor(backend=backend, build="ed-draw")
    editor.bootstrap()

    result = editor.draw({
        "src_name": "Landing",
        "dst_name": "Dashboard",
        "secure": True,
        "purpose": "user navigates between pages",
    })
    assert result["applied"]
    stored = editor.store.get("ed-draw")
    assert stored is not None
    assert any(
        r["type"] == "CONNECTS_TO"
        and r["src"] == "page_landing"
        for r in stored["graph"]["rels"]
    )


def test_editor_assist_sets_up_and_executes_procedural_skill():
    backend = _sealed_backend()
    registered: list[str] = []
    executed: list[tuple[str, dict]] = []

    def register(name, description, steps, preconditions=None,
                 effects=None, category="general"):
        registered.append(name)
        return {"skill": name}

    def execute(name, context=None):
        executed.append((name, context or {}))
        return {"executed_steps": ["load", "parse", "apply", "save"]}

    backend.hooks["procedural_register"] = register
    backend.hooks["procedural_execute"] = execute

    editor = _Editor(backend=backend, build="ed-assist")
    editor.bootstrap()

    result = editor.assist(
        "Connect the db to the dashboard with a secure auth.")
    assert result["applied"]
    assert result["stored_as"] == "ed-assist"
    assert "oreo_graph_edit" in registered
    assert executed and executed[0][0] == "oreo_graph_edit"
    assert executed[0][1]["build"] == "ed-assist"
    assert result["skill"]["executed"] is True

    cold = _Editor(backend=backend, build="ed-assist")
    cold_graph = cold.graph()
    assert any(
        r.get("type") == "CONNECTS_TO"
        and r.get("from") == "page_dashboard"
        and r.get("to") == "db_maindb"
        for r in cold_graph["graph"]["relationships"]
    )


def test_react_editor_build_served():
    from mem20agentz.oreditor import REACT_DIR
    assert REACT_DIR.is_dir(), "React build missing — run web/ npm run build"
    index = REACT_DIR / "index.html"
    assert index.exists()
    html = index.read_text()
    assert '<div id="root"></div>' in html
    has_asset = (
        (REACT_DIR / "assets").is_dir()
        and list((REACT_DIR / "assets").glob("*.js"))
    )
    assert has_asset, "React bundle not built"

    backend = _sealed_backend()
    server = OreoEditor(backend=backend, build="ed-react")
    url = server.serve(port=0)
    base = url.rsplit("/editor", 1)[0]
    try:
        with urllib.request.urlopen(f"{base}/react", timeout=5) as res:
            assert res.status == 200
            body = res.read().decode("utf-8")
            assert '<div id="root"></div>' in body
        with urllib.request.urlopen(f"{base}/api/model", timeout=5) as res:
            assert res.status == 200
    finally:
        server.stop()