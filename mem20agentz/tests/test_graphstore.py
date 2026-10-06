"""Test the OREO graph store round-trip through the sealed-substrate seam.

The graph store must (1) serialize a real GIR Graph to JSON, (2) persist it
as a mem20agentz-tagged fact, (3) round-trip name/kind/graph payload, and
(4) appear in `Backup.export` graphs listing with the same injected backend.
No live substrate is touched here: the server is shared, so these run hermetic.
"""

from __future__ import annotations

from mem20agentz import _substrate
from mem20agentz.backup import Backup
from mem20agentz.graphstore import GraphStore
from mem20oreo.parser.nl_parser.semantic_parser import parse_nl
from mem20oreo.parser.gir import NodeKind


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


def test_graph_store_save_and_round_trip():
    backend = _sealed_backend()
    store = GraphStore(backend=backend)
    graph = parse_nl("let x be 3 now let y be x plus 1 now print y")

    assert len(graph.nodes) == 12
    kinds = {n.kind for n in graph.nodes.values()}
    assert NodeKind.LITERAL in kinds
    assert NodeKind.VARIABLE in kinds

    result = store.save("demo-trip", graph, kind="gir",
                        meta={"seed": "test"})
    assert result["ok"] is True
    assert result["name"] == "demo-trip"

    back = store.get("demo-trip")
    assert back is not None
    assert back["kind"] == "gir"
    assert back["graph"]["name"] == graph.name

    names = store.list(kind="gir")
    assert any(r["name"] == "demo-trip" for r in names)


def test_backup_export_lists_graphs():
    backend = _sealed_backend()
    store = GraphStore(backend=backend)
    graph = parse_nl("let x be 3 now let y be x plus 1 now print y")
    store.save("backup-graph", graph)

    doc = Backup(backend=backend).export(out="/tmp/mem20agentz-graphstore-test.json.gz")
    assert doc["ok"] is True
    assert doc["graphs"] == 1

    import gzip
    import json
    with gzip.open(doc["path"], "rt", encoding="utf-8") as fh:
        payload = json.load(fh)
    assert any(g["name"] == "backup-graph" for g in payload["graphs"])


def test_graph_store_missing_is_none():
    backend = _sealed_backend()
    assert GraphStore(backend=backend).get("does-not-exist") is None


def test_architecture_graph_round_trip():
    backend = _sealed_backend()
    store = GraphStore(backend=backend)
    from mem20oreo.parser.architecture.runtime import GraphRuntime

    rt = GraphRuntime(use_llm=False)
    rt.say("I need a db, three pages and a couple of includes.")
    rt.say("Connect the db to the landing page with a secure auth.")

    result = store.save("arch-trip", rt.graph, kind="architecture")
    assert result["ok"] is True

    back = store.get("arch-trip")
    assert back["kind"] == "architecture"
    assert len(back["graph"]["nodes"]) == 7
    assert any(r["type"] == "CONNECTS_TO" for r in back["graph"]["rels"])
    assert any(g["name"] == "arch-trip"
               for g in store.list(kind="architecture"))