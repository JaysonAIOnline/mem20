"""Tests for the four ops added 2026-09-27: boolean, remesh, displace, skin.

Each pins measured behaviour rather than "it did not crash". The volume checks use
analytic answers, so a regression that quietly returns plausible nonsense fails
here instead of shipping.

The known limitation is pinned on purpose: the thin lens where two spheres
overlap is badly eroded by the one-cell shell, and that must stay visible in the
test suite rather than being discovered later by a user.
"""

import math

import pytest

from mem20kilnz.errors import OpFailed

SPHERE_VOLUME = 4.0 / 3.0 * math.pi


def two_cubes(kiln, offset=1.0):
    """Two side-2 cubes, each volume 8, overlapping by 1x2x2 = 4."""
    kiln.op({"op": "create", "primitive": "cube", "name": "A", "size": [2, 2, 2]})
    kiln.op(
        {
            "op": "create",
            "primitive": "cube",
            "name": "B",
            "size": [2, 2, 2],
            "translation": [offset, 0, 0],
        }
    )
    kiln.op({"op": "select", "target": "A"})


def sphere_at(kiln, name, offset=(0, 0, 0)):
    kiln.op(
        {
            "op": "create",
            "primitive": "sphere",
            "name": name,
            "size": [2, 2, 2],
            "translation": list(offset),
        }
    )


# -- boolean -------------------------------------------------------------


@pytest.mark.parametrize(
    "mode,exact",
    [("union", 12.0), ("intersect", 4.0), ("difference", 4.0)],
)
def test_boolean_on_cubes_matches_the_exact_answer(kiln, mode, exact):
    """Cubes have a trivial exact answer, so this separates a logic bug from a
    geometry limitation."""
    two_cubes(kiln)
    r = kiln.op({"op": "boolean", "mode": mode, "other": "B", "resolution": 48})["data"]
    assert r["watertight"], r
    assert r["non_finite_verts"] == 0
    assert r["nonmanifold_edges"] == 0
    assert r["signed_volume"] == pytest.approx(exact, rel=0.15)


def test_boolean_spans_both_operands_not_just_one(kiln):
    """It operated on sphere A alone once, leaving the union inside A's bounds."""
    two_cubes(kiln, offset=3.0)
    kiln.op({"op": "boolean", "mode": "union", "other": "B", "resolution": 40})
    node = [n for n in kiln.call("describe", {})["nodes"] if n["name"].endswith("_union")][0]
    # Two cubes at x=0 and x=3 span -1..4.
    assert node["local_min"][0] == pytest.approx(-1.0, abs=0.25)
    assert node["local_max"][0] == pytest.approx(4.0, abs=0.25)


def test_boolean_respects_node_transforms(kiln):
    """A boolean in local space gives the wrong answer for a transformed operand,
    and moving an object is the most ordinary thing a user does.

    Two overlapping cubes 8 each with a 4 overlap union to 12. Rotating B a
    quarter turn about z keeps them overlapping at the same volume, so the
    answer must be unchanged: if the operands were used in local space the two
    cubes would land on top of each other and the union would read 8.
    """
    kiln.op({"op": "create", "primitive": "cube", "name": "A", "size": [2, 2, 2]})
    kiln.op(
        {
            "op": "create",
            "primitive": "cube",
            "name": "B",
            "size": [2, 2, 2],
            "translation": [1, 0, 0],
            "rotation": [0, 0, 90],
        }
    )
    kiln.op({"op": "select", "target": "A"})
    r = kiln.op({"op": "boolean", "mode": "union", "other": "B", "resolution": 40})["data"]
    assert abs(r["signed_volume"]) == pytest.approx(12.0, rel=0.2), r


def test_boolean_union_of_two_spheres_is_close(kiln):
    kiln.reset()
    sphere_at(kiln, "A")
    sphere_at(kiln, "B", (1, 0, 0))
    kiln.op({"op": "select", "target": "A"})
    r = kiln.op({"op": "boolean", "mode": "union", "other": "B", "resolution": 80})["data"]
    exact = 2 * SPHERE_VOLUME - math.pi * 2.25 / 3.0
    assert r["watertight"], r
    assert abs(r["signed_volume"]) == pytest.approx(exact, rel=0.15)


