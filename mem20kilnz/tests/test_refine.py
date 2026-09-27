"""Tests for the refine stage.

The stage exists to add detail honestly, so the tests check two things: that
the triangle count rises, and that it rises for the right reason. A test that
only checked the count would pass for the subdivision approach, which reaches
the same number while destroying the asset.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mem20kilnz import budgets as B
from mem20kilnz import validate as V
from mem20kilnz.refine import ALLOWED_OPS, refine, refine_file


def test_refine_adds_real_geometry_to_a_box(kiln):
    kiln.reset()
    kiln.op({"op": "create", "primitive": "cube", "name": "Box", "size": [1, 1, 1]})
    report = refine(kiln, family="prop", target_tier="standard", max_steps=6)
    assert report.triangles_before > 0
    assert report.triangles_after > report.triangles_before, "refine added nothing"
    assert report.steps, "refine recorded no steps"
    assert report.steps[0].gained > 0


def test_allowed_ops_exclude_anything_that_only_inflates():
    """The exclusion is structural, not a convention."""
    assert "subsurf" not in ALLOWED_OPS
    assert "subdivide" not in ALLOWED_OPS
    assert "subdivide_surface" not in ALLOWED_OPS
    assert "catmull_clark" not in ALLOWED_OPS
    assert set(ALLOWED_OPS) == {"bevel"}


def test_refine_never_reports_a_tier_it_did_not_measure(kiln):
    """A 12-triangle cube cannot reach 2,000 triangles for a prop honestly."""
    kiln.reset()
    kiln.op({"op": "create", "primitive": "cube", "name": "Tiny", "size": [0.2, 0.2, 0.2]})
    report = refine(kiln, family="prop", target_tier="standard", max_steps=2)
    band = B.tier_band("prop", "standard")
    inside = band[0] <= report.triangles_after <= band[1]
    assert report.target_reached is inside
    assert (report.achieved_tier == "standard") is inside


def test_refine_terminates_when_progress_stops(kiln):
    """Bounded: the loop must exit rather than bevel forever."""
    kiln.reset()
    kiln.op({"op": "create", "primitive": "cube", "name": "B", "size": [1, 1, 1]})
    report = refine(kiln, family="prop", target_tier="hero", max_steps=8)
    assert report.stopped_because, "an unfinished run must say why it stopped"
    assert len(report.steps) <= 8


def test_refine_on_an_empty_scene_refuses_and_says_why(kiln):
    kiln.reset()
    report = refine(kiln, family="prop", target_tier="standard")
    assert report.applied is False
    assert "no geometry" in report.stopped_because
    assert report.triangles_before == 0
    assert report.achieved_tier == "none"


def test_refine_rejects_an_unknown_tier_by_name(kiln):
    kiln.reset()
    kiln.op({"op": "create", "primitive": "cube", "name": "B"})
    with pytest.raises(ValueError, match="unknown detail tier"):
        refine(kiln, family="prop", target_tier="ultra")


def test_refine_measures_from_a_real_export_not_from_bookkeeping(kiln, tmp_path):
    """The count must match the file, or the report is fiction."""
    kiln.reset()
    kiln.op({"op": "create", "primitive": "cube", "name": "B", "size": [1, 1, 1]})
    report = refine(kiln, family="prop", target_tier="standard", max_steps=3)
    out = tmp_path / "out.glb"
    kiln.export(str(out))
    assert report.triangles_after == V.validate(out).total_triangles


def test_refine_file_writes_a_refined_copy(kiln, tmp_path):
    src = tmp_path / "in.glb"
    kiln.reset()
    kiln.op({"op": "create", "primitive": "cube", "name": "Src", "size": [1, 1, 1]})
    kiln.export(str(src))
    before_bytes = src.stat().st_size

    report, dst = refine_file(src, family="prop", target_tier="standard", max_steps=4)
    assert report.triangles_after >= report.triangles_before
    out = Path(dst)
    assert out.is_file()
    assert src.stat().st_size == before_bytes, "refine_file modified its input"
    assert V.validate(out).total_triangles == report.triangles_after


def test_blockout_target_stops_immediately(kiln):
    """Already at the target means no work, and the report says so."""
    kiln.reset()
    kiln.op({"op": "create", "primitive": "cube", "name": "B", "size": [1, 1, 1]})
    report = refine(kiln, family="prop", target_tier="blockout", max_steps=6)
    assert report.target_reached is True
    assert report.steps == []
    assert "blockout" in report.stopped_because


def test_multiple_meshes_are_all_refined(kiln):
    kiln.reset()
    kiln.op({"op": "create", "primitive": "cube", "name": "A", "size": [1, 1, 1]})
    kiln.op({"op": "create", "primitive": "cube", "name": "B", "size": [1, 1, 1]})
    report = refine(kiln, family="prop", target_tier="standard", max_steps=4)
    assert report.steps[0].nodes_beveled == 2
    assert report.steps[0].nodes_skipped == 0


def test_overshoot_is_rolled_back_not_just_stopped(kiln, tmp_path):
    """Stopping the loop is not enough: the asset must not ship over budget.

    A single pass can multiply the count far past the ceiling, so the pass is
    undone and the export that follows must be inside the budget.
    """
    kiln.reset()
    # Ten meshes at 2 segments: measured to overshoot on the second pass, so the
    # rollback path is exercised deterministically.
    for i in range(10):
        kiln.op({"op": "create", "primitive": "cube", "name": f"M{i}", "size": [1, 1, 1]})
    report = refine(kiln, family="prop", target_tier="standard", max_steps=6, segments=2)
    ceiling = B.tier_band("prop", "standard")[1]
    assert report.overshot is True
    assert report.stopped_because
    assert report.target_reached is False, "an overshoot must not count as reaching the target"
    assert report.triangles_after <= ceiling, (
        f"{report.triangles_after} triangles still exceeds the {ceiling} ceiling after rollback"
    )

    out = tmp_path / "after_rollback.glb"
    kiln.export(str(out))
    assert V.validate(out).total_triangles <= ceiling


def test_overshoot_note_records_the_rejected_count(kiln):
    kiln.reset()
    for i in range(10):
        kiln.op({"op": "create", "primitive": "cube", "name": f"M{i}", "size": [1, 1, 1]})
    report = refine(kiln, family="prop", target_tier="standard", max_steps=6, segments=2)
    if report.overshot:
        assert any("rolled back" in s.note for s in report.steps)
        assert "over the standard ceiling" in report.stopped_because
