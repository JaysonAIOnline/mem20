"""Tests for the simulated-partition write path used by cog's imagination tools.

Two defects are pinned here:

1. ``_persist_simulated`` stored ``str(out)[:1500]``. Tools that request more
   than 1500 tokens (imagination_simulate asks for 1800, imagination_concept
   for 1200 plus retrieved memory) had their records silently clipped. The
   stored record looked complete and was not.
2. ``_persist_simulated`` swallowed every exception. A persistence failure
   returned a clean success to the caller while the imaginative output was lost
   with no error and no log.

These are bounded tests. No real LLM call is made; ``remember_simulated`` is
stubbed and both the passing and failing paths are exercised directly.
"""

import importlib.util
import sys
import types

import pytest


def _load_server_module():
    """Load mcp/server.py by path so the site-packages `mcp` package is not shadowed."""
    spec = importlib.util.spec_from_file_location("mem20_mcp_server", "/opt/mem20/mcp/server.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["mem20_mcp_server"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def server_mod(monkeypatch):
    mod = _load_server_module()
    monkeypatch.setattr(mod, "MEMORY_SYSTEM_AVAILABLE", True, raising=False)
    return mod


def _make_server(server_mod):
    srv = server_mod.Mem20MCPServer.__new__(server_mod.Mem20MCPServer)
    return srv


class _Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return {"id": "sim-1"}


class _Boom:
    def __call__(self, **kwargs):
        raise RuntimeError("simulated partition unavailable")


def _install_fake_memory(monkeypatch, fn):
    fake = types.ModuleType("memory")
    fake.remember_simulated = fn
    monkeypatch.setitem(sys.modules, "memory", fake)


def test_full_output_is_stored_not_truncated(server_mod, monkeypatch):
    """A body well past the old 1500-char cap must be stored whole."""
    rec = _Recorder()
    _install_fake_memory(monkeypatch, rec)

    body = "x" * 9000
    srv = _make_server(server_mod)
    srv._persist_simulated({"topic": "imagination"}, body, "simulate")

    assert len(rec.calls) == 1
    stored = rec.calls[0]["content"]
    assert len(stored) == 9000, f"stored body was clipped to {len(stored)} chars"
    assert stored == body


def test_no_1500_char_truncation_boundary(server_mod, monkeypatch):
    """Exactly at and just past the old cap, nothing is dropped."""
    rec = _Recorder()
    _install_fake_memory(monkeypatch, rec)
    srv = _make_server(server_mod)

    for size in (1499, 1500, 1501, 5000):
        srv._persist_simulated({}, "y" * size, "concept")
        assert len(rec.calls[-1]["content"]) == size


def test_persist_failure_raises_instead_of_being_swallowed(server_mod, monkeypatch):
    """The old `except Exception: pass` hid total loss behind a clean return."""
    _install_fake_memory(monkeypatch, _Boom())
    srv = _make_server(server_mod)

    with pytest.raises(RuntimeError, match="simulated partition unavailable"):
        srv._persist_simulated({}, "a valuable imagined output", "concept")


def test_empty_output_is_a_no_op(server_mod, monkeypatch):
    """No output means nothing to persist, and that is not an error."""
    rec = _Recorder()
    _install_fake_memory(monkeypatch, rec)
    srv = _make_server(server_mod)

    srv._persist_simulated({}, "", "concept")
    assert rec.calls == []


def test_grounded_memory_is_never_reached(server_mod, monkeypatch):
    """The write must go to the simulated partition only.

    The fake module exposes a `remember` attribute that explodes if touched.
    """
    touched = []

    def grounded(*a, **k):
        touched.append(k)
        raise AssertionError("grounded memory was written to")

    fake = types.ModuleType("memory")
    fake.remember = grounded
    rec = _Recorder()
    fake.remember_simulated = rec
    sys.modules["memory"] = fake

    srv = _make_server(server_mod)
    srv._persist_simulated({}, "speculative content", "model")
    assert touched == []
    assert len(rec.calls) == 1


def test_imagination_dream_is_gone():
    """Cog's dream loop was deleted; nothing may reintroduce it by name."""
    sys.path.insert(0, "/opt/mem20/cog")
    try:
        import cognitive_engine as ce
    finally:
        sys.path.pop(0)
    assert not hasattr(ce, "imagination_dream")
    assert not hasattr(ce, "aimagination_dream")