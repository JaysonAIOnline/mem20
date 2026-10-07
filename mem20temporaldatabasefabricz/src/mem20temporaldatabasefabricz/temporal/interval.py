"""Half-open interval algebra for bi-temporal reasoning.

Every interval is `[start, end)`: the start instant is inside the interval, the
end instant is not. That single convention removes the off-by-one ambiguity that
makes "what was true at noon" disagree with "what was true at midnight" after a
correction lands exactly on a boundary.

Two axes, never conflated:

  valid  when the claim was true in the world
  known  when the system held the claim

A correction closes the OLD version's `known` interval and opens a new one. It
never closes the old version's `valid` interval, because the world did not
change - only our belief about it did.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

__all__ = ["Interval", "parse_ts", "fmt_ts", "contains", "overlaps", "FOREVER"]

FOREVER = None  # an open end: the claim has not been closed on that axis


class TimestampError(ValueError):
    """Raised when a timestamp cannot be parsed into an aware instant."""


def parse_ts(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp into an aware UTC datetime.

    None means "open end" and passes through. Naive timestamps are rejected
    rather than silently assumed to be UTC: a fact whose valid-time is known to
    within twelve hours is not the thing this engine is for.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError as exc:
            raise TimestampError(f"not an ISO-8601 timestamp: {value!r}") from exc
    if dt.tzinfo is None:
        raise TimestampError(f"timestamp has no timezone, refusing to guess: {value!r}")
    return dt.astimezone(timezone.utc)


def fmt_ts(dt: datetime | None) -> str | None:
    """Render an aware datetime back to a normalised UTC ISO-8601 string."""
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat()


def _sort_key(value: str | None, default: datetime) -> datetime:
    parsed = parse_ts(value)
    return default if parsed is None else parsed


def contains(start: str | None, end: str | None, instant: str) -> bool:
    """Is `instant` inside the half-open interval [start, end)?

    An absent start means the interval reaches back without limit; an absent end
    means it is still open.
    """
    t = parse_ts(instant)
    assert t is not None, "instant is required"
    begin = _sort_key(start, datetime.min.replace(tzinfo=timezone.utc))
    finish = parse_ts(end)
    if t < begin:
        return False
    if finish is not None and t >= finish:
        return False
    return True


def overlaps(a_start: str | None, a_end: str | None,
             b_start: str | None, b_end: str | None) -> bool:
    """Do two half-open intervals share at least one instant?"""
    lo = max(
        _sort_key(a_start, datetime.min.replace(tzinfo=timezone.utc)),
        _sort_key(b_start, datetime.min.replace(tzinfo=timezone.utc)),
    )
    a_finish = parse_ts(a_end)
    b_finish = parse_ts(b_end)
    if a_finish is not None and lo >= a_finish:
        return False
    if b_finish is not None and lo >= b_finish:
        return False
    return True


@dataclass(frozen=True)
class Interval:
    """One version of one attribute, on both axes at once.

    A version is identified by (subject, attribute, version_id). The version's
    payload lives behind `value_ref` - this engine stores when a claim was
    believed, never a second copy of the claim itself, so it cannot drift out of
    sync with whatever store actually owns the content.
    """

    subject: str
    attribute: str
    version_id: str
    valid_from: str
    known_from: str
    valid_to: str | None = FOREVER
    known_to: str | None = FOREVER
    value_ref: str = ""
    provenance: dict = field(default_factory=dict)

    def valid_at(self, instant: str) -> bool:
        return contains(self.valid_from, self.valid_to, instant)

    def known_at(self, instant: str) -> bool:
        return contains(self.known_from, self.known_to, instant)

    def is_current(self, instant: str | None = None) -> bool:
        """True when the claim is both valid and believed at `instant`."""
        probe = instant or self.known_from
        return self.valid_at(probe) and self.known_at(probe)

    def sort_key(self) -> tuple:
        """Deterministic total order, so equal queries always give equal output."""
        return (
            _sort_key(self.known_from, datetime.min.replace(tzinfo=timezone.utc)),
            _sort_key(self.valid_from, datetime.min.replace(tzinfo=timezone.utc)),
            self.version_id,
        )

    def slice_of(self, valid_at: str | None, known_at: str | None) -> str:
        """Name the bi-temporal slice this version belongs to for a given as-of pair."""
        v_true = True if valid_at is None else self.valid_at(valid_at)
        k_true = True if known_at is None else self.known_at(known_at)
        if v_true and k_true:
            return "valid_now_known_now"
        if not v_true and k_true:
            return "valid_then_known_now"
        if v_true and not k_true:
            return "valid_now_known_then"
        return "valid_then_known_then"

    def to_dict(self) -> dict:
        return {
            "subject": self.subject,
            "attribute": self.attribute,
            "version_id": self.version_id,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "known_from": self.known_from,
            "known_to": self.known_to,
            "value_ref": self.value_ref,
            "provenance": dict(self.provenance),
        }