"""Tests for mem20_mcp's forwarding contract.

The package's entire purpose is to be a thin, honest forwarder to the canonical
MCP tree at /opt/mem20/mcp. The failure that matters is subtle and quiet: if the
forwarder ever falls back to a local copy, the estate runs stale tool logic while
appearing healthy. So these tests are mostly about the refusal to do that.

``MEM20_CANONICAL_MCP_ROOT`` exists precisely so the canonical root can be
redirected at a fixture tree; the real default is exercised too.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import mem20_mcp
import pytest
from mem20_mcp import _forward

REAL_ROOT = Path("/opt/mem20/mcp")


@pytest.fixture
def fake_canonical(tmp_path, monkeypatch):
    """A minimal but valid canonical tree: server.py plus a tools/ directory."""
    root = tmp_path / "canonical"
    (root / "tools").mkdir(parents=True)
    (root / "server.py").write_text("TOOLS = ['alpha', 'beta']\nSERVER = 'fake'\n")
    (root / "tools" / "thing.py").write_text("NAME = 'thing'\ndef hello():\n    return 'hi'\n")
    (root / "tools" / "broken_syntax.py").write_text("def (:\n")
    monkeypatch.setenv("MEM20_CANONICAL_MCP_ROOT", str(root))
    return root


@pytest.fixture(autouse=True)
def _restore_modules():
    """Snapshot sys.modules/sys.path so forwarding experiments do not leak."""
    modules = dict(sys.modules)
    path = list(sys.path)
    yield
    for name in list(sys.modules):
        if name not in modules:
            del sys.modules[name]
    sys.modules.update(modules)
    sys.path[:] = path


# --- canonical_root ----------------------------------------------------------


def test_default_canonical_root_is_the_real_tree():
    """The default must be the tree that is actually running."""
    assert _forward.DEFAULT_CANONICAL_ROOT == "/opt/mem20/mcp"
    if REAL_ROOT.is_dir():
        assert os.path.isfile(REAL_ROOT / "server.py")
        assert (REAL_ROOT / "tools").is_dir()


def test_canonical_root_honours_the_override(fake_canonical):
    assert _forward.canonical_root() == str(fake_canonical.resolve())


def test_canonical_root_puts_the_canonical_tree_first_on_sys_path(fake_canonical):
    _forward.canonical_root()
    assert sys.path[0] == str(fake_canonical.resolve()), (
        "canonical code must win over any same-named local package"
    )


def test_canonical_root_is_idempotent_on_sys_path(fake_canonical):
    _forward.canonical_root()
    _forward.canonical_root()
    assert sys.path.count(str(fake_canonical.resolve())) == 1


def test_a_missing_server_py_fails_loudly(tmp_path, monkeypatch):
    """Refusing is the whole point: a silent fallback is the bug this prevents."""
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("MEM20_CANONICAL_MCP_ROOT", str(empty))
    with pytest.raises(ImportError) as excinfo:
        _forward.canonical_root()
    message = str(excinfo.value)
    assert "server.py" in message
    assert "Refusing to load stale local copies" in message


def test_a_missing_tools_directory_fails_loudly(tmp_path, monkeypatch):
    partial = tmp_path / "partial"
    partial.mkdir()
    (partial / "server.py").write_text("x = 1\n")
    monkeypatch.setenv("MEM20_CANONICAL_MCP_ROOT", str(partial))
    with pytest.raises(ImportError) as excinfo:
        _forward.canonical_root()
    assert "tools" in str(excinfo.value)


def test_a_nonexistent_root_fails_loudly(tmp_path, monkeypatch):
    monkeypatch.setenv("MEM20_CANONICAL_MCP_ROOT", str(tmp_path / "ghost"))
    with pytest.raises(ImportError):
        _forward.canonical_root()


# --- load --------------------------------------------------------------------


def test_load_returns_the_canonical_module(fake_canonical):
    module = _forward.load("tools/thing.py", "tools.thing")
    assert module.NAME == "thing"
    assert module.hello() == "hi"


def test_loaded_module_comes_from_the_canonical_file(fake_canonical):
    module = _forward.load("tools/thing.py", "tools.thing")
    assert Path(module.__file__).resolve() == (fake_canonical / "tools" / "thing.py").resolve()


def test_load_reuses_sys_modules_when_it_already_holds_the_canonical_file(fake_canonical):
    first = _forward.load("tools/thing.py", "tools.thing")
    second = _forward.load("tools/thing.py", "tools.thing")
    assert first is second, "the same canonical file must not be executed twice"
    assert sys.modules["tools.thing"] is first


def test_load_avoids_self_import_when_the_key_is_held_by_stale_code(fake_canonical):
    """A bare `import tools.thing` that resolved to old code must not be reused."""
    stale = type(sys)("tools.thing")
    stale.__file__ = "/opt/mem20/mem20_mcp/tools/thing.py"  # the stale local copy
    stale.NAME = "STALE"
    sys.modules["tools.thing"] = stale

    module = _forward.load("tools/thing.py", "tools.thing")
    assert module.NAME == "thing", "forwarding returned the stale module"
    assert module is not stale


def test_load_reuses_a_private_key_on_a_second_stale_conflict(fake_canonical):
    for path in ("/opt/mem20/mem20_mcp/tools/thing.py", "/somewhere/else/thing.py"):
        stale = type(sys)("tools.thing")
        stale.__file__ = path
        stale.NAME = "STALE"
        sys.modules["tools.thing"] = stale
        module = _forward.load("tools/thing.py", "tools.thing")
        assert module.NAME == "thing"


def test_load_of_a_missing_file_raises(fake_canonical):
    with pytest.raises((ImportError, FileNotFoundError)):
        _forward.load("tools/does_not_exist.py", "tools.does_not_exist")


def test_a_broken_canonical_module_raises_rather_than_returning_a_half_module(fake_canonical):
    with pytest.raises(SyntaxError):
        _forward.load("tools/broken_syntax.py", "tools.broken_syntax")


# --- the package's public surface -------------------------------------------


def test_package_re_exports_the_canonical_root():
    assert mem20_mcp.canonical_root is _forward.canonical_root
    assert "canonical_root" in mem20_mcp.__all__


def test_resolved_canonical_root_is_absolute():
    assert os.path.isabs(mem20_mcp.__canonical_root__)


def test_every_shim_module_forwards_rather_than_reimplementing():
    """Each shim module must expose the canonical module's attributes."""
    shim = Path(mem20_mcp.__file__).parent
    shims = [p for p in shim.glob("*.py") if p.stem not in {"_forward", "__init__"}]
    assert shims, "expected shim modules to check"
    for path in shims:
        source = path.read_text(encoding="utf-8")
        assert "__getattr__" in source or "_forward" in source, (
            f"{path.name} does not appear to forward; it may hold a stale copy"
        )
