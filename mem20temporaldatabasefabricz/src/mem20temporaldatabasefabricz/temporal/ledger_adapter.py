"""Bridge to mem20's existing memory ledger.

Two rules make this additive rather than a parallel system:

  1. The ledger stays the single authority for content. A version holds a
     `value_ref` pointing at a memory record id plus a content hash - never a
     second copy of the text. Nothing here can drift out of sync with what
     recall() returns.

  2. No new write path. Intervals are DERIVED from the append-only ledger that
     already exists, so remember()/supersede() need no changes and cannot be
     bypassed. The known axis comes for free from ledger order: a record was
     known from its `ts` until the `supersede` event that replaced it.

That is why correcting a fact in memory.py makes history queryable without
anyone having to remember to notify the temporal engine.
"""

from __future__ import annotations

import hashlib
from typing import Any, Iterable

from .engine import BiTemporalEngine
from .interval import Interval
from .store import TemporalStore

__all__ = ["derive_intervals", "build_engine", "temporal_filter",
           "content_hash", "TEMPORAL_DIAGNOSTICS"]

DEFAULT_SUBJECT = "topic"
FACT_ATTRIBUTE = "fact"


def content_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:16]


def derive_intervals(records: Iterable[dict]) -> list[Interval]:
    """Derive bi-temporal versions from memory-engine ledger rows.

    The subtle part is the correction case. memory.py's `supersede()` writes a
    marker row describing the OLD fact's validity window, and leaves the
    original `remember` row on disk untouched - so the original still carries
    `valid_to: null` and looks current. A single-axis reader therefore has two
    choices, both wrong: hide the original (history unreachable, which is the
    defect this replaces) or show it alongside its replacement (two answers to
    one question).

    Splitting the axes resolves it. The original's VALID interval ends at the
    correction, because the world changed. Its KNOWN interval ends at the
    correction too, because our belief changed. Both end, at the same instant
    here, but they are independent axes and only the known axis would have moved
    if we had merely retracted the belief.
    """
    records = list(records)

    superseded_at: dict[str, str | None] = {}
    superseded_valid_to: dict[str, str | None] = {}
    for row in records:
        if row.get("action") == "supersede" and row.get("supersedes_id"):
            target = str(row["supersedes_id"])
            superseded_at[target] = row.get("ts")
            superseded_valid_to[target] = row.get("valid_to")

    intervals: list[Interval] = []
    for row in records:
        if row.get("action") != "remember":
            continue
        rid = row.get("id")
        if not rid:
            continue
        # A ledger row without timestamps cannot be placed on either axis.
        # Refusing loudly beats deriving an interval from a half-empty row and
        # reporting a confident answer about the wrong instant.
        valid_from = row.get("valid_from") or row.get("ts")
        known_from = row.get("ts")
        if not valid_from or not known_from:
            raise ValueError(
                f"ledger record {rid!r} has no usable timestamps "
                f"(valid_from={row.get('valid_from')!r}, ts={row.get('ts')!r}); "
                f"a bi-temporal interval cannot be derived from it"
            )
        known_to = superseded_at.get(rid)
        valid_to = superseded_valid_to.get(rid)
        if valid_to is None:
            valid_to = row.get("valid_to")
        content = row.get("content") or ""
        intervals.append(Interval(
            subject=row.get("topic") or "unknown",
            attribute=FACT_ATTRIBUTE,
            version_id=str(rid),
            valid_from=valid_from,
            valid_to=valid_to,
            known_from=known_from,
            known_to=known_to,
            value_ref=str(rid),
            provenance={
                "actor": row.get("actor"),
                "tags": row.get("tags") or [],
                "priority": row.get("priority"),
                "content_hash": content_hash(content),
                "source": row.get("source"),
                # declared = the caller supplied an event time; assumed = the
                # store defaulted it to ingestion time. Legacy rows predate the
                # field and were always defaulted.
                "event_time_basis": row.get("event_time_basis")
                or ("declared" if row.get("valid_from")
                    and row.get("valid_from") != row.get("ts")
                    else "assumed_ingestion"),
            },
        ))
    intervals.sort(key=Interval.sort_key)
    return intervals


