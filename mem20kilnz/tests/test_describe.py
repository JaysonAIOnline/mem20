"""Tests for the plain-English description.

These check that the words match the measurements. A description that reads well
while stating the wrong number is worse than no description, so the assertions
are against measured values, and the colour tests are against the maths rather
than against a list of expected strings.
"""

from __future__ import annotations

import pytest

from mem20kilnz.describe import (
    Box,
    _node_matrix,
    _relative_size,
    _world_box,
    colour_name,
    describe,
    finish_name,
    mat_apply_point,
    mat_mul,
    mat_scale,
    mat_translate,
)


def _scene(kiln):
    kiln.reset()
    kiln.op({"op": "create", "primitive": "cube", "name": "Crate",
             "size": [1, 1, 1], "albedo": [0.7, 0.5, 0.3]})
    kiln.op({"op": "create", "primitive": "cube", "name": "Band",
             "size": [1.1, 1.1, 0.2], "translation": [0, 0, 0.55],
             "albedo": [0.25, 0.25, 0.28], "metallic": 0.9, "roughness": 0.3})
    kiln.op({"op": "parent", "target": "Band", "parent": "Crate"})
    return kiln


def _export(kiln, tmp_path, name="m"):
    out = tmp_path / f"{name}.glb"
    kiln.export(str(out))
    return out


# -- colour ---------------------------------------------------------------


@pytest.mark.parametrize("rgb,expected", [
    ((0.02, 0.02, 0.02), "black"),
    ((0.99, 0.99, 0.99), "white"),
    ((0.5, 0.5, 0.52), "grey"),
    ((0.8, 0.8, 0.8), "light grey"),
    ((0.8, 0.1, 0.1), "red"),
    ((0.9, 0.5, 0.05), "orange"),
    ((0.9, 0.85, 0.1), "yellow"),
    ((0.1, 0.3, 0.8), "blue"),
    ((0.7, 0.5, 0.3), "brown"),
])
def test_colour_names(rgb, expected):
    assert colour_name(rgb) == expected


def test_saturated_orange_is_not_called_brown():
    """Brown is desaturated. A vivid orange must stay orange."""
    assert colour_name((0.9, 0.5, 0.05)) == "orange"
    assert colour_name((0.7, 0.5, 0.3)) == "brown"


def test_colour_survives_out_of_range_input():
    for bad in [(-1.0, 0.5, 0.5), (2.0, 0.0, 0.0)]:
        assert isinstance(colour_name(bad), str)
        assert colour_name(bad)


def test_finish_describes_behaviour_in_words():
    assert "metallic" in finish_name(0.5, 1.0)
    assert "very rough" in finish_name(0.9, 0.0)
    assert "matte" in finish_name(0.6, 0.0)
    assert "mirror" in finish_name(0.05, 0.0)


# -- transforms -----------------------------------------------------------


def test_translation_moves_world_bounds():
    local = Box((-0.5, -0.5, -0.5), (0.5, 0.5, 0.5))
    world = _world_box(local, mat_translate((0.0, 0.0, 0.55)))
    assert world.min[2] == pytest.approx(0.05)
    assert world.max[2] == pytest.approx(1.05)


