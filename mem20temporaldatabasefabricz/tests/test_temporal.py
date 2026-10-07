"""Tests for the bi-temporal engine.

Deterministic by construction: an injected clock, no sleeps, no real time. Every
test terminates; a temporal test suite that waits on wall-clock time is a
defect.
"""

from __future__ import annotations

import pytest

from mem20temporaldatabasefabricz.temporal import (
    BiTemporalEngine, ChainError, InvariantError, TemporalStore, contains,
    overlaps, parse_ts, version_id_for,
)

T0 = "2026-03-01T00:00:00+00:00"
T1 = "2026-03-01T06:00:00+00:00"
T2 = "2026-03-01T12:00:00+00:00"
T3 = "2026-03-01T18:00:00+00:00"
T4 = "2026-03-02T00:00:00+00:00"


class Clock:
    """A hand-advanced clock. Every instant in these tests is explicit."""

    def __init__(self, start: str = T0):
        self.at = start
        self.steps = [start]

    def __call__(self) -> str:
        return self.at

    def set(self, value: str) -> str:
        self.at = value
        self.steps.append(value)
        return self.at


@pytest.fixture()
def clock():
    return Clock()


@pytest.fixture()
def engine(tmp_path, clock):
    store = TemporalStore(tmp_path / "temporal.db")
    yield BiTemporalEngine(store, clock=clock)
    store.close()


class TestIntervalAlgebra:
    def test_half_open_start_is_inside(self):
        assert contains(T1, T2, T1) is True

    def test_half_open_end_is_outside(self):
        assert contains(T1, T2, T2) is False

    def test_open_end_never_closes(self):
        assert contains(T1, None, "2099-01-01T00:00:00+00:00") is True

    def test_absent_start_reaches_back(self):
        assert contains(None, T1, "2000-01-01T00:00:00+00:00") is True

    def test_instant_before_start_is_outside(self):
        assert contains(T1, T2, T0) is False

    def test_offsets_are_normalised_not_lexicographic(self):
        """+05:00 and Z must compare by instant, not by string."""
        assert contains("2026-03-01T06:00:00+00:00", None,
                        "2026-03-01T11:30:00+05:30") is True

    def test_z_suffix_is_accepted(self):
        assert contains("2026-03-01T00:00:00Z", None, "2026-03-01T01:00:00Z") is True

    def test_naive_timestamp_is_refused(self):
        with pytest.raises(ValueError, match="no timezone"):
            parse_ts("2026-03-01T00:00:00")

    def test_garbage_timestamp_is_refused(self):
        with pytest.raises(ValueError, match="ISO-8601"):
            parse_ts("last tuesday-ish")

    def test_touching_intervals_do_not_overlap(self):
        assert overlaps(T1, T2, T2, T3) is False

    def test_overlapping_intervals_overlap(self):
        assert overlaps(T1, T3, T2, T4) is True


class TestVersionIdentity:
    def test_version_id_is_content_addressed(self):
        a = version_id_for("s", "a", T1, "v")
        b = version_id_for("s", "a", T1, "v")
        assert a == b

    def test_version_id_changes_with_value(self):
        assert version_id_for("s", "a", T1, "v1") != version_id_for("s", "a", T1, "v2")

    def test_version_id_changes_with_known_time(self):
        assert version_id_for("s", "a", T1, "v") != version_id_for("s", "a", T2, "v")


class TestTheBugThisExistsFor:
    """The defect: a correction destroys the ability to ask about the past."""

    def test_pre_correction_truth_survives_a_correction(self, engine, clock):
        engine.assert_belief("deploy.target", "value", "staging", known_at=T1)
        engine.correct("deploy.target", "value", "production", known_at=T2)

        past = engine.query("deploy.target", valid_at=T1, known_at=T1)
        assert past.value_refs() == ["staging"]
        assert past.slice_name == "valid_then_known_then"

    def test_correction_does_not_rewrite_valid_time(self, engine):
        first = engine.assert_belief("deploy.target", "value", "staging", known_at=T1)
        engine.correct("deploy.target", "value", "production", known_at=T2)

        after = engine.query("deploy.target", valid_at=T3, known_at=T3)
        assert after.value_refs() == ["production"]
        # The new version inherited the ORIGINAL valid_from: correcting a belief
        # does not make the claim newly true.
        assert after.versions[0].valid_from == first.valid_from == T1

    def test_current_view_shows_only_the_latest(self, engine):
        engine.assert_belief("deploy.target", "value", "staging", known_at=T1)
        engine.correct("deploy.target", "value", "production", known_at=T2)

        now = engine.query("deploy.target")
        assert now.value_refs() == ["production"]

    def test_old_version_is_never_deleted(self, engine):
        engine.assert_belief("deploy.target", "value", "staging", known_at=T1)
        engine.correct("deploy.target", "value", "production", known_at=T2)
        engine.correct("deploy.target", "value", "canary", known_at=T3)

        chain = engine.history("deploy.target")
        assert [v.value_ref for v in chain] == ["staging", "production", "canary"]

    def test_believed_then_view_excludes_the_later_correction(self, engine):
        engine.assert_belief("deploy.target", "value", "staging", known_at=T1)
        engine.correct("deploy.target", "value", "production", known_at=T2)

        believed_then = engine.query("deploy.target", known_at=T1)
        assert believed_then.value_refs() == ["staging"]


