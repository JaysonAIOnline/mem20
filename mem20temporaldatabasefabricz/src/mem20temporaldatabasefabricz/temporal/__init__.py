"""mem20 bi-temporal memory: two axes, one store.

Separates when something was TRUE (valid time) from when the system KNEW it
(known time), so "what was true at noon" and "what did we believe at noon" are
different questions with different answers.

Nothing here duplicates content. A version points at a payload via `value_ref`;
whatever store owns the content stays the single authority, and this engine
records only when the belief existed.
"""

from .interval import Interval, TimestampError, contains, fmt_ts, overlaps, parse_ts
from .store import ChainError, TemporalStore, version_id_for
from .engine import (BiTemporalEngine, FOUR_SLICES, InvariantError, QueryResult,
                     TemporalError, event_time_coverage, slice_for_query)
from .ledger_adapter import build_engine, derive_intervals, temporal_filter

__all__ = [
    "Interval", "TimestampError", "contains", "fmt_ts", "overlaps", "parse_ts",
    "TemporalStore", "ChainError", "version_id_for",
    "BiTemporalEngine", "TemporalError", "InvariantError", "QueryResult",
    "FOUR_SLICES", "slice_for_query", "event_time_coverage",
    "derive_intervals", "build_engine", "temporal_filter",
]

__version__ = "1.1.0"