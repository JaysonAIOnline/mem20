"""mem20_mcp — thin real loader for the canonical mem20 MCP server.

The canonical, *running* mem20 MCP server lives at /opt/mem20/mcp (proven by the
live process table, ``mcp-server.service`` and opencode.jsonc). Every module in
this package is a read-only forwarder to that tree — see :mod:`mem20_mcp._forward`.
This package therefore boots the identical real tool set instead of stale drift,
and both ``import mem20_mcp.server`` and the top-level ``tools.*`` imports used by
the canonical server resolve to one shared implementation.
"""

from ._forward import canonical_root as canonical_root

__canonical_root__ = canonical_root()
__all__ = ["__canonical_root__", "canonical_root"]