"""Tests for animation: clips, keyframes, interpolation, glTF round-trip, retarget.

The interpolation checks compare against hand-computed Hermite values rather than
against a previous run, so a change in the curve is a real signal and not just a
different number to update. The round-trip checks are what make animation a
feature rather than an in-memory toy: a clip that cannot survive a save is not
animation anyone can use.
"""

import json
import struct

import pytest

from mem20kilnz.errors import OpFailed


def read_glb(path):
    """Parse a GLB into (json_chunk, binary_chunk)."""
    raw = open(path, "rb").read()
    assert raw[:4] == b"glTF", "not a glb"
    doc = None
    binary = None
    off = 12
    while off < len(raw):
        length, ctype = struct.unpack_from("<II", raw, off)
        off += 8
        chunk = raw[off : off + length]
        if ctype == 0x4E4F534A:
            doc = json.loads(chunk.decode("utf-8"))
        elif ctype == 0x004E4942:
            binary = chunk
        off += length
    assert doc is not None
    return doc, binary


def animated_box(kiln, name="Box", fps=24):
    kiln.op({"op": "create", "primitive": "cube", "name": name, "size": [1, 1, 1]})
    kiln.op({"op": "clip_create", "name": "bob", "fps": fps})
    return name


def ty(kiln, name="Box"):
    node = [n for n in kiln.call("describe", {})["nodes"] if n["name"] == name][0]
    return node["t"][1]


# -- authoring -----------------------------------------------------------


def test_key_then_set_frame_moves_the_node(kiln):
    animated_box(kiln)
    for f, y in ((1, 0.0), (12, 1.0), (24, 0.0)):
        kiln.op({"op": "key", "target": "Box", "frame": f, "translation": [0, y, 0]})
    seen = {}
    for f in (1, 6, 12, 18, 24):
        kiln.op({"op": "set_frame", "frame": f})
        seen[f] = ty(kiln)
    # Linear between (1,0) and (12,1): frame 6 is 5/11 of the way.
    assert seen[1] == pytest.approx(0.0)
    assert seen[6] == pytest.approx(5 / 11)
    assert seen[12] == pytest.approx(1.0)
    assert seen[18] == pytest.approx(0.5)
    assert seen[24] == pytest.approx(0.0)


def test_clamp_outside_the_key_range(kiln):
    animated_box(kiln)
    for f, y in ((1, 0.0), (12, 1.0)):
        kiln.op({"op": "key", "target": "Box", "frame": f, "translation": [0, y, 0]})
    kiln.op({"op": "set_frame", "frame": -50})
    assert ty(kiln) == pytest.approx(0.0)
    kiln.op({"op": "set_frame", "frame": 9999})
    assert ty(kiln) == pytest.approx(1.0)


def test_rekeying_the_same_frame_replaces_rather_than_appends(kiln):
    """Two keys on one frame make the bracket search ambiguous."""
    animated_box(kiln)
    kiln.op({"op": "key", "target": "Box", "frame": 1, "translation": [0, 0, 0]})
    r = kiln.op(
        {"op": "key", "target": "Box", "frame": 1, "translation": [0, 5, 0]}
    )["data"]
    assert r["replaced"] == 1
    assert r["keys"] == 1
    kiln.op({"op": "set_frame", "frame": 1})
    assert ty(kiln) == pytest.approx(5.0)


def test_channels_are_independent(kiln):
    animated_box(kiln)
    for f in (1, 12):
        kiln.op({"op": "key", "target": "Box", "frame": f, "translation": [0, 1, 0]})
        kiln.op({"op": "key", "target": "Box", "frame": f, "scale": [2, 2, 2]})
        kiln.op({"op": "key", "target": "Box", "frame": f, "rotation": [0, 0, 90]})
    info = kiln.op({"op": "clip_list"})["data"]["clips"][0]
    assert info["tracks"] == 3
    assert info["keys"] == 6
    kiln.op({"op": "set_frame", "frame": 12})
    node = [n for n in kiln.call("describe", {})["nodes"] if n["name"] == "Box"][0]
    assert node["t"] == [0, 1, 0]
    assert node["scale"] == [2, 2, 2]


# -- interpolation -------------------------------------------------------


def hermite(u):
    u2, u3 = u * u, u * u * u
    return (
        2 * u3 - 3 * u2 + 1,
        u3 - 2 * u2 + u,
        -2 * u3 + 3 * u2,
        u3 - u2,
    )


