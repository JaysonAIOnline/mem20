"""Tests for external mesh ingest.

The point of these is honesty: probe must measure rather than assume, and a
file the importer cannot read must be refused by name instead of producing an
empty asset that looks like a success.
"""

from __future__ import annotations

import json
from pathlib import Path

from mem20kilnz.ingest import SUPPORTED_SUFFIXES, convert, probe
from mem20kilnz.pipeline import BuildRequest, build

DEMO = "engine/examples/demo.glb"


def test_probe_measures_a_real_glb():
    p = probe(DEMO)
    assert p.ok is True
    assert p.recognised is True
    assert p.format == "glTF binary"
    assert p.meshes == 3
    assert p.triangles == 542
    assert p.vertices > 0
    assert p.has_normals is True
    assert p.has_uvs is True
    assert p.glb_bytes == Path(DEMO).stat().st_size
    assert len(p.sha256) == 64


def test_probe_reports_the_budget_gap_rather_than_a_verdict_only():
    p = probe(DEMO, family="prop")
    assert p.budget["lod0_min"] == 2000
    assert p.budget["ok"] is False
    # The reason names the tier, so a refusal says which bar was applied.
    assert "under the standard floor" in p.budget["reason"]
    assert p.budget["tier"] == "standard"
    assert p.gate_ok is False


def test_probe_does_not_modify_the_file(tmp_path):
    """Probe is read-only, so the hash must be identical afterwards."""
    import hashlib

    before = hashlib.sha256(Path(DEMO).read_bytes()).hexdigest()
    probe(DEMO)
    after = hashlib.sha256(Path(DEMO).read_bytes()).hexdigest()
    assert before == after


def test_probe_refuses_a_missing_file_by_name(tmp_path):
    p = probe(tmp_path / "absent.glb")
    assert p.ok is False
    assert p.recognised is False
    assert "no file at" in p.reason


def test_probe_refuses_an_unsupported_extension(tmp_path):
    f = tmp_path / "model.fbx"
    f.write_bytes(b"fbx bytes")
    p = probe(f)
    assert p.ok is False
    assert p.recognised is False
    assert "unsupported extension" in p.reason
    assert ".glb" in p.reason


def test_probe_reports_a_corrupt_glb_as_not_ok(tmp_path):
    bad = tmp_path / "broken.glb"
    bad.write_bytes(b"definitely not gltf" * 20)
    p = probe(bad)
    assert p.recognised is True
    assert p.ok is False
    assert p.reason


def test_probe_accepts_obj_but_says_geometry_was_not_measured(tmp_path):
    f = tmp_path / "SM_Quad.obj"
    f.write_text("v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nf 1 2 3 4\n", encoding="utf-8")
    p = probe(f)
    assert p.recognised is True
    assert p.ok is True
    assert p.triangles == 0
    assert "not measured" in p.reason


def test_supported_suffixes_are_the_ones_the_importer_reads():
    assert set(SUPPORTED_SUFFIXES) == {".glb", ".gltf", ".obj"}


def test_convert_preserves_geometry_and_marks_provenance(tmp_path):
    out = tmp_path / "out"
    records = convert([DEMO], out)
    assert len(records) == 1
    r = records[0]
    assert r["source"] == "external"
    assert r["converted"] is True
    assert r["error"] == ""
    assert r["glb_bytes"] > 0
    assert r["imported_triangles"] == 542, "import must not lose triangles"
    assert len(r["input_sha256"]) == 64
    assert len(r["glb_sha256"]) == 64
    assert r["input_sha256"] != r["glb_sha256"], "the copy is a distinct artifact"

    manifest = json.loads(Path(r["manifest"]).read_text())
    assert manifest["kind"] == "ingest"
    assert manifest["source"] == "external"
    assert manifest["input"]["sha256"] == r["input_sha256"]
    assert [e["op"].get("op") for e in manifest["journal"]] == ["import"]


def test_convert_refuses_an_unreadable_file_and_says_why(tmp_path):
    junk = tmp_path / "junk.glb"
    junk.write_bytes(b"nope")
    records = convert([junk], tmp_path / "out")
    assert records[0]["converted"] is False
    assert records[0]["error"]


def test_convert_refuses_an_unsupported_format_without_touching_the_engine(tmp_path):
    fbx = tmp_path / "mesh.fbx"
    fbx.write_bytes(b"fbx")
    records = convert([fbx], tmp_path / "out")
    r = records[0]
    assert r["converted"] is False
    assert "unsupported extension" in r["error"]
    assert r["glb"] == ""
    assert not (tmp_path / "out" / "mesh.glb").exists()


def test_convert_handles_a_generated_asset_as_an_external_input(kiln, tmp_path):
    """A file we generated is still external input to the ingest path."""
    built = build(
        BuildRequest(brief="create sphere SM_Src size 1 1 1", out_dir=tmp_path / "src",
                     name="SM_Src", gate=False, preview=False),
        kiln=kiln,
    )
    records = convert([built.glb], tmp_path / "out")
    assert records[0]["converted"] is True
    assert records[0]["imported_triangles"] == built.triangles
    assert records[0]["input_sha256"] == built.glb_sha256
