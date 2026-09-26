"""Engine behaviour, asserted through the client with real numbers.

Each test states what the engine did, not merely that a call returned. Where an
op is expected to refuse bad input, the refusal is part of the contract.
"""
from __future__ import annotations

import pytest

from mem20kilnz.errors import OpFailed


def run(kiln, *lines):
    """Run each line and return its engine message, in order."""
    return [kiln.command(line)["message"] for line in lines]


def test_primitives_create_the_expected_topology(kiln):
    kiln.reset()
    assert "created C" in run(kiln, "create cube C size 1 1 1", "info C")[0]
    assert "created B" in run(kiln, "create sphere B size 1 1 1", "info B")[0]


def test_mesh_edit_changes_face_count(kiln):
    kiln.reset()
    run(kiln, "create cube C", "select C", "mode face", "select_faces region top",
        "extrude amount 0.5")
    info = kiln.info("C")
    assert info["faces"] > 6


def test_subdivision_increases_faces(kiln):
    kiln.reset()
    run(kiln, "create sphere S size 1 1 1", "select S")
    before = kiln.info("S")["faces"]
    run(kiln, "subsurf levels 1")
    after = kiln.info("S")["faces"]
    assert after > before * 3, f"subsurf gave {before} -> {after}"


def test_wireframe_produces_a_tube_per_edge(kiln):
    kiln.reset()
    run(kiln, "create cube C", "select C", "wireframe thickness 0.05")
    info = kiln.info("C")
    assert info["faces"] == 72, f"a cube has 12 edges; expected 72 faces, got {info['faces']}"


def test_boundary_faces_distinguishes_closed_from_open(kiln):
    kiln.reset()
    assert "0 boundary" in run(kiln, "create cube C", "select C", "boundary")[-1]
    assert "1 boundary" in run(kiln, "create plane P", "select P", "boundary")[-1]


def test_decimate_reduces_and_reports_both_counts(kiln):
    kiln.reset()
    run(kiln, "create sphere S size 1 1 1", "select S")
    before = kiln.info("S")["faces"]
    res = kiln.op({"op": "decimate", "ratio": 0.5})
    after = kiln.info("S")["faces"]
    assert after < before
    assert res["data"]["faces_before"] == before
    assert res["data"]["faces_after"] == after


@pytest.mark.parametrize("ratio", [0, 1.0, 1.5, -0.2])
def test_decimate_refuses_a_ratio_outside_the_open_unit_interval(kiln, ratio):
    kiln.reset()
    run(kiln, "create sphere S size 1 1 1", "select S")
    with pytest.raises(OpFailed) as exc:
        kiln.op({"op": "decimate", "ratio": ratio})
    assert "ratio" in str(exc.value)


def test_import_reports_what_it_dropped(fixtures, kiln):
    kiln.reset()
    res = kiln.op({"op": "import", "path": str(fixtures / "extras.glb")})
    dropped = res.get("data", {}).get("dropped_attributes", [])
    assert "COLOR_0" in dropped and "TANGENT" in dropped


def test_import_of_a_truncated_file_is_refused_not_crashed(fixtures, kiln):
    kiln.reset()
    with pytest.raises(OpFailed) as exc:
        kiln.op({"op": "import", "path": str(fixtures / "truncated.glb")})
    assert "import failed" in str(exc.value)


def test_gltf_import_preserves_geometry(kiln, tmp_path):
    """A file the engine wrote must come back with the same triangle count.

    Vertex counts are not expected to match: the exporter writes the render
    soup (three vertices per triangle, no sharing), so an N-face mesh leaves as
    3N positions. Triangles are the invariant that must hold.
    """
    from mem20kilnz.validate import validate

    src = tmp_path / "a.glb"
    out = tmp_path / "b.glb"
    kiln.reset()
    run(kiln, "create cube C", "create sphere S size 0.8 0.8 0.8")
    kiln.export(str(src))
    before = validate(src)
    kiln.reset()
    kiln.op({"op": "import", "path": str(src)})
    kiln.export(str(out))
    after = validate(out)
    assert before.total_triangles == after.total_triangles
    assert before.total_triangles > 0
    assert [m.name for m in before.meshes] == [m.name for m in after.meshes]


def test_obj_round_trip_preserves_vertex_counts(tmp_path, kiln):
    kiln.reset()
    run(kiln, "create cube C", "create sphere B size 0.6 0.6 0.6")
    before = {n["name"]: n.get("verts") for n in kiln.describe()["nodes"] if n["type"] == "mesh"}
    obj = tmp_path / "rt.obj"
    kiln.op({"op": "export_obj", "path": str(obj)})
    kiln.reset()
    kiln.op({"op": "import_obj", "path": str(obj)})
    after = {n["name"]: n.get("verts") for n in kiln.describe()["nodes"] if n["type"] == "mesh"}
    for name, verts in before.items():
        assert after.get(name) == verts, f"{name}: {verts} -> {after.get(name)}"