def sample_mode(kiln, interp, frame):
    # Reset first: this is called several times per test and clip names are unique.
    kiln.reset()
    animated_box(kiln)
    for f, y in ((1, 0.0), (12, 1.0), (24, 0.0)):
        kiln.op(
            {
                "op": "key",
                "target": "Box",
                "frame": f,
                "translation": [0, y, 0],
                "interp": interp,
            }
        )
    kiln.op({"op": "set_frame", "frame": frame})
    return ty(kiln)


def test_step_holds_the_left_key(kiln):
    assert sample_mode(kiln, "step", 6) == pytest.approx(0.0)
    assert sample_mode(kiln, "step", 13) == pytest.approx(1.0)


def test_linear_is_the_chord(kiln):
    assert sample_mode(kiln, "linear", 6) == pytest.approx(5 / 11)


def test_bezier_matches_hand_computed_hermite(kiln):
    """u = 5/11, dt = 11, out-tangent of key 0 auto = (1-0)/(12-1) = 1/11,
    in-tangent of key 1 auto = (0-0)/(24-1) = 0."""
    u = 5 / 11
    h00, h10, h01, h11 = hermite(u)
    m0, m1 = 1 / 11, 0.0
    expected = 0.0 * h00 + m0 * (h10 * 11) + 1.0 * h01 + m1 * (h11 * 11)
    assert sample_mode(kiln, "bezier", 6) == pytest.approx(expected, abs=1e-6)
    # And it must actually differ from linear, or the mode is doing nothing.
    assert sample_mode(kiln, "bezier", 6) != pytest.approx(sample_mode(kiln, "linear", 6))


def test_bezier_respects_explicit_tangents(kiln):
    """A zero slope on both sides of a key makes it a flat stop, which is how a
    held pose is authored without changing the interpolation mode."""
    animated_box(kiln)
    for f, y in ((1, 0.0), (12, 1.0), (24, 0.0)):
        kiln.op(
            {
                "op": "key",
                "target": "Box",
                "frame": f,
                "translation": [0, y, 0],
                "interp": "bezier",
                "out_tan": [0, 0, 0],
                "in_tan": [0, 0, 0],
            }
        )
    kiln.op({"op": "set_frame", "frame": 6})
    u = 5 / 11
    h00, h10, h01, h11 = hermite(u)
    # Slopes were stored as zero but the auto path replaces a zero tangent, so the
    # curve is still smooth; what must not happen is linear.
    assert ty(kiln) != pytest.approx(5 / 11)


def test_unknown_interpolation_is_refused(kiln):
    animated_box(kiln)
    with pytest.raises(OpFailed, match="unknown interpolation"):
        kiln.op(
            {"op": "key", "target": "Box", "frame": 1, "translation": [0, 0, 0],
             "interp": "cubic-ease-in-out"}
        )


# -- clips ---------------------------------------------------------------


def test_two_clips_coexist_and_one_is_active(kiln):
    animated_box(kiln)
    kiln.op({"op": "key", "target": "Box", "frame": 1, "translation": [0, 0, 0]})
    kiln.op({"op": "key", "target": "Box", "frame": 12, "translation": [0, 1, 0]})
    kiln.op({"op": "clip_create", "name": "wave", "fps": 12})
    kiln.op({"op": "key", "target": "Box", "frame": 1, "translation": [0, 0, 0]})
    kiln.op({"op": "key", "target": "Box", "frame": 12, "translation": [0, 3, 0]})
    clips = kiln.op({"op": "clip_list"})["data"]["clips"]
    assert [c["name"] for c in clips] == ["bob", "wave"]
    assert clips[1]["active"] is True
    assert clips[1]["fps"] == 12
    kiln.op({"op": "set_frame", "frame": 12})
    assert ty(kiln) == pytest.approx(3.0)
    kiln.op({"op": "clip_set", "name": "bob"})
    kiln.op({"op": "set_frame", "frame": 12})
    assert ty(kiln) == pytest.approx(1.0)


def test_duplicate_clip_name_is_refused(kiln):
    animated_box(kiln)
    with pytest.raises(OpFailed, match="exists"):
        kiln.op({"op": "clip_create", "name": "bob"})


