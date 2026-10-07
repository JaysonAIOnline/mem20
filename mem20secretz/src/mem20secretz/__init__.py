"""mem20secretz — secrets governance for the mem20 estate.

Read-only by construction. This package inspects; it never rewrites, moves, or
redacts anything on disk. Redaction is an output-layer concern belonging to the
caller, never to the store.
"""

from .sweep import Finding, SweepResult, sweep, load_store

__all__ = ["Finding", "SweepResult", "sweep", "load_store"]
__version__ = "0.1.0"