def build_engine(store: TemporalStore, records: Iterable[dict],
                 clock=None) -> BiTemporalEngine:
    """Populate a durable engine from ledger rows. Idempotent by construction.

    Re-running this against a longer ledger adds the new versions and leaves
    existing ones alone, so the store can be rebuilt or replayed safely.

    Versions already present are skipped before any event is appended. Without
    that, a caller that re-syncs per request (as the HTTP surface does) would
    append a fresh `ingest` event for every historical row on every call, and the
    event log would grow quadratically while the answers stayed correct. Cheap
    to avoid, so it is avoided.
    """
    engine = BiTemporalEngine(store, clock=clock) if clock \
        else BiTemporalEngine(store)
    present = {row["version_id"] for row in store.all_versions()}
    added = 0
    for interval in derive_intervals(records):
        if interval.version_id in present:
            continue
        # write_version bypasses assert_belief's "one open belief" check because
        # ledger-derived versions already encode the correction chain; re-asserting
        # each in turn would refuse the second and later ones.
        engine.store.append_event(engine.now(), "ingest", interval.to_dict())
        engine.store.put_version({
            "version_id": interval.version_id,
            "subject": interval.subject,
            "attribute": interval.attribute,
            "valid_from": interval.valid_from,
            "valid_to": interval.valid_to,
            "known_from": interval.known_from,
            "known_to": interval.known_to,
            "value_ref": interval.value_ref,
            "provenance": interval.provenance,
        }, seq=engine.store.count_events())
        present.add(interval.version_id)
        added += 1
    engine.last_sync_added = added
    return engine


def temporal_filter(engine: BiTemporalEngine, ids: Iterable[str],
                    valid_at: str | None = None,
                    known_at: str | None = None) -> set[str]:
    """Restrict an existing retrieval result set to a bi-temporal slice.

    This is how the temporal layer composes with the retrieval stack that is
    already live. Callers run their normal search - hybrid, vector, graph, or
    plain ledger recall - and then narrow the candidates with time. Retrieval
    decides relevance; this decides currency. Neither replaces the other.
    """
    candidates = {str(i) for i in ids}
    if not candidates:
        return set()
    keep: set[str] = set()
    # A memory record id IS the version id by construction, so narrowing a
    # retrieval result set needs no index lookup - just the interval for each
    # candidate. Retrieval decided relevance; this decides currency.
    for row in engine.store.all_versions():
        if row["version_id"] not in candidates:
            continue
        interval = engine._row_to_interval(row)
        if known_at is not None:
            if not interval.known_at(known_at):
                continue
        elif interval.known_to is not None:
            continue
        if valid_at is not None and not interval.valid_at(valid_at):
            continue
        keep.add(row["version_id"])
    return keep


def recency_prior(engine: BiTemporalEngine, valid_at: str | None = None,
                  known_at: str | None = None) -> dict[str, float]:
    """A 0..1 weight per version, for use as a tie-breaker beside real scores.

    Deliberately a prior, not a filter. Semantic and lexical relevance stay in
    charge; this only breaks ties toward currency so that a superseded fact does
    not outrank its correction merely on wording.
    """
    from .interval import parse_ts
    out: dict[str, float] = {}
    probe = parse_ts(valid_at or known_at or "")
    for row in engine.store.all_versions():
        interval = engine._row_to_interval(row)
        if known_at is None and interval.known_to is not None:
            continue
        if valid_at is not None and not interval.valid_at(valid_at):
            continue
        if probe is None:
            out[row["version_id"]] = 1.0
            continue
        learned = parse_ts(interval.known_from)
        if learned is None:
            out[row["version_id"]] = 0.0
            continue
        age_days = max(0.0, (probe - learned).total_seconds() / 86400.0)
        out[row["version_id"]] = round(1.0 / (1.0 + age_days / 30.0), 6)
    return out


TEMPORAL_DIAGNOSTICS = {
    "valid_from_defaults_to": "ingestion time",
    "why": (
        "memory.py's remember() sets valid_from = now when the caller supplies "
        "no explicit event time. A fact about last Tuesday learned today is "
        "therefore recorded as though it only became true today, so the valid "
        "axis cannot distinguish late-arriving facts from fresh ones. Until a "
        "caller passes valid_from explicitly, this engine reports that state "
        "rather than inferring an event time it was never given."
    ),
    "remedy": "pass valid_from=<event time> to remember(), or valid_from to assert_belief()",
}