"""Bi-temporal query engine.

The question this answers is not "what is true?" but the harder pair:

    "what was true at T?"      the valid axis  - the world
    "what did we believe at T?" the known axis  - the system

Those differ the moment anything is learned late, corrected, or retracted, which
is most of the time in a real memory. A single-axis store cannot tell a
retracted belief from one that was never held, and answering "what did we know
at noon?" with today's facts is how a memory system becomes quietly untrustworthy.

Guarantees:
  * corrections never delete. They close the old version's known interval and
    append a new version. The old belief stays queryable forever.
  * a correction never edits valid time. The world did not change.
  * at most one version per (subject, attribute) is open on the known axis.
  * ordering is total and deterministic, so equal queries give equal answers.
  * intervals are half-open `[start, end)`.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from .interval import Interval, parse_ts
from .store import TemporalStore, version_id_for

__all__ = ["BiTemporalEngine", "TemporalError", "InvariantError", "QueryResult",
           "FOUR_SLICES", "slice_for_query", "event_time_coverage",
           "load_provenance"]

FOUR_SLICES = ("valid_now_known_now", "valid_then_known_now",
               "valid_now_known_then", "valid_then_known_then")


class TemporalError(RuntimeError):
    """Base for bi-temporal refusals."""


class InvariantError(TemporalError):
    """Raised when an operation would break a bi-temporal invariant."""


def _require_ts(value: str) -> datetime:
    """parse_ts, for call sites where the value is known to be present."""
    parsed = parse_ts(value)
    if parsed is None:
        raise InvariantError(f"a timestamp is required here, got {value!r}")
    return parsed


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slice_for_query(valid_at: str | None, known_at: str | None) -> str:
    """Name the slice a *query* asks about.

    The four slices name the QUESTION, not the answer. An omitted `valid_at`
    means "now" on the world axis; a supplied one means "then". So
    `query(valid_at=T)` is the as-of join - what was true at T, judged against
    everything we know today - whether or not anything comes back. Deriving the
    slice from whether the result happens to contain the probe instant would
    make an empty answer indistinguishable from the wrong question, which is
    precisely the ambiguity that makes single-axis temporal stores untrustworthy.
    """
    return f"{'valid_now' if valid_at is None else 'valid_then'}_" \
           f"{'known_now' if known_at is None else 'known_then'}"


def load_provenance(value: Any) -> dict:
    """Provenance as a dict, whether it came from memory as JSON text or a dict.

    SQLite hands back the column as the JSON string it was stored as, while
    in-memory callers pass a real dict. Both reach this engine, so every reader
    of provenance goes through here rather than assuming one shape.
    """
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def event_time_coverage(versions: list[dict]) -> dict:
    """How much of a store's valid axis is actually declared event time.

    A version whose event time was defaulted to its ingestion time carries a
    valid_from that is *assumed*, not known. Those versions cannot support a
    "was this true before we learned it?" question, because the valid axis and
    the known axis are the same instant by construction.

    This counts them rather than asserting a limitation in prose, so the number
    can only go up as callers declare real event times. Legacy rows with no
    `event_time_basis` are counted as assumed: they predate the field and were
    all defaulted.
    """
    declared = assumed = 0
    for version in versions:
        basis = load_provenance(version.get("provenance")).get("event_time_basis")
        if basis == "declared":
            declared += 1
        else:
            assumed += 1
    total = declared + assumed
    return {
        "versions": total,
        "declared_event_time": declared,
        "assumed_event_time": assumed,
        "declared_fraction": round(declared / total, 4) if total else 0.0,
        "as_of_join_is_sound": assumed == 0,
        "note": (
            "The as-of join (valid_then_known_now) cannot separate a late-arriving "
            "fact from a fresh one for any version counted as assumed. Write with "
            "an explicit valid_from to raise declared_event_time."
        ),
    }


class QueryResult:
    """A slice query plus the audit context that produced it."""

    __slots__ = ("subject", "attribute", "valid_at", "known_at", "slice_name",
                 "versions")

    def __init__(self, subject: str | None, attribute: str | None,
                 valid_at: str | None, known_at: str | None,
                 versions: list[Interval]):
        self.subject = subject
        self.attribute = attribute
        self.valid_at = valid_at
        self.known_at = known_at
        self.versions = versions
        self.slice_name = slice_for_query(valid_at, known_at)

    def __len__(self) -> int:
        return len(self.versions)

    def __iter__(self):
        return iter(self.versions)

    def value_refs(self) -> list[str]:
        return [v.value_ref for v in self.versions]

    def to_dict(self) -> dict:
        return {
            "subject": self.subject,
            "attribute": self.attribute,
            "valid_at": self.valid_at,
            "known_at": self.known_at,
            "slice": self.slice_name,
            "count": len(self.versions),
            "versions": [v.to_dict() for v in self.versions],
        }


class BiTemporalEngine:
    """Records what was believed, when it was believed, and when it was true."""

    def __init__(self, store: TemporalStore, clock=_utc_now):
        self.store = store
        self._clock = clock
        self._seq = store.count()
        # How many versions the most recent ledger sync added; 0 means the store
        # was already current. Surfaced so callers can tell a real sync from a
        # no-op instead of inferring it from timing.
        self.last_sync_added = 0

    # -- helpers --------------------------------------------------------

    def now(self) -> str:
        return self._clock()

    @staticmethod
    def _row_to_interval(row: dict) -> Interval:
        return Interval(
            subject=row["subject"], attribute=row["attribute"],
            version_id=row["version_id"], valid_from=row["valid_from"],
            valid_to=row.get("valid_to"), known_from=row["known_from"],
            known_to=row.get("known_to"), value_ref=row.get("value_ref", ""),
            provenance=load_provenance(row.get("provenance")),
        )

    def _open_known(self, subject: str, attribute: str) -> list[Interval]:
        """Versions still open on the known axis."""
        return [self._row_to_interval(r)
                for r in self.store.versions_for(subject, attribute)
                if r.get("known_to") is None]

    # -- assertions -----------------------------------------------------

    def assert_belief(self, subject: str, attribute: str, value_ref: str,
                      valid_from: str | None = None, known_at: str | None = None,
                      provenance: dict | None = None) -> Interval:
        """Record that we hold `value_ref` about (subject, attribute).

        valid_from defaults to now: in the absence of evidence, when a claim
        became true and when we learned it are the same instant. Callers that
        know better - a fact about last Tuesday, learned today - must say so,
        because that difference is exactly what the two axes exist to record.
        """
        known_from = known_at or self.now()
        valid = valid_from or known_from
        vid = version_id_for(subject, attribute, known_from, value_ref)

        already = [r for r in self.store.versions_for(subject, attribute)
                   if r["version_id"] == vid]
        if already:
            return self._row_to_interval(already[0])

        # Only one belief per attribute may be open at a time. Asserting while
        # another is open is a correction expressed as an assertion.
        open_now = self._open_known(subject, attribute)
        if open_now:
            raise InvariantError(
                f"{subject}.{attribute} already holds an open belief "
                f"({open_now[0].version_id}, known_from={open_now[0].known_from}). "
                f"Use correct() to supersede it, or retract() to close it."
            )

        self._seq += 1
        row = {
            "version_id": vid, "subject": subject, "attribute": attribute,
            "valid_from": valid, "valid_to": None,
            "known_from": known_from, "known_to": None,
            "value_ref": value_ref, "provenance": provenance or {},
        }
        self.store.append_event(self.now(), "assert", row)
        self.store.put_version(row, seq=self._seq)
        return self._row_to_interval(row)

    def correct(self, subject: str, attribute: str, value_ref: str,
                known_at: str | None = None, valid_from: str | None = None,
                provenance: dict | None = None) -> Interval:
        """Supersede the current belief, preserving it as history.

        The old version keeps its valid interval and loses only its known
        interval, so both questions stay answerable afterwards:
          "what was true then?"      -> the old version
          "what did we believe then?" -> the old version
          "what is true now?"        -> the new version
        """
        known_from = known_at or self.now()
        open_now = self._open_known(subject, attribute)
        if not open_now:
            raise InvariantError(
                f"nothing to correct: {subject}.{attribute} holds no open belief")

        newest = max(open_now, key=lambda i: i.sort_key())
        if _require_ts(known_from) < _require_ts(newest.known_from):
            raise InvariantError(
                f"a correction cannot be known before what it replaces: "
                f"known_at={known_from} precedes the belief's known_from="
                f"{newest.known_from}")

        # valid time carries forward: correcting our belief about a claim that
        # was already true does not make it newly true.
        valid = valid_from or newest.valid_from

        self._seq += 1
        row = {
            "version_id": version_id_for(subject, attribute, known_from, value_ref),
            "subject": subject, "attribute": attribute,
            "valid_from": valid, "valid_to": newest.valid_to,
            "known_from": known_from, "known_to": None,
            "value_ref": value_ref,
            "provenance": {**(provenance or {}),
                           "corrects": newest.version_id,
                           "corrected_at": known_from},
        }
        self.store.append_event(self.now(), "correct", row)
        for old in open_now:
            self.store.append_event(self.now(), "close_known", {
                "version_id": old.version_id, "known_to": known_from,
                "reason": "corrected",
            })
            self.store.close_version(old.version_id, known_from, seq=self._seq)
        self.store.put_version(row, seq=self._seq)
        return self._row_to_interval(row)

    def retract(self, subject: str, attribute: str, known_at: str | None = None,
                reason: str = "retracted") -> list[Interval]:
        """Stop believing, without asserting a replacement and without editing
        what was true. Returns the versions that were closed."""
        known_from = known_at or self.now()
        open_now = self._open_known(subject, attribute)
        if not open_now:
            return []
        for old in open_now:
            self.store.append_event(self.now(), "retract", {
                "version_id": old.version_id, "known_to": known_from, "reason": reason})
            self.store.close_version(old.version_id, known_from, seq=self._seq)
        return [self._row_to_interval(r) for r in
                self.store.versions_for(subject, attribute)
                if r["version_id"] in {i.version_id for i in open_now}]

    def expire(self, subject: str, attribute: str, valid_to: str,
               reason: str = "no_longer_true") -> Interval:
        """Close the VALID interval: the claim itself stopped being true.

        Distinct from retract(): the world changed rather than our belief, and
        the fact that we learned that later is itself recorded on the known axis.
        """
        open_now = self._open_known(subject, attribute)
        if not open_now:
            raise InvariantError(
                f"nothing to expire: {subject}.{attribute} holds no open belief")
        target = max(open_now, key=lambda i: i.sort_key())
        if _require_ts(valid_to) <= _require_ts(target.valid_from):
            raise InvariantError(
                f"valid_to={valid_to} must be after valid_from={target.valid_from}")
        self.store.append_event(self.now(), "expire", {
            "version_id": target.version_id, "valid_to": valid_to, "reason": reason})
        self.store.close_validity(target.version_id, valid_to)
        return self._row_to_interval(
            {**target.to_dict(), "valid_to": valid_to})

    # -- queries --------------------------------------------------------

    def query(self, subject: str, valid_at: str | None = None,
              known_at: str | None = None, attribute: str | None = None,
              include_closed: bool = False) -> QueryResult:
        """Answer a bi-temporal as-of question.

        valid_at restricts the world axis; known_at restricts the belief axis.
        Omitting either means "now" on that axis. Passing both is the full
        as-of join and yields the retroactively-known slice.
        """
        rows = self.store.versions_for(subject, attribute)
        out: list[Interval] = []
        for row in rows:
            interval = self._row_to_interval(row)
            if not include_closed and interval.known_to is not None and known_at is None:
                continue
            if valid_at is not None and not interval.valid_at(valid_at):
                continue
            if known_at is not None and not interval.known_at(known_at):
                continue
            out.append(interval)
        out.sort(key=Interval.sort_key)
        return QueryResult(subject, attribute, valid_at, known_at, out)

    def history(self, subject: str, attribute: str | None = None) -> list[Interval]:
        """Every version, oldest belief first, including superseded ones."""
        rows = self.store.versions_for(subject, attribute)
        out = [self._row_to_interval(r) for r in rows]
        out.sort(key=Interval.sort_key)
        return out

    def four_slices(self, subject: str, instant: str,
                    attribute: str | None = None) -> dict:
        """All four slices at one instant, which is the actual diagnostic.

        valid_then_known_now  - we learned later that this was true then
                                (late-arriving facts)
        valid_now_known_then  - we believed it then and it is still true
                                (were we right?)
        valid_then_known_then - the ordinary historical view
        valid_now_known_now  - the current view
        """
        buckets = {name: [] for name in FOUR_SLICES}
        for interval in self.history(subject, attribute):
            buckets[interval.slice_of(instant, instant)].append(interval)
        return {
            "instant": instant,
            "subject": subject,
            "attribute": attribute,
            "slices": {name: [v.to_dict() for v in vs] for name, vs in buckets.items()},
            "counts": {name: len(vs) for name, vs in buckets.items()},
        }

    def explain(self, subject: str, valid_at: str | None = None,
                known_at: str | None = None, attribute: str | None = None) -> dict:
        """Why does the engine answer what it answers?"""
        result = self.query(subject, valid_at=valid_at, known_at=known_at,
                            attribute=attribute)
        chain = self.history(subject, attribute)
        for interval in result.versions:
            superseded_by = [v.version_id for v in chain
                             if v.provenance.get("corrects") == interval.version_id]
            interval.provenance.setdefault("superseded_by", superseded_by)
        return {
            "question": {
                "subject": subject, "attribute": attribute,
                "valid_at": valid_at, "known_at": known_at,
                "asked_at": self.now(),
            },
            "answer": result.to_dict(),
            "full_chain_length": len(chain),
            "chain": [v.to_dict() for v in chain],
        }

    def export(self, subject: str | None = None) -> dict:
        """Deterministic export: same state always serialises identically."""
        rows = (self.store.versions_for(subject) if subject
                else self.store.all_versions())
        rows.sort(key=lambda r: (r["subject"], r["attribute"], r["known_from"],
                                 r["version_id"]))
        return {
            "exported_at": self.now(),
            "version_count": len(rows),
            "event_count": self.store.count_events(),
            "chain": self.store.verify_chain(),
            "versions": rows,
        }