class TestFourSlices:
    def test_late_arriving_fact_lands_in_valid_then_known_now(self, engine):
        # Learned at T3, but it was true since T1. A single-axis store either
        # invents the fact in the past or loses the past entirely.
        engine.assert_belief("deploy.target", "value", "staging",
                              valid_from=T1, known_at=T3)

        # The as-of join: the past, judged against everything known today.
        # known_at omitted == "now" on the belief axis.
        retro = engine.query("deploy.target", valid_at=T1)
        assert retro.slice_name == "valid_then_known_now"
        assert retro.value_refs() == ["staging"]

    def test_believed_then_but_still_true_is_valid_now_known_then(self, engine):
        engine.assert_belief("cfg.pool", "size", "8", known_at=T1)
        # valid axis omitted == now; known axis probed at T1. "Were we right?"
        still_true = engine.query("cfg.pool", known_at=T1)
        assert still_true.slice_name == "valid_now_known_then"
        assert still_true.value_refs() == ["8"]

    def test_historical_view_is_valid_then_known_then(self, engine):
        engine.assert_belief("cfg.pool", "size", "8", known_at=T1)
        engine.correct("cfg.pool", "size", "16", known_at=T2)
        old = engine.query("cfg.pool", valid_at=T1, known_at=T1)
        assert old.slice_name == "valid_then_known_then"

    def test_all_four_slices_are_reported(self, engine):
        slices = engine.four_slices("cfg.pool", T3)
        assert set(slices["slices"]) == {
            "valid_now_known_now", "valid_then_known_now",
            "valid_now_known_then", "valid_then_known_then"}


class TestInvariants:
    def test_cannot_assert_over_an_open_belief(self, engine):
        engine.assert_belief("s", "a", "v1", known_at=T1)
        with pytest.raises(InvariantError, match="correct\\(\\)"):
            engine.assert_belief("s", "a", "v2", known_at=T2)

    def test_cannot_correct_an_empty_attribute(self, engine):
        with pytest.raises(InvariantError, match="nothing to correct"):
            engine.correct("s", "a", "v1", known_at=T1)

    def test_correction_cannot_predate_what_it_replaces(self, engine):
        engine.assert_belief("s", "a", "v1", known_at=T2)
        with pytest.raises(InvariantError, match="cannot be known before"):
            engine.correct("s", "a", "v2", known_at=T1)

    def test_only_one_open_belief_at_a_time(self, engine):
        engine.assert_belief("s", "a", "v1", known_at=T1)
        engine.correct("s", "a", "v2", known_at=T2)
        engine.correct("s", "a", "v3", known_at=T3)
        open_versions = [v for v in engine.history("s", "a") if v.known_to is None]
        assert len(open_versions) == 1
        assert open_versions[0].value_ref == "v3"

    def test_expire_must_move_time_forward(self, engine):
        engine.assert_belief("s", "a", "v1", valid_from=T2, known_at=T2)
        with pytest.raises(InvariantError, match="must be after valid_from"):
            engine.expire("s", "a", valid_to=T1)

    def test_expire_closes_valid_time_not_known_time(self, engine):
        engine.assert_belief("s", "a", "v1", valid_from=T1, known_at=T1)
        engine.expire("s", "a", valid_to=T2)
        latest = engine.history("s", "a")[-1]
        assert latest.valid_to == T2
        assert latest.known_to is None


