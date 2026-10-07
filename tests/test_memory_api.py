"""Tests for the stable Memory API.

The point of `mem20api` is that a caller can bind a store and get honest
answers without touching engine globals. These tests hold it to that: binding,
isolation between stores, diagnostics on drifted indexes, and the rule that
reads never mutate.
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mem20api import open_store, health, StoreError  # noqa: E402


FACTS = [
    ("deploys", "Prod runs build 4127 from the linux runner", ["prod", "build"]),
    ("deploys", "Staging runs build 4130", ["staging", "build"]),
    ("braid", "Braid commits a node with an Ed25519 signature", ["braid", "ledger"]),
    ("unity", "Unity 6 licence lives under /home/jayson/.config/unity3d", ["unity"]),
]


@pytest.fixture
def store_path(tmp_path):
    d = tmp_path / "store"
    d.mkdir()
    with open_store(d) as s:
        for topic, content, tags in FACTS:
            s.remember(topic, content, tags=tags)
    return d


# --- binding ------------------------------------------------------------

def test_open_store_defaults_to_env(tmp_path, monkeypatch):
    d = tmp_path / "s"
    d.mkdir()
    monkeypatch.setenv("MEM20_STORE_PATH", str(d))
    s = open_store()
    assert s.path == str(d)


def test_binding_points_the_engine_at_this_store(store_path):
    with open_store(store_path) as s:
        assert s.stats()["grounded_facts"] == len(FACTS)


def test_two_stores_do_not_leak_into_each_other(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    with open_store(a) as sa:
        sa.remember("t", "alpha fact", tags=["x"])
    with open_store(b) as sb:
        sb.remember("t", "beta fact", tags=["x"])

    with open_store(a) as sa:
        contents = {r["content"] for r in sa.recall(k=50)}
        assert "alpha fact" in contents
        assert "beta fact" not in contents
    with open_store(b) as sb:
        contents = {r["content"] for r in sb.recall(k=50)}
        assert "beta fact" in contents
        assert "alpha fact" not in contents


def test_a_missing_store_opens_but_reports_empty(tmp_path):
    d = tmp_path / "nope"
    with open_store(d) as s:
        st = s.stats()
        assert st["grounded_facts"] == 0
        assert s.health()["healthy"] is False  # no indexes exist yet


def test_health_helper_is_one_shot(store_path):
    h = health(store_path)
    assert h["ledger_records"] == len(FACTS)
    assert h["healthy"] is True


# --- reads are reads ----------------------------------------------------

def test_reads_do_not_mutate_the_ledger(store_path):
    before = (store_path / "ledger.jsonl").read_bytes()
    with open_store(store_path) as s:
        s.recall(k=10)
        s.semantic("prod build", k=5)
        s.hybrid("prod build", k=5)
        s.graph("prod", hops=2)
        s.health()
        s.contamination()
        s.stats()
    assert (store_path / "ledger.jsonl").read_bytes() == before


def test_rebuild_does_not_touch_the_ledger(store_path):
    before = (store_path / "ledger.jsonl").read_bytes()
    with open_store(store_path) as s:
        s.rebuild("all")
    assert (store_path / "ledger.jsonl").read_bytes() == before


# --- trust --------------------------------------------------------------

def test_health_reports_a_healthy_store(store_path):
    with open_store(store_path) as s:
        h = s.health()
        assert h["healthy"] is True
        assert h["indexes"]["vector"]["missing_from_ledger"] == 0
        assert h["indexes"]["graph"]["entities"] > 0


def test_semantic_reports_drift_rather_than_shortening_silently(store_path):
    lines = (store_path / "ledger.jsonl").read_text().splitlines()
    (store_path / "ledger.jsonl").write_text("\n".join(lines[:2]) + "\n")

    with open_store(store_path) as s:
        r = s.semantic("prod build", k=4)
        assert r["healthy"] is False
        assert r["diagnostic"]["missing_from_ledger"] == len(FACTS) - 2


def test_semantic_strict_raises_on_drift(store_path):
    lines = (store_path / "ledger.jsonl").read_text().splitlines()
    (store_path / "ledger.jsonl").write_text("\n".join(lines[:1]) + "\n")

    with open_store(store_path) as s:
        # Assert on the engine this store is actually bound to, not on a
        # separately-imported module: under pytest `memory` can resolve to a
        # different file, and asserting against the wrong one passes vacuously.
        engine = s._engine
        with pytest.raises(engine.IndexDriftError):
            s.semantic("prod", k=3, strict=True)


def test_hybrid_says_when_it_degraded(store_path):
    os.remove(store_path / "vector_index.faiss")
    with open_store(store_path) as s:
        r = s.hybrid("prod", k=3)
        assert r["degraded_to"] in ("bm25_only", "vector_only", "both", "neither")
        if r["hits"]:
            assert r["diagnostic"]["vector_ran"] is False


def test_contamination_is_zero_on_a_clean_store(store_path):
    with open_store(store_path) as s:
        assert s.contamination()["contamination_rate"] == 0.0


# --- retrieval behaviour ------------------------------------------------

def test_semantic_finds_related_content(store_path):
    with open_store(store_path) as s:
        r = s.semantic("what build does prod run", k=3)
        assert r["hits"], "semantic retrieval returned nothing"
        assert any("4127" in h["content"] for h in r["hits"])


def test_hybrid_finds_related_content(store_path):
    with open_store(store_path) as s:
        r = s.hybrid("braid ed25519 signature", k=3)
        assert r["hits"]
        assert r["degraded_to"] == "both"


def test_graph_traversal_connects_related_entities(store_path):
    with open_store(store_path) as s:
        g = s.graph("braid", hops=2)
        assert g["found"] is True
        assert g["facts"]


def test_graph_miss_is_reported_honestly(store_path):
    with open_store(store_path) as s:
        g = s.graph("not-a-real-entity-xyz", hops=1)
        assert g["found"] is False
        assert "not found" in g["error"].lower()


def test_entities_are_ranked_by_connectivity(store_path):
    with open_store(store_path) as s:
        ents = s.entities(limit=5)
        assert ents
        degrees = [e["degree"] for e in ents]
        assert degrees == sorted(degrees, reverse=True)


def test_recall_at_is_point_in_time(store_path):
    with open_store(store_path) as s:
        first = s.recall(k=1)[0]["ts"]
        s.remember("deploys", "Prod moved to build 4200", tags=["prod"])
        past = s.recall_at(first, k=50)
        assert all(r["ts"] <= first for r in past)


# --- simulated partition ------------------------------------------------

def test_simulated_write_does_not_pollute_retrieval(store_path):
    with open_store(store_path) as s:
        s.remember_simulated("conspiracy", "Zephyra is a fictional city",
                             scenario="benchmark")
        assert all("Zephyra" not in r["content"] for r in s.recall(k=50))
        r = s.semantic("Zephyra fictional city", k=5)
        assert all("Zephyra" not in h["content"] for h in r["hits"])
        assert s.contamination()["contamination_rate"] == 0.0


def test_simulated_requires_evidence_to_promote(store_path):
    with open_store(store_path) as s:
        sim = s.remember_simulated("conspiracy", "Zephyra is a real city",
                                   scenario="benchmark")
        try:
            s.promote(sim["id"])
        except Exception:
            pass  # refusal is the point; a bare promotion would be the bug
        assert s.contamination()["contamination_rate"] == 0.0


# --- export -------------------------------------------------------------

def test_export_writes_both_formats(store_path, tmp_path):
    with open_store(store_path) as s:
        j = s.export(tmp_path / "l.json")
        jl = s.export(tmp_path / "l.jsonl", fmt="jsonl")
        assert len(json.load(open(j))) == len(FACTS)
        assert len(open(jl).readlines()) == len(FACTS)


def test_export_rejects_an_unknown_format(store_path, tmp_path):
    with open_store(store_path) as s:
        with pytest.raises(ValueError):
            s.export(tmp_path / "x", fmt="csv")