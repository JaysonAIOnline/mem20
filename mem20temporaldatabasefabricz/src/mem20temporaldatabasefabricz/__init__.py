"""mem20 bi-temporal memory.

Two axes, kept separate:

  valid  when a claim was true in the world
  known  when this system held the belief

Most memory stores track only the first, which makes "what was true before the
correction?" unanswerable and "what did we believe then?" indistinguishable
from "what is true now?". This package answers both.
"""

from .temporal import (BiTemporalEngine, ChainError, Interval, InvariantError,
                       QueryResult, TemporalError, TemporalStore, contains,
                       event_time_coverage, overlaps, parse_ts, slice_for_query,
                       version_id_for)

__all__ = [
    "BiTemporalEngine", "Interval", "TemporalStore", "QueryResult",
    "TemporalError", "InvariantError", "ChainError",
    "contains", "overlaps", "parse_ts", "version_id_for", "slice_for_query",
    "event_time_coverage",
]

__version__ = "1.1.0"