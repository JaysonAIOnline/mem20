"""MALIC braid integration: persist harness lessons into the fountain.

The braid harness (`notebooks/research/malic_harness/braid.py`) currently keeps
lessons only in a process-lifetime in-memory `BraidLedger`. This adapter closes
the loop with 00_reference_store: every lesson the rings produce is pushed into
the persistent fountain, and rings can pull teachable references mid-collision.

Usage (wrap the harness BraidLedger):

    from reference_store.braid import FountainLedger
    ledger = FountainLedger(store_root=..., ring='ring_a')
    ledger.write_back(lesson)   # persists to the fountain (dedupes by diff_id)
    ledger.pull("ring_a")       # pull teachable refs to seed this ring

The adapter is intentionally a drop-in for the harness `BraidLedger`: same
`write_back(lesson) -> bool` contract (returns True if the lesson was already
seen, aligning with the harness dedupe counting).
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from .store import ReferenceStore, RefLesson


def lesson_to_ref(lesson) -> RefLesson:
    """Map a harness `Lesson` to a fountain RefLesson with provenance."""
    return RefLesson(
        category=lesson.category,
        kind=lesson.kind,
        text=lesson.text,
        origin_ring=lesson.origin_ring,
        energy=lesson.energy,
        hops=lesson.hops,
        confidence=lesson.confidence,
        ts=lesson.ts,
        cid=lesson.diff_id,      # reuse harness content address exactly
    )


class FountainLedger:
    """Drop-in BraidLedger replacement that persists to 00_reference_store."""

    def __init__(self, store_root: str, ring: str = "ring_unknown") -> None:
        self.store = ReferenceStore(store_root)
        self.ring = ring
        self._seen: set = set()
        # Seed seen-set from what the fountain already knows about this ring.
        for lesson in self.store.all():
            self._seen.add(lesson.cid)

    def write_back(self, lesson) -> bool:
        """Persist a lesson to the fountain; return existed (dedupe flag).

        Mirrors the harness contract: True if diff_id was already seen.
        """
        existed = lesson.diff_id in self._seen
        self._seen.add(lesson.diff_id)
        ref = lesson_to_ref(lesson)
        self.store.push(
            category=lesson.category,
            kind=lesson.kind,
            text=lesson.text,
            origin_ring=lesson.origin_ring,
            actor=f"member@{self.ring}",
            ring=self.ring,
            energy=lesson.energy,
            hops=lesson.hops,
            confidence=lesson.confidence,
            ts=lesson.ts,
        )
        return existed

    def pull(self, ring: str = "", limit: int = 20) -> List[RefLesson]:
        """Pull teachable references for the given ring (or self.ring)."""
        target = ring or self.ring
        cids = [l.cid for l in self.store.search(origin_ring=target, limit=limit)]
        return self.store.pull(cids, actor=f"member@{target}", ring=target)

    def snapshot(self, ring: str = "") -> dict:
        target = ring or self.ring
        return self.store.snapshot(target).to_dict()

    def stats(self) -> dict:
        return self.store.stats()