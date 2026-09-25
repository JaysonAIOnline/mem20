"""Reference index: scalar/metadata search over committed references.

Serves the fountain's search need -- find teachable reference by category,
kind, origin ring, text terms, etc. The core store is content-addressed and
append-only; this index is a derivable projection (rebuilt from the store),
so it never diverges from ground truth.

Two concrete backends:
    * InMemoryIndex  - an in-process inverted index over text + metadata.
    * JsonlIndex     - index persisted as JSONL (mirrors mem20's bm25 corpus
                       style) for durability across processes.
"""

from __future__ import annotations

import json
import os
import re
from typing import Dict, List

from .store import RefLesson


def _tokens(text: str) -> List[str]:
    # '_' is a word separator in lesson text (e.g. "pitfall-malformed_json"),
    # so split on it to let partial-word searches match.
    return re.findall(r"[a-zA-Z0-9]+", text.lower())


class RefIndex:
    """Base interface for a reference index (in-memory by default)."""

    def __init__(self) -> None:
        self._docs: Dict[str, RefLesson] = {}  # ref_id -> lesson

    def build(self, lessons: List[RefLesson]) -> None:
        self._docs = {l.ref_id: l for l in lessons}

    def add(self, lesson: RefLesson) -> None:
        self._docs[lesson.ref_id] = lesson

    def search(self, needle: str, category: str = "", kind: str = "", limit: int = 20) -> List[RefLesson]:
        raise NotImplementedError

    def filter(
        self,
        category: str = "",
        kind: str = "",
        origin_ring: str = "",
        min_confidence: float = 0.0,
        limit: int = 50,
    ) -> List[RefLesson]:
        out = []
        for lesson in self._docs.values():
            if category and lesson.category != category:
                continue
            if kind and lesson.kind != kind:
                continue
            if origin_ring and lesson.origin_ring != origin_ring:
                continue
            if lesson.confidence < min_confidence:
                continue
            out.append(lesson)
        out.sort(key=lambda l: l.confidence, reverse=True)
        return out[:limit]


class InMemoryIndex(RefIndex):
    """Simple inverted index over tokens in lesson text + category/kind."""

    def __init__(self) -> None:
        super().__init__()
        self._inverted: Dict[str, List[str]] = {}

    def build(self, lessons: List[RefLesson]) -> None:
        super().build(lessons)
        self._inverted = {}
        for lesson in lessons:
            for tok in set(_tokens(lesson.text) + [lesson.category, lesson.kind]):
                self._inverted.setdefault(tok, []).append(lesson.ref_id)

    def add(self, lesson: RefLesson) -> None:
        super().add(lesson)
        for tok in set(_tokens(lesson.text) + [lesson.category, lesson.kind]):
            self._inverted.setdefault(tok, []).append(lesson.ref_id)

    def search(self, needle: str, category: str = "", kind: str = "", limit: int = 20) -> List[RefLesson]:
        toks = _tokens(needle)
        if not toks:
            return self.filter(category=category, kind=kind, limit=limit)
        # score by presence of query tokens using the inverted index
        scores: Dict[str, int] = {}
        for tok in toks:
            for ref_id in self._inverted.get(tok, []):
                scores[ref_id] = scores.get(ref_id, 0) + 1
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        out = []
        for ref_id, _score in ranked[:limit]:
            lesson = self._docs[ref_id]
            if category and lesson.category != category:
                continue
            if kind and lesson.kind != kind:
                continue
            out.append(lesson)
        return out


class JsonlIndex(RefIndex):
    """Index persisted as JSONL so it survives across processes."""

    def __init__(self, path: str) -> None:
        super().__init__()
        self.path = path

    def build(self, lessons: List[RefLesson]) -> None:
        super().build(lessons)
        if self.path:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            with open(self.path, "w") as fh:
                for lesson in lessons:
                    fh.write(json.dumps(lesson.to_dict()) + "\n")

    def add(self, lesson: RefLesson) -> None:
        super().add(lesson)
        if self.path:
            with open(self.path, "a") as fh:
                fh.write(json.dumps(lesson.to_dict()) + "\n")

    def search(self, needle: str, category: str = "", kind: str = "", limit: int = 20) -> List[RefLesson]:
        return InMemoryIndex.search(self, needle, category=category, kind=kind, limit=limit)
