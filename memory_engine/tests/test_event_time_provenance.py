"""Tests for event-time provenance and validation.

A store that defaults an event time to ingestion time is making an assumption.
This suite makes that assumption visible and refuses the cases where it would be
actively wrong, rather than silently normalising them.
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


class TestEventTimeBasis:
    def test_defaulted_event_time_is_marked_assumed(self, mem):
        rec = mem.remember(topic="t", content="no event time given")
        assert rec["event_time_basis"] == mem.EVENT_TIME_ASSUMED

    def test_declared_event_time_is_marked_declared(self, mem):
        rec = mem.remember(topic="t", content="has an event time",
                           valid_from="2020-01-01T00:00:00+00:00")
        assert rec["event_time_basis"] == mem.EVENT_TIME_DECLARED

    def test_basis_reaches_the_ledger(self, mem):
        mem.remember(topic="t", content="declared", valid_from="2020-01-01T00:00:00+00:00")
        mem.remember(topic="t", content="assumed")
        rows = {r["content"]: r for r in mem._load_ledger()}
        assert rows["declared"]["event_time_basis"] == "declared"
        assert rows["assumed"]["event_time_basis"] == "assumed_ingestion"

    def test_declared_event_time_still_drives_valid_from(self, mem):
        rec = mem.remember(topic="t", content="old news",
                           valid_from="2020-01-01T00:00:00+00:00")
        assert rec["valid_from"] == "2020-01-01T00:00:00+00:00"
        assert rec["ts"] != rec["valid_from"]


class TestEventTimeValidation:
    def test_naive_timestamp_is_refused(self, mem):
        with pytest.raises(ValueError, match="must carry a timezone"):
            mem.remember(topic="t", content="c", valid_from="2020-01-01T00:00:00")

    def test_garbage_is_refused(self, mem):
        with pytest.raises(ValueError, match="ISO-8601"):
            mem.remember(topic="t", content="c", valid_from="not-a-date")

    def test_future_is_refused(self, mem):
        with pytest.raises(ValueError, match="in the future"):
            mem.remember(topic="t", content="c", valid_from="2999-01-01T00:00:00+00:00")

    def test_implausible_past_is_refused(self, mem):
        with pytest.raises(ValueError, match="missing century|more than"):
            mem.remember(topic="t", content="c", valid_from="1620-01-01T00:00:00+00:00")

    def test_legitimate_history_is_accepted(self, mem):
        rec = mem.remember(topic="t", content="ancient but real",
                           valid_from="1999-12-31T00:00:00+00:00")
        assert rec["valid_from"].startswith("1999-12-31")

    def test_offset_is_normalised_to_utc(self, mem):
        rec = mem.remember(topic="t", content="c",
                           valid_from="2020-01-01T05:30:00+05:30")
        assert rec["valid_from"] == "2020-01-01T00:00:00+00:00"

    def test_zz_suffix_is_accepted(self, mem):
        rec = mem.remember(topic="t", content="c", valid_from="2020-01-01T00:00:00Z")
        assert rec["valid_from"] == "2020-01-01T00:00:00+00:00"

    def test_small_clock_skew_is_tolerated(self, mem):
        """Agents and hosts disagree by seconds; refusing that would be pedantry."""
        future = mem._now()
        rec = mem.validate_event_time(future, now=mem._now())
        assert rec

    def test_refused_write_leaves_no_record(self, mem):
        before = len(mem._load_ledger())
        with pytest.raises(ValueError):
            mem.remember(topic="t", content="rejected", valid_from="2999-01-01T00:00:00+00:00")
        assert len(mem._load_ledger()) == before

    def test_validate_is_pure(self, mem):
        original = "2020-01-01T05:30:00+05:30"
        mem.validate_event_time(original)
        assert original == "2020-01-01T05:30:00+05:30"


class TestAdapterReadsTheBasis:
    def test_legacy_rows_without_the_field_count_as_assumed(self, mem):
        sys.path.insert(0, "/opt/mem20/mem20temporaldatabasefabricz")
        from mem20temporaldatabasefabricz.temporal.ledger_adapter import derive_intervals

        intervals = derive_intervals([
            {"id": "a", "action": "remember", "ts": "2026-01-01T00:00:00+00:00",
             "valid_from": "2026-01-01T00:00:00+00:00", "topic": "t", "content": "c"},
        ])
        assert intervals[0].provenance["event_time_basis"] == "assumed_ingestion"

    def test_declared_field_survives_into_provenance(self, mem):
        sys.path.insert(0, "/opt/mem20/mem20temporaldatabasefabricz")
        from mem20temporaldatabasefabricz.temporal.ledger_adapter import derive_intervals

        intervals = derive_intervals([
            {"id": "a", "action": "remember", "ts": "2026-01-02T00:00:00+00:00",
             "valid_from": "2026-01-01T00:00:00+00:00", "topic": "t", "content": "c",
             "event_time_basis": "declared"},
        ])
        assert intervals[0].provenance["event_time_basis"] == "declared"