class TestRetractVersusExpire:
    def test_retract_closes_belief_and_leaves_truth(self, engine):
        engine.assert_belief("s", "a", "v1", valid_from=T1, known_at=T1)
        engine.retract("s", "a", known_at=T2)

        v = engine.history("s", "a")[0]
        assert v.known_to == T2
        assert v.valid_to is None, "retracting a belief must not edit what was true"

    def test_after_retraction_nothing_is_currently_believed(self, engine):
        engine.assert_belief("s", "a", "v1", known_at=T1)
        engine.retract("s", "a", known_at=T2)
        assert len(engine.query("s")) == 0

    def test_but_history_is_still_reachable(self, engine):
        engine.assert_belief("s", "a", "v1", known_at=T1)
        engine.retract("s", "a", known_at=T2)
        assert engine.query("s", known_at=T1).value_refs() == ["v1"]

    def test_retract_can_then_be_reasserted(self, engine):
        engine.assert_belief("s", "a", "v1", known_at=T1)
        engine.retract("s", "a", known_at=T2)
        engine.assert_belief("s", "a", "v1", known_at=T3)
        assert engine.query("s").value_refs() == ["v1"]
        assert len(engine.history("s", "a")) == 2

    def test_retract_on_empty_is_a_no_op(self, engine):
        assert engine.retract("s", "a", known_at=T1) == []


class TestDeterminismAndIdempotency:
    def test_repeated_assert_is_idempotent(self, engine):
        a = engine.assert_belief("s", "a", "v1", known_at=T1)
        b = engine.assert_belief("s", "a", "v1", known_at=T1)
        assert a.version_id == b.version_id
        assert len(engine.history("s", "a")) == 1

    def test_history_order_is_stable(self, engine):
        engine.assert_belief("s", "a", "v1", known_at=T1)
        engine.correct("s", "a", "v2", known_at=T2)
        engine.correct("s", "a", "v3", known_at=T3)
        first = [v.version_id for v in engine.history("s", "a")]
        second = [v.version_id for v in engine.history("s", "a")]
        assert first == second

    def test_identical_sequences_produce_identical_answers(self, tmp_path, clock):
        results = []
        for name in ("one.db", "two.db"):
            store = TemporalStore(tmp_path / name)
            eng = BiTemporalEngine(store, clock=clock)
            eng.assert_belief("s", "a", "v1", known_at=T1)
            eng.correct("s", "a", "v2", known_at=T2)
            results.append([v.version_id for v in eng.query("s", valid_at=T1, known_at=T1).versions])
            store.close()
        assert results[0] == results[1]


class TestChainIntegrity:
    def test_chain_verifies_after_writes(self, engine):
        engine.assert_belief("s", "a", "v1", known_at=T1)
        engine.correct("s", "a", "v2", known_at=T2)
        assert engine.store.verify_chain()["ok"] is True

    def test_every_write_appends_an_event(self, engine):
        engine.assert_belief("s", "a", "v1", known_at=T1)
        engine.correct("s", "a", "v2", known_at=T2)
        engine.retract("s", "a", known_at=T3)
        kinds = [e["kind"] for e in engine.store.events()]
        assert "assert" in kinds and "correct" in kinds and "retract" in kinds

    def test_tampering_is_detected(self, engine):
        engine.assert_belief("s", "a", "v1", known_at=T1)
        engine.store._conn.execute(
            "UPDATE events SET payload = ? WHERE seq = 1", ('{"tampered":true}',))
        engine.store._conn.commit()
        with pytest.raises(ChainError, match="mismatch|prev_hash"):
            engine.store.verify_chain()

    def test_deleting_an_event_breaks_the_chain(self, engine):
        engine.assert_belief("s", "a", "v1", known_at=T1)
        engine.correct("s", "a", "v2", known_at=T2)
        engine.store._conn.execute("DELETE FROM events WHERE seq = 1")
        engine.store._conn.commit()
        with pytest.raises(ChainError):
            engine.store.verify_chain()


class TestExplain:
    def test_explain_reports_the_chain_and_the_answer(self, engine):
        engine.assert_belief("deploy.target", "value", "staging", known_at=T1)
        engine.correct("deploy.target", "value", "production", known_at=T2)

        report = engine.explain("deploy.target", valid_at=T1, known_at=T1)
        assert report["answer"]["count"] == 1
        assert report["answer"]["versions"][0]["value_ref"] == "staging"
        assert report["full_chain_length"] == 2

    def test_explain_marks_what_superseded_each_version(self, engine):
        first = engine.assert_belief("s", "a", "v1", known_at=T1)
        engine.correct("s", "a", "v2", known_at=T2)

        report = engine.explain("s", valid_at=T1, known_at=T1)
        answered = report["answer"]["versions"][0]
        assert answered["provenance"]["superseded_by"], "superseded_by should be populated"

    def test_correction_records_what_it_corrects(self, engine):
        first = engine.assert_belief("s", "a", "v1", known_at=T1)
        second = engine.correct("s", "a", "v2", known_at=T2)
        assert second.provenance["corrects"] == first.version_id


