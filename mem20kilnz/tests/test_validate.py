"""Tests for the read-only validator and the budget/naming gate.

These cover a real bug class: `validate` and `gate` were the same call, so a
structurally perfect file reported FAIL because of a budget warning, and
`check_budgets` findings were being discarded rather than appended.
"""

from __future__ import annotations

import pytest

from mem20kilnz import validate as V

DEMO = "engine/examples/demo.glb"


def test_demo_file_is_structurally_valid():
    """Structure only. The demo is under budget and mis-named, but that is not
    a structural defect."""
    report = V.validate(DEMO)
    assert report.ok is True
    assert report.version.startswith("2")
    assert report.total_triangles > 0
    assert report.meshes


def test_gate_ok_is_derived_from_findings_not_the_stored_verdict():
    """`ok` is fixed during validation; `gate_ok` must also see later findings."""
    report = V.validate(DEMO)
    assert report.ok is True
    assert report.gate_ok is True

    # A budget error appended after validation must flip the gate verdict.
    report.findings.append(V.Finding("error", "budget", "injected", "prop"))
    assert report.ok is True
    assert report.gate_ok is False


def test_budget_shortfall_is_an_error_and_naming_is_a_warning():
    report = V.validate(DEMO)
    report.findings.extend(V.check_budgets(report, family="prop"))
    codes = {(f.severity, f.code) for f in report.findings}
    assert ("error", "budget") in codes, f"expected a budget error, got {codes}"
    assert ("warning", "naming") in codes, f"expected naming warnings, got {codes}"


def test_require_prefix_escalates_naming_to_an_error():
    report = V.validate(DEMO)
    strict = V.check_budgets(report, family="prop", require_prefix=True)
    naming = [f for f in strict if f.code == "naming"]
    assert naming, "demo meshes have no roadmap prefix, so strict mode must find them"
    assert all(f.severity == "error" for f in naming), (
        "strict mode must escalate naming misses from warning to error"
    )
    # The budget error is independent of the naming strictness.
    assert any(f.code == "budget" and f.severity == "error" for f in strict)


def test_truncated_file_fails_structurally():
    tmp = pytest.importorskip("pathlib")
    broken = tmp.Path("broken.glb")
    broken.write_bytes(tmp.Path(DEMO).read_bytes()[:200])
    report = V.validate(broken)
    assert report.ok is False
    assert any(f.code == "length_mismatch" for f in report.errors)


def test_non_glb_input_is_refused_not_crashed(tmp_path):
    junk = tmp_path / "not.glb"
    junk.write_bytes(b"this is not a gltf file at all")
    report = V.validate(junk)
    assert report.ok is False
    assert report.findings


def test_gate_wraps_validate_and_applies_budgets():
    report = V.gate(DEMO, family="prop")
    assert report.ok is False, "the demo is under the LOD0 floor, so the gate must refuse it"
    assert report.gate_ok is False
    assert any(f.code == "budget" for f in report.errors)
