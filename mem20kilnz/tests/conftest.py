"""Shared fixtures.

The engine is required, not optional. A test that silently skips because the
binary is missing is exactly how a broken build looks green, so the fixture
fails loudly instead.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mem20kilnz import engine as _engine  # noqa: E402
from mem20kilnz.errors import EngineMissing  # noqa: E402
from mem20kilnz.rpc import Kiln  # noqa: E402


@pytest.fixture(scope="session")
def engine_dir() -> Path:
    return _engine.engine_source_dir()


@pytest.fixture(scope="session")
def binary() -> str:
    try:
        return str(_engine.binary_path())
    except EngineMissing as exc:
        pytest.fail(str(exc))


@pytest.fixture()
def kiln(binary):
    k = Kiln(binary)
    try:
        yield k
    finally:
        k.close()


@pytest.fixture(scope="session")
def fixtures(tmp_path_factory) -> Path:
    """Generate the glTF/GLB fixture corpus once per session."""
    sys.path.insert(0, str(ROOT / "tests"))
    import make_fixtures

    out = tmp_path_factory.mktemp("fixtures")
    import contextlib
    import io

    argv = sys.argv
    sys.argv = ["make_fixtures.py", str(out)]
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            make_fixtures.main()
    finally:
        sys.argv = argv
    return out