def test_boolean_intersection_of_two_spheres_is_a_known_limitation(kiln):
    """Pinned as a failure, on purpose.

    The lens where two unit spheres overlap is thin at its tips, and the
    conservative rasterizer has to consume a whole cell of shell, which erodes
    exactly those tips. Measured 51% low, converging only as O(1/res) rather than
    O(h^2), so it is not a resolution the caller can dial out of. Fixing it
    properly needs a signed distance field rather than a binary occupancy field.
    This test fails loudly if the number moves in either direction, so a real fix
    has to update it deliberately.
    """
    kiln.reset()
    sphere_at(kiln, "A")
    sphere_at(kiln, "B", (1, 0, 0))
    kiln.op({"op": "select", "target": "A"})
    r = kiln.op({"op": "boolean", "mode": "intersect", "other": "B", "resolution": 80})["data"]
    exact = math.pi * 2.25 / 3.0
    measured = abs(r["signed_volume"]) / exact
    assert 0.40 < measured < 0.60, (
        f"sphere intersection is {measured:.2f} of the exact volume; if this has "
        "moved, update the documented limitation in CONFWORK.md"
    )


def test_boolean_rejects_nonsense_instead_of_guessing(kiln):
    two_cubes(kiln)
    with pytest.raises(OpFailed, match="unknown mode"):
        kiln.op({"op": "boolean", "mode": "xor", "other": "B"})
    with pytest.raises(OpFailed, match="existing node"):
        kiln.op({"op": "boolean", "mode": "union", "other": "nope"})
    with pytest.raises(OpFailed, match="same object"):
        kiln.op({"op": "boolean", "mode": "union", "other": "A"})


def test_disjoint_intersection_reports_that_it_produced_nothing(kiln):
    """An empty result is a real answer, and saying so beats an empty mesh."""
    two_cubes(kiln, offset=10.0)
    with pytest.raises(OpFailed, match="no surface"):
        kiln.op({"op": "boolean", "mode": "intersect", "other": "B", "resolution": 32})


# -- remesh --------------------------------------------------------------


def test_remesh_produces_a_closed_manifold_surface(kiln):
    kiln.op({"op": "create", "primitive": "sphere", "name": "S", "size": [2, 2, 2]})
    r = kiln.op({"op": "remesh", "resolution": 40})["data"]
    assert r["watertight"], r
    assert r["boundary_edges"] == 0
    assert r["nonmanifold_edges"] == 0
    assert r["non_finite_verts"] == 0
    # The source sphere is 288 triangles; a res-40 field is a genuinely
    # different, denser tessellation of the same surface.
    assert r["faces_before"] == 288
    assert r["faces_after"] > 288


def test_remesh_volume_tracks_the_source_within_the_documented_erosion(kiln):
    """The one-cell shell costs real volume. Pinned so the cost stays known."""
    kiln.op({"op": "create", "primitive": "sphere", "name": "S", "size": [2, 2, 2]})
    r = kiln.op({"op": "remesh", "resolution": 80})["data"]
    ratio = abs(r["signed_volume"]) / SPHERE_VOLUME
    assert 0.85 < ratio < 1.0, f"remeshed volume ratio {ratio:.3f} moved outside the known range"


def test_remesh_never_produces_nan(kiln):
    """It did once: remeshing a remesh hit a 0/0 on a degenerate face and the
    whole volume became NaN, which serialised to null and hid the failure."""
    kiln.op({"op": "create", "primitive": "sphere", "name": "S", "size": [2, 2, 2]})
    for _ in range(3):
        r = kiln.op({"op": "remesh", "resolution": 24})["data"]
        assert r["non_finite_verts"] == 0, r
        assert r["signed_volume"] is not None


def test_remesh_by_target_triangle_count(kiln):
    kiln.op({"op": "create", "primitive": "sphere", "name": "S", "size": [2, 2, 2]})
    r = kiln.op({"op": "remesh", "target": 2000})["data"]
    assert r["faces_after"] < 4000, r
    assert r["watertight"], r


def test_remesh_refuses_a_mesh_it_cannot_read_as_a_solid(kiln):
    """A plane is open, so it has no interior to voxelize."""
    kiln.op({"op": "create", "primitive": "plane", "name": "P", "size": [2, 2, 2]})
    with pytest.raises(OpFailed):
        kiln.op({"op": "remesh", "resolution": 32})


# -- displace ------------------------------------------------------------


