"""Shared sys.path repair for mem20 projects laid out as <project>/<name>/.

Import this from a project's conftest.py. See /opt/mem20/conftest.py for the
full explanation of the namespace-shadowing failure this repairs.
"""

from __future__ import annotations

import os
import sys


def apply(project_dir: str) -> None:
    """Stop the parent of `project_dir` from shadowing the real package."""
    parent = os.path.dirname(os.path.abspath(project_dir))
    sys.path[:] = [p for p in sys.path if p not in ("", ".", parent)]
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)
