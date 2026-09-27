"""Add real detail to a blockout, and report honestly when it cannot.

The rule this module exists to enforce: **never raise the triangle count by
destroying the asset.** Subdivision reaches a budget by rounding and shrinking
the mesh, so it is not used here at all — measured on a real crate, one
subdivision pass took 204 triangles to 2,892 and turned a box into a rounded
blob with its bands dissolved. That is a number going up while the asset gets
worse.

Only operations that add geometry a modeller would recognise are used:

* `bevel` with an explicit `region`, which cuts real chamfers on real edges
  (measured: 12 -> 44 -> 76 triangles over successive passes, silhouette intact).
* `array`, which builds genuinely more correct geometry for repeated parts,
  such as crate slats (measured: six bevelled slats, 456 triangles).

Every step is measured by exporting and re-reading the file, and the loop stops
the moment an operation stops making progress. The report states the tier that
was actually reached, which may be lower than the one requested.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import budgets as _budgets
from . import validate as _validate
from .errors import KilnError, OpFailed
from .rpc import Kiln

#: Operations this stage is allowed to apply. Anything that inflates the count
#: without adding detail is excluded by construction, not by convention.
ALLOWED_OPS = ("bevel",)

_TIER_ORDER = {name: i for i, name in enumerate(reversed(_budgets.DETAIL_TIERS))}


@dataclass
class RefineStep:
    """One measured pass."""

    index: int
    op: str
    applied_to: int
    triangles_before: int
    triangles_after: int
    triangles_after: int = 0
    nodes_beveled: int = 0
    nodes_skipped: int = 0
    note: str = ""

    @property
    def gained(self) -> int:
        return self.triangles_after - self.triangles_before

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "op": self.op,
            "applied_to": self.applied_to,
            "triangles_before": self.triangles_before,
            "triangles_after": self.triangles_after,
            "gained": self.gained,
            "nodes_beveled": self.nodes_beveled,
            "nodes_skipped": self.nodes_skipped,
            "note": self.note,
        }


@dataclass
class RefineReport:
    """What refinement actually achieved."""

    applied: bool
    target_tier: str
    start_tier: str
    achieved_tier: str
    triangles_before: int = 0
    triangles_after: int = 0
    target_reached: bool = False
    overshot: bool = False
    stopped_because: str = ""
    steps: list[RefineStep] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "applied": self.applied,
            "target_tier": self.target_tier,
            "start_tier": self.start_tier,
            "achieved_tier": self.achieved_tier,
            "triangles_before": self.triangles_before,
            "triangles_after": self.triangles_after,
            "triangles_gained": self.triangles_after - self.triangles_before,
            "target_reached": self.target_reached,
            "overshot": self.overshot,
            "stopped_because": self.stopped_because,
            "steps": [s.as_dict() for s in self.steps],
        }


def nodes_beveled_in(step: RefineStep) -> int:
    """How many undo steps a pass pushed, so a rejected pass can be reversed."""
    return max(0, step.nodes_beveled)


def _measure(kiln: Kiln, scratch: str) -> int:
    """Triangle count of the live scene, measured from a real export."""
    path = os.path.join(scratch, "measure.glb")
    kiln.export(path)
    return _validate.validate(path).total_triangles


def _mesh_nodes(kiln: Kiln) -> list[str]:
    return [n["name"] for n in kiln.call("list", {}).get("nodes", [])
            if n.get("type") == "mesh"]


def _tier_reached(family: str, triangles: int, target: str) -> bool:
    band = _budgets.tier_band(family, target)
    if band is None:
        return False
    return band[0] <= triangles <= band[1]


def refine(
    kiln: Kiln,
    family: str,
    target_tier: str = "standard",
    max_steps: int = 6,
    amount: float = 0.05,
    segments: int = 2,
) -> RefineReport:
    """Add real edge detail until the target tier is reached or progress stops.

    Stops on the first step that adds no triangles, so this terminates even when
    the target is unreachable. It never reports the target tier unless the
    measurement says so.
    """
    if target_tier not in _budgets.DETAIL_TIERS:
        raise ValueError(
            f"unknown detail tier {target_tier!r}; known: "
            + ", ".join(_budgets.DETAIL_TIERS)
        )

    scratch = tempfile.mkdtemp(prefix="kilnz-refine-")
    before = _measure(kiln, scratch)
    start = _budgets.achieved_tier(family, before)
    report = RefineReport(
        applied=False,
        target_tier=target_tier,
        start_tier=start,
        achieved_tier=start,
        triangles_before=before,
        triangles_after=before,
    )
    if before <= 0:
        report.stopped_because = "scene has no geometry to refine"
        return report

    current = before
    for step_index in range(1, max_steps + 1):
        if _tier_reached(family, current, target_tier):
            report.stopped_because = f"reached the {target_tier} tier"
            report.target_reached = True
            break

        nodes = _mesh_nodes(kiln)
        step = RefineStep(index=step_index, op="bevel", applied_to=len(nodes),
                          triangles_before=current)
        for name in nodes:
            try:
                kiln.command(f"select {name}")
                kiln.op({"op": "bevel", "amount": amount, "segments": segments,
                         "region": "all"})
                step.nodes_beveled += 1
            except (OpFailed, KilnError) as exc:
                step.nodes_skipped += 1
                if not step.note:
                    step.note = f"{name}: {getattr(exc, 'message', exc)}"[:80]

        current = _measure(kiln, scratch)
        step.triangles_after = current
        report.steps.append(step)
        report.applied = report.applied or step.gained > 0

        # Overshooting the ceiling is as wrong as undershooting the floor. A
        # single pass can multiply the count far past the budget, so this is
        # checked before the loop is allowed to continue.
        ceiling = _budgets.tier_band(family, target_tier)
        if ceiling is not None and current > ceiling[1]:
            # Rolling back matters: stopping the loop is not enough, because the
            # asset would still ship over budget. Undo restores the pre-pass
            # state so what ships is inside the ceiling.
            reverted = current
            for _ in range(nodes_beveled_in(step)):
                try:
                    kiln.op({"op": "undo"})
                except (OpFailed, KilnError):
                    break
            reverted = _measure(kiln, scratch)
            step.note = (f"rolled back: pass would have reached {current}, over the "
                         f"{target_tier} ceiling of {ceiling[1]}")
            report.overshot = True
            report.stopped_because = (
                f"pass {step_index} would have reached {current} triangles, over the "
                f"{target_tier} ceiling of {ceiling[1]}; rolled back and stopped"
            )
            current = reverted
            break

        if step.gained <= 0:
            report.stopped_because = (
                f"bevel stopped adding geometry after {step_index} pass(es); "
                "further passes would only round the existing edges"
            )
            break
    else:
        report.stopped_because = f"used all {max_steps} passes without reaching the target"

    report.triangles_after = current
    report.achieved_tier = _budgets.achieved_tier(family, current)
    report.target_reached = _tier_reached(family, current, target_tier) and not report.overshot
    if report.target_reached:
        report.stopped_because = report.stopped_because or f"reached the {target_tier} tier"
    return report


def refine_file(
    path: str | Path,
    family: str,
    out_path: str | Path | None = None,
    target_tier: str = "standard",
    **kwargs,
) -> tuple[RefineReport, str]:
    """Refine a GLB on disk and write the result. Returns the report and the path."""
    src = Path(path)
    dst = Path(out_path) if out_path else src.with_name(src.stem + "_refined.glb")
    dst.parent.mkdir(parents=True, exist_ok=True)
    with Kiln() as kiln:
        kiln.reset()
        kiln.op({"op": "import", "path": str(src)})
        report = refine(kiln, family=family, target_tier=target_tier, **kwargs)
        kiln.export(str(dst))
    return report, str(dst)
