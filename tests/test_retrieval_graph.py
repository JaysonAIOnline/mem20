"""Retrieval tests: index/ledger agreement, semantic resolution, entity graph.

These cover three defects that shipped:

1. Semantic and BM25 indexes drift from the ledger when it is truncated or
   compacted. Retrieval used to drop every unresolvable hit silently, so a store
   with 2,681 vectors and 371 live records returned zero results and reported
   success. A caller could not tell "nothing matches" from "your index is
   stale". `index_health` and the `_index_drift` diagnostic now make the
   difference observable, and `strict=True` turns it into an error.

2. Graph traversal could never return anything. The old implementation
   lowercased each fact and then tested `token[0].isupper()`, which is never
   true for a lowercased character, so the entity set was always empty. It now
   reads a graph built at write time.

3. Entity extraction silently degraded to nothing when spaCy was absent. The
   extractor is dependency-free by design.
"""
import json
import os

import pytest

from memory_engine import memory as M


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("MEM20_STORE_PATH", str(tmp_path))
    M.STORE_DIR = str(tmp_path)
    M.MEM_DIR = str(tmp_path.parent)
    M.LEDGER = os.path.join(M.STORE_DIR, "ledger.jsonl")
    M.ENTRIES = os.path.join(M.STORE_DIR, "entries")
    M.INDEX = os.path.join(M.STORE_DIR, "INDEX.md")
    M.BACKUP_DIR = os.path.join(M.STORE_DIR, "backups")
    M.VECTOR_INDEX = os.path.join(M.STORE_DIR, "vector_index.faiss")
    M.VECTOR_META = os.path.join(M.STORE_DIR, "vector_meta.jsonl")
    M.BM25_INDEX = os.path.join(M.STORE_DIR, "bm25_index.pkl")
    M.BM25_CORPUS = os.path.join(M.STORE_DIR, "bm25_corpus.jsonl")
    M.GRAPH_INDEX = os.path.join(M.STORE_DIR, "memory_graph.json")
    M.SIMULATED_LEDGER = os.path.join(M.STORE_DIR, "simulated_ledger.jsonl")
    os.makedirs(M.ENTRIES, exist_ok=True)
    return tmp_path


FACTS = [
    ("unity", "Unity 6 licence lives under /home/jayson/.config/unity3d/Unity/licenses",
     ["unity", "licence"]),
    ("unity", "The Unity editor binary is /home/jayson/Unity/Hub/Editor/6000.5.9f1/Editor/Unity",
     ["unity", "editor"]),
    ("cloudflare", "Cloudflare DNS updates use a scoped zone-read-only API token",
     ["cloudflare", "dns"]),
    ("sprint", "Jayson wants graph retrieval, semantic returns nothing right now",
     ["roadmap"]),
]


def _seed():
    for topic, content, tags in FACTS:
        M.remember(topic, content, tags=tags)


# --- index health -------------------------------------------------------

def test_index_health_reports_a_fresh_store_as_healthy(store):
    _seed()
    h = M.index_health()
    assert h["healthy"] is True
    assert h["ledger_records"] == len(FACTS)
    assert h["indexes"]["vector"]["missing_from_ledger"] == 0
    assert h["indexes"]["vector"]["meta_matches_index"] is True


def test_index_health_detects_ledger_truncation(store):
    _seed()
    lines = open(M.LEDGER).read().splitlines()
    with open(M.LEDGER, "w") as f:
        f.write("\n".join(lines[:2]) + "\n")

    h = M.index_health()
    assert h["healthy"] is False
    vec = h["indexes"]["vector"]
    assert vec["indexed"] == len(FACTS)
    assert vec["resolvable"] == 2
    assert vec["missing_from_ledger"] == len(FACTS) - 2


def test_index_health_absent_indexes_are_not_healthy(store):
    h = M.index_health()
    assert h["healthy"] is False
    assert h["indexes"]["vector"]["present"] is False
    assert h["indexes"]["graph"]["present"] is False


# --- semantic retrieval -------------------------------------------------

def test_semantic_returns_results_on_a_healthy_store(store):
    _seed()
    r = M.recall_semantic("unity licence", k=3)
    assert r, "semantic retrieval returned nothing on a consistent store"
    assert all("error" not in x for x in r)
    assert r[0]["_index_drift"]["healthy"] is True


def test_semantic_reports_drift_instead_of_silence(store):
    _seed()
    lines = open(M.LEDGER).read().splitlines()
    with open(M.LEDGER, "w") as f:
        f.write("\n".join(lines[:2]) + "\n")

    r = M.recall_semantic("unity", k=4)
    assert r, "should still return the resolvable records"
    drift = r[0]["_index_drift"]
    assert drift["healthy"] is False
    assert drift["missing_from_ledger"] == 2
    assert drift["dropped_orphans"] == 2


def test_semantic_strict_raises_on_a_drifted_store(store):
    _seed()
    lines = open(M.LEDGER).read().splitlines()
    with open(M.LEDGER, "w") as f:
        f.write("\n".join(lines[:2]) + "\n")

    with pytest.raises(M.IndexDriftError) as ei:
        M.recall_semantic("unity", k=3, strict=True)
    assert "rebuild_vectors" in str(ei.value)


def test_semantic_does_not_index_past_the_metadata_list(store):
    """A FAISS index larger than the metadata list must not index past the end."""
    _seed()
    meta = M._load_vector_meta()
    os.remove(M.VECTOR_META)
    with open(M.VECTOR_META, "w") as f:
        f.write(json.dumps(meta[0]) + "\n")  # truncate metadata only

    r = M.recall_semantic("unity", k=5)
    assert len(r) <= 1
    assert r[0]["_index_drift"]["healthy"] is False


