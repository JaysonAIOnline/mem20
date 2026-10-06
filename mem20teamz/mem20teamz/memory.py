"""Memory seam: per-room recall/store through injected hooks.

The default hooks keep an in-process transcript mirror (offline-safe).
Production wires these to the mem20 memory engine; tests inject fakes.
"""

from __future__ import annotations

from typing import Callable, Optional


class Memory:
    def __init__(self, recall: Optional[Callable] = None,
                 remember: Optional[Callable] = None) -> None:
        self._recall = recall or (lambda room, k=20: [])
        self._remember = remember or (lambda room, sender, text: None)
        self.mirror: list[dict] = []

    def recall(self, room: str, k: int = 20) -> list[dict]:
        try:
            hits = self._recall(room, k)
        except Exception:
            hits = []
        local = [m for m in self.mirror if m["room"] == room][-k:]
        return list(hits) + local

    def remember(self, room: str, sender: str, text: str) -> None:
        self.mirror.append({"room": room, "sender": sender, "text": text})
        try:
            self._remember(room, sender, text)
        except Exception:
            pass
