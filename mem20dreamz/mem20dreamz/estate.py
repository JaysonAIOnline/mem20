"""What actually exists, versus what the estate merely claims exists.

The dreamer is inventing things that do not exist yet. That only produces
something new if it knows what *does* exist - otherwise it reinvents the tool
that is already sitting two directories away.

So this module draws a line the dreamer can see:

  installed  - a real package on disk, with a pyproject.toml
  claimed    - a capability node in braid
  phantom    - claimed in braid, but no matching package: asserted, not proven
  unclaimed  - installed, but nothing in braid says it exists

The phantom list is the valuable half. A claim nobody implemented is a real gap,
and pretending otherwise is how a fleet ends up with 400 capabilities and no
grounding.

This module only reads. It never writes to braid, the estate, or a live service.
"""

from __future__ import annotations

import json
import os
from typing import Any

ESTATE_ROOT = os.environ.get("MEM20DREAM_ESTATE_ROOT", "/opt/mem20")
BRAID_LOG = os.environ.get("MEM20DREAM_BRAID_LOG", "/opt/mem20/store/braid/mem20.braid")

#: The feed goes into a panelist's context, so it is capped. A truncated honest
#: list beats a complete one that crowds out the actual brief.
MAX_LISTED = 40


def _root(root: str | None) -> str:
    return root if root is not None else ESTATE_ROOT


def _log_path(log_path: str | None) -> str:
    return log_path if log_path is not None else BRAID_LOG


# --- what is really installed ------------------------------------------------


def installed_subsystems(root: str | None = None) -> list[dict[str, Any]]:
    """Real, installable packages on disk. Presence of pyproject.toml is the test."""
    root = _root(root)
    out: list[dict[str, Any]] = []
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        return out
    for name in entries:
        path = os.path.join(root, name)
        if not os.path.isdir(path):
            continue
        manifest = os.path.join(path, "pyproject.toml")
        if not os.path.isfile(manifest):
            continue
        out.append(
            {
                "name": name,
                "packaged": True,
                "has_tests": os.path.isdir(os.path.join(path, "tests")),
                "has_readme": os.path.isfile(os.path.join(path, "README.md")),
            }
        )
    return out


def tool_counts() -> dict[str, int]:
    """How many tools the estate can actually reach, if the inventory is readable."""
    path = os.path.join(ESTATE_ROOT, "toolchest", "inventory.json")
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    counts = data.get("counts")
    return {k: v for k, v in counts.items() if isinstance(v, int)} if isinstance(counts, dict) else {}


def inventory_notes() -> list[str]:
    """Warnings the inventory itself raised, e.g. packages it could not find."""
    path = os.path.join(ESTATE_ROOT, "toolchest", "inventory.json")
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []
    notes = data.get("notes")
    return [str(n) for n in notes][:8] if isinstance(notes, list) else []


# --- what braid merely claims -------------------------------------------------


def capability_claims(log_path: str | None = None) -> dict[str, dict[str, Any]]:
    """Latest capability claim per id. Read-only; the log is never modified."""
    log_path = _log_path(log_path)
    claims: dict[str, dict[str, Any]] = {}
    try:
        handle = open(log_path, encoding="utf-8")  # noqa: SIM115
    except OSError:
        return claims
    with handle:
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            try:
                node = json.loads(raw)
            except ValueError:
                continue
            if node.get("op") != "write:capability":
                continue
            body = (node.get("payload") or {}).get("payload") or {}
            ident = body.get("id") or (node.get("payload") or {}).get("entity_id") or ""
            if not ident:
                continue
            claims[str(ident)] = {
                "id": str(ident),
                "name": body.get("name") or str(ident),
                "provides": body.get("provides") or [],
                "depth": node.get("depth"),
                "cid": (node.get("cid") or "")[:16],
            }
    return claims


# --- the honest comparison ---------------------------------------------------


