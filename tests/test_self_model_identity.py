import asyncio
import os
import sys
import tempfile

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MCP = os.path.join(REPO, "mcp")
if MCP not in sys.path:
    sys.path.insert(0, MCP)

import server


@pytest.fixture(autouse=True)
def clean_store(monkeypatch):
    """Give every test an empty store so identities cannot leak between tests."""
    store = tempfile.mkdtemp(prefix="selfmodel_test_")
    monkeypatch.setenv("MEM20_STORE_PATH", store)
    for module in ("memory", "memory_engine.memory"):
        sys.modules.pop(module, None)
    yield store
    for module in ("memory", "memory_engine.memory"):
        sys.modules.pop(module, None)


def call(handler, args):
    s = server.Mem20MCPServer()
    return asyncio.new_event_loop().run_until_complete(getattr(s, handler)(args))


def test_identity_is_required():
    out = call("_self_model_create", {"capabilities": ["x"]})
    assert out.startswith("Error:"), out
    assert "identity is required" in out


def test_two_identities_coexist_without_shadowing():
    first = call("_self_model_create", {
        "identity": "big-pickle", "actor": "big-pickle",
        "capabilities": ["building"], "values": ["proof"],
    })
    second = call("_self_model_create", {
        "identity": "space-bunny", "actor": "space-bunny",
        "capabilities": ["auditing"], "values": ["honesty"],
    })
    assert "Self-model recorded" in first, first
    assert "Self-model recorded" in second, second

    a = call("_self_model_get", {"identity": "big-pickle"})
    b = call("_self_model_get", {"identity": "space-bunny"})
    assert "building" in a and "auditing" not in a, a
    assert "auditing" in b and "building" not in b, b


def test_identity_cannot_overwrite_another():
    call("_self_model_create", {
        "identity": "big-pickle", "actor": "big-pickle", "capabilities": ["building"],
    })
    denied = call("_self_model_create", {
        "identity": "big-pickle", "actor": "space-bunny", "capabilities": ["hijacked"],
    })
    assert denied.startswith("Access denied"), denied
    assert "space-bunny" in denied

    after = call("_self_model_get", {"identity": "big-pickle"})
    assert "hijacked" not in after, after


def test_owner_can_keep_updating_own_model():
    call("_self_model_create", {
        "identity": "space-bunny", "actor": "space-bunny", "capabilities": ["first"],
    })
    again = call("_self_model_create", {
        "identity": "space-bunny", "actor": "space-bunny", "capabilities": ["second"],
    })
    assert "Self-model recorded" in again, again
    out = call("_self_model_get", {"identity": "space-bunny"})
    assert "second" in out, out


def test_registry_lists_every_identity():
    call("_self_model_create", {"identity": "big-pickle", "actor": "big-pickle"})
    call("_self_model_create", {"identity": "space-bunny", "actor": "space-bunny"})
    roster = call("_self_model_get", {})
    assert "Self-Model Registry" in roster, roster
    assert "big-pickle" in roster, roster
    assert "space-bunny" in roster, roster
    assert "2 identities registered" in roster, roster


def test_prefix_identity_does_not_leak_across_records():
    call("_self_model_create", {
        "identity": "pickle", "actor": "owner-pickle", "capabilities": ["short-name"],
    })
    call("_self_model_create", {
        "identity": "pickle-extra", "actor": "owner-extra", "capabilities": ["long-name"],
    })
    short = call("_self_model_get", {"identity": "pickle"})
    long = call("_self_model_get", {"identity": "pickle-extra"})
    assert "short-name" in short, short
    assert "long-name" not in short, short
    assert "long-name" in long, long
    assert "short-name" not in long, long


def test_legacy_records_are_attributed_to_their_identity():
    from memory import remember

    remember(
        topic="self_model",
        content=(
            "Self-Model: {'capabilities': ['legacy-build'], 'values': ['legacy-value'], "
            "'identity': 'big-pickle, grounded builder agent', 'created': '2026-01-01T00:00:00'}"
        ),
        tags=["self_model", "identity", "core"],
        priority="high",
    )
    out = call("_self_model_get", {"identity": "big-pickle"})
    assert "legacy-build" in out, out
    assert "legacy (legacy record)" in out or "unknown (legacy record)" in out, out

    other = call("_self_model_get", {"identity": "space-bunny"})
    assert "legacy-build" not in other, other


def test_roster_separates_legacy_from_new_records():
    from memory import remember

    remember(
        topic="self_model",
        content=(
            "Self-Model: {'capabilities': ['old'], 'values': [], "
            "'identity': 'big-pickle, grounded builder agent', 'created': '2026-01-01T00:00:00'}"
        ),
        tags=["self_model", "identity", "core"],
        priority="high",
    )
    call("_self_model_create", {
        "identity": "space-bunny", "actor": "space-bunny", "capabilities": ["new"],
    })
    roster = call("_self_model_get", {})
    assert "2 identities registered" in roster, roster
    assert "legacy records: 1" in roster, roster