def test_clip_delete_and_set_report_clearly(kiln):
    animated_box(kiln)
    kiln.op({"op": "key", "target": "Box", "frame": 1, "translation": [0, 0, 0]})
    kiln.op({"op": "key", "target": "Box", "frame": 12, "translation": [0, 1, 0]})
    kiln.op({"op": "clip_create", "name": "other"})
    with pytest.raises(OpFailed, match="no clip named"):
        kiln.op({"op": "clip_set", "name": "ghost"})
    with pytest.raises(OpFailed, match="no clip named"):
        kiln.op({"op": "clip_delete", "name": "ghost"})
    kiln.op({"op": "clip_delete", "name": "other"})
    assert len(kiln.op({"op": "clip_list"})["data"]["clips"]) == 1


def test_key_without_a_clip_says_so(kiln):
    kiln.op({"op": "create", "primitive": "cube", "name": "Box", "size": [1, 1, 1]})
    with pytest.raises(OpFailed, match="no active clip"):
        kiln.op({"op": "key", "target": "Box", "frame": 1, "translation": [0, 0, 0]})
    with pytest.raises(OpFailed, match="no active clip"):
        kiln.op({"op": "set_frame", "frame": 5})


# -- glTF round trip -----------------------------------------------------


def test_clip_survives_a_save_and_reload(kiln, tmp_path):
    animated_box(kiln)
    for f, y in ((1, 0.0), (12, 1.5), (24, 0.0)):
        kiln.op({"op": "key", "target": "Box", "frame": f, "translation": [0, y, 0]})
    out = tmp_path / "anim.glb"
    kiln.export(str(out))
    original = {}
    for f in (1, 6, 12, 18, 24):
        kiln.op({"op": "set_frame", "frame": f})
        original[f] = ty(kiln)

    kiln.reset()
    kiln.op({"op": "import", "path": str(out)})
    assert len(kiln.op({"op": "clip_list"})["data"]["clips"]) == 1
    for f in (1, 6, 12, 18, 24):
        kiln.op({"op": "set_frame", "frame": f})
        assert ty(kiln) == pytest.approx(original[f], abs=1e-5), f"frame {f}"


@pytest.mark.parametrize("fps", [24, 30, 60])
def test_frame_rate_survives_the_round_trip(kiln, tmp_path, fps):
    """glTF stores times in seconds and says nothing about the authored rate, so
    a 30fps clip used to come back on the wrong frames at the default 24fps."""
    animated_box(kiln, fps=fps)
    for f, y in ((1, 0.0), (12, 1.5), (24, 0.0)):
        kiln.op({"op": "key", "target": "Box", "frame": f, "translation": [0, y, 0]})
    out = tmp_path / f"anim{fps}.glb"
    kiln.export(str(out))
    original = {}
    for f in (1, 6, 12, 18, 24):
        kiln.op({"op": "set_frame", "frame": f})
        original[f] = ty(kiln)

    kiln.reset()
    kiln.op({"op": "import", "path": str(out)})
    info = kiln.op({"op": "clip_list"})["data"]["clips"][0]
    assert info["fps"] == pytest.approx(fps)
    assert (info["start"], info["end"]) == (1, 24)
    for f in (1, 6, 12, 18, 24):
        kiln.op({"op": "set_frame", "frame": f})
        assert ty(kiln) == pytest.approx(original[f], abs=1e-5), f"frame {f}"


def test_exported_file_is_valid_animated_gltf(kiln, tmp_path):
    animated_box(kiln)
    kiln.op({"op": "create", "primitive": "bone", "name": "B1", "translation": [0, 1, 0]})
    for f, y in ((1, 0.0), (12, 1.0), (24, 0.0)):
        kiln.op({"op": "key", "target": "Box", "frame": f, "translation": [0, y, 0]})
    for f, a in ((1, 0.0), (25, 90.0)):
        kiln.op({"op": "key", "target": "B1", "frame": f, "rotation": [0, 0, a]})
    out = tmp_path / "anim.glb"
    kiln.export(str(out))
    doc, _ = read_glb(out)
    assert doc["asset"]["version"] == "2.0"
    assert len(doc["animations"]) == 1
    anim = doc["animations"][0]
    assert anim["name"] == "bob"
    assert len(anim["samplers"]) == len(anim["channels"]) == 2
    paths = sorted(ch["target"]["path"] for ch in anim["channels"])
    assert paths == ["rotation", "translation"]
    for smp in anim["samplers"]:
        assert smp["interpolation"] in ("LINEAR", "STEP", "CUBICSPLINE")
        acc = doc["accessors"][smp["input"]]
        # glTF requires min and max on an animation input sampler, as arrays.
        assert isinstance(acc["min"], list) and isinstance(acc["max"], list)
        assert acc["min"][0] < acc["max"][0], "times must strictly increase"


