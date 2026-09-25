"""Core reference store: content-addressed blobs + provenance chain + push/pull.

Data model mirrors the braid harness `Lesson`:
    category, kind (failure/success), text, origin_ring, energy, hops,
    confidence, ts, diff_id (content hash).

Additions for the fountain (persistence + provenance):
    * cid           - content address = stable hash of (category|kind|text),
                      identical to the harness `diff_id` (namespace kept).
    * ref_id        - unique record id (uuid) so the SAME lesson content can be
                      re-seen/pushed by different rings without collision.
    * provenance    - chain of {actor, ring, action, ts, energy, hops} hops that
                      trace how the lesson moved through the braid from origin.
    * prior_head    - link to the store head at write time (append-only chain).

The store is append-only: no overwrite/delete of committed blobs. A lesson's
immutable core (content-addressed) is stored once; repeated pushes by other rings
append new provenance hops, never mutate the original blob.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

# Matches braid.py's content_hash("category", "kind", "text")[:16].
# Kept byte-identical so existing lesson.diff_id values line up 1:1.
HEAD_FILE = "head.json"
SUMMARY_FILE = "summary.json"


def _tokens(text: str) -> List[str]:
    # Tokenize on any non-alphanumeric char, including '_' (lesson text uses
    # forms like "pitfall-malformed_json" / "token_rotation", so '_' is a word
    # separator, not glue).
    return re.findall(r"[a-zA-Z0-9]+", text.lower())


def content_address(category: str, kind: str, text: str) -> str:
    """Content-address a lesson's semantic payload.

    Byte-identical to the braid harness `content_hash(category, kind, text)`
    (sha256("category|kind|text")[:16]) so the fountain dedupes against lessons
    the in-memory ledger already produced. No namespace prefix -- the harness
    has none, and 00 is the persistent form of that same ledger.
    """
    raw = f"{category}|{kind}|{text}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


@dataclass
class RefHop:
    """One provenance hop: how a lesson moved through the braid."""

    actor: str
    ring: str
    action: str  # 'origin' | 'push' | 'pull' | 'accept' | 'drop'
    ts: int
    energy: float
    hops: int
    confidence: float

    def to_dict(self) -> dict:
        return {
            "actor": self.actor,
            "ring": self.ring,
            "action": self.action,
            "ts": self.ts,
            "energy": self.energy,
            "hops": self.hops,
            "confidence": self.confidence,
        }


@dataclass
class RefLesson:
    """A committed reference (the atomic unit of the fountain)."""

    category: str
    kind: str
    text: str
    origin_ring: str
    energy: float
    hops: int
    confidence: float
    ts: int
    cid: str = field(default="")      # content address (== content_address)
    ref_id: str = field(default="")   # record id (uuid)
    provenance: List[RefHop] = field(default_factory=list)
    prior_head: str = field(default="")  # chain link to prior store head

    def __post_init__(self) -> None:
        if not self.cid:
            self.cid = content_address(self.category, self.kind, self.text)
        if not self.ref_id:
            self.ref_id = uuid.uuid4().hex

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "kind": self.kind,
            "text": self.text,
            "origin_ring": self.origin_ring,
            "energy": self.energy,
            "hops": self.hops,
            "confidence": self.confidence,
            "ts": self.ts,
            "cid": self.cid,
            "ref_id": self.ref_id,
            "prior_head": self.prior_head,
            "provenance": [h.to_dict() for h in self.provenance],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RefLesson":
        obj = cls(
            category=d["category"],
            kind=d["kind"],
            text=d["text"],
            origin_ring=d.get("origin_ring", ""),
            energy=d.get("energy", 1.0),
            hops=d.get("hops", 1),
            confidence=d.get("confidence", 0.7),
            ts=d.get("ts", 0),
            cid=d.get("cid", ""),
            ref_id=d.get("ref_id", ""),
            prior_head=d.get("prior_head", ""),
        )
        obj.provenance = [RefHop(**h) for h in d.get("provenance", [])]
        return obj


@dataclass
class RefSnapshot:
    """Point-in-time view of a ring's shared reference state (per-ring knowledge)."""

    ring: str
    tstamp: int
    cids: List[str] = field(default_factory=list)
    head: str = field(default="")

    def to_dict(self) -> dict:
        return {"ring": self.ring, "tstamp": self.tstamp, "cids": self.cids, "head": self.head}


