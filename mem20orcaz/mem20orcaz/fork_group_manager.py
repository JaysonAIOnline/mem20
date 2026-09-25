"""Fork group coordination for mem20orcaz.

Pure-stdlib port of OrKa's ``ForkGroupManager`` (the in-memory
``SimpleForkGroupManager`` variant). Coordinates parallel branches spawned by
fork nodes and awaited by join nodes: group lifecycle, per-agent completion
tracking, pending-agent discovery and branch-sequence ordering.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional


class ForkGroupError(Exception):
    """Raised for invalid fork-group operations."""


class SimpleForkGroupManager:
    """In-memory fork group manager (Redis-free)."""

    def __init__(self) -> None:
        self._groups: Dict[str, Dict[str, Any]] = {}
        self._branch_seq: Dict[str, Dict[str, str]] = {}

    # -- lifecycle -------------------------------------------------------------
    def create_group(self, group_id: Optional[str] = None) -> str:
        gid = group_id or self.generate_group_id("group")
        self._groups[gid] = {
            "id": gid,
            "members": {},
            "created_at": time.time(),
            "completed_at": None,
        }
        return gid

    def delete_group(self, group_id: str) -> None:
        self._groups.pop(group_id, None)
        self._branch_seq.pop(group_id, None)

    def group_exists(self, group_id: str) -> bool:
        return group_id in self._groups

    def get_group(self, group_id: str) -> Optional[Dict[str, Any]]:
        return self._groups.get(group_id)

    def list_groups(self) -> List[str]:
        return list(self._groups.keys())

    # -- membership -------------------------------------------------------------
    def add_members(self, group_id: str, members: List[str]) -> None:
        grp = self._require(group_id)
        status_by_id = grp["members"]
        for m in members:
            status_by_id.setdefault(m, {"status": "pending", "count": 0})

    def mark_agent_done(self, group_id: str, agent_id: str) -> None:
        grp = self._require(group_id)
        status_by_id = grp["members"]
        st = status_by_id.setdefault(agent_id, {"status": "pending", "count": 0})
        st["status"] = "done"
        st["count"] = int(st.get("count", 0)) + 1

    def mark_agent_failed(self, group_id: str, agent_id: str) -> None:
        grp = self._require(group_id)
        status_by_id = grp["members"]
        st = status_by_id.setdefault(agent_id, {"status": "pending", "count": 0})
        st["status"] = "failed"

    def is_group_done(self, group_id: str) -> bool:
        grp = self._groups.get(group_id)
        if not grp:
            return False
        members = grp["members"]
        if not members:
            return True
        return all(st["status"] in ("done", "failed") for st in members.values())

    def list_pending_agents(self, group_id: str) -> List[str]:
        grp = self._groups.get(group_id)
        if not grp:
            return []
        return [aid for aid, st in grp["members"].items() if st["status"] == "pending"]

    def list_group_members(self, group_id: str) -> List[str]:
        grp = self._groups.get(group_id)
        return list(grp["members"].keys()) if grp else []

    def agent_status(self, group_id: str, agent_id: str) -> Optional[Dict[str, Any]]:
        grp = self._groups.get(group_id)
        if not grp:
            return None
        return grp["members"].get(agent_id)

    def status_map(self, group_id: str) -> Dict[str, Dict[str, Any]]:
        grp = self._groups.get(group_id)
        return dict(grp["members"]) if grp else {}

    def clear_group(self, group_id: str) -> None:
        grp = self._groups.get(group_id)
        if grp:
            grp["members"] = {}
            grp["completed_at"] = None

    # -- ids and sequencing -------------------------------------------------------
    def generate_group_id(self, base_id: str) -> str:
        return f"{base_id}:{uuid.uuid4().hex[:8]}"

    def track_branch_sequence(self, fork_group_id: str, agent_sequence: List[str]) -> None:
        self._branch_seq[fork_group_id] = {aid: (agent_sequence[i - 1] if i > 0 else None)
                                           for i, aid in enumerate(agent_sequence)}

    def next_in_sequence(self, fork_group_id: str, agent_id: str) -> Optional[str]:
        """Return the agent that should follow ``agent_id`` in a branch sequence."""
        seq = self._branch_seq.get(fork_group_id, {})
        return seq.get(agent_id)

    def _require(self, group_id: str) -> Dict[str, Any]:
        grp = self._groups.get(group_id)
        if not grp:
            raise ForkGroupError(f"fork group {group_id!r} does not exist")
        return grp


ForkGroupManager = SimpleForkGroupManager  # stdlib alias (Redis variant not ported)