def test_scale_widens_world_bounds():
    local = Box((0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
    world = _world_box(local, mat_scale((2.0, 1.0, 1.0)))
    assert world.size == pytest.approx((2.0, 1.0, 1.0))


def test_a_quarter_turn_rotates_the_bounds():
    """A 90-degree turn about z swaps x and y."""
    local = Box((0.0, 0.0, 0.0), (2.0, 1.0, 1.0))
    world = _world_box(local, _node_matrix({"rotation": [0.0, 0.0, 0.70710678, 0.70710678]}))
    assert world.size[0] == pytest.approx(1.0, abs=1e-6)
    assert world.size[1] == pytest.approx(2.0, abs=1e-6)
    assert world.size[2] == pytest.approx(1.0, abs=1e-6)


def test_child_transform_composes_through_the_parent():
    """Parent T(1) S(2), child T(0.5), point at child-local x=0.5.

    The child's own transform moves 0.5 to 1.0 in parent space; the parent then
    scales that to 2.0 and offsets by 1.0, giving world x=3.0. Getting 2.0 here
    means the child's translation was dropped.
    """
    parent = mat_mul(mat_translate((1.0, 0.0, 0.0)), mat_scale((2.0, 2.0, 2.0)))
    child = mat_translate((0.5, 0.0, 0.0))
    world = mat_mul(parent, child)
    assert mat_apply_point(world, (0.5, 0.0, 0.0))[0] == pytest.approx(3.0)


def test_a_matrix_chain_beats_collapsing_to_one_trs():
    """Why this is a matrix and not a translation/quaternion/scale triple.

    T*R*S composed with T*R*S is not itself a TRS, because the inner translation
    has nowhere to go in that form. With a rotation on both nodes and a
    non-uniform parent scale the naive collapse comes out with the wrong sign.
    """
    r90 = (0.0, 0.0, 0.70710678, 0.70710678)
    parent = _node_matrix({"scale": [2, 1, 1], "rotation": list(r90)})
    child = _node_matrix({"rotation": list(r90), "translation": [1, 0, 0]})
    got = mat_apply_point(mat_mul(parent, child), (0.0, 0.0, 0.0))
    assert got[1] == pytest.approx(2.0, abs=1e-5)
    assert got[1] > 0, "a collapsed TRS gives -2.0 here, the wrong side of the origin"


# -- relative size --------------------------------------------------------


def test_relative_size_uses_width_not_volume():
    """A small cube is a real part even when its volume share is tiny."""
    big = type("P", (), {"name": "Chest", "size": (2.0, 1.0, 1.0),
                         "volume": 2.0})()
    lock = type("P", (), {"name": "Lock", "size": (0.2, 0.2, 0.2),
                          "volume": 0.008})()
    text = _relative_size(lock, big)
    assert "sliver" not in text, text
    assert "0.10" in text or "small part" in text


def test_a_wide_but_thin_band_is_still_reported_as_thin():
    """A band is wider than the chest it wraps, so width alone says "105%".

    That is true and useless. Thinness has to be judged against the part's own
    smallest side, which is what identifies it as a strip.
    """
    big = type("P", (), {"name": "Chest", "size": (2.0, 1.0, 1.0), "volume": 2.0})()
    band = type("P", (), {"name": "Band", "size": (2.1, 0.05, 0.1),
                          "volume": 0.0105})()
    text = _relative_size(band, big)
    assert "thin" in text, text
    assert "wider than Chest" in text, text


# -- description of a real file ------------------------------------------


def test_describe_measures_a_real_export(kiln, tmp_path):
    _scene(kiln)
    d = describe(_export(kiln, tmp_path))
    assert d.ok is True
    assert len(d.parts) == 2
    assert d.total_triangles == 24
    # Vertices are welded on (position, normal, uv), so the export is no longer
    # a triangle soup. Two cubes sharing none: 24 welded corners, not the 72 a
    # soup would write and not the 16 a position-only weld would give.
    assert d.total_vertices == 48, "the export regressed to a triangle soup"
    assert d.total_vertices < d.total_triangles * 3


def test_dimensions_are_world_space_not_local(kiln, tmp_path):
    """The band sits above the crate, so the model is taller than the crate."""
    _scene(kiln)
    d = describe(_export(kiln, tmp_path))
    crate = next(p for p in d.parts if p.name == "Crate")
    band = next(p for p in d.parts if p.name == "Band")
    assert crate.size == pytest.approx((1.0, 1.0, 1.0), abs=1e-5)
    # Band local extent is 0.2 tall, placed at z=0.55 -> world top at 0.65.
    assert band.box.max[2] == pytest.approx(0.65, abs=1e-5)
    assert d.overall.size[2] == pytest.approx(1.15, abs=1e-5), (
        "overall height must include the raised band, not just the crate"
    )


def test_colour_and_material_reach_the_prose(kiln, tmp_path):
    _scene(kiln)
    text = describe(_export(kiln, tmp_path)).text()
    assert "brown" in text
    assert "metallic" in text
    assert "matte" in text or "satin" in text


def test_parentage_is_reported(kiln, tmp_path):
    _scene(kiln)
    d = describe(_export(kiln, tmp_path))
    band = next(p for p in d.parts if p.name == "Band")
    assert band.parent == "Crate"
    assert "attached to Crate" in d.text()


def test_proportion_words_reflect_the_actual_shape(kiln, tmp_path):
    kiln.reset()
    kiln.op({"op": "create", "primitive": "cube", "name": "Ball",
             "size": [1, 1, 1]})
    assert "cube in proportion" in describe(_export(kiln, tmp_path)).text()

    kiln.reset()
    kiln.op({"op": "create", "primitive": "cube", "name": "Rod",
             "size": [10, 0.2, 0.2]})
    assert "long, thin" in describe(_export(kiln, tmp_path, "rod")).text()


def test_a_flat_model_says_so_rather_than_dividing_by_zero(kiln, tmp_path):
    kiln.reset()
    kiln.op({"op": "create", "primitive": "plane", "name": "Floor",
             "size": [4, 4, 1]})
    d = describe(_export(kiln, tmp_path, "flat"))
    assert "flat" in d.text() or d.overall.size[2] == pytest.approx(0.0, abs=1e-6)


def test_it_says_when_likeness_cannot_be_judged(kiln, tmp_path):
    """Geometry can be measured; whether it resembles the brief cannot."""
    _scene(kiln)
    d = describe(_export(kiln, tmp_path))
    assert any("likeness" in n for n in d.not_computable)


def test_a_missing_file_is_refused_not_guessed(tmp_path):
    d = describe(tmp_path / "nope.glb")
    assert d.ok is False
    assert "no file" in d.reason
    assert d.not_computable


def test_a_file_with_no_meshes_says_so(kiln, tmp_path):
    """A scene of only a camera has nothing measurable, and must say so."""
    kiln.reset()
    kiln.op({"op": "create", "primitive": "camera", "name": "OnlyCam"})
    out = tmp_path / "cam.glb"
    kiln.export(str(out))
    d = describe(out)
    assert d.ok is False
    assert "no mesh nodes" in d.reason
    assert d.not_computable


def test_description_is_serialisable(kiln, tmp_path):
    import json

    _scene(kiln)
    json.dumps(describe(_export(kiln, tmp_path)).as_dict())


def test_manifest_carries_the_description_on_every_export(kiln, tmp_path):
    import json

    from mem20kilnz.pipeline import BuildRequest, build

    build(
        BuildRequest(brief="create cube SM_D size 1 1 1", out_dir=tmp_path,
                     name="SM_D", gate=False, preview=False),
        kiln=kiln,
    )
    manifest = json.loads((tmp_path / "SM_D.manifest.json").read_text())
    assert manifest["description"] is not None
    assert "1 part" in manifest["description"]["summary"]
    assert manifest["description"]["parts"][0]["name"] == "SM_D"
