"""Forwarding module — see mem20_mcp._forward.

Re-exports the canonical server module (/opt/mem20/mcp/server.py) so that
``import mem20_mcp.server`` and ``from mem20_mcp.server import Mem20MCPServer``
load the exact, real, running implementation.
"""

import sys as _sys

from mem20_mcp._forward import load as _load

_impl = _load("server.py", "server")


def __getattr__(name):
    return getattr(_impl, name)


__all__ = [n for n in dir(_impl) if not n.startswith("_")]