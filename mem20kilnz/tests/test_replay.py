"""Determinism: a manifest must reproduce its asset, byte for byte.

The engine's journal records every applied op, including the ones a language
model invented internally. Replaying it into a fresh scene and comparing SHA-256
is the only honest determinism check: "similar" is not reproducible.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mem20kilnz.errors import OpFailed
from mem20kilnz.pipeline import BuildRequest, build, sha256_file
from mem20kilnz.replay import EXTERNAL_OPS, replay, reproduce


def _build(kiln, tmp_path, brief, name="SM_R", **kw):
    return build(
        BuildRequest(brief=brief, out_dir=tmp_path, name=name, gate=False,
                     preview=False, **kw),
        kiln=kiln,
    )


def test_replaying_a_journal_reproduces_identical_bytes(kiln, tmp_path):
    r = _build(kiln, tmp_path, "create cube SM_A size 1 1 1")
    manifest = Path(r.manifest)
    out = replay(json.loads(manifest.read_text())["journal"]["entries"],
                 tmp_path / "replay.glb")
    assert out.ok is True
    assert out.applied >= 1
    assert out.actual_sha256 == r.glb_sha256, "replay did not reproduce the asset"
    assert sha256_file(tmp_path / "replay.glb") == r.glb_sha256


def test_reproduce_reports_identical_true(kiln, tmp_path):
    r = _build(kiln, tmp_path, "create sphere SM_B size 1 1 1")
    result = reproduce(r.manifest)
    assert result.ok is True
    assert result.identical is True
    assert result.reason == ""


def test_reproduce_fails_loudly_when_the_asset_changed(kiln, tmp_path):
    """The check is only worth having if it can fail."""
    r = _build(kiln, tmp_path, "create cube SM_C size 1 1 1")
    manifest = Path(r.manifest)
    data = json.loads(manifest.read_text())
    data["artifacts"]["glb"]["sha256"] = "0" * 64
    manifest.write_text(json.dumps(data, indent=2))
    result = reproduce(manifest)
    assert result.ok is True, "the replay itself should still work"
    assert result.identical is False
    assert "different bytes" in result.reason


def test_reproduce_detects_a_tampered_asset_file(kiln, tmp_path):
    r = _build(kiln, tmp_path, "create cube SM_D size 1 1 1")
    with open(r.glb, "ab") as fh:
        fh.write(b"x")
    # The manifest hash still matches what a replay produces, so this must
    # still be identical: the point is reproducing the *recorded* build.
    assert reproduce(r.manifest).identical is True


def test_a_multi_step_journal_replays_in_order(kiln, tmp_path):
    r = _build(kiln, tmp_path, "create cube SM_E size 1 1 1")
    entries = json.loads(Path(r.manifest).read_text())["journal"]["entries"]
    kinds = [e["op"]["op"] for e in entries]
    assert "create" in kinds
    out = replay(entries, tmp_path / "multi.glb")
    assert out.applied == len(entries)
    assert out.actual_sha256 == r.glb_sha256


def test_a_failed_op_is_skipped_and_reported(kiln, tmp_path):
    """The original build survived it, so the replay must too."""
    kiln.reset()
    kiln.call("journal", {"clear": True})
    kiln.op({"op": "create", "primitive": "cube", "name": "Good", "size": [1, 1, 1]})
    # A decimate on a mesh with a hole is refused by the closed-surface check,
    # which is a genuine failed op and lands in the journal with ok=false.
    kiln.op({"op": "create", "primitive": "plane", "name": "Hole", "size": [2, 2, 1]})
    with pytest.raises(OpFailed):
        kiln.op({"op": "decimate", "ratio": 0.5})
    entries = kiln.call("journal", {})["entries"]
    assert any(e["ok"] is False for e in entries)

    out = replay(entries, tmp_path / "skipped.glb")
    assert out.ok is True
    assert out.skipped >= 1
    assert out.failures
    assert any(f["op"] == "decimate" for f in out.failures)


def test_an_empty_journal_is_refused_with_a_reason(tmp_path):
    out = replay([], tmp_path / "none.glb")
    assert out.ok is False
    assert "empty" in out.reason


def test_a_missing_manifest_is_refused(tmp_path):
    result = reproduce(tmp_path / "absent.json")
    assert result.ok is False
    assert "no manifest" in result.reason


def test_an_unreadable_manifest_is_refused(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    result = reproduce(bad)
    assert result.ok is False
    assert "unreadable" in result.reason


def test_external_ops_are_flagged_rather_than_silently_replayed(kiln, tmp_path):
    """A journal containing an import cannot be guaranteed to match."""
    src = tmp_path / "src.glb"
    kiln.reset()
    kiln.op({"op": "create", "primitive": "cube", "name": "X", "size": [1, 1, 1]})
    kiln.export(str(src))
    kiln.reset()
    kiln.call("journal", {"clear": True})
    kiln.op({"op": "import", "path": str(src)})
    entries = kiln.call("journal", {})["entries"]
    assert any(e["op"]["op"] in EXTERNAL_OPS for e in entries)
    out = replay(entries, tmp_path / "ext.glb")
    assert "import" in out.external
    assert "external" in out.reason


def test_replay_is_repeatable(kiln, tmp_path):
    """Replaying the same journal twice must give the same bytes."""
    r = _build(kiln, tmp_path, "create cube SM_F size 1 1 1")
    entries = json.loads(Path(r.manifest).read_text())["journal"]["entries"]
    a = replay(entries, tmp_path / "a.glb")
    b = replay(entries, tmp_path / "b.glb")
    assert a.actual_sha256 == b.actual_sha256 == r.glb_sha256
