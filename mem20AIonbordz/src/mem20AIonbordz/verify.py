"""Drift detection.

A generated pack is a snapshot. This re-probes every fact it recorded and reports
what no longer matches, so the reader learns that the document has gone stale
instead of quietly trusting it.

It is deliberately read-only. It reports; it never rewrites the pack, because a
verifier that edits what it inspects is exactly the failure mode the governance
rules forbid.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .discover import (
    SITEMAP_JSON,
    discover_commands,
    discover_paths,
    discover_ports,
    discover_sitemap_age,
    discover_subsystems,
    discover_units,
)
from .facts import FactSet


@dataclass
class Drift:
    key: str
    recorded: object
    now: object
    kind: str
    volatile: bool = False

    @property
    def drifted(self) -> bool:
        # Volatile facts (live sockets, unit states) are observed and reported but
        # never counted as drift: they change by design, and holding a verifier to
        # a moving target would make it useless.
        if self.volatile:
            return False
        return self.recorded != self.now

    def line(self) -> str:
        state = "DRIFT" if self.drifted else ("live" if self.volatile else "ok")
        if self.drifted:
            return f"  [{state}] {self.key}: was {self.recorded!r} now {self.now!r}"
        if self.volatile:
            return f"  [{state}] {self.key}: {self.now!r}"
        return f"  [{state}] {self.key}: {self.now!r}"

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "recorded": self.recorded,
            "now": self.now,
            "kind": self.kind,
            "volatile": self.volatile,
            "drifted": self.drifted,
        }


VOLATILE_KINDS = {"port", "unit"}


def _current_facts(sitemap: Path = SITEMAP_JSON) -> FactSet:
    """Re-probe exactly the same fact set that generation recorded.

    Missing a probe here would make every pack report phantom drift, so this
    must stay in step with `discover.collect_all`.
    """
    facts = FactSet()
    discover_paths(facts)
    discover_commands(facts)
    discover_ports(facts)
    discover_units(facts)
    discover_subsystems(facts, sitemap)
    discover_sitemap_age(facts, sitemap)
    return facts


def verify_pack(pack_dir: Path, sitemap: Path = SITEMAP_JSON) -> list[Drift]:
    """Compare the pack's recorded facts against the live host."""
    manifest_path = pack_dir / "onboarding.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"no onboarding.json in {pack_dir}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    recorded = {f["key"]: f for f in manifest.get("facts", [])}

    now_facts = _current_facts(sitemap)
    now = {f.key: f.value for f in now_facts}

    results: list[Drift] = []

    for key, fact in recorded.items():
        results.append(
            Drift(key, fact["value"], now.get(key), fact["kind"], fact["kind"] in VOLATILE_KINDS)
        )

    for key in now:
        if key not in recorded:
            results.append(Drift(key, None, now[key], "new"))

    return results


def render(results: list[Drift], pack_dir: Path) -> str:
    drifted = [r for r in results if r.drifted]
    lines = [
        f"Verifying {pack_dir}",
        f"  checked {len(results)} claim(s); {len(drifted)} drifted.",
        "",
    ]
    if drifted:
        lines.append("DRIFTED:")
        for row in drifted:
            lines.append(row.line())
        lines.append("")
        lines.append("Re-run `mem20aionbordz new` to regenerate the pack.")
    else:
        lines.append("No drift. Every recorded claim still matches this host.")
    return "\n".join(lines)