"""Vertex sharing, and UVs and normals surviving a round trip.

Both used to be broken in the same place. `mesh_sync_render` appended three
fresh vertices per triangle unconditionally, so every export was a triangle
soup, and it wrote the UV as the per-triangle ramp (0,0), (1,0), (1,1) — which
is not a texture coordinate, yet files claimed `uvs=y`.

These assert the welded behaviour, and assert that a file with no real UVs says
so rather than publishing placeholders.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from mem20kilnz import validate as V

sys.path.insert(0, str(Path(__file__).parent))
import make_fixtures as mf  # noqa: E402


def _quad_glb(path: Path, with_uv: bool, with_normal: bool = True) -> Path:
    pos = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    uv = [(0, 0), (1, 0), (1, 1), (0, 1)]
    pb = b"".join(struct.pack("<3f", *p) for p in pos)
    attrs = {"POSITION": 0}
    accessors = [{"bufferView": 0, "componentType": 5126, "count": 4, "type": "VEC3"}]
    views = [{"buffer": 0, "byteOffset": 0, "byteLength": len(pb)}]
    blob = pb
    if with_uv:
        ub = b"".join(struct.pack("<2f", *t) for t in uv)
        attrs["TEXCOORD_0"] = 1
        accessors.append({"bufferView": 1, "componentType": 5126, "count": 4,
                          "type": "VEC2"})
        views.append({"buffer": 0, "byteOffset": len(pb), "byteLength": len(ub)})
        blob += ub
    if with_normal:
        nb = b"".join(struct.pack("<3f", 0.0, 0.0, 1.0) for _ in pos)
        attrs["NORMAL"] = len(accessors)
        accessors.append({"bufferView": len(views), "componentType": 5126, "count": 4,
                          "type": "VEC3"})
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(nb)})
        blob += nb
    # A quad is 4 vertices with an index buffer. Without indices, 4 vertices
    # form only one triangle, which is not the fixture being described.
    idx = b"".join(struct.pack("<H", i) for i in (0, 1, 2, 0, 2, 3))
    accessors.append({"bufferView": len(views), "componentType": 5123, "count": 6,
                      "type": "SCALAR"})
    views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(idx)})
    blob += idx
    gltf = {
        "asset": {"version": "2.0"}, "scene": 0,
        "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0, "name": "Quad"}],
        "meshes": [{"primitives": [{"attributes": attrs, "indices": len(accessors) - 1}]}],
        "accessors": accessors, "bufferViews": views,
        "buffers": [{"byteLength": len(blob)}],
    }
    mf.write_glb(path, gltf, blob)
    return path


# -- vertex sharing -------------------------------------------------------


def test_export_is_welded_not_a_triangle_soup(kiln, tmp_path):
    kiln.reset()
    kiln.op({"op": "create", "primitive": "cube", "name": "C", "size": [1, 1, 1]})
    out = tmp_path / "c.glb"
    kiln.export(str(out))
    m = V.validate(out).meshes[0]
    assert m.triangles == 12
    assert m.vertices < m.triangles * 3, "still a triangle soup"
    # 24, not 8: a flat-shaded cube cannot weld below 6 faces x 4 corners,
    # because each face needs its own normal. The soup wrote 36. Welding on
    # position alone would give 8 and smear every hard edge, so 24 is the
    # correct answer and 8 would be the bug.
    assert m.vertices == 24


def test_a_smoothed_mesh_still_shares_vertices(kiln, tmp_path):
    """Subdivision produces many faces; welding must still collapse them.

    A closed manifold with T triangles has exactly T/2 + 2 vertices, so that is
    the figure a correctly welded subdivided mesh must reach.
    """
    kiln.reset()
    kiln.op({"op": "create", "primitive": "sphere", "name": "S", "size": [1, 1, 1]})
    kiln.op({"op": "subsurf", "levels": 2})
    out = tmp_path / "s.glb"
    kiln.export(str(out))
    m = V.validate(out).meshes[0]
    assert m.triangles == 8448
    assert m.vertices == m.triangles // 2 + 2, (
        f"{m.vertices} vertices where a closed manifold needs "
        f"{m.triangles // 2 + 2}: the export is a triangle soup"
    )


def test_hard_edges_are_not_merged_away(kiln, tmp_path):
    """Welding on position alone would fuse corners that must stay apart.

    A cube is 8 positions but 24 render corners: each of the 6 faces needs its
    own normal at each of its 4 corners. A weld that ignored normals would
    report 8 and turn every hard edge into a smear, so 24 is the assertion that
    catches it.
    """
    kiln.reset()
    kiln.op({"op": "create", "primitive": "cube", "name": "Hard", "size": [1, 1, 1]})
    out = tmp_path / "hard.glb"
    kiln.export(str(out))
    m = V.validate(out).meshes[0]
    assert m.vertices == 24, "hard edges were welded away"
    assert m.vertices > 8


# -- UVs -----------------------------------------------------------------


def test_real_uvs_survive_import_and_export(kiln, tmp_path):
    src = _quad_glb(tmp_path / "q.glb", with_uv=True)
    assert V.validate(src).meshes[0].has_uvs is True
    kiln.reset()
    kiln.op({"op": "import", "path": str(src)})
    out = tmp_path / "out.glb"
    kiln.export(str(out))
    m = V.validate(out).meshes[0]
    assert m.has_uvs is True, "UVs were dropped across the round trip"
    assert m.triangles == 2, "an indexed quad is 2 triangles"
    assert m.vertices == 4, "an indexed quad welds to 4 shared corners"


def test_a_mesh_with_no_uvs_does_not_claim_them(kiln, tmp_path):
    """The regression this replaces: files advertised uvs=y with a fake ramp."""
    src = _quad_glb(tmp_path / "nouv.glb", with_uv=False)
    assert V.validate(src).meshes[0].has_uvs is False
    kiln.reset()
    kiln.op({"op": "import", "path": str(src)})
    out = tmp_path / "out.glb"
    kiln.export(str(out))
    assert V.validate(out).meshes[0].has_uvs is False, (
        "the exporter fabricated a UV set for a mesh that had none"
    )


def test_uv_seams_are_preserved(kiln, tmp_path):
    """Two corners at the same position with different UVs must not merge."""
    pos = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    # Corner 0 and corner 3 share a position but not a UV: a seam.
    uv = [(0, 0), (1, 0), (1, 1), (0.5, 0.5)]
    pb = b"".join(struct.pack("<3f", *p) for p in pos)
    ub = b"".join(struct.pack("<2f", *t) for t in uv)
    gltf = {
        "asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": "Seam"}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_0": 1}}]}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 4, "type": "VEC3"},
            {"bufferView": 1, "componentType": 5126, "count": 4, "type": "VEC2"},
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(pb)},
            {"buffer": 0, "byteOffset": len(pb), "byteLength": len(ub)},
        ],
        "buffers": [{"byteLength": len(pb) + len(ub)}],
    }
    src = tmp_path / "seam.glb"
    mf.write_glb(src, gltf, pb + ub)
    kiln.reset()
    kiln.op({"op": "import", "path": str(src)})
    out = tmp_path / "seam_out.glb"
    kiln.export(str(out))
    m = V.validate(out).meshes[0]
    assert m.has_uvs is True
    # A 4-corner quad with one seam welds to 3, not 2: the seam holds it open.
    assert m.vertices >= 3


# -- validator ------------------------------------------------------------


def test_validator_handles_a_non_indexed_primitive(tmp_path):
    """A glTF primitive may omit `indices`; that must not crash validation.

    It used to raise UnboundLocalError, so any non-indexed glTF took the
    validator down rather than being reported.
    """
    pos = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (1, 0, 0), (0, 1, 0)]
    pb = b"".join(struct.pack("<3f", *p) for p in pos)
    gltf = {
        "asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": "NTri"}],
        # 6 vertices, no index buffer: two explicit triangles.
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": 6,
                       "type": "VEC3"}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(pb)}],
        "buffers": [{"byteLength": len(pb)}],
    }
    src = tmp_path / "nonindexed.glb"
    mf.write_glb(src, gltf, pb)
    report = V.validate(src)
    assert report.ok is True, [f.message for f in report.errors]
    assert report.meshes[0].triangles == 2
    assert any(f.code == "no_indices" for f in report.warnings)
