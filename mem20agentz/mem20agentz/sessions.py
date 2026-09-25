"""Sessions — per-profile conversation history + lifecycle.

Sessions live in the mem20 ledger (tags mem20agentz+session+<profile>) so they
survive restarts, are searchable, and respect the store's no-delete discipline:
"prune" archives (re-tags) rather than destroying history.
"""

from __future__ import annotations

import re
import uuid
from typing import Optional

from ._substrate import Backend, get_backend

_SESSION_RE = re.compile(r"session:([^:]+):([^:]+)$")


class Sessions:
    def __init__(self, backend: Optional[Backend] = None,
                 default_profile: str = "mem20") -> None:
        self._b = backend or get_backend()
        self.default_profile = default_profile

    def new(self, profile: Optional[str] = None,
            title: Optional[str] = None) -> str:
        profile = profile or self.default_profile
        sid = uuid.uuid4().hex[:12]
        self._b.session_add(profile, sid, title or f"session {sid[:6]}")
        return sid

    def list(self, profile: Optional[str] = None) -> list[dict]:
        profile = profile or self.default_profile
        rows = []
        for hit in self._b.session_list(profile):
            topic = hit.get("topic", "") if isinstance(hit, dict) else ""
            m = _SESSION_RE.match(topic)
            if not m:
                continue
            sid = m.group(2)
            if _is_archived(hit):
                continue
            rows.append({
                "session_id": sid,
                "profile": m.group(1),
                "title": _title(hit),
                "ts": _ts(hit),
            })
        rows.sort(key=lambda r: r["ts"], reverse=True)
        return rows

    def rename(self, session_id: str, title: str,
               profile: Optional[str] = None) -> dict:
        profile = profile or self.default_profile
        return self._b.session_update(profile, session_id, title=title)

    def prune(self, profile: Optional[str] = None, keep: int = 0) -> list[str]:
        """Archive everything beyond `keep` newest (no deletion)."""
        profile = profile or self.default_profile
        rows = self.list(profile)
        doomed = rows[keep:]
        for row in doomed:
            self._b.session_update(profile, row["session_id"],
                                   meta={"archived": True})
        return [r["session_id"] for r in doomed]


def _title(hit: dict) -> str:
    if isinstance(hit, dict) and hit.get("content"):
        content = hit["content"]
        return content.split(": ", 1)[-1] if ": " in content else content[:40]
    return ""


def _ts(hit: dict) -> float:
    """Timestamp as epoch float. The substrate returns either a numeric ts or
    an ISO-8601 string (created_at), so both are normalized here."""
    from datetime import datetime

    raw = hit.get("ts") or hit.get("created_at") or 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
        except ValueError:
            try:
                return float(raw)
            except ValueError:
                return 0.0
    return 0.0


def _is_archived(hit: dict) -> bool:
    if not isinstance(hit, dict):
        return False
    return bool(hit.get("meta", {}).get("archived"))