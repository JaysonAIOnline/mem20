"""Tests for the grounded/simulated firewall across every retrieval surface.

The vector, BM25 and graph index write paths call _assert_grounded. Pinned
blocks are a fourth surface: they are injected at session start and are immune
to pruning and supersede, so they need the same write-time firewall and the same
audit coverage. Detection only reports; it never rewrites stored content.
"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SIM_TEXT = "the dragon guards the vault beneath the north gate of the city"


@pytest.fixture()
def mem(tmp_path, monkeypatch):
    """A memory module bound to an isolated store, reloaded per test."""
    monkeypatch.setenv("MEM20_STORE_PATH", str(tmp_path / "store"))
    for mod in [m for m in list(sys.modules) if m == "memory"]:
        del sys.modules[mod]
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    module = importlib.import_module("memory")
    yield module
    for name in [m for m in list(sys.modules) if m == "memory"]:
        del sys.modules[name]


class TestIndexWritePathsGuarded:
    """The three index write paths already had the firewall. Prove it holds."""

    def test_all_index_write_paths_call_the_firewall(self, mem):
        for fn in ("_add_to_vector_index", "_add_to_bm25_index", "_add_to_graph_index"):
            names = mem.__dict__[fn].__code__.co_names
            assert "_assert_grounded" in names, f"{fn} lost its grounded firewall"

    def test_firewall_rejects_simulated_record(self, mem):
        with pytest.raises(ValueError, match="Only grounded records"):
            mem._assert_grounded(
                {"id": "s1", "origin": "simulated", "store": "simulated"}, "vector")

    def test_firewall_allows_grounded_and_untagged(self, mem):
        mem._assert_grounded({"id": "g1", "origin": "grounded", "store": "grounded"}, "bm25")
        mem._assert_grounded({"id": "g2"}, "bm25")


class TestSimulatedPartitionStaysIsolated:
    def test_simulated_never_lands_in_the_grounded_ledger(self, mem):
        rec = mem.remember_simulated(topic="mythos", content=SIM_TEXT)
        assert not any(r.get("id") == rec["id"] for r in mem._load_ledger())
        assert any(r.get("id") == rec["id"] for r in mem._load_simulated_ledger())

    def test_remember_refuses_the_simulated_write_path(self, mem):
        with pytest.raises(PermissionError, match="grounded-only"):
            mem.remember(topic="mythos", content="x", _allow_simulated=True)


class TestPinnedBlockFirewall:
    """Half one: a pin that DECLARES simulated provenance is refused."""

    def test_declared_simulated_pin_is_refused(self, mem):
        with pytest.raises(ValueError, match="Only grounded records"):
            mem.pin_block("bad", SIM_TEXT, origin="simulated")

    def test_declared_simulated_store_is_refused(self, mem):
        with pytest.raises(ValueError, match="pinned"):
            mem.pin_block("bad", SIM_TEXT, origin="simulated", store="simulated")

    def test_authored_pin_still_works_and_is_tagged(self, mem):
        out = mem.pin_block("good", "Jayson prefers tailwind over bootstrap.",
                            reason="stated preference")
        assert out["pinned"] is True
        assert out["origin"] == "grounded"
        block = mem._load_pinned()["blocks"]["good"]
        assert block["origin"] == "grounded"
        assert block["store"] == "grounded"
        assert block["epistemic_status"] == "user_stated"
        assert block["content_hash"]

    def test_pin_records_provenance_for_the_audit(self, mem):
        mem.pin_block("good", "an authored note about the build")
        block = mem._load_pinned()["blocks"]["good"]
        for field in ("origin", "store", "epistemic_status", "pinned_ts", "actor"):
            assert field in block, f"pinned entry is missing {field}"


class TestPinnedBlockAudit:
    """Half two: an UNDECLARED simulated copy is reported by the audit.

    No write-time firewall can catch this - the caller declares nothing wrong -
    so the audit is the only thing standing between imagined content and
    unconditional session-start injection.
    """

    def test_audit_detects_simulated_content_pinned_as_grounded(self, mem):
        mem.remember_simulated(topic="mythos", content=SIM_TEXT)
        mem.pin_block("smuggled", f"Notes: {SIM_TEXT}. See the plan.")

        audit = mem.audit_contamination()
        assert audit["status"] == "CONTAMINATED"
        hits = audit["violations_pinned_simulated_content"]
        assert [h["block_id"] for h in hits] == ["smuggled"]

    def test_audit_recommendation_is_not_no_action_while_contaminated(self, mem):
        """The rate divides by grounded facts, so a fresh store reads 0.0 while
        being contaminated. Recommendation must follow the status, not the rate."""
        mem.remember_simulated(topic="mythos", content=SIM_TEXT)
        mem.pin_block("smuggled", SIM_TEXT)

        audit = mem.audit_contamination()
        assert audit["contamination_rate"] == 0.0
        assert audit["status"] == "CONTAMINATED"
        assert audit["recommendation"] != "No action needed."

    def test_audit_does_not_rewrite_the_smuggled_block(self, mem):
        mem.remember_simulated(topic="mythos", content=SIM_TEXT)
        mem.pin_block("smuggled", SIM_TEXT)
        before = mem._load_pinned()["blocks"]["smuggled"]["content"]

        mem.audit_contamination()

        assert mem._load_pinned()["blocks"]["smuggled"]["content"] == before

    def test_authored_pin_is_not_a_violation(self, mem):
        mem.remember_simulated(topic="mythos", content=SIM_TEXT)
        mem.pin_block("authored", "The deploy target is production, per the rollout doc.")

        audit = mem.audit_contamination()
        assert audit["violations_pinned_simulated_content"] == []
        assert audit["status"] == "CLEAN"

    def test_short_shared_phrasing_is_not_a_violation(self, mem):
        """Below MIN_SIM_CONTENT_MATCH a match is incidental, not a copied claim."""
        mem.remember_simulated(topic="mythos", content="vault")
        mem.pin_block("authored", "the vault door needs a new hinge")
        assert mem.audit_contamination()["violations_pinned_simulated_content"] == []

    def test_graph_surface_is_audited(self, mem):
        audit = mem.audit_contamination()
        assert "violations_simulated_in_graph" in audit

    def test_clean_store_reports_clean(self, mem):
        mem.remember(topic="ops", content="the runbook lives in the ops directory")
        audit = mem.audit_contamination()
        assert audit["status"] == "CLEAN"
        assert audit["recommendation"] == "No action needed."


class TestBackwardsCompatibility:
    def test_untagged_pinned_block_is_not_a_violation(self, mem):
        """Blocks pinned before this change carry no provenance tags. They must
        stay readable and must not suddenly count as violations."""
        mem.remember_simulated(topic="mythos", content=SIM_TEXT)
        data = mem._load_pinned()
        data["blocks"]["legacy"] = {"content": "an old pinned block", "reason": "",
                                    "pinned_ts": "2026-01-01T00:00:00+00:00", "actor": "agent"}
        data["order"].append("legacy")
        mem._save_pinned(data)

        audit = mem.audit_contamination()
        assert "legacy" not in audit["violations_pinned_origin_not_grounded"]
        assert audit["status"] == "CLEAN"

    def test_untagged_pinned_block_is_still_readable(self, mem):
        data = mem._load_pinned()
        data["blocks"]["legacy"] = {"content": "an old pinned block", "reason": "",
                                    "pinned_ts": "2026-01-01T00:00:00+00:00", "actor": "agent"}
        data["order"].append("legacy")
        mem._save_pinned(data)
        assert mem.get_pinned_block("legacy")

    def test_pin_block_signature_is_backwards_compatible(self, mem):
        """Old positional call shape must still work."""
        out = mem.pin_block("old-style", "content here", "a reason", "an-actor")
        assert out["pinned"] is True

    def test_repin_preserves_the_existing_refusal(self, mem):
        mem.pin_block("dup", "first")
        with pytest.raises(ValueError, match="already pinned"):
            mem.pin_block("dup", "second")