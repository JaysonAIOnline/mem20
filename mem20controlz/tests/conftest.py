import os
import socket
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)


def _unshadow():
    """Evict the namespace-package shadow of mem20controlz.

    rootdir is /opt/mem20, so pytest imports this conftest as
    ``mem20controlz.tests.conftest`` and resolves the parent by scanning
    /opt/mem20. That directory has no __init__.py, so Python hands back a
    __file__-less namespace package named mem20controlz whose __path__ is the
    project directory rather than the package directory. Drop it and re-import
    so the tests get the real mem20controlz/__init__.py from REPO.
    """
    stale = sys.modules.get("mem20controlz")
    if stale is not None and getattr(stale, "__file__", None) is None:
        del sys.modules["mem20controlz"]
    import mem20controlz

    return mem20controlz


_unshadow()


def _refuse(*args, **kwargs):
    raise AssertionError("test attempted a real network or subprocess call")


@pytest.fixture(autouse=True)
def hermetic(monkeypatch):
    """Fail loudly if a test ever reaches for a socket or a spawned process."""
    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(subprocess, "Popen", _refuse)