def test_hybrid_reports_a_dead_vector_half_rather_than_hiding_it(store):
    _seed()
    os.remove(M.VECTOR_INDEX)

    r = M.recall_hybrid("unity", k=3)
    if r:
        retrieval = r[0]["_retrieval"]
        assert retrieval["degraded_to"] == "bm25_only"
        assert retrieval["vector_ran"] is False


# --- entity graph -------------------------------------------------------

def test_remember_writes_the_graph_index(store):
    _seed()
    assert os.path.exists(M.GRAPH_INDEX)
    g = M._load_graph()
    assert g["nodes"], "graph has no entities after four writes"


def test_graph_recall_finds_related_entities(store):
    _seed()
    r = M.recall_graph("unity", hops=2)
    assert r["found"] is True
    assert r["start"] == "unity"
    names = {e["entity"] for e in r["entities"]}
    assert "licence" in names
    assert "editor" in names
    assert r["facts"], "graph recall returned entities but no facts"


def test_graph_recall_hop_distance_is_recorded(store):
    _seed()
    r = M.recall_graph("unity", hops=2)
    by_name = {e["entity"]: e for e in r["entities"]}
    assert by_name["unity"]["hop"] == 0
    assert by_name["unity"]["is_start"] is True
    assert by_name["licence"]["hop"] == 1


def test_graph_recall_matches_partial_entity_names(store):
    _seed()
    r = M.recall_graph("cloud", hops=1)
    assert r["found"] is True


def test_graph_recall_reports_a_miss_honestly(store):
    _seed()
    r = M.recall_graph("definitely-not-an-entity", hops=2)
    assert r["found"] is False
    assert "not found" in r["error"].lower()
    assert r["known_entities"] > 0


def test_graph_recall_says_so_when_the_graph_is_absent(store):
    r = M.recall_graph("unity")
    assert r["found"] is False
    assert r.get("graph_present") is False
    assert "rebuild_graph" in r["error"]


def test_graph_recall_requires_an_entity(store):
    r = M.recall_graph("")
    assert r["found"] is False
    assert r["error"] == "entity is required"


# --- entity extraction --------------------------------------------------

def test_extraction_keeps_topics_and_tags():
    rec = {"topic": "unity", "tags": ["licence", "editor"],
           "content": "The Unity Editor binary is here."}
    ents = [e.lower() for e in M._graph_extract_entities(rec)]
    assert "unity" in ents
    assert "licence" in ents
    assert "editor" in ents


def test_extraction_finds_capitalised_runs():
    rec = {"topic": "", "tags": [],
           "content": "Jayson ships the release through Cloudflare DNS."}
    ents = [e.lower() for e in M._graph_extract_entities(rec)]
    assert "jayson" in ents
    assert "cloudflare dns" in ents


def test_extraction_does_not_glue_adjacent_filenames():
    """'roadmap.md agents.md' is two files, not one entity name.

    Gluing produced entity names like 'roadmap.md agents.md gates.md' that match
    no real query and can never be retrieved.
    """
    rec = {"topic": "", "tags": [],
           "content": "Read roadmap.md agents.md gates.md before starting."}
    ents = M._graph_extract_entities(rec)
    assert "roadmap.md agents.md gates.md" not in ents
    assert "roadmap.md" in ents
    assert "agents.md" in ents


def test_extraction_keeps_a_real_multiword_phrase():
    rec = {"topic": "", "tags": [],
           "content": "Jayson ships through Cloudflare DNS today."}
    assert "Cloudflare DNS" in M._graph_extract_entities(rec)


def test_extraction_drops_stopwords():
    rec = {"topic": "the", "tags": ["and"],
           "content": "The thing is not there."}
    ents = [e.lower() for e in M._graph_extract_entities(rec)]
    assert "the" not in ents
    assert "and" not in ents


def test_extraction_is_case_insensitive_against_duplicates():
    rec = {"topic": "Unity", "tags": ["unity"], "content": "unity unity"}
    ents = M._graph_extract_entities(rec)
    assert len([e for e in ents if e.lower() == "unity"]) == 1


def test_extraction_does_not_depend_on_spacy():
    """The old graph path silently produced an empty graph without spaCy."""
    rec = {"topic": "braid", "tags": ["ledger"],
           "content": "Braid commits a node with an Ed25519 signature."}
    assert M._graph_extract_entities(rec)


# --- rebuild + contamination firewall -----------------------------------

def test_rebuild_graph_recovers_from_a_deleted_index(store):
    _seed()
    os.remove(M.GRAPH_INDEX)
    msg = M.rebuild_graph()
    assert "entities" in msg
    assert M.recall_graph("unity", hops=1)["found"] is True


def test_rebuild_graph_reports_honest_counts(store):
    _seed()
    g = M._load_graph()
    msg = M.rebuild_graph()
    assert str(len(g["nodes"])) in msg


def test_simulated_content_never_enters_the_graph(store):
    M.remember_simulated("imagined", "Zephyra is a fictional city",
                         scenario="test")
    if os.path.exists(M.GRAPH_INDEX):
        keys = set(M._load_graph()["nodes"].keys())
        assert "zephyra" not in keys
    else:
        assert not os.path.exists(M.GRAPH_INDEX)


def test_graph_index_rejects_a_simulated_record_directly():
    fake = {"id": "x", "ts": "t", "topic": "t", "tags": [], "content": "c",
            "origin": "simulated", "store": "simulated"}
    with pytest.raises(ValueError, match="Refusing to add"):
        M._add_to_graph_index(fake)


def test_health_is_computed_from_the_persisted_graph(store):
    _seed()
    h = M.index_health()
    g = json.load(open(M.GRAPH_INDEX))
    assert h["indexes"]["graph"]["entities"] == len(g["nodes"])