import os
import sys
import tempfile

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

# Isolate engine DATA from any real store (and from live memory) so tests never
# touch or leak user data. The engine code itself is the real repo copy.
_STORE = tempfile.mkdtemp(prefix="mem20_store_")
os.environ["MEM20_STORE_PATH"] = _STORE

import memory_engine.memory as M  # noqa: E402  (import after path/env are set)


def _reload():
    import importlib

    importlib.reload(M)
    return M


@pytest.fixture
def fresh_store():
    """A clean engine against an empty temp store (no contamination from real memory)."""
    return _reload()
