"""Concept-baseline documents (the cleanroom split).

A baseline records what we keep (idea, observable behavior) versus what we
add or change (our own design) — plus run steps. It is the document that
proves a build is an independent implementation, not a copy.
"""

from __future__ import annotations

from pathlib import Path


def write_baseline(out_dir: str | Path, *, name: str, source: str,
                   keeps: str, changes: str, run_steps: str) -> Path:
    """Write BASELINE.md into out_dir. Returns its path."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if not keeps.strip() or not changes.strip():
        raise ValueError("keeps and changes must both be non-empty")
    doc = (
        f"# Concept baseline: {name}\n\n"
        f"Source studied (behavior only, no code copied): {source}\n\n"
        f"## What we keep (idea, observable behavior)\n\n{keeps.strip()}\n\n"
        f"## What we add or change (our own design)\n\n{changes.strip()}\n\n"
        f"## Run steps\n\n{run_steps.strip()}\n"
    )
    path = out / "BASELINE.md"
    path.write_text(doc, encoding="utf-8")
    return path