def test_reflect_names_the_identity_it_audited():
    call("_self_model_create", {
        "identity": "space-bunny", "actor": "space-bunny", "capabilities": ["auditing"],
    })
    out = call("_self_model_reflect", {"focus": "all", "identity": "space-bunny"})
    assert "Identity under reflection: space-bunny" in out, out


def test_reflect_defaults_to_most_recent_identity():
    call("_self_model_create", {
        "identity": "big-pickle", "actor": "big-pickle", "capabilities": ["older"],
    })
    call("_self_model_create", {
        "identity": "space-bunny", "actor": "space-bunny", "capabilities": ["newest"],
    })
    out = call("_self_model_reflect", {"focus": "all"})
    assert "Identity under reflection: space-bunny" in out, out


def test_incumbent_legacy_identity_cannot_be_claimed_by_another_actor():
    """An identity that already has records but no owner is the incumbent's.

    The first-writer bootstrap must not let a different actor claim it, which is
    how one identity would silently annex another's history.
    """
    from memory import remember

    remember(
        topic="self_model",
        content=(
            "Self-Model: {'capabilities': ['incumbent-work'], 'values': [], "
            "'identity': 'big-pickle, grounded builder agent', 'created': '2026-01-01T00:00:00'}"
        ),
        tags=["self_model", "identity", "core"],
        priority="high",
    )
    denied = call("_self_model_create", {
        "identity": "big-pickle", "actor": "space-bunny", "capabilities": ["annexed"],
    })
    assert denied.startswith("Access denied"), denied
    assert "incumbent" in denied, denied

    after = call("_self_model_get", {"identity": "big-pickle"})
    assert "annexed" not in after, after


def test_incumbent_identity_may_adopt_its_own_records():
    from memory import remember

    remember(
        topic="self_model",
        content=(
            "Self-Model: {'capabilities': ['incumbent-work'], 'values': [], "
            "'identity': 'big-pickle, grounded builder agent', 'created': '2026-01-01T00:00:00'}"
        ),
        tags=["self_model", "identity", "core"],
        priority="high",
    )
    allowed = call("_self_model_create", {
        "identity": "big-pickle", "actor": "big-pickle", "capabilities": ["continued"],
    })
    assert "Self-model recorded" in allowed, allowed
    assert "(bootstrap)" in allowed, allowed


def test_unused_identity_name_can_be_claimed():
    first = call("_self_model_create", {
        "identity": "brand-new", "actor": "agent-z", "capabilities": ["fresh"],
    })
    assert "Self-model recorded" in first, first
    assert "bootstrap" in first, first


def test_busy_store_does_not_hide_an_incumbent_from_authorization():
    """Newer per-identity rows must not crowd legacy rows out of the scan.

    recall() matches topics by substring, so the unscoped legacy topic shares
    matches with every per-identity topic. A narrow scan returns only the newest
    rows, the exact-topic filter then drops them, and an incumbent identity looks
    unclaimed — which is how a second identity could annex it.
    """
    from memory import remember

    remember(
        topic="self_model",
        content=(
            "Self-Model: {'capabilities': ['incumbent-work'], 'values': [], "
            "'identity': 'big-pickle, grounded builder agent', 'created': '2020-01-01T00:00:00'}"
        ),
        tags=["self_model", "identity", "core"],
        priority="high",
    )
    for i in range(12):
        out = call("_self_model_create", {
            "identity": "noisy-agent", "actor": "noisy-agent", "capabilities": [f"noise-{i}"],
        })
        assert "Self-model recorded" in out, out

    denied = call("_self_model_create", {
        "identity": "big-pickle", "actor": "space-bunny", "capabilities": ["annexed"],
    })
    assert denied.startswith("Access denied"), denied
    assert "annexed" not in call("_self_model_get", {"identity": "big-pickle"})


def test_legacy_history_survives_many_other_identities():
    from memory import remember

    remember(
        topic="self_model",
        content=(
            "Self-Model: {'capabilities': ['old-work'], 'values': [], "
            "'identity': 'big-pickle, grounded builder agent', 'created': '2020-01-01T00:00:00'}"
        ),
        tags=["self_model", "identity", "core"],
        priority="high",
    )
    for i in range(10):
        call("_self_model_create", {
            "identity": f"other-{i}", "actor": f"other-{i}", "capabilities": ["x"],
        })
    out = call("_self_model_get", {"identity": "big-pickle"})
    assert "old-work" in out, out


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
