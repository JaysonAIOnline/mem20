"""Tests for the asset catalogue.

The catalogue reads manifests, never geometry, so these tests build real assets
through the DSL and then check that the index reports exactly what happened.
"""

from __future__ import annotations

import json
from pathlib import Path

from mem20kilnz.catalogue import Catalogue
from mem20kilnz.pipeline import BuildRequest, build


def _build(kiln, tmp_path, brief, name, **kw):
    return build(
        BuildRequest(brief=brief, out_dir=tmp_path / "assets", name=name, preview=False, **kw),
        kiln=kiln,
    )


def test_empty_root_yields_an_empty_catalogue(tmp_path):
    cat = Catalogue(tmp_path / "nothing")
    assert len(cat) == 0
    assert cat.passing() == []
    assert cat.summary()["tracked"] == 0


def test_catalogue_indexes_built_assets(kiln, tmp_path):
    _build(kiln, tmp_path, "create sphere SM_Sph size 1 1 1", "SM_Sph", gate=False)
    cat = Catalogue(tmp_path / "assets")
    assert len(cat) == 1
    entry = cat.entries[0]
    assert entry.name == "SM_Sph"
    assert entry.glb_bytes > 0
    assert entry.triangles > 0
    assert entry.ok is True
    assert entry.problems == []
    assert entry.glb_sha256


def test_summary_separates_passing_from_refused(kiln, tmp_path):
    _build(kiln, tmp_path, "create cube SM_Big size 2 2 2", "SM_Big", gate=False)
    _build(kiln, tmp_path, "create cube SM_Tiny size 0.1 0.1 0.1", "SM_Tiny",
           family="prop", gate=True, auto_refine=False)
    cat = Catalogue(tmp_path / "assets")
    summary = cat.summary()
    assert summary["tracked"] == 2
    assert summary["refused"] == 1
    assert summary["errored"] == 0
    assert summary["total_triangles"] > 0


def test_find_filters_combine_as_and(kiln, tmp_path):
    _build(kiln, tmp_path, "create sphere SM_A size 1 1 1", "SM_A", gate=False)
    _build(kiln, tmp_path, "create cube SM_B size 1 1 1", "SM_B", gate=False)
    cat = Catalogue(tmp_path / "assets")
    assert [e.name for e in cat.find(name="SM_A")] == ["SM_A"]
    assert len(cat.find(min_triangles=1)) == 2
    assert cat.find(name="SM_A", min_triangles=10_000) == []
    assert [e.name for e in cat.find(contains="sphere")] == ["SM_A"]


def test_a_glb_with_no_manifest_is_reported_untracked(kiln, tmp_path):
    assets = tmp_path / "assets"
    _build(kiln, tmp_path, "create sphere SM_Tracked size 1 1 1", "SM_Tracked", gate=False)
    (assets / "SM_Smuggled.glb").write_bytes(b"not from the pipeline")
    cat = Catalogue(assets)
    assert len(cat) == 1
    assert len(cat.untracked) == 1
    assert cat.untracked[0].endswith("SM_Smuggled.glb")
    assert cat.summary()["untracked_glb"] == 1


def test_a_deleted_asset_is_flagged_on_its_entry(kiln, tmp_path):
    r = _build(kiln, tmp_path, "create sphere SM_Gone size 1 1 1", "SM_Gone", gate=False)
    Path(r.glb).unlink()
    cat = Catalogue(tmp_path / "assets")
    assert cat.entries[0].problems == ["glb missing"]
    assert cat.passing() == [], "an entry with a missing artifact must not count as passing"
    assert cat.summary()["with_problems"] == 1


def test_an_unreadable_manifest_is_not_silently_dropped(kiln, tmp_path):
    assets = tmp_path / "assets"
    _build(kiln, tmp_path, "create sphere SM_Ok size 1 1 1", "SM_Ok", gate=False)
    (assets / "broken.manifest.json").write_text("{not json", encoding="utf-8")
    cat = Catalogue(assets)
    assert len(cat) == 1
    assert len(cat.unreadable) == 1
    assert cat.summary()["unreadable_manifests"] == 1


def test_passing_requires_ok_and_gate_and_intact_artifact(kiln, tmp_path):
    _build(kiln, tmp_path, "create sphere SM_Gated size 1 1 1", "SM_Gated", gate=False)
    cat = Catalogue(tmp_path / "assets")
    assert cat.passing() == [], "gate_ok is None when the gate never ran, which is not a pass"
    assert cat.summary()["refused"] == 0


def test_entry_as_dict_is_json_serialisable(kiln, tmp_path):
    _build(kiln, tmp_path, "create sphere SM_J size 1 1 1", "SM_J", gate=False)
    cat = Catalogue(tmp_path / "assets")
    json.dumps(cat.entries[0].as_dict())
    json.dumps(cat.summary())


def test_nested_directories_are_indexed(kiln, tmp_path):
    _build(kiln, tmp_path, "create sphere SM_Deep size 1 1 1", "SM_Deep", gate=False)
    cat = Catalogue(tmp_path)
    assert any(e.name == "SM_Deep" for e in cat.entries)