class _ChainHead:
    """Persisted append-only chain head (written atomically)."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._head = ""
        self._count = 0
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r") as fh:
                    data = json.load(fh)
                self._head = data.get("head", "")
                self._count = data.get("count", 0)
            except (OSError, ValueError):
                pass

    @property
    def head(self) -> str:
        return self._head

    @property
    def count(self) -> int:
        return self._count

    def advance(self, new_head: str) -> None:
        with self._lock:
            self._head = new_head
            self._count += 1
            tmp = self.path + ".tmp"
            with open(tmp, "w") as fh:
                json.dump({"head": self._head, "count": self._count}, fh)
            os.replace(tmp, self.path)


class ReferenceStore:
    """Append-only, content-addressed reference store (the fountain).

    Addresses:
        * push(lesson, actor, ring, action)  -> commit blob + provenance hop;
                                                dedupes by content address.
        * pull(cids, actor, ring)            -> fetch committed references and
                                                record a 'pull' provenance hop.
        * search(needle)                     -> fs-scan over content + metadata.
        * snapshot(ring)                     -> per-ring knowledge snapshot.
        * head / proof                       -> append-only chain + verify proof.
    """

    def __init__(self, root: str) -> None:
        self.root = root
        os.makedirs(root, exist_ok=True)
        self.ledger_path = os.path.join(root, "ledger.jsonl")
        self.head_path = os.path.join(root, HEAD_FILE)
        self.blobs_dir = os.path.join(root, "blobs")
        os.makedirs(self.blobs_dir, exist_ok=True)
        self._chain = _ChainHead(self.head_path)
        # RLock: push() holds the lock and internally calls _append_ledger_line()
        # (which must guard the append). Reentrant so push can nest safely.
        self._lock = threading.RLock()
        self._lessons: Dict[str, RefLesson] = {}  # ref_id -> lesson
        self._by_cid: Dict[str, List[str]] = {}   # cid   -> [ref_id]
        self._load_ledger()

    # ---- persistence ---------------------------------------------------

    def _load_ledger(self) -> None:
        if not os.path.exists(self.ledger_path):
            return
        with open(self.ledger_path, "r") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("type") != "lesson":
                    continue
                lesson = RefLesson.from_dict(d["lesson"])
                self._lessons[lesson.ref_id] = lesson
                self._by_cid.setdefault(lesson.cid, []).append(lesson.ref_id)

    def _append_ledger_line(self, record: dict) -> None:
        with self._lock:
            with open(self.ledger_path, "a") as fh:
                fh.write(json.dumps(record) + "\n")
                fh.flush()

    def _write_blob(self, lesson: RefLesson) -> None:
        # Immutable blob: content-addressed, written once.
        p = os.path.join(self.blobs_dir, lesson.cid + ".json")
        if not os.path.exists(p):
            with open(p, "w") as fh:
                json.dump(lesson.to_dict(), fh)

    # ---- API -----------------------------------------------------------

    @property
    def head(self) -> str:
        return self._chain.head

    @property
    def count(self) -> int:
        return self._chain.count

    def proof(self) -> dict:
        """Append-only chain proof: re-derive head from ledger and compare."""
        computed_head, n = self._recompute_head()
        return {
            "head": self._chain.head,
            "computed_head": computed_head,
            "count": n,
            "valid": computed_head == self._chain.head,
        }

    def _recompute_head(self) -> "tuple[str, int]":
        """Re-scan ledger to independently recompute the chain head."""
        h = ""
        n = 0
        if os.path.exists(self.ledger_path):
            with open(self.ledger_path, "r") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    if d.get("type") != "lesson":
                        continue
                    blk = d["lesson"]
                    h = hashlib.sha256((h + "|" + blk["cid"]).encode()).hexdigest()
                    n += 1
        return h, n

    def push(
        self,
        category: str,
        kind: str,
        text: str,
        origin_ring: str,
        actor: str = "member",
        ring: str = "",
        energy: float = 1.0,
        hops: int = 1,
        confidence: float = 0.7,
        ts: Optional[int] = None,
    ) -> dict:
        """Commit a lesson to the fountain. Returns dedupe info.

        No overwrite/delete: the content-addressed blob is committed once.
        A re-push of identical content (same category|kind|text) is a dedupe --
        it appends a provenance hop recording the new actor/ring but does not
        duplicate the blob.
        """
        ts = ts if ts is not None else int(time.time())
        cid = content_address(category, kind, text)

        with self._lock:
            if cid in self._by_cid:
                # dedupe: record origin hop only if never seen, else a push hop
                ref_ids = self._by_cid[cid]
                first = self._lessons[ref_ids[0]]
                ring_used = ring or origin_ring
                hop = RefHop(
                    actor=actor, ring=ring_used, action="push",
                    ts=ts, energy=energy, hops=hops, confidence=confidence,
                )
                first.provenance.append(hop)
                self._append_ledger_line({"type": "hop", "ref_id": first.ref_id, "hop": hop.to_dict()})
                return {
                    "status": "dedupe",
                    "cid": cid,
                    "ref_id": first.ref_id,
                    "ts": ts,
                }

            head = self._chain.head
            lesson = RefLesson(
                category=category, kind=kind, text=text,
                origin_ring=origin_ring, energy=energy, hops=hops,
                confidence=confidence, ts=ts, cid=cid, prior_head=head,
            )
            ring_used = ring or origin_ring
            lesson.provenance.append(RefHop(
                actor=actor, ring=ring_used, action="origin",
                ts=ts, energy=energy, hops=hops, confidence=confidence,
            ))

            self._lessons[lesson.ref_id] = lesson
            self._by_cid.setdefault(cid, []).append(lesson.ref_id)
            self._write_blob(lesson)
            self._append_ledger_line({"type": "lesson", "lesson": lesson.to_dict()})
            self._chain.advance(hashlib.sha256((head + "|" + cid).encode()).hexdigest())
            return {"status": "committed", "cid": cid, "ref_id": lesson.ref_id, "ts": ts}

    def pull(self, cids: Iterable[str], actor: str = "member", ring: str = "", ts: Optional[int] = None) -> List[RefLesson]:
        """Pull already-committed references by content address.

        Records a 'pull' provenance hop for each, enabling audit of which ring
        consumed which lesson mid-collision. Missing cids are skipped silently.
        """
        ts = ts if ts is not None else int(time.time())
        got: List[RefLesson] = []
        for cid in cids:
            ref_ids = self._by_cid.get(cid)
            if not ref_ids:
                continue
            lesson = self._lessons[ref_ids[0]]
            lesson.provenance.append(RefHop(
                actor=actor, ring=ring, action="pull",
                ts=ts, energy=lesson.energy, hops=lesson.hops, confidence=lesson.confidence,
            ))
            self._append_ledger_line({"type": "hop", "ref_id": lesson.ref_id, "hop": lesson.provenance[-1].to_dict()})
            got.append(lesson)
        return got

    def get(self, cid: str) -> Optional[RefLesson]:
        ref_ids = self._by_cid.get(cid)
        if not ref_ids:
            return None
        return self._lessons[ref_ids[0]]

    def search(
        self,
        needle: str = "",
        category: str = "",
        kind: str = "",
        origin_ring: str = "",
        min_confidence: float = 0.0,
        limit: int = 20,
    ) -> List[RefLesson]:
        """Search/search-filter committed references.

        Lightweight lexical match over text + category/kind, plus scalar
        filters (kind, category, origin_ring, min_confidence). This is a pure
        projection of the append-only ledger -- no divergence from ground truth.
        """
        out: List[RefLesson] = []
        toks = _tokens(needle) if needle else []
        for lesson in self._lessons.values():
            if category and lesson.category != category:
                continue
            if kind and lesson.kind != kind:
                continue
            if origin_ring and lesson.origin_ring != origin_ring:
                continue
            if lesson.confidence < min_confidence:
                continue
            if toks:
                hay = _tokens(lesson.text + " " + lesson.category + " " + lesson.kind)
                if not all(tok in hay for tok in toks):
                    continue
            out.append(lesson)
        out.sort(key=lambda l: (l.kind == "success", l.confidence), reverse=True)
        return out[:limit]

    def all(self) -> List[RefLesson]:
        return list(self._lessons.values())

    def stats(self) -> dict:
        lessons = self._lessons
        by_kind = {}
        by_cat = {}
        origins = set()
        for lesson in lessons.values():
            by_kind[lesson.kind] = by_kind.get(lesson.kind, 0) + 1
            by_cat[lesson.category] = by_cat.get(lesson.category, 0) + 1
            origins.add(lesson.origin_ring)
        return {
            "records": len(lessons),
            "unique_cids": len(self._by_cid),
            "by_kind": by_kind,
            "by_category": by_cat,
            "origin_rings": sorted(origins),
            "head": self._chain.head,
            "proof_valid": self.proof()["valid"],
        }

    def snapshot(self, ring: str) -> RefSnapshot:
        """Per-ring knowledge snapshot: cids attributable to a ring's origin or hops."""
        cids: List[str] = []
        for lesson in self._lessons.values():
            hops_rings = {h.ring for h in lesson.provenance}
            if lesson.origin_ring == ring or ring in hops_rings:
                cids.append(lesson.cid)
        return RefSnapshot(
            ring=ring,
            tstamp=int(time.time()),
            cids=sorted(set(cids)),
            head=self._chain.head,
        )
