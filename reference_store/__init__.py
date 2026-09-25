"""00_reference_store -- the MALIC braid's shared reference substrate (the fountain).

Phase 00 of hypo-map-1. Persistent, content-addressed store backing the learning
braid. Lessons that rings collide over and exchange live here and accrete across
server life so no ring ever starts blank and one failure on ring 1 is teachable
reference material on ring 3 in the same beat.

Grounding: the braid harness (`notebooks/research/malic_harness/braid.py`) keeps
lessons only in a process-lifetime in-memory `BraidLedger`. That is the exact gap
this module closes -- 00_reference_store is the *persistent* form of the same
lesson ledger, using the same `diff_id` content hash so nothing is reinvented.
"""

from .store import (
    ReferenceStore,
    RefLesson,
    RefSnapshot,
)
from .index import RefIndex, InMemoryIndex, JsonlIndex

__all__ = [
    "ReferenceStore",
    "RefLesson",
    "RefSnapshot",
    "RefIndex",
    "InMemoryIndex",
    "JsonlIndex",
]
