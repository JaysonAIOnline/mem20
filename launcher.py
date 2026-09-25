#!/usr/bin/env python3
"""Console-script entry point for mem20 (`mem20-mcp`).

The real MCP server lives in the local `mcp/` directory and is designed to be
run as a *script* (``python mcp/mcp_server.py``), not imported as a package.
Importing it as ``mcp.mcp_server`` would shadow the ``mcp`` SDK package and
break ``from mcp.server import Server``.

This launcher finds the bundled server directory, puts it on ``sys.path``, and
runs ``mcp_server.py`` via runpy — exactly as ``python mcp/mcp_server.py``
would. It is fully equivalent to the repo-root invocation and keeps the same
stdio + ``:8080`` health behaviour.
"""
import os
import runpy
import sys
from importlib.resources import files
from pathlib import Path


def _mcp_dir() -> str:
    """Locate the bundled MCP server directory."""
    # Primary: repo layout (editable install / git checkout) — mcp/ next to
    # this file, or the legacy mem20_runtime/mcp bundle.
    here = Path(__file__).resolve().parent
    for candidate in (here / "mcp", here / "mem20_runtime" / "mcp"):
        if candidate.is_dir():
            return str(candidate)
    # Installed-package fallback: MCP files shipped as package data.
    try:
        p = files("mem20_runtime").joinpath("mcp")
        path = Path(p)
        if path.is_dir():
            return str(path)
    except Exception:
        pass
    raise RuntimeError("Could not locate the bundled mem20 MCP server directory.")


def main() -> None:
    mcp_dir = _mcp_dir()
    if mcp_dir not in sys.path:
        sys.path.insert(0, mcp_dir)
    # Run the bundled entry-point exactly like `python mcp/mcp_server.py`.
    runpy.run_path(os.path.join(mcp_dir, "mcp_server.py"), run_name="__main__")


if __name__ == "__main__":
    main()