def test_displace_keeps_the_surface_closed(kiln):
    kiln.op({"op": "create", "primitive": "sphere", "name": "S", "size": [2, 2, 2]})
    kiln.op({"op": "remesh", "resolution": 40})
    r = kiln.op({"op": "displace", "amplitude": 0.25, "frequency": 4, "seed": 7})["data"]
    assert r["watertight"], r
    assert r["non_finite_verts"] == 0 if "non_finite_verts" in r else True


def test_displace_grows_the_surface_and_amplitude_scales_it(kiln):
    """Zero-mean noise barely moves a sphere's volume, so the meaningful measure is
    surface area: displacement must add area, and more amplitude must add more."""
    areas = []
    base_area = None
    for amp in (0.0, 0.15, 0.45):
        kiln.reset()
        kiln.op({"op": "create", "primitive": "sphere", "name": "S", "size": [2, 2, 2]})
        remeshed = kiln.op({"op": "remesh", "resolution": 40})["data"]
        r = kiln.op(
            {"op": "displace", "amplitude": amp, "frequency": 5, "seed": 3}
        )["data"]
        assert r["non_finite_verts"] == 0, r
        if base_area is None:
            base_area = remeshed["surface_area"]
        areas.append(r["surface_area"])
    # Zero amplitude must be a genuine no-op on the surface.
    assert areas[0] == pytest.approx(base_area, rel=1e-5), (
        f"amplitude 0 changed the surface: {areas[0]} vs remesh {base_area}"
    )
    assert areas[0] < areas[1] < areas[2], f"area did not scale with amplitude: {areas}"


def test_displace_is_deterministic_for_a_given_seed(kiln):
    """The journal replays byte-identically, so seeded noise must too."""
    runs = []
    for _ in range(2):
        kiln.reset()
        kiln.op({"op": "create", "primitive": "sphere", "name": "S", "size": [2, 2, 2]})
        kiln.op({"op": "remesh", "resolution": 24})
        runs.append(
            kiln.op({"op": "displace", "amplitude": 0.2, "frequency": 4, "seed": 11})[
                "data"
            ]["signed_volume"]
        )
    assert runs[0] == runs[1]


def test_displace_validates_its_arguments(kiln):
    kiln.op({"op": "create", "primitive": "sphere", "name": "S", "size": [2, 2, 2]})
    with pytest.raises(OpFailed, match="frequency"):
        kiln.op({"op": "displace", "frequency": 0})
    with pytest.raises(OpFailed, match="octaves"):
        kiln.op({"op": "displace", "octaves": 0})


# -- skin ----------------------------------------------------------------


def test_skin_binds_every_vertex_with_normalised_weights(kiln):
    kiln.op({"op": "create", "primitive": "sphere", "name": "S", "size": [2, 2, 2]})
    kiln.op({"op": "create", "primitive": "bone", "name": "B1", "translation": [-0.4, 0, 0]})
    kiln.op({"op": "create", "primitive": "bone", "name": "B2", "translation": [0.4, 0, 0]})
    kiln.op({"op": "select", "target": "S"})
    r = kiln.op({"op": "skin", "bones": ["B1", "B2"], "falloff": 0.6})["data"]
    assert r["verts"] == 266
    assert r["bones"] == 2
    assert r["weights_not_normalised"] == 0, r
    node = [n for n in kiln.call("describe", {})["nodes"] if n["name"] == "S"][0]
    assert node["skinned"] is True


def test_skin_uses_bone_world_positions_not_local(kiln):
    """A bone parented and translated elsewhere must pull weight its own way."""
    kiln.op({"op": "create", "primitive": "sphere", "name": "S", "size": [2, 2, 2]})
    kiln.op({"op": "create", "primitive": "bone", "name": "root", "translation": [0, 0, 0]})
    kiln.op(
        {
            "op": "create",
            "primitive": "bone",
            "name": "tip",
            "translation": [0.6, 0, 0],
            "parent": "root",
        }
    )
    kiln.op({"op": "select", "target": "S"})
    r = kiln.op({"op": "skin", "bones": ["root", "tip"], "falloff": 0.5})["data"]
    assert r["bones"] == 2
    assert r["weights_not_normalised"] == 0, r


def test_skin_rejects_a_non_bone(kiln):
    kiln.op({"op": "create", "primitive": "sphere", "name": "S", "size": [2, 2, 2]})
    kiln.op({"op": "select", "target": "S"})
    with pytest.raises(OpFailed, match="not a bone"):
        kiln.op({"op": "skin", "bones": ["S"]})
    with pytest.raises(OpFailed, match="no bones"):
        kiln.op({"op": "skin"})