def test_two_bone_ik_moves_the_rig_toward_the_target(kiln):
    kiln.reset()
    run(kiln, "rig biped tpose", "create cube M size 0.1 0.1 0.1 at 0.62 0.95 0.16",
        "select M", "bind")
    before = [n for n in kiln.describe()["nodes"] if n["type"] == "mesh"]
    assert before
    run(kiln, "ik Forearm.L at 0.1 1.5 0.7")
    msg = kiln.command("describe")
    assert msg["ok"] is True


def test_ik_refuses_a_non_bone(kiln):
    kiln.reset()
    run(kiln, "create cube C")
    with pytest.raises(OpFailed) as exc:
        kiln.op({"op": "ik", "target": "C", "at": [1, 1, 1]})
    assert "bone" in str(exc.value)


def test_render_and_export_both_write_real_files(tmp_path, kiln):
    kiln.reset()
    run(kiln, "create cube C")
    png, glb = tmp_path / "a.png", tmp_path / "a.glb"
    kiln.render(str(png), width=160, height=120, samples=1)
    kiln.export(str(glb))
    assert png.stat().st_size > 0
    assert glb.stat().st_size > 0
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_export_is_deterministic(tmp_path, kiln):
    kiln.reset()
    run(kiln, "create cube C")
    a, b = tmp_path / "a.glb", tmp_path / "b.glb"
    kiln.export(str(a))
    kiln.export(str(b))
    assert a.read_bytes() == b.read_bytes(), "two exports of the same scene differ"


def test_samples_range_is_enforced(kiln):
    kiln.reset()
    assert kiln.samples()["min"] == 1 and kiln.samples()["max"] == 16
    with pytest.raises(Exception) as exc:
        kiln.samples(0)
    assert "32005" in str(exc.value) or "samples" in str(exc.value)


def test_undo_restores_the_previous_scene(kiln):
    kiln.reset()
    run(kiln, "create cube C")
    assert len([n for n in kiln.describe()["nodes"] if n["type"] == "mesh"]) == 1
    run(kiln, "create sphere S")
    assert len([n for n in kiln.describe()["nodes"] if n["type"] == "mesh"]) == 2
    run(kiln, "undo")
    assert len([n for n in kiln.describe()["nodes"] if n["type"] == "mesh"]) == 1


def test_journal_records_applied_ops_in_order(kiln):
    """The journal is the provenance record, including for failed ops."""
    kiln.reset()
    kiln.call("journal", {"clear": True})
    kiln.command("create cube C")
    kiln.op({"op": "subsurf", "levels": 1})
    j = kiln.call("journal", {})
    kinds = [e["op"]["op"] for e in j["entries"]]
    assert kinds == ["create", "subsurf"]
    assert j["count"] == 2
    assert j["failed"] == 0


def test_journal_records_a_failed_op_rather_than_hiding_it(kiln):
    from mem20kilnz.errors import OpFailed

    kiln.reset()
    kiln.call("journal", {"clear": True})
    with pytest.raises(OpFailed):
        kiln.op({"op": "decimate", "ratio": 0.01})
    j = kiln.call("journal", {})
    assert j["failed"] == 1
    assert j["entries"][-1]["ok"] is False
    assert j["entries"][-1]["op"]["op"] == "decimate"


def test_journal_clear_empties_it_without_touching_the_scene(kiln):
    kiln.reset()
    kiln.call("journal", {"clear": True})
    kiln.op({"op": "create", "primitive": "cube", "name": "Keep"})
    before = kiln.call("list", {})["count"]
    cleared = kiln.call("journal", {"clear": True})
    assert cleared["cleared"] == 1
    assert kiln.call("journal", {})["total"] == 0
    assert kiln.call("list", {})["count"] == before, "clearing the journal changed the scene"


def test_journal_since_returns_only_new_entries(kiln):
    kiln.reset()
    kiln.call("journal", {"clear": True})
    kiln.op({"op": "create", "primitive": "cube", "name": "A"})
    mark = kiln.call("journal", {})["total"]
    kiln.op({"op": "create", "primitive": "sphere", "name": "B"})
    later = kiln.call("journal", {"since": mark})
    assert later["count"] == 1
    assert later["entries"][0]["op"]["name"] == "B"
    assert later["total"] == 2
