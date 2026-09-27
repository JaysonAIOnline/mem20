"""Decimation quality, measured rather than asserted.

Counting triangles is not quality. These assert the properties that actually
matter -- the surface stays closed, nothing degenerates, and the method that
claims to preserve the surface does -- using the project's own mesh_metrics.

The QEM refusal is pinned deliberately: a decimator that returns a larger mesh
than it was given must fail loudly, not quietly ship.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from mem20kilnz.errors import OpFailed

sys.path.insert(0, str(Path(__file__).parent))
import mesh_metrics as MM  # noqa: E402


def sphere(kiln, size=(2, 2, 2), segments=24):
    kiln.reset()
    kiln.op({"op": "create", "primitive": "sphere", "name": "S",
             "size": list(size), "segments": segments})


def export_metrics(kiln, tmp_path, name="m"):
    p = tmp_path / f"{name}.glb"
    kiln.export(str(p))
    return MM.metrics(p)


def test_the_baseline_sphere_is_watertight(kiln, tmp_path):
    """Everything is measured against this, so it has to be true."""
    sphere(kiln)
    m = export_metrics(kiln, tmp_path, "base")
    assert m["watertight"] is True, m
    assert m["boundary_edges"] == 0
    assert m["nonmanifold_edges"] == 0
    assert m["degenerate_tris"] == 0


def test_a_smooth_sphere_welds_and_a_flat_one_does_not(kiln, tmp_path):
    """Smooth shading is what lets corners share; flat cannot, by definition."""
    sphere(kiln)
    smooth = export_metrics(kiln, tmp_path, "smooth")
    assert smooth["watertight"] is True

    kiln.op({"op": "shade_flat"})
    flat = export_metrics(kiln, tmp_path, "flat")
    assert flat["vertices"] > smooth["vertices"], (
        "flat shading should prevent welding, since every face has its own normal"
    )


def test_shade_ops_are_idempotent_and_report_state(kiln):
    sphere(kiln)
    # A sphere is smooth by default, so shade_flat is the call that changes it.
    assert "flat shading" in kiln.op({"op": "shade_flat"})["message"]
    assert "already flat" in kiln.op({"op": "shade_flat"})["message"]
    assert "smooth shading" in kiln.op({"op": "shade_smooth"})["message"]
    assert "already smooth" in kiln.op({"op": "shade_smooth"})["message"]


def test_clustering_preserves_a_closed_surface(kiln, tmp_path):
    """The shipped default must not tear the mesh open."""
    sphere(kiln)
    before = export_metrics(kiln, tmp_path, "b")
    kiln.op({"op": "decimate", "ratio": 0.5})
    after = export_metrics(kiln, tmp_path, "a")
    assert after["triangles"] < before["triangles"], "nothing was reduced"
    assert after["boundary_edges"] == 0, "decimation opened a hole"
    assert after["nonmanifold_edges"] == 0
    assert after["degenerate_tris"] == 0
    assert after["non_finite_verts"] == 0


def test_volume_drift_stays_bounded(kiln, tmp_path):
    sphere(kiln)
    before = export_metrics(kiln, tmp_path, "b")
    kiln.op({"op": "decimate", "ratio": 0.5})
    after = export_metrics(kiln, tmp_path, "a")
    drift = abs(after["signed_volume"] - before["signed_volume"]) / abs(before["signed_volume"])
    assert drift < 0.25, f"signed volume drifted {drift * 100:.1f}%"


def test_qem_refuses_instead_of_returning_a_larger_mesh(kiln):
    """Pinned deliberately.

    QEM is implemented but does not meet the quality bar: three attempts are
    recorded in failures.md, and the current one turns a 528-triangle sphere
    into 1,470 triangles. It must fail loudly, not quietly return a bigger mesh.
    """
    sphere(kiln)
    with pytest.raises(OpFailed) as exc:
        kiln.op({"op": "decimate", "ratio": 0.5, "method": "qem"})
    message = str(exc.value)
    assert "not available" in message
    assert "larger" in message or "cluster" in message


def test_an_unknown_method_is_refused_by_name(kiln):
    sphere(kiln)
    with pytest.raises(OpFailed) as exc:
        kiln.op({"op": "decimate", "ratio": 0.5, "method": "magic"})
    assert "unknown method" in str(exc.value)
