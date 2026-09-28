"""Tests for mem20wasmz's real logic.

The package had no tests at all. What is worth testing here is the part that
makes decisions and records state: canonical serialisation, stable hashing,
secret redaction, the dependency topological sort, and the safety gate. Those are
the places a silent regression would do real harm.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from mem20wasmz.core import (
    SafetyBlocked,
    canonical,
    clamp,
    mean,
    redact,
    similarity,
    stable_hash,
    topo,
    words,
)

# --- canonical form and hashing ---------------------------------------------


def test_canonical_is_order_independent():
    """Two equal dicts written in different orders must serialise identically."""
    a = {"b": 1, "a": 2}
    b = {"a": 2, "b": 1}
    assert canonical(a) == canonical(b)
    assert stable_hash(a) == stable_hash(b)


def test_canonical_has_no_incidental_whitespace():
    text = canonical({"a": 1, "b": [1, 2]})
    assert ", " not in text and ": " not in text
    assert text == '{"a":1,"b":[1,2]}'


def test_canonical_preserves_unicode_rather_than_escaping_it():
    text = canonical({"note": "café ✓"})
    assert "café ✓" in text


def test_canonical_falls_back_to_str_for_unserialisable_values():
    class Opaque:
        def __str__(self) -> str:
            return "opaque"

    assert "opaque" in canonical({"x": Opaque()})


def test_stable_hash_is_hex_sha256_and_value_sensitive():
    digest = stable_hash({"a": 1})
    assert len(digest) == 64
    int(digest, 16)  # raises if not hex
    assert digest != stable_hash({"a": 2})
    assert digest != stable_hash({"a": "1"}), "1 and '1' must not collide"


def test_stable_hash_handles_nested_structures():
    left = {"a": [{"b": 1}, {"c": [1, 2, {"d": None}]}]}
    right = {"a": [{"b": 1}, {"c": [1, 2, {"d": None}]}]}
    assert stable_hash(left) == stable_hash(right)


# --- redaction ---------------------------------------------------------------


def test_redact_removes_known_secret_keys_at_every_depth():
    payload = {
        "user": "alice",
        "password": "hunter2",
        "nested": {"api_key": "sk-live-123", "keep": "visible"},
        "list": [{"token": "abc"}],
    }
    cleaned = redact(payload)
    assert cleaned["user"] == "alice"
    assert cleaned["nested"]["keep"] == "visible"
    assert cleaned["password"] == "[REDACTED]"
    assert cleaned["nested"]["api_key"] == "[REDACTED]"
    assert cleaned["list"][0]["token"] == "[REDACTED]"


def test_redact_matches_secret_keys_case_insensitively():
    assert redact({"PassWord": "x"})["PassWord"] == "[REDACTED]"
    assert redact({"API_KEY": "x"})["API_KEY"] == "[REDACTED]"


def test_redact_does_not_mutate_its_input():
    payload = {"password": "hunter2"}
    redact(payload)
    assert payload["password"] == "hunter2", "redaction must not rewrite the caller's data"


def test_redact_leaves_scalars_and_unknown_keys_alone():
    assert redact("plain") == "plain"
    assert redact(7) == 7
    assert redact({"note": "fine"}) == {"note": "fine"}


def test_redact_scrubs_a_credential_embedded_in_free_text():
    """An error string has no sensitive KEY, so a dict-only redaction missed these."""
    assert "sekret" not in redact("auth failed for token=sekret-abc123")
    assert redact("auth failed for token=sekret-abc123").endswith("[REDACTED]")
    assert "sk-9" not in redact("api_key: sk-9f8e7d")


def test_redact_does_not_mangle_ordinary_prose():
    """False positives would corrupt real error messages into uselessness."""
    for sentence in (
        "the token was rejected",
        "password policy requires rotation",
        "connection reset by peer",
        "cookies were sent but ignored",
    ):
        assert redact(sentence) == sentence, f"ordinary prose was altered: {sentence!r}"


# --- small numeric and text helpers -----------------------------------------


@pytest.mark.parametrize(
    "value,expected", [(-1.0, 0.0), (0.5, 0.5), (1.0, 1.0), (2.0, 1.0), (float("nan"), 1.0)]
)
def test_clamp_keeps_values_in_range(value, expected):
    assert clamp(value) == pytest.approx(expected)


def test_clamp_respects_explicit_bounds():
    assert clamp(5, lo=0, hi=10) == 5
    assert clamp(-5, lo=0, hi=10) == 0
    assert clamp(50, lo=0, hi=10) == 10


def test_words_lowercases_and_splits_on_non_alphanumerics():
    assert words("Hello, World! 42") == {"hello", "world", "42"}


def test_similarity_is_one_for_identical_text_and_zero_for_disjoint():
    assert similarity("a b c", "a b c") == pytest.approx(1.0)
    assert similarity("alpha", "beta") == 0.0


def test_similarity_is_symmetric_and_bounded():
    left, right = "agent fleet", "fleet of agents"
    assert similarity(left, right) == similarity(right, left)
    assert 0.0 <= similarity(left, right) <= 1.0


def test_similarity_does_not_divide_by_zero_on_empty_input():
    assert similarity("", "") == 0.0


def test_mean_of_empty_is_zero_not_an_error():
    assert mean([]) == 0
    assert mean([2, 4]) == pytest.approx(3.0)


# --- topological sort --------------------------------------------------------


def test_topo_orders_dependencies_before_dependents():
    order, cyclic = topo(["a", "b", "c"], [("a", "b"), ("b", "c")])
    assert cyclic == []
    assert order.index("a") < order.index("b") < order.index("c")


def test_topo_is_deterministic_for_independent_nodes():
    first, _ = topo(["z", "a", "m"], [])
    second, _ = topo(["z", "a", "m"], [])
    assert first == second == ["a", "m", "z"], "ties must break the same way every run"


def test_topo_reports_a_cycle_instead_of_silently_dropping_nodes():
    # root -> a -> b -> a: the cycle is a/b, and root is still orderable.
    order, cyclic = topo(["root", "a", "b"], [("root", "a"), ("a", "b"), ("b", "a")])
    assert order == ["root"]
    assert set(cyclic) == {"a", "b"}, "the nodes in the cycle must be reported"


def test_topo_returns_nothing_ordered_when_everything_is_cyclic():
    order, cyclic = topo(["a", "b"], [("a", "b"), ("b", "a")])
    assert order == []
    assert set(cyclic) == {"a", "b"}


def test_topo_ignores_edges_pointing_at_unknown_nodes():
    order, cyclic = topo(["a"], [("a", "ghost")])
    assert cyclic == []
    assert order == ["a"]


def test_topo_on_an_empty_graph():
    assert topo([], []) == ([], [])


def test_topo_handles_a_diamond():
    order, cyclic = topo(
        ["top", "left", "right", "bottom"],
        [("top", "left"), ("top", "right"), ("left", "bottom"), ("right", "bottom")],
    )
    assert cyclic == []
    assert order.index("top") == 0
    assert order[-1] == "bottom", "the join must come last"


# --- state store -------------------------------------------------------------


def test_state_store_creates_its_parent_directory(tmp_path):
    from mem20wasmz.core import StateStore

    path = tmp_path / "deeply" / "nested" / "state.db"
    StateStore(path)
    assert path.exists()


def test_a_job_survives_closing_and_reopening_the_store(tmp_path):
    from mem20wasmz.core import StateStore

    path = tmp_path / "state.db"
    store = StateStore(path)
    job, created = store.create_job({"goal": "ship", "n": 1})
    assert created is True
    assert store.get_job(job["id"])["state"] == "queued"

    reopened = StateStore(path)
    assert reopened.get_job(job["id"]) is not None, "a job must not vanish on reload"


def test_get_job_returns_none_for_an_unknown_id(tmp_path):
    from mem20wasmz.core import StateStore

    store = StateStore(tmp_path / "s.db")
    assert store.get_job("no-such-job") is None


def test_create_job_is_idempotent_for_the_same_key(tmp_path):
    """A retried request must not create a second job."""
    from mem20wasmz.core import StateStore

    store = StateStore(tmp_path / "s.db")
    first, created_first = store.create_job({"goal": "ship"}, idem="key-1")
    second, created_second = store.create_job({"goal": "ship"}, idem="key-1")
    assert created_first is True
    assert created_second is False, "a retried idem key must not create a second job"
    assert first["id"] == second["id"]
    assert len(store.list_jobs()) == 1


def test_job_state_can_be_advanced_and_cancelled(tmp_path):
    from mem20wasmz.core import StateStore

    store = StateStore(tmp_path / "s.db")
    job, _ = store.create_job({"goal": "ship"})
    store.update_job(job["id"], "running")
    assert store.get_job(job["id"])["state"] == "running"
    assert store.cancel(job["id"]) is True
    assert store.get_job(job["id"])["state"] == "cancelled"


def test_a_finished_job_cannot_be_cancelled(tmp_path):
    from mem20wasmz.core import StateStore

    store = StateStore(tmp_path / "s.db")
    job, _ = store.create_job({"goal": "ship"})
    store.update_job(job["id"], "succeeded", result={"ok": True})
    assert store.cancel(job["id"]) is False, "a settled job must not be cancelled"


def test_cancelling_an_unknown_job_is_false_not_an_error(tmp_path):
    from mem20wasmz.core import StateStore

    assert StateStore(tmp_path / "s.db").cancel("no-such-job") is False


def test_cache_round_trips_and_expires(tmp_path):
    from mem20wasmz.core import StateStore

    store = StateStore(tmp_path / "s.db")
    store.cache_put("k", {"v": 1})
    assert store.cache_get("k") == {"v": 1}
    assert store.cache_get("missing") is None
    assert store.cache_get("k", max_age=-1) is None, "an expired entry must not be served"


def test_cache_put_overwrites_rather_than_duplicating(tmp_path):
    from mem20wasmz.core import StateStore

    store = StateStore(tmp_path / "s.db")
    store.cache_put("k", {"v": 1})
    store.cache_put("k", {"v": 2})
    assert store.cache_get("k") == {"v": 2}


def test_events_are_recorded_in_order(tmp_path):
    from mem20wasmz.core import StateStore

    store = StateStore(tmp_path / "s.db")
    job, _ = store.create_job({"goal": "ship"})
    store.emit("started", job_id=job["id"])
    store.emit("finished", job_id=job["id"])
    kinds = [e["kind"] for e in store.events()]
    assert kinds[-2:] == ["started", "finished"]
    assert "job.queued" in kinds, "creating a job should itself be recorded"


def test_a_secret_in_the_request_never_reaches_the_database(tmp_path):
    """create_job redacts before writing - this is the behaviour to preserve."""
    from mem20wasmz.core import StateStore

    path = tmp_path / "s.db"
    store = StateStore(path)
    store.create_job({"user": "alice", "password": "hunter2"})

    blob = path.read_bytes()
    assert b"hunter2" not in blob, "a plaintext password reached the database"
    assert b"alice" in blob, "non-secret fields must still be stored"


def test_a_secret_in_a_job_result_never_reaches_the_database(tmp_path):
    """update_job must redact exactly as create_job does.

    This was a real leak: the result was written verbatim, so a token returned
    by a job sat in an unencrypted SQLite file. Fixed by redacting the result
    and the error string on the way in.
    """
    from mem20wasmz.core import StateStore

    path = tmp_path / "s.db"
    store = StateStore(path)
    job, _ = store.create_job({"goal": "ship"})
    store.update_job(job["id"], "done", result={"api_key": "sk-live-abc", "ok": True})

    blob = path.read_bytes()
    assert b"sk-live-abc" not in blob, "update_job persisted a plaintext API key"
    stored = store.get_job(job["id"])
    assert "[REDACTED]" in stored["result"], "the secret must be replaced, not dropped"
    assert "sk-live-abc" not in stored["result"]
    assert '"ok":true' in stored["result"], "non-secret fields must survive redaction"

    # The event log is a second write path and was the one that actually leaked.
    for (payload,) in sqlite3.connect(path).execute("SELECT payload FROM events"):
        assert "sk-live-abc" not in payload, f"the event log still holds the secret: {payload}"


def test_a_secret_in_an_error_string_is_also_redacted(tmp_path):
    from mem20wasmz.core import StateStore

    path = tmp_path / "s.db"
    store = StateStore(path)
    job, _ = store.create_job({"goal": "ship"})
    store.update_job(job["id"], "failed", error="auth failed for token=sekret-abc123")
    blob = path.read_bytes()
    assert b"sekret-abc123" not in blob, "an error string can carry a credential too"


# --- safety gate -------------------------------------------------------------


def test_safety_gate_blocks_high_risk_without_explicit_authorisation():
    from mem20wasmz.core import SafetyGate

    gate = SafetyGate()
    for action in sorted(gate.HIGH_RISK):
        with pytest.raises(SafetyBlocked):
            gate.check({"action": action})


def test_safety_gate_allows_a_low_risk_action():
    from mem20wasmz.core import SafetyGate

    assert SafetyGate().check({"action": "analyze"}) is None
    assert SafetyGate().check({"action": "read_a_file"}) is None


def test_safety_gate_blocks_the_unsafe_marker():
    from mem20wasmz.core import SafetyGate

    with pytest.raises(SafetyBlocked):
        SafetyGate().check({"unsafe": True})


def test_safety_gate_allows_high_risk_once_explicitly_authorised():
    from mem20wasmz.core import SafetyGate

    gate = SafetyGate()
    for action in sorted(gate.HIGH_RISK):
        assert gate.check({"action": action, "allow_automatic_action": True}) is None


def test_safety_gate_is_case_insensitive_about_the_action():
    from mem20wasmz.core import SafetyGate

    with pytest.raises(SafetyBlocked):
        SafetyGate().check({"action": "DEPLOY"})


def test_canonical_round_trips_through_json():
    """What is hashed must survive being written and read back."""
    payload = {"a": 1, "b": ["x", None, True], "c": {"d": 2.5}}
    assert json.loads(canonical(payload)) == payload