def estate_report(root: str | None = None, log_path: str | None = None) -> dict[str, Any]:
    """Claimed versus proven, with the comparison's own weakness stated.

    A claim is matched to a package by *name*. That is a weak join - `mem20cviz`
    and `cap.cv-inference.v1` are plausibly the same thing spelled differently -
    so a claim with no name match is reported as UNVERIFIED, not as absent.
    Overstating that gap would feed the dreamer a falsehood, which is worse than
    admitting the join is fuzzy.
    """
    root = _root(root)
    log_path = _log_path(log_path)
    installed = installed_subsystems(root)
    claims = capability_claims(log_path)
    installed_names = {s["name"] for s in installed}

    def _stem(identifier: str) -> str:
        # cap.text.normalize.v1 -> text ; mem20textz -> text
        core = identifier.split(".", 1)[-1] if identifier.startswith("cap.") else identifier
        for prefix in ("mem20", "mem30"):
            core = core.removeprefix(prefix)
        parts = [p for p in core.split(".") if p and not p.startswith("v") or p == "v1"]
        core = ".".join(p for p in parts if p not in {"v1", "v2"})
        return core.rstrip("z").lower()

    proven_stems = {_stem(s["name"]) for s in installed}
    unverified, junk = [], []
    for claim in claims.values():
        if len(claim["id"]) <= 3 and "." not in claim["id"]:
            junk.append(claim)  # ids like "a", "b", "c" are probe noise, not capability
        elif _stem(claim["id"]) not in proven_stems and claim["id"] not in installed_names:
            unverified.append(claim)

    return {
        "installed_count": len(installed),
        "claimed_count": len(claims),
        "unverified_claim_count": len(unverified),
        "junk_claim_count": len(junk),
        "match_basis": "name-only; a no-match claim is unverified, not proven absent",
        "installed": [s["name"] for s in installed],
        "unverified_claims": sorted(unverified, key=lambda c: c["id"])[:MAX_LISTED],
        "junk_claims": sorted(junk, key=lambda c: c["id"])[:MAX_LISTED],
        "tool_counts": tool_counts(),
        "notes": inventory_notes(),
        "tested": [s["name"] for s in installed if s["has_tests"]],
    }


def estate_feed(root: str | None = None, log_path: str | None = None) -> str:
    """Compact, honest context for the panel. States limits; invents nothing."""
    report = estate_report(root, log_path)
    if not report["installed_count"]:
        return "ESTATE: could not be read. Assume nothing about what exists."

    lines = [
        "THE ESTATE AS IT ACTUALLY IS (measured, not remembered):",
        f"  installed packages : {report['installed_count']} (real, on disk)",
    ]
    tools = report.get("tool_counts") or {}
    if tools:
        summary = ", ".join(f"{k}={v}" for k, v in tools.items())
        lines.append(f"  reachable tools    : {summary}")
    lines.append(f"  capability claims  : {report['claimed_count']} recorded in braid")
    if report["installed"]:
        names = ", ".join(report["installed"][:MAX_LISTED])
        lines.append(f"  INSTALLED, do not reinvent: {names}")
    if report["unverified_claims"]:
        names = ", ".join(c["id"] for c in report["unverified_claims"][:12])
        lines.append(
            f"  CLAIMED BUT UNVERIFIED ({report['unverified_claim_count']}) - match is by "
            f"name only, so these may exist under another name or may be fiction: {names}"
        )
    if report["junk_claims"]:
        lines.append(
            f"  OBVIOUSLY NOT REAL: {len(report['junk_claims'])} placeholder claims "
            f"(e.g. {', '.join(c['id'] for c in report['junk_claims'][:6])})"
        )
    for note in report["notes"][:3]:
        lines.append(f"  INVENTORY WARNING: {note[:110]}")
    lines.append(
        "Anything not listed may or may not exist. Propose what genuinely does not "
        "exist yet; do not re-propose something already installed, and do not assume a "
        "claim means it was built."
    )
    return "\n".join(lines)


def context_block(root: str | None = None, log_path: str | None = None) -> str:
    """Alias used by the engine, kept separate so tests can stub one name."""
    return estate_feed(root, log_path)
