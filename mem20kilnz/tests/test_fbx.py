"""FBX import, against real FBX files.

These use the 19 FBX models shipped by assimp's own test-data package, so the
importer is checked against files produced by other tools rather than by kiln.
One of them is deliberately corrupt and is expected to be refused with a reason
that names assimp, not with a JSON complaint about a binary file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

MODELS = Path("/usr/share/assimp/models/FBX")
CORRUPT = "transparentTest.fbx"

pytestmark = pytest.mark.skipif(
    not MODELS.is_dir(), reason="assimp test models not installed"
)


def fbx_files() -> list[Path]:
    return sorted(MODELS.rglob("*.fbx")) + sorted(MODELS.rglob("*.FBX"))


def test_real_fbx_files_are_present():
    """If this fails the suite below is vacuous."""
    assert len(fbx_files()) >= 15, "expected the assimp FBX corpus"


def test_box_fbx_imports_with_its_geometry(kiln):
    kiln.reset()
    result = kiln.op({"op": "import", "path": str(MODELS / "box.fbx")})
    assert result["ok"] is True
    assert result["data"]["meshes"] >= 1
    assert result["data"]["reader"] == "assimp"
    # A box is 12 triangles.
    # describe() reports per-node face counts; a box is 12 triangles.
    faces = sum(n["faces"] for n in kiln.call("describe", {})["nodes"] if "faces" in n)
    assert faces == 12


def test_multi_mesh_file_keeps_every_mesh(kiln):
    kiln.reset()
    result = kiln.op({"op": "import", "path": str(MODELS / "cubes_nonames.fbx")})
    assert result["data"]["meshes"] == 4
    assert len(kiln.call("list", {})["nodes"]) >= 4


def test_imported_material_carries_albedo_and_roughness(kiln):
    kiln.reset()
    kiln.op({"op": "import", "path": str(MODELS / "phong_cube.fbx")})
    described = kiln.call("describe", {})
    mesh = next(n for n in described["nodes"] if n["type"] == "mesh")
    assert "material" in mesh, "material was dropped on FBX import"
    assert "albedo" in mesh and "roughness" in mesh


def test_a_corrupt_fbx_is_refused_naming_assimp(kiln):
    """The error must not blame glTF for a binary FBX failure."""
    path = MODELS / CORRUPT
    if not path.is_file():
        pytest.skip("corrupt sample not present")
    kiln.reset()
    with pytest.raises(Exception) as exc:
        kiln.op({"op": "import", "path": str(path)})
    message = str(exc.value)
    assert "assimp" in message, message
    assert "gltf" not in message.lower(), f"misleading error for a binary file: {message}"


def test_a_non_fbx_file_is_still_read_by_the_gltf_reader(kiln, tmp_path):
    """Adding assimp must not steal glTF from the native reader.

    assimp advertises .glb support but cannot actually read a bare .gltf, and it
    would be a silent regression to hand kiln's own tested glTF path to a second
    implementation. Built with the project's own fixture writer so the container
    is correct.
    """
    import struct
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    import make_fixtures as mf

    positions = [(-1, -1, 0), (1, -1, 0), (0, 1, 0)]
    buf = b"".join(struct.pack("<3f", *p) for p in positions)
    gltf = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": "Tri"}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3,
                       "type": "VEC3"}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(buf)}],
        "buffers": [{"byteLength": len(buf)}],
    }
    path = tmp_path / "native.glb"
    mf.write_glb(path, gltf, buf)

    kiln.reset()
    result = kiln.op({"op": "import", "path": str(path)})
    assert result["ok"] is True
    # The native reader reports primitives; assimp would add a "reader" key.
    assert "primitives" in result["data"], result["data"]
    assert "reader" not in result["data"], "glTF should not go through assimp"


def test_every_readable_fbx_imports_without_error(kiln):
    """A corpus sweep: nothing may crash or silently produce nothing."""
    readable, refused = [], []
    for path in fbx_files():
        kiln.reset()
        try:
            result = kiln.op({"op": "import", "path": str(path)})
        except Exception as exc:
            refused.append((path.name, str(exc)))
            continue
        assert result["data"].get("meshes", 0) > 0, f"{path.name} imported nothing"
        readable.append(path.name)
    assert len(readable) >= 15
    # The only expected refusal is the deliberately corrupt sample.
    for name, _ in refused:
        assert CORRUPT in name, f"unexpected refusal: {name}"
