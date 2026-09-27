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


def test_decimation_preserves_a_closed_surface(kiln, tmp_path):
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
    assert drift < 0.10, f"signed volume drifted {drift * 100:.1f}%"


def test_qem_hits_the_target_and_keeps_the_surface_closed(kiln, tmp_path):
    """QEM is the default because it is measurably the better of the two.

    On a watertight sphere it reaches the requested ratio, stays closed with no
    degenerate faces, and drifts far less volume than clustering.
    """
    sphere(kiln)
    before = export_metrics(kiln, tmp_path, "b")
    kiln.op({"op": "decimate", "ratio": 0.5})
    after = export_metrics(kiln, tmp_path, "a")
    assert 0.45 <= after["triangles"] / before["triangles"] <= 0.55, (
        f"asked for 50%, got {after['triangles'] / before['triangles'] * 100:.0f}%"
    )
    assert after["boundary_edges"] == 0
    assert after["nonmanifold_edges"] == 0
    assert after["degenerate_tris"] == 0
    drift = abs(after["signed_volume"] - before["signed_volume"]) / abs(before["signed_volume"])
    assert drift < 0.05, f"signed volume drifted {drift * 100:.1f}%"


def test_qem_beats_clustering_on_volume_drift(kiln, tmp_path):
    """The reason QEM is the default, pinned so it cannot silently regress."""
    sphere(kiln)
    base = export_metrics(kiln, tmp_path, "base")
    drifts = {}
    for method in ("qem", "cluster"):
        sphere(kiln)
        kiln.op({"op": "decimate", "ratio": 0.5, "method": method})
        m = export_metrics(kiln, tmp_path, method)
        drifts[method] = abs(m["signed_volume"] - base["signed_volume"]) / abs(
            base["signed_volume"])
    assert drifts["qem"] < drifts["cluster"], drifts


def test_an_unknown_method_is_refused_by_name(kiln):
    sphere(kiln)
    with pytest.raises(OpFailed) as exc:
        kiln.op({"op": "decimate", "ratio": 0.5, "method": "magic"})
    assert "unknown method" in str(exc.value)


def test_a_holed_mesh_is_refused_rather_than_reduced(kiln):
    """A decimator run on a broken mesh returns confident nonsense.

    Subdivision is fixed and produces closed surfaces, so the hole is made
    directly: deleting a face from a sphere leaves a surface the decimator must
    decline rather than reduce into something plausible.
    """
    sphere(kiln)
    kiln.op({"op": "select", "target": "S"})
    kiln.op({"op": "mode", "mode": "face"})
    kiln.op({"op": "select_faces", "faces": [0]})
    kiln.op({"op": "delete_faces"})
    with pytest.raises(OpFailed) as exc:
        kiln.op({"op": "decimate", "ratio": 0.5})
    message = str(exc.value)
    assert "not a closed surface" in message
    assert "boundary edge" in message


# -- subdivision ---------------------------------------------------------


def test_subdivision_keeps_a_closed_surface(kiln, tmp_path):
    """The defect this pins: subdivision left holes and a signed volume of zero.

    Three causes, all fixed: the quad sub-faces needed the face point, the
    triangle corners needed the preceding edge point, and the triangulation had
    to fan from the edge point so diagonals cannot coincide across an original
    edge.
    """
    for prim in ("sphere", "torus", "cylinder", "cone"):
        kiln.reset()
        kiln.op({"op": "create", "primitive": prim, "name": "S", "size": [2, 2, 2]})
        for level in (0, 1, 2):
            if level:
                kiln.op({"op": "subsurf", "levels": 1})
            m = export_metrics(kiln, tmp_path, f"{prim}{level}")
            assert m["boundary_edges"] == 0, f"{prim} level {level} opened a hole"
            assert m["nonmanifold_edges"] == 0, (
                f"{prim} level {level} has {m['nonmanifold_edges']} non-manifold edges"
            )
            assert m["degenerate_tris"] == 0
            assert m["non_finite_verts"] == 0


def test_subdivision_volume_converges_instead_of_collapsing(kiln, tmp_path):
    """It used to reach exactly 0.0 from inconsistent normals cancelling."""
    kiln.reset()
    kiln.op({"op": "create", "primitive": "sphere", "name": "S", "size": [2, 2, 2]})
    base = export_metrics(kiln, tmp_path, "v0")["signed_volume"]
    volumes = []
    for level in (1, 2):
        kiln.op({"op": "subsurf", "levels": 1})
        volumes.append(export_metrics(kiln, tmp_path, f"v{level}")["signed_volume"])
    assert all(v != 0.0 for v in volumes), volumes
    assert all(abs(v) > abs(base) * 0.5 for v in volumes), (
        f"volume collapsed: {base} -> {volumes}"
    )


def test_a_subdivided_mesh_can_now_be_decimated(kiln, tmp_path):
    """The reason subdivision had to be fixed: the closed-surface check refused it."""
    kiln.reset()
    kiln.op({"op": "create", "primitive": "sphere", "name": "S", "size": [2, 2, 2]})
    kiln.op({"op": "subsurf", "levels": 1})
    before = export_metrics(kiln, tmp_path, "sb")
    kiln.op({"op": "decimate", "ratio": 0.5})
    after = export_metrics(kiln, tmp_path, "sa")
    assert after["triangles"] < before["triangles"]
    assert after["boundary_edges"] == 0
    assert after["nonmanifold_edges"] == 0
    assert after["watertight"] is True
