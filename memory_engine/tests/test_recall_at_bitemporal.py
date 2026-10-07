"""Tests for correction-aware as-of recall.

The defect these lock down: memory.py's supersede() writes a marker row and
leaves the original untouched, so the original still reads valid_to=null. The
as-of query used to strip superseded rows before filtering on time, which made
"what was true before the correction?" unanswerable - the exact question a
bi-temporal store exists to answer.

recall_at(as_of=None) must stay byte-identical to its previous behaviour: the
present has one answer, so superseded rows stay hidden there.
"""

from __future__ import annotations

import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture()
def mem(tmp_path, monkeypatch):
    monkeypatch.setenv("MEM20_STORE_PATH", str(tmp_path / "store"))
    sys.modules.pop("memory", None)
    module = importlib.import_module("memory")
    yield module
    sys.modules.pop("memory", None)


def contents(records):
    return [r.get("content") for r in records]


class TestAsOfSurvivesCorrection:
    def test_pre_correction_truth_is_returned_after_a_correction(self, mem):
        original = mem.remember(topic="deploy.target", content="deploy target is staging")
        learned_at = original["valid_from"]

        mem.supersede(original["id"], "deploy target is production")

        past = mem.recall_at(as_of=learned_at, topic="deploy.target")
        assert contents(past) == ["deploy target is staging"]

    def test_the_correction_is_returned_for_later_instants(self, mem):
        original = mem.remember(topic="deploy.target", content="deploy target is staging")
        corrected = mem.supersede(original["id"], "deploy target is production")

        later = mem.recall_at(as_of=corrected["valid_from"], topic="deploy.target")
        assert contents(later) == ["deploy target is production"]

    def test_history_accumulates_rather_than_vanishing(self, mem):
        original = mem.remember(topic="svc", content="runs on port 8080")
        first = original["valid_from"]
        second = mem.supersede(original["id"], "runs on port 9090")
        third = mem.supersede(second["id"], "runs on port 80")

        assert contents(mem.recall_at(as_of=first, topic="svc")) == ["runs on port 8080"]
        assert contents(mem.recall_at(as_of=second["valid_from"], topic="svc")) == \
            ["runs on port 9090"]
        assert contents(mem.recall_at(as_of=third["valid_from"], topic="svc")) == \
            ["runs on port 80"]

    def test_current_view_is_unchanged_by_the_fix(self, mem):
        original = mem.remember(topic="deploy.target", content="staging")
        mem.supersede(original["id"], "production")
        assert contents(mem.recall(topic="deploy.target")) == ["production"]

    def test_no_as_of_query_returns_only_the_latest(self, mem):
        original = mem.remember(topic="svc", content="v1")
        mem.supersede(original["id"], "v2")
        now_view = mem.recall_at(topic="svc")
        assert contents(now_view) == ["v2"]


class TestBoundaryBehaviour:
    def test_half_open_interval_includes_its_start(self, mem):
        rec = mem.remember(topic="svc", content="v1")
        at = mem.recall_at(as_of=rec["valid_from"], topic="svc")
        assert contents(at) == ["v1"]

    def test_half_open_interval_excludes_its_end(self, mem):
        """The instant a correction lands belongs to the correction, not the
        fact it replaced. Half-open [start, end) is what makes that exact."""
        original = mem.remember(topic="svc", content="v1")
        corrected = mem.supersede(original["id"], "v2")
        at_end = mem.recall_at(as_of=corrected["valid_from"], topic="svc")
        assert contents(at_end) == ["v2"]

    def test_instant_before_anything_was_learned_returns_nothing(self, mem):
        mem.remember(topic="svc", content="v1")
        assert mem.recall_at(as_of="2000-01-01T00:00:00+00:00", topic="svc") == []


class TestNonTemporalBehaviourIsUntouched:
    def test_topic_filter_still_applies_to_as_of(self, mem):
        original = mem.remember(topic="alpha", content="a1")
        mem.supersede(original["id"], "a2")
        assert mem.recall_at(as_of=original["valid_from"], topic="alpha")
        assert mem.recall_at(as_of=original["valid_from"], topic="beta") == []

    def test_tag_filter_still_applies_to_as_of(self, mem):
        original = mem.remember(topic="svc", content="v1", tags=["ops"])
        mem.supersede(original["id"], "v2")
        assert contents(mem.recall_at(as_of=original["valid_from"], topic="svc", tags=["ops"])) == ["v1"]
        assert mem.recall_at(as_of=original["valid_from"], topic="svc", tags=["nope"]) == []

    def test_k_limit_still_applies(self, mem):
        for i in range(6):
            mem.remember(topic="svc", content=f"v{i}")
        assert len(mem.recall_at(topic="svc", k=3)) <= 3

    def test_simulated_stays_excluded_by_default(self, mem):
        mem.remember(topic="svc", content="grounded v1")
        mem.remember_simulated(topic="svc", content="imagined v1")
        found = contents(mem.recall_at(topic="svc"))
        assert "imagined v1" not in found

    def test_correction_axes_helper_reports_both_axes(self, mem):
        original = mem.remember(topic="svc", content="v1")
        mem.supersede(original["id"], "v2")
        recs = mem._load_ledger()
        known_to, valid_to = mem._correction_axes(recs)
        assert str(original["id"]) in known_to
        assert str(original["id"]) in valid_to

    def test_unrelated_topics_are_untouched_by_a_correction(self, mem):
        other = mem.remember(topic="other", content="independent v1")
        original = mem.remember(topic="svc", content="v1")
        mem.supersede(original["id"], "v2")
        assert contents(mem.recall_at(as_of=other["valid_from"], topic="other")) == \
            ["independent v1"]