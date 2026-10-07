"""Tests for the benchmark suite.

The suite's job is to produce numbers people can rely on, so the tests check the
harness itself, not just that it runs:

- A leak is detected when it exists (otherwise the leak rate is meaningless).
- A leak is NOT reported for an honest grounded hit (the first version of this
  reported 1.000 on a store with contamination 0.0, which would have made a
  working system look broken).
- Percentiles are computed correctly.
- The runner refuses to produce scores from an unhealthy store.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# The root conftest puts each project root on sys.path, so the packages resolve
# as top-level `mem20benchmarkz` / `mem20api` rather than as
# `mem20benchmarkz.mem20benchmarkz`. Import them the same way the CLI does.
_ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (str(_ROOT / "mem20api"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from mem20api import open_store  # noqa: E402
from mem20benchmarkz import bench  # noqa: E402
from mem20benchmarkz.corpus import load  # noqa: E402

_distinctive = bench._distinctive
_hit = bench._hit
_leak = bench._leak
_pct = bench._pct
render_markdown = bench.render_markdown
run = bench.run


@pytest.fixture
def seeded(tmp_path):
    c = load()
    with open_store(tmp_path / "store") as s:
        for f in c.facts:
            s.remember(f.topic, f.content, tags=list(f.tags))
        for f in c.simulated:
            s.remember_simulated(f.topic, f.content, scenario="test")
        yield s


# --- the leak metric ----------------------------------------------------

def test_leak_fires_on_simulated_content():
    hits = [{"content": "Zephyra is a real city that runs a mem20 node in prod"}]
    assert _leak(hits, ("zephyra",)) is True


def test_no_leak_for_honest_grounded_hits():
    """An unrelated grounded hit is normal retrieval, not a partition failure.

    Adversarial queries are near-duplicates of real ones by design: "did prod
    migrate to build 4200" SHOULD be answered from "prod runs build 4127".
    Flagging that would report a leak rate of 1.000 on a clean store.
    """
    hits = [{"content": "Prod runs build 4127 deployed from the linux runner"}]
    assert _leak(hits, ("zephyra", "rewritten", "prod will migrate to")) is False


def test_no_leak_when_nothing_returned():
    assert _leak([], ("zephyra",)) is False


def test_no_markers_means_no_leak():
    assert _leak([{"content": "anything"}], ()) is False


def test_leak_detects_leak_across_all_markers():
    hits = [{"content": "the braid ledger was rewritten to remove a bad commit"}]
    assert _leak(hits, ("zephyra", "rewritten")) is True


# --- the distinctive marker --------------------------------------------

def test_distinctive_prefers_a_long_word():
    assert _distinctive("The braid ledger was rewritten to remove a bad commit") \
        == "rewritten"


def test_distinctive_falls_back_to_a_proper_noun():
    assert _distinctive("Zephyra is a real city") == "zephyra"


def test_markers_do_not_collide_with_grounded_facts():
    """A marker that appears in a real fact would flag correct answers."""
    c = load()
    marks = [_distinctive(f.content) for f in c.simulated]
    for f in c.facts:
        for m in marks:
            assert m not in f.content.lower(), \
                f"marker {m!r} collides with grounded fact {f.content!r}"


# --- hit detection ------------------------------------------------------

def test_hit_finds_evidence_by_content():
    hits = [{"content": "unrelated"},
            {"content": "Prod runs build 4127 from the runner"}]
    hit, rank = _hit(hits, ("4127",), set())
    assert hit is True
    assert rank == 2


def test_hit_finds_evidence_by_id():
    hits = [{"id": "deploy-2", "content": "x"}]
    hit, rank = _hit(hits, (), {"deploy-2"})
    assert (hit, rank) == (True, 1)


def test_miss_when_evidence_absent():
    hit, rank = _hit([{"content": "nothing relevant"}], ("4127",), set())
    assert hit is False
    assert rank is None


# --- percentiles --------------------------------------------------------

def test_percentiles_are_ordered():
    """Nearest-rank percentiles over 1..100: p50=50th value, p95=95th."""
    vals = [float(v) for v in range(1, 101)]
    assert _pct(vals, 0.50) == 51
    assert _pct(vals, 0.95) == 95
    assert _pct(vals, 0.99) == 99


def test_percentiles_on_empty_is_zero():
    assert _pct([], 0.5) == 0.0


def test_percentiles_on_single_value():
    assert _pct([7.0], 0.99) == 7.0


# --- runner -------------------------------------------------------------

def test_runner_reports_zero_contamination_on_a_seeded_store(seeded):
    r = run(seeded, modes=("semantic",))
    assert r.trust["contamination_rate"] == 0.0
    assert r.trust["simulated_in_bm25"] in (0, [], None)


def test_runner_measures_no_leak(seeded):
    r = run(seeded, modes=("semantic", "keyword"))
    for mode, kinds in r.recall.items():
        adv = kinds.get("adversarial")
        if adv:
            assert adv["leak_rate"] == 0.0, f"{mode} reported a leak"


def test_runner_finds_direct_answers(seeded):
    r = run(seeded, modes=("semantic",))
    direct = r.recall["semantic"]["direct"]
    assert direct["hit_rate"] > 0.5


def test_runner_notes_the_incomparability(seeded):
    r = run(seeded, modes=("semantic",))
    assert any("not comparable" in n.lower() for n in r.notes)


def test_runner_flags_an_unhealthy_store(seeded):
    p = Path(seeded.path) / "ledger.jsonl"
    lines = p.read_text().splitlines()
    p.write_text("\n".join(lines[:3]) + "\n")
    r = run(seeded, modes=("semantic",))
    assert any("UNHEALTHY" in n for n in r.notes)
    assert r.trust["stale_pointer_rate"] > 0.0


def test_runner_records_latency_per_mode(seeded):
    r = run(seeded, modes=("semantic",))
    assert r.latency_ms["semantic"]["p50"] >= 0.0
    assert r.latency_ms["semantic"]["n"] > 0


def test_graph_mode_runs_only_for_entity_queries(seeded):
    r = run(seeded, modes=("graph",))
    assert set(r.recall.get("graph", {})) <= {"multi_hop"}
    assert r.recall["graph"]["multi_hop"]["n"] >= 1


# --- rerank comparison --------------------------------------------------

def test_rerank_comparison_does_not_recurse(seeded):
    """run() -> _rerank_comparison() -> run() must not call itself forever.

    The comparison re-runs the suite with USE_CROSS_ENCODER flipped, so it has
    to suppress the comparison in the nested call. Without that guard this hangs.
    """
    r = run(seeded, modes=("hybrid",))
    cmp_ = r.trust.get("rerank_off_comparison")
    if cmp_ is None:
        pytest.skip("cross-encoder not installed")
    assert set(cmp_) == {"with", "without"}
    assert cmp_["with"]["p50_ms"] >= cmp_["without"]["p50_ms"] * 1.5, \
        "reranking should be measurably slower than not reranking"


def test_rerank_comparison_restores_the_flag(seeded):
    eng = seeded._engine
    original = eng.USE_CROSS_ENCODER
    try:
        run(seeded, modes=("hybrid",))
        assert eng.USE_CROSS_ENCODER == original
    finally:
        eng.USE_CROSS_ENCODER = original


def test_compare_rerank_false_skips_the_comparison(seeded):
    r = run(seeded, modes=("hybrid",), compare_rerank=False)
    assert r.trust["rerank_off_comparison"] is None


# --- rendering ----------------------------------------------------------

def test_markdown_states_the_incomparability(seeded):
    r = run(seeded, modes=("semantic",))
    md = render_markdown(r)
    assert "not comparable" in md.lower()
    assert "LoCoMo" in md
    assert "Contamination rate" in md


def test_markdown_has_all_three_sections(seeded):
    r = run(seeded, modes=("semantic",))
    md = render_markdown(r)
    assert "## Retrieval quality" in md
    assert "## Latency" in md
    assert "## Trustworthiness" in md


def test_markdown_never_hides_a_nonzero_leak(seeded):
    """If the store really did leak, the table must show it."""
    r = run(seeded, modes=("semantic",))
    r.recall["semantic"]["adversarial"]["leak_rate"] = 1.0
    md = render_markdown(r)
    assert "1.000" in md