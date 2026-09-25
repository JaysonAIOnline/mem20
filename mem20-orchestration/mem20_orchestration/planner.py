"""Plan validation: catch bad Blender op sequences before they reach Blender.

A wrong op name is a runtime `AttributeError` deep inside a live Blender
session, minutes after a long build started. Validating the whole sequence
against the real catalog first turns that into an immediate, specific report.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .catalog import Catalog, CatalogError, load as load_catalog


@dataclass
class Finding:
    severity: str
    index: int
    op: str
    message: str

    def as_dict(self) -> dict:
        return {"severity": self.severity, "index": self.index,
                "op": self.op, "message": self.message}


@dataclass
class Report:
    total_steps: int = 0
    valid_steps: int = 0
    findings: list[Finding] = field(default_factory=list)
    modules_used: list[str] = field(default_factory=list)
    blender_version: str = ""

    @property
    def ok(self) -> bool:
        return not any(f.severity == "error" for f in self.findings)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warning"]

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "total_steps": self.total_steps,
            "valid_steps": self.valid_steps,
            "blender_version": self.blender_version,
            "modules_used": self.modules_used,
            "errors": [f.as_dict() for f in self.errors],
            "warnings": [f.as_dict() for f in self.warnings],
        }


def _step_op(step) -> str:
    if isinstance(step, str):
        return step
    if isinstance(step, dict):
        for key in ("op", "name", "operator"):
            if key in step and isinstance(step[key], str):
                return step[key]
    return ""


def validate(steps, catalog: Catalog | None = None) -> Report:
    """Validate an ordered sequence of Blender ops against the real catalog."""
    cat = catalog or load_catalog()
    report = Report(blender_version=cat.blender_version)
    report.total_steps = len(steps)
    modules: list[str] = []
    seen: dict[str, int] = {}

    for index, step in enumerate(steps):
        op_name = _step_op(step)
        if not op_name:
            report.findings.append(Finding(
                "error", index, "",
                "step has no op name (expected a string or {'op': ...})"))
            continue

        if not op_name.startswith("bpy.ops."):
            report.findings.append(Finding(
                "error", index, op_name,
                f"op must start with 'bpy.ops.', got {op_name!r}"))
            continue

        entry = cat.get(op_name)
        if entry is None:
            module = op_name[len("bpy.ops."):].partition(".")[0]
            known = module in cat.modules
            report.findings.append(Finding(
                "error", index, op_name,
                f"unknown operator in Blender {cat.blender_version}"
                + ("" if known else f"; module 'bpy.ops.{module}' does not exist")
            ))
            continue

        report.valid_steps += 1
        if entry.module not in modules:
            modules.append(entry.module)
        if op_name in seen:
            report.findings.append(Finding(
                "warning", index, op_name,
                f"already run at step {seen[op_name]}; repeated ops can be "
                "non-idempotent"))
        else:
            seen[op_name] = index

    report.modules_used = sorted(modules)
    return report


def load_plan(path: str) -> list:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("steps"), list):
        return data["steps"]
    raise ValueError("plan must be a JSON list, or an object with a 'steps' list")


def save_plan(path: str, steps: list, blender_version: str = "") -> None:
    payload = {"blender_version": blender_version, "steps": steps}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")


__all__ = ["Finding", "Report", "validate", "load_plan", "save_plan",
           "CatalogError"]
