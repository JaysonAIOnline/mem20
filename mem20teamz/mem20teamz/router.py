"""Routing: mentions wake named profiles, the rest becomes a plan."""

from __future__ import annotations

import re

_MENTION = re.compile(r"@([A-Za-z0-9_][A-Za-z0-9_.\-]*)")

_ACTION_WORDS = ("build", "make", "create", "fix", "write", "test", "review",
                 "plan", "design", "ship", "deploy", "summarize", "research")


def mentions(text: str) -> list[str]:
    """Profile names mentioned with @. Order-preserved, deduplicated."""
    seen: list[str] = []
    for match in _MENTION.finditer(text):
        name = match.group(1).rstrip(".")
        if name and name not in seen:
            seen.append(name)
    return seen


def parse_plan(text: str) -> dict:
    """Deterministic intent parse: action words + targets become steps."""
    lowered = text.lower()
    actions = [word for word in _ACTION_WORDS if word in lowered]
    words = [w.strip(".,!?;:") for w in text.split()]
    targets = [w for w in words if len(w) > 3 and w.lower() not in actions
               and not w.startswith("@")][:5]
    steps = [f"{action} {target}" for action in actions[:3]
             for target in targets[:2]] or ["acknowledge request"]
    return {"actions": actions, "targets": targets, "steps": steps}


def route(store, room: str, sender: str, text: str) -> dict:
    """Route a posted message. Returns a routing record (no side effects
    beyond the post itself; delivery is the caller's job)."""
    posted = store.post(room, sender, text)
    woken: list[dict] = []
    for name in mentions(text):
        member = store.find_profile(room, name)
        if member:
            woken.append(member)
    if woken:
        return {"kind": "direct", "message": posted, "woken": woken,
                "plan": None}
    return {"kind": "broadcast", "message": posted, "woken": [],
            "plan": parse_plan(text)}
