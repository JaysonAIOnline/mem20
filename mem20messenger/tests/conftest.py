"""Test bootstrap for mem20messenger.

Two environment problems are handled here, neither by weakening production code.

1. *Import shadowing.* Every package lives at ``<project>/<name>/``. Depending on
   the working directory, Python can match the project directory
   ``mem20messenger`` as a bare namespace package - which has no ``app``, no
   database and no functions - and that shadow wins over the real package. Rather
   than depend on which directories happen to be on ``sys.path``, the package is
   loaded explicitly from its file and registered in ``sys.modules``.

2. *Import-time state.* The module opens its SQLite database at import time under
   ``$HOME/.mem20/messenger``. ``HOME`` is redirected to a throwaway directory
   first, so tests never touch the real account database.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # /opt/mem20/mem20messenger
PACKAGE_DIR = PROJECT_ROOT / "mem20messenger"
PACKAGE_INIT = PACKAGE_DIR / "__init__.py"


def _prepare_environment() -> None:
    home = PROJECT_ROOT / ".test-home"
    home.mkdir(parents=True, exist_ok=True)
    os.environ["HOME"] = str(home)

    project = str(PROJECT_ROOT)
    if project not in sys.path:
        sys.path.insert(0, project)


def _load_package():
    """Import mem20messenger from its real path, bypassing namespace shadowing."""
    if "mem20messenger" in sys.modules:
        existing = sys.modules["mem20messenger"]
        if getattr(existing, "__file__", None):
            return existing
        del sys.modules["mem20messenger"]

    spec = importlib.util.spec_from_file_location("mem20messenger", PACKAGE_INIT)
    if spec is None or spec.loader is None:  # pragma: no cover - broken install
        raise ImportError(f"cannot load {PACKAGE_INIT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["mem20messenger"] = module
    # The package does `from . import run`, so the subpackage must be importable
    # by name before the body executes.
    spec.loader.exec_module(module)
    return module


_prepare_environment()
messenger = _load_package()
