"""Unified memory engine surface.

Re-exports the full API from ``memory_engine.memory`` — the single source of
truth for the Hermes tiered-memory system.  All runtime code (agentz substrate,
MCP handlers, CLI tools) should ``import memory`` and get this surface.

Data lives under ``MEM20_STORE_PATH`` (default ``~/.mem20/store``).
"""

from memory_engine.memory import *  # noqa: F401,F403
from memory_engine.memory import (  # noqa: F401
    _load_ledger,
    _append_ledger,
    _scrub_secrets,
    SUPERSEDED,
    main as _engine_main,
)