def test_bones_can_be_created_without_importing_a_fixture(kiln):
    """They could not before: bones only arrived via glTF/FBX import, which left
    parent, pose, ik and skin unusable on a built scene."""
    kiln.op({"op": "create", "primitive": "bone", "name": "B"})
    assert any(n["type"] == "bone" for n in kiln.call("describe", {})["nodes"])
    with pytest.raises(OpFailed, match="not a bone node"):
        kiln.op({"op": "create", "primitive": "bone", "name": "C", "parent": "nope"})
    # A bone may be parented to another bone.
    kiln.op({"op": "create", "primitive": "bone", "name": "B2", "parent": "B"})
    assert any(n["name"] == "B2" for n in kiln.call("describe", {})["nodes"])


def test_skin_actually_reaches_the_exported_file(kiln, tmp_path):
    """It did not once.

    `skin` filled the mesh, `describe` reported skinned=True, and the exporter
    wrote no JOINTS_0, no WEIGHTS_0 and no skins array at all, so the weights
    existed only in memory and vanished on save. This pins the whole chain.
    """
    import json
    import struct

    kiln.op({"op": "create", "primitive": "sphere", "name": "S", "size": [2, 2, 2]})
    kiln.op({"op": "create", "primitive": "bone", "name": "B1", "translation": [-0.4, 0, 0]})
    kiln.op({"op": "create", "primitive": "bone", "name": "B2", "translation": [0.4, 0, 0]})
    kiln.op({"op": "select", "target": "S"})
    kiln.op({"op": "skin", "bones": ["B1", "B2"], "falloff": 0.6})
    out = tmp_path / "skinned.glb"
    kiln.export(str(out))

    raw = out.read_bytes()
    assert raw[:4] == b"glTF"
    doc = None
    off = 12
    while off < len(raw):
        length, ctype = struct.unpack_from("<II", raw, off)
        off += 8
        if ctype == 0x4E4F534A:  # JSON
            doc = json.loads(raw[off : off + length].decode("utf-8"))
        off += length
    assert doc is not None and doc["asset"]["version"] == "2.0"

    assert doc.get("skins"), "no skins array in the exported file"
    skin = doc["skins"][0]
    assert len(skin["joints"]) == 2
    names = [doc["nodes"][j]["name"] for j in skin["joints"]]
    assert names == ["B1", "B2"], names
    ibm = doc["accessors"][skin["inverseBindMatrices"]]
    assert (ibm["type"], ibm["count"], ibm["componentType"]) == ("MAT4", 2, 5126)

    attrs = doc["meshes"][0]["primitives"][0]["attributes"]
    assert "JOINTS_0" in attrs and "WEIGHTS_0" in attrs, sorted(attrs)
    skinned_nodes = [n for n in doc["nodes"] if "skin" in n]
    assert len(skinned_nodes) == 1
    assert doc["skins"][skinned_nodes[0]["skin"]]["joints"] == skin["joints"]


def test_boolean_difference_of_two_spheres_is_a_known_limitation(kiln):
    """Pinned as a failure, on purpose.

    The crescent left by subtracting one sphere from another is thin where the
    two surfaces nearly touch, and the conservative rasterizer consumes a whole
    cell of shell there. Measured ~42% high and 25-28 non-manifold edges, so this
    is not merely imprecise: the result is not a valid closed surface. A signed
    distance field would be the proper fix, not a resolution bump.
    """
    kiln.reset()
    sphere_at(kiln, "A")
    sphere_at(kiln, "B", (1, 0, 0))
    kiln.op({"op": "select", "target": "A"})
    r = kiln.op({"op": "boolean", "mode": "difference", "other": "B", "resolution": 80})["data"]
    exact = SPHERE_VOLUME - math.pi * 2.25 / 3.0
    ratio = abs(r["signed_volume"]) / exact
    assert 1.2 < ratio < 1.7, (
        f"sphere difference is {ratio:.2f} of the exact volume; if this has moved, "
        "update the documented limitation in CONFWORK.md"
    )
    assert r["nonmanifold_edges"] > 0, (
        "the sphere difference is now manifold, which means the limitation is gone "
        "and the docs need updating"
    )
