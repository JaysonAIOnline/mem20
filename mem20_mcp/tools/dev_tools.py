"""Forwarding module — see mem20_mcp._forward.

Re-exports the canonical tools module dev_tools.py (its Mixin and registration) from the canonical tree (single source of truth) so the
mem20_mcp package exposes the real, running implementation and never stale
drift.
"""

from mem20_mcp._forward import load as _load

_impl = _load('tools/dev_tools.py', 'tools.dev_tools')


def __getattr__(name):
    return getattr(_impl, name)


__all__ = [n for n in dir(_impl) if not n.startswith("_")]