class TestPersistence:
    def test_state_survives_reopen(self, tmp_path, clock):
        path = tmp_path / "persist.db"
        store = TemporalStore(path)
        eng = BiTemporalEngine(store, clock=clock)
        eng.assert_belief("s", "a", "v1", known_at=T1)
        eng.correct("s", "a", "v2", known_at=T2)
        store.close()

        reopened = TemporalStore(path)
        eng2 = BiTemporalEngine(reopened, clock=clock)
        assert eng2.query("s", valid_at=T1, known_at=T1).value_refs() == ["v1"]
        assert eng2.query("s").value_refs() == ["v2"]
        assert reopened.verify_chain()["ok"] is True
        reopened.close()

    def test_export_is_deterministic(self, engine):
        engine.assert_belief("s", "a", "v1", known_at=T1)
        engine.assert_belief("s", "b", "v2", known_at=T1)
        one = engine.export()
        two = engine.export()
        assert [r["version_id"] for r in one["versions"]] == \
               [r["version_id"] for r in two["versions"]]

class TestEventTimeCoverage:
    """The valid axis is only as good as the event times behind it."""

    def test_counts_declared_and_assumed(self, engine):
        engine.store.put_version({
            "version_id": "v1", "subject": "s", "attribute": "a",
            "valid_from": T0, "known_from": T0, "value_ref": "x",
            "provenance": {"event_time_basis": "declared"}})
        engine.store.put_version({
            "version_id": "v2", "subject": "s", "attribute": "b",
            "valid_from": T0, "known_from": T0, "value_ref": "y",
            "provenance": {"event_time_basis": "assumed_ingestion"}})
        from mem20temporaldatabasefabricz.temporal.engine import event_time_coverage
        cov = event_time_coverage(engine.store.all_versions())
        assert cov["declared_event_time"] == 1
        assert cov["assumed_event_time"] == 1
        assert cov["declared_fraction"] == 0.5
        assert cov["as_of_join_is_sound"] is False

    def test_sound_only_when_every_version_is_declared(self, engine):
        engine.store.put_version({
            "version_id": "v1", "subject": "s", "attribute": "a",
            "valid_from": T0, "known_from": T0, "value_ref": "x",
            "provenance": {"event_time_basis": "declared"}})
        from mem20temporaldatabasefabricz.temporal.engine import event_time_coverage
        assert event_time_coverage(engine.store.all_versions())["as_of_join_is_sound"] is True

    def test_legacy_versions_without_provenance_count_as_assumed(self, engine):
        engine.store.put_version({
            "version_id": "v1", "subject": "s", "attribute": "a",
            "valid_from": T0, "known_from": T0, "value_ref": "x", "provenance": {}})
        from mem20temporaldatabasefabricz.temporal.engine import event_time_coverage
        cov = event_time_coverage(engine.store.all_versions())
        assert cov["assumed_event_time"] == 1

    def test_empty_store_is_trivially_sound(self):
        from mem20temporaldatabasefabricz.temporal.engine import event_time_coverage
        cov = event_time_coverage([])
        assert cov["versions"] == 0 and cov["as_of_join_is_sound"] is True


class TestLoadProvenance:
    """Regression: SQLite returns the provenance column as JSON text, not a dict.

    An endpoint returning 500 because it assumed a dict was the real failure this
    caught; it would have silently mis-counted had the shape differed more gently.
    """

    def test_parses_json_text(self):
        from mem20temporaldatabasefabricz.temporal.engine import load_provenance
        assert load_provenance('{"event_time_basis":"declared"}')["event_time_basis"] == "declared"

    def test_passes_through_dicts(self):
        from mem20temporaldatabasefabricz.temporal.engine import load_provenance
        assert load_provenance({"a": 1}) == {"a": 1}

    def test_empty_and_garbage_become_empty_dicts(self):
        from mem20temporaldatabasefabricz.temporal.engine import load_provenance
        for value in (None, "", "not json", "[]", 5):
            assert load_provenance(value) == {}

    def test_coverage_survives_string_provenance(self, engine):
        """The exact shape SQLite hands back."""
        engine.store.put_version({
            "version_id": "v1", "subject": "s", "attribute": "a",
            "valid_from": T0, "known_from": T0, "value_ref": "x",
            "provenance": {"event_time_basis": "declared"}})
        rows = engine.store.all_versions()
        assert isinstance(rows[0]["provenance"], str), "expected SQLite's JSON text"
        from mem20temporaldatabasefabricz.temporal.engine import event_time_coverage
        assert event_time_coverage(rows)["declared_event_time"] == 1
