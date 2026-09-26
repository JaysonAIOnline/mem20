"""KilNZ — the native mem20 3D subsystem.

AI-first: the agent is the caller. Every engine capability is an op reachable
over JSON-RPC, and this package is the client, the build harness for the native
kernel, and the pipeline that turns a brief into a verified asset.

Standard library only. The engine is a C++ binary this package builds and owns.
"""
from __future__ import annotations

__version__ = "0.1.0"

from .errors import (
    EngineMissing,
    KilnError,
    OpFailed,
    ValidationFailed,
)
from .rpc import Kiln

__all__ = ["Kiln", "KilnError", "OpFailed", "EngineMissing", "ValidationFailed", "__version__"]


def engine_dir():
    """Where the C++ kernel source lives, next to this package."""
    from pathlib import Path

    return Path(__file__).resolve().parent.parent / "engine"
