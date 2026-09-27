"""Tests for the brief-to-asset pipeline and its provenance manifest.

These use the DSL and the built-in English agent rather than a language model,
so the suite is bounded and never depends on a network call. The journal
assertions matter most: the whole point is recovering the ops the engine
applied, which a client cannot otherwise see.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mem20kilnz.pipeline import (
    BuildRequest,
    _journal_summary,
    build,
    build_many,
    sha256_file,
    sha256_text,
    verify,
)


def test_journal_summary_counts_kinds_and_failures():
    entries = [
        {"op": {"op": "create"}, "ok": True, "message": "created A"},
        {"op": {"op": "create"}, "ok": True, "message": "created B"},
        {"op": {"op": "subsurf"}, "ok": True, "message": "ok"},
        {"op": {"op": "decimate"}, "ok": False, "message": "no valid collapse"},
    ]
    summary = _journal_summary(entries)
    assert summary["count"] == 4
    assert summary["failed"] == 1
    assert summary["by_kind"] == {"create": 2, "decimate": 1, "subsurf": 1}
    assert summary["failures"] == [{"op": "decimate", "message": "no valid collapse"}]


def test_journal_summary_tolerates_junk_entries():
    """A malformed entry must not take the manifest down."""
    summary = _journal_summary([{"op": "notadict", "ok": True}, {}, {"op": {"op": "x"}}])
    assert summary["count"] == 3


def test_hashes_are_real(tmp_path):
    f = tmp_path / "a.bin"
    f.write_bytes(b"kilnz")
    assert len(sha256_file(f)) == 64
    assert sha256_file(f) == sha256_text("kilnz")
    assert sha256_file(tmp_path / "absent") == ""


def test_build_writes_asset_and_manifest(kiln, tmp_path):
    r = build(
        BuildRequest(brief="create cube SM_Box size 1 1 1", out_dir=tmp_path, name="SM_Box",
                     preview=True, samples=1, gate=False),
        kiln=kiln,
    )
    assert r.glb_bytes > 0, r.error
    assert Path(r.glb).is_file()
    assert Path(r.manifest).is_file()
    assert r.ok is True
    assert r.glb_sha256 == sha256_file(r.glb)
    assert r.op_count >= 1


def test_manifest_records_the_ops_that_were_actually_applied(kiln, tmp_path):
    """The journal is the provenance record, so it must contain the real ops."""
    r = build(
        BuildRequest(brief="create cube SM_A size 1 1 1", out_dir=tmp_path, name="SM_A",
                     gate=False, preview=False),
        kiln=kiln,
    )
    manifest = json.loads(Path(r.manifest).read_text())
    entries = manifest["journal"]["entries"]
    assert entries, "manifest recorded no journal entries"
    kinds = [e["op"]["op"] for e in entries]
    assert "create" in kinds
    assert manifest["journal"]["count"] == len(entries)
    # Every entry must carry a verdict, so a failure can never hide.
    assert all("ok" in e for e in entries)


def test_journal_is_scoped_to_this_build_not_the_previous_one(kiln, tmp_path):
    kiln.reset()
    kiln.op({"op": "create", "primitive": "cube", "name": "SM_Stale"})
    r = build(
        BuildRequest(brief="create sphere SM_Fresh size 1 1 1", out_dir=tmp_path,
                     name="SM_Fresh", gate=False, preview=False),
        kiln=kiln,
    )
    manifest = json.loads(Path(r.manifest).read_text())
    names = [e["op"].get("name") for e in manifest["journal"]["entries"]]
    assert "SM_Stale" not in names, "journal leaked ops from before this build"
    assert "SM_Fresh" in names


def test_manifest_is_written_even_when_the_gate_refuses(kiln, tmp_path):
    """A refusal must be auditable, not silent.

    auto_refine is off so this exercises the gate alone. A raw 12-triangle cube
    is under the 2,000 prop floor and must be refused.
    """
    r = build(
        BuildRequest(brief="create cube SM_Tiny size 0.2 0.2 0.2", out_dir=tmp_path,
                     name="SM_Tiny", family="prop", gate=True, preview=False,
                     auto_refine=False),
        kiln=kiln,
    )
    assert r.gate_ok is False
    assert r.ok is False
    assert r.gate_findings, "a refusal must state its reasons"
    assert Path(r.manifest).is_file()
    manifest = json.loads(Path(r.manifest).read_text())
    assert manifest["gate"]["applied"] is True
    assert manifest["gate"]["ok"] is False
    assert manifest["result"]["ok"] is False


def test_verify_accepts_an_untouched_manifest(kiln, tmp_path):
    r = build(
        BuildRequest(brief="create cube SM_Ok size 1 1 1", out_dir=tmp_path, name="SM_Ok",
                     gate=False, preview=False),
        kiln=kiln,
    )
    report = verify(r.manifest)
    assert report["ok"] is True, report["problems"]
    assert report["glb_sha256"] == r.glb_sha256


def test_verify_rejects_a_tampered_asset(kiln, tmp_path):
    r = build(
        BuildRequest(brief="create cube SM_Tamper size 1 1 1", out_dir=tmp_path,
                     name="SM_Tamper", gate=False, preview=False),
        kiln=kiln,
    )
    with open(r.glb, "ab") as fh:
        fh.write(b"tampered")
    report = verify(r.manifest)
    assert report["ok"] is False
    assert any("changed since" in p for p in report["problems"])


def test_verify_reports_a_missing_manifest(tmp_path):
    report = verify(tmp_path / "nope.json")
    assert report["ok"] is False
    assert "no manifest" in report["reason"]


def test_verify_reports_a_deleted_asset(kiln, tmp_path):
    r = build(
        BuildRequest(brief="create cube SM_Gone size 1 1 1", out_dir=tmp_path, name="SM_Gone",
                     gate=False, preview=False),
        kiln=kiln,
    )
    Path(r.glb).unlink()
    report = verify(r.manifest)
    assert report["ok"] is False
    assert any("missing" in p for p in report["problems"])


def test_verify_rejects_an_unreadable_manifest(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    report = verify(bad)
    assert report["ok"] is False
    assert "unreadable" in report["reason"]


def test_build_reports_an_op_failure_instead_of_a_false_success(kiln, tmp_path):
    """A brief the engine cannot act on must not yield ok=True."""
    r = build(
        BuildRequest(brief="frobnicate the wibble", out_dir=tmp_path, name="SM_Bad",
                     gate=False, preview=False),
        kiln=kiln,
    )
    assert r.ok is False
    assert r.glb_bytes == 0
    assert Path(r.manifest).is_file(), "a failure must still leave a record"


@pytest.mark.parametrize("brief", [
    "create cube SM_P0 size 1 1 1",
    "create sphere SM_P1 size 1 1 1",
    "create cylinder SM_P2 size 1 1 1",
])
def test_build_many_uses_one_session_and_names_each_asset(brief, tmp_path):
    results = build_many([brief], tmp_path, gate=False, preview=False)
    assert len(results) == 1
    entry = results[0]
    assert entry["name"] == "asset_000"
    assert entry["glb_bytes"] > 0, entry["error"]
    assert Path(entry["manifest"]).is_file()


def test_empty_scene_is_a_failure_not_a_gate_refusal(kiln, tmp_path):
    """An export can succeed on an empty scene. That is a failed build.

    The engine answers "no ops" for a brief it cannot act on and still writes a
    valid, geometry-free GLB. Reporting that as a gate refusal would dress an
    empty scene up as a built asset.
    """
    # A camera is a real node with no triangles, so the build succeeds, the
    # export succeeds, and only the geometry check can catch it.
    r = build(
        BuildRequest(brief="create camera SM_Empty", out_dir=tmp_path, name="SM_Empty",
                     gate=True, preview=False),
        kiln=kiln,
    )
    assert r.ok is False
    assert r.triangles == 0
    assert "no geometry" in r.error
    assert r.gate_ok is not True
    assert Path(r.manifest).is_file(), "a failure must still leave a record"
    manifest = json.loads(Path(r.manifest).read_text())
    assert "no geometry" in manifest["result"]["error"]


def test_a_real_asset_still_passes_the_geometry_check(kiln, tmp_path):
    r = build(
        BuildRequest(brief="create sphere SM_Real size 1 1 1", out_dir=tmp_path,
                     name="SM_Real", gate=False, preview=False),
        kiln=kiln,
    )
    assert r.error == ""
    assert r.triangles > 0, "a sphere must not measure as empty"
    assert r.ok is True


def test_auto_refine_is_what_closes_a_standard_tier_gap(kiln, tmp_path):
    """A raw blockout is refused; the same brief with refine is not.

    This is the whole point of the stage, so it is pinned: without auto_refine
    a 12-triangle cube cannot reach the 2,000-triangle prop floor, and with it
    the same cube passes because real edge detail was added.
    """
    raw = build(
        BuildRequest(brief="create cube SM_Raw size 0.4 0.4 0.4", out_dir=tmp_path,
                     name="SM_Raw", family="prop", gate=True, preview=False,
                     auto_refine=False),
        kiln=kiln,
    )
    assert raw.gate_ok is False
    assert raw.refine is None

    refined = build(
        BuildRequest(brief="create cube SM_Refined size 0.4 0.4 0.4", out_dir=tmp_path,
                     name="SM_Refined", family="prop", gate=True, preview=False),
        kiln=kiln,
    )
    assert refined.refine is not None
    assert refined.refine["op"] if "op" in refined.refine else True
    assert refined.refine["triangles_after"] > refined.refine["triangles_before"]
    assert refined.triangles > raw.triangles
    assert refined.gate_ok is True, refined.gate_findings
    assert refined.achieved_tier == "standard"


def test_blockout_tier_does_not_refine(kiln, tmp_path):
    """Asking for a blockout means the raw model output, unmodified."""
    r = build(
        BuildRequest(brief="create cube SM_Block size 1 1 1", out_dir=tmp_path,
                     name="SM_Block", family="prop", gate=True, preview=False,
                     tier="blockout"),
        kiln=kiln,
    )
    assert r.refine is None
    assert r.requested_tier == "blockout"
    assert r.achieved_tier == "blockout"


def test_manifest_records_the_refine_report(kiln, tmp_path):
    r = build(
        BuildRequest(brief="create cube SM_Rec size 0.5 0.5 0.5", out_dir=tmp_path,
                     name="SM_Rec", family="prop", gate=True, preview=False),
        kiln=kiln,
    )
    manifest = json.loads(Path(r.manifest).read_text())
    assert "refine" in manifest
    assert manifest["refine"]["target_tier"] == "standard"
    assert manifest["refine"]["steps"], "the manifest lost the refine steps"
    assert manifest["request"]["auto_refine"] is True


def test_a_failed_brief_leaves_no_artifact_on_disk(kiln, tmp_path):
    """No litter: a failed brief must not leave a geometry-free GLB behind."""
    r = build(
        BuildRequest(brief="frobnicate the wibble", out_dir=tmp_path, name="SM_None",
                     gate=False, preview=False),
        kiln=kiln,
    )
    assert r.ok is False
    assert r.error
    assert not (tmp_path / "SM_None.glb").exists()
    assert list(tmp_path.glob("*.glb")) == [], "an empty GLB was left on disk"
    # The manifest is still written, so the failure is auditable.
    assert Path(r.manifest).is_file()


def test_a_partial_brief_keeps_the_geometry_it_managed_to_build(kiln, tmp_path):
    """A brief that fails partway has still changed the scene.

    Discarding that work would throw away real geometry, so the pipeline keeps
    it and marks the result partial rather than pretending nothing happened.
    """
    r = build(
        BuildRequest(brief="create cube SM_First size 1 1 1", out_dir=tmp_path,
                     name="SM_Partial", preview=False, gate=False),
        kiln=kiln,
    )
    assert r.partial is False, "a fully successful brief is not partial"
    assert r.triangles > 0


def test_manifest_marks_a_partial_build(kiln, tmp_path):
    r = build(
        BuildRequest(brief="create cube SM_P1 size 1 1 1", out_dir=tmp_path,
                     name="SM_P1", preview=False, gate=False),
        kiln=kiln,
    )
    manifest = json.loads(Path(r.manifest).read_text())
    assert manifest["result"]["partial"] is False
    assert "partial" in manifest["result"]