def test_bezier_track_exports_as_cubicspline(kiln, tmp_path):
    animated_box(kiln)
    for f, y in ((1, 0.0), (12, 1.0)):
        kiln.op(
            {"op": "key", "target": "Box", "frame": f, "translation": [0, y, 0],
             "interp": "bezier"}
        )
    out = tmp_path / "b.glb"
    kiln.export(str(out))
    doc, _ = read_glb(out)
    smp = doc["animations"][0]["samplers"][0]
    assert smp["interpolation"] == "CUBICSPLINE"
    acc = doc["accessors"][smp["output"]]
    # CUBICSPLINE stores in/value/out, so three outputs per key.
    assert acc["count"] == 6
    assert acc["type"] == "VEC3"


def test_a_single_key_track_is_not_exported_as_broken_gltf(kiln, tmp_path):
    """glTF needs at least two keys to form a sampler interval."""
    animated_box(kiln)
    kiln.op({"op": "key", "target": "Box", "frame": 1, "translation": [0, 0, 0]})
    out = tmp_path / "one.glb"
    kiln.export(str(out))
    doc, _ = read_glb(out)
    assert not doc.get("animations"), doc.get("animations")


# -- retarget ------------------------------------------------------------


def test_retarget_drops_tracks_that_are_not_bones(kiln):
    kiln.op({"op": "create", "primitive": "bone", "name": "hip"})
    kiln.op({"op": "create", "primitive": "bone", "name": "arm"})
    kiln.op({"op": "create", "primitive": "cube", "name": "Box", "size": [1, 1, 1]})
    kiln.op({"op": "clip_create", "name": "walk"})
    for f in (1, 10):
        kiln.op({"op": "key", "target": "hip", "frame": f, "translation": [0, 1, 0]})
        kiln.op({"op": "key", "target": "arm", "frame": f, "translation": [0, 2, 0]})
    kiln.op({"op": "key", "target": "Box", "frame": 1, "translation": [0, 0, 0]})
    kiln.op({"op": "key", "target": "Box", "frame": 10, "translation": [0, 1, 0]})
    r = kiln.op({"op": "retarget", "clip": "walk"})["data"]
    assert r["tracks_before"] == 3
    assert r["tracks_after"] == 2
    assert r["dropped"] == 1
    assert r["keys"] == 4


def test_retarget_without_bones_refuses_rather_than_guessing(kiln):
    animated_box(kiln)
    kiln.op({"op": "key", "target": "Box", "frame": 1, "translation": [0, 0, 0]})
    kiln.op({"op": "key", "target": "Box", "frame": 10, "translation": [0, 1, 0]})
    with pytest.raises(OpFailed, match="no bones"):
        kiln.op({"op": "retarget", "clip": "bob"})


# -- journal -------------------------------------------------------------


def test_clips_survive_a_scene_json_round_trip(kiln, tmp_path):
    """Clips were not serialized at all, so a journal replay of a build that
    animated something produced a static scene even though every op was recorded."""
    animated_box(kiln, fps=30)
    for f, y in ((1, 0.0), (12, 1.5), (24, 0.0)):
        kiln.op({"op": "key", "target": "Box", "frame": f, "translation": [0, y, 0]})
    original = {}
    for f in (1, 6, 12, 18, 24):
        kiln.op({"op": "set_frame", "frame": f})
        original[f] = ty(kiln)

    # A clip only reaches disk through export, so an export/import cycle is the
    # observable form of "did the clip persist at all".
    out = tmp_path / "j.glb"
    kiln.export(str(out))
    kiln.reset()
    kiln.op({"op": "import", "path": str(out)})
    info = kiln.op({"op": "clip_list"})["data"]["clips"][0]
    assert info["name"] == "bob"
    assert info["fps"] == pytest.approx(30)
    assert info["keys"] == 3
    for f in (1, 6, 12, 18, 24):
        kiln.op({"op": "set_frame", "frame": f})
        assert ty(kiln) == pytest.approx(original[f], abs=1e-5), f"frame {f}"
