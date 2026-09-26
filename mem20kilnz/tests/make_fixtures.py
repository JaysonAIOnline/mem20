#!/usr/bin/env python3
"""Generate glTF/GLB fixtures that exercise import paths kiln's exporter never emits.

kiln's own exporter writes float32 POSITION, uint16/uint32 indices, TRIANGLES
only, one primitive per mesh, TRS node transforms, and no skins. An importer
tested only against its own exporter proves nothing, so every fixture here
targets a path the exporter cannot produce.

Byte lengths and offsets are computed by BinBuilder rather than written by hand:
hand-written lengths are how you ship a fixture that Blender itself rejects.

Usage:  python3 make_fixtures.py <outdir>
"""

import base64
import json
import os
import struct
import sys

CHUNK_JSON = 0x4E4F534A
CHUNK_BIN = 0x004E4942


def pad4(b, fill=0):
    while len(b) % 4:
        b += bytes([fill])
    return b


class BinBuilder:
    def __init__(self):
        self.parts = []
        self.n = 0

    def add(self, data, align=4):
        pad = (-self.n) % align
        if pad:
            self.parts.append(b"\x00" * pad)
            self.n += pad
        off = self.n
        self.parts.append(data)
        self.n += len(data)
        return off, len(data)

    def bytes(self):
        return b"".join(self.parts)


def write_glb(path, gltf, binary):
    js = pad4(json.dumps(gltf, separators=(",", ":")).encode("utf-8"), 0x20)
    bs = pad4(binary, 0x00)
    total = 12 + 8 + len(js) + (8 + len(bs) if bs else 0)
    out = b"glTF" + struct.pack("<II", 2, total)
    out += struct.pack("<II", len(js), CHUNK_JSON) + js
    if bs:
        out += struct.pack("<II", len(bs), CHUNK_BIN) + bs
    with open(path, "wb") as f:
        f.write(out)
    return total


def bv(off, length, target=None, stride=None):
    d = {"buffer": 0, "byteOffset": off, "byteLength": length}
    if target:
        d["target"] = target
    if stride:
        d["byteStride"] = stride
    return d


def acc(bv_index, ctype, count, atype, **kw):
    d = {"bufferView": bv_index, "componentType": ctype, "count": count, "type": atype}
    d.update(kw)
    return d


def f3(verts):
    return b"".join(struct.pack("<3f", *v) for v in verts)


def u16(idxs):
    return b"".join(struct.pack("<H", i) for i in idxs)


def u32(idxs):
    return b"".join(struct.pack("<I", i) for i in idxs)


def bounds(verts):
    lo = [min(v[i] for v in verts) for i in range(3)]
    hi = [max(v[i] for v in verts) for i in range(3)]
    return lo, hi


TRI = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]


def simple(name, outdir, node_extra=None, mat=True, ext=None, path=None):
    b = BinBuilder()
    po, pl = b.add(f3(TRI))
    io_, il = b.add(u16([0, 1, 2]))
    node = {"name": "N", "mesh": 0}
    if node_extra:
        node.update(node_extra)
    g = {
        "asset": {"version": "2.0", "generator": "kilnz-fixture"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [node],
        "meshes": [{"name": "m", "primitives": [{"attributes": {"POSITION": 0},
                                                  "indices": 1}]}],
        "buffers": [{"byteLength": b.n}],
        "bufferViews": [bv(po, pl, 34962), bv(io_, il, 34963)],
        "accessors": [acc(0, 5126, 3, "VEC3", min=bounds(TRI)[0], max=bounds(TRI)[1]),
                      acc(1, 5123, 3, "SCALAR")],
    }
    if mat:
        g["materials"] = [{"name": "red",
                           "pbrMetallicRoughness": {"baseColorFactor": [1, 0, 0, 1],
                                                    "metallicFactor": 0.0,
                                                    "roughnessFactor": 0.5}}]
        g["meshes"][0]["primitives"][0]["material"] = 0
    if ext:
        g["meshes"][0]["primitives"][0]["extensions"] = ext
    p = path or os.path.join(outdir, name + ".glb")
    return write_glb(p, g, b.bytes()), {"meshes": 1, "faces": 1, "vertices": 3}


# --------------------------------------------------------------------------
def fx_quantized(outdir):
    """uint16 positions, uint32 indices, scale carried on the node."""
    verts = [(0, 0, 0), (100, 0, 0), (0, 100, 0), (0, 0, 100)]
    b = BinBuilder()
    po, pl = b.add(b"".join(struct.pack("<3H", *v) for v in verts))
    io_, il = b.add(u32([0, 1, 2, 0, 2, 3]))
    lo, hi = bounds(verts)
    g = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "Quantized", "mesh": 0, "scale": [0.01, 0.01, 0.01]}],
        "meshes": [{"name": "q", "primitives": [{"attributes": {"POSITION": 0},
                                                  "indices": 1, "material": 0}]}],
        "materials": [{"name": "red",
                       "pbrMetallicRoughness": {"baseColorFactor": [1, 0, 0, 1]}}],
        "buffers": [{"byteLength": b.n}],
        "bufferViews": [bv(po, pl, 34962), bv(io_, il, 34963)],
        "accessors": [acc(0, 5123, 4, "VEC3", min=lo, max=hi), acc(1, 5125, 6, "SCALAR")],
    }
    return write_glb(os.path.join(outdir, "quantized.glb"), g, b.bytes()), \
        {"meshes": 1, "faces": 2, "vertices": 4}


# --------------------------------------------------------------------------
def fx_interleaved(outdir):
    """One bufferView with byteStride 32: pos, normal, uv interleaved per vertex."""
    verts = [((0, 0, 0), (0, 0, 1), (0, 0)), ((1, 0, 0), (0, 0, 1), (1, 0)),
             ((0, 1, 0), (0, 0, 1), (0, 1))]
    stride = 32
    body = b"".join(struct.pack("<3f3f2f", *p, *n, *uv) for p, n, uv in verts)
    b = BinBuilder()
    po, pl = b.add(body)
    io_, il = b.add(u16([0, 1, 2]))
    g = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "Interleaved", "mesh": 0}],
        "meshes": [{"name": "il", "primitives": [
            {"attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2},
             "indices": 3, "material": 0}]}],
        "materials": [{"name": "m", "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1]}}],
        "buffers": [{"byteLength": b.n}],
        "bufferViews": [bv(po, pl, 34962, stride=stride), bv(io_, il, 34963)],
        "accessors": [acc(0, 5126, 3, "VEC3", min=bounds(TRI)[0], max=bounds(TRI)[1]),
                      acc(0, 5126, 3, "VEC3"), acc(0, 5126, 3, "VEC2"),
                      acc(1, 5123, 3, "SCALAR")],
    }
    return write_glb(os.path.join(outdir, "interleaved.glb"), g, b.bytes()), \
        {"meshes": 1, "faces": 1, "vertices": 3}


# --------------------------------------------------------------------------
def fx_sparse(outdir):
    """A sparse accessor overriding positions 1 and 3 of five."""
    verts = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 1)]
    b = BinBuilder()
    po, pl = b.add(f3(verts))
    io_, il = b.add(u16([0, 1, 2]))
    sio_, sil = b.add(u16([1, 3]))
    svo_, svl = b.add(f3([(9, 0, 0), (0, 0, 9)]))
    g = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "Sparse", "mesh": 0}],
        "meshes": [{"name": "sp", "primitives": [{"attributes": {"POSITION": 0},
                                                  "indices": 1}]}],
        "buffers": [{"byteLength": b.n}],
        "bufferViews": [bv(po, pl, 34962), bv(io_, il, 34963),
                        bv(sio_, sil), bv(svo_, svl)],
        "accessors": [acc(0, 5126, 5, "VEC3", min=bounds(verts)[0], max=bounds(verts)[1]),
                      acc(1, 5123, 3, "SCALAR")],
    }
    g["accessors"][0]["sparse"] = {"count": 2,
                                   "indices": {"bufferView": 2, "byteOffset": 0,
                                               "componentType": 5123},
                                   "values": {"bufferView": 3}}
    return write_glb(os.path.join(outdir, "sparse.glb"), g, b.bytes()), \
        {"meshes": 1, "faces": 1, "vertices": 5}


# --------------------------------------------------------------------------
def fx_modes(outdir):
    """TRIANGLE_STRIP, TRIANGLE_FAN and a POINTS primitive in one mesh."""
    verts = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    b = BinBuilder()
    po, pl = b.add(f3(verts))
    a1, l1 = b.add(u16([0, 1, 2, 3]))
    a2, l2 = b.add(u16([0, 1, 2, 3]))
    a3, l3 = b.add(u16([0, 1]))
    g = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "Modes", "mesh": 0}],
        "meshes": [{"name": "md", "primitives": [
            {"attributes": {"POSITION": 0}, "indices": 1, "mode": 5},
            {"attributes": {"POSITION": 0}, "indices": 2, "mode": 6},
            {"attributes": {"POSITION": 0}, "indices": 3, "mode": 0},
        ]}],
        "buffers": [{"byteLength": b.n}],
        "bufferViews": [bv(po, pl, 34962), bv(a1, l1, 34963), bv(a2, l2, 34963),
                        bv(a3, l3, 34963)],
        "accessors": [acc(0, 5126, 4, "VEC3", min=bounds(verts)[0], max=bounds(verts)[1]),
                      acc(1, 5123, 4, "SCALAR"), acc(2, 5123, 4, "SCALAR"),
                      acc(3, 5123, 2, "SCALAR")],
    }
    # kiln has one Mesh per primitive, so the 4 shared positions are copied into
    # each of the 2 usable primitives: 8 positions across 2 meshes, not 4.
    return write_glb(os.path.join(outdir, "modes.glb"), g, b.bytes()), \
        {"meshes": 2, "faces": 4, "vertices": 8}


# --------------------------------------------------------------------------
def fx_multiprim(outdir):
    """One mesh, two primitives, two materials, two materials indices."""
    t0 = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
    t1 = [(2, 0, 0), (3, 0, 0), (2, 1, 0)]
    b = BinBuilder()
    p0, l0 = b.add(f3(t0))
    p1, l1 = b.add(f3(t1))
    i0, il0 = b.add(u16([0, 1, 2]))
    i1, il1 = b.add(u16([0, 1, 2]))
    g = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "Multi", "mesh": 0, "translation": [0, 5, 0]}],
        "meshes": [{"name": "mp", "primitives": [
            {"attributes": {"POSITION": 0}, "indices": 2, "material": 0},
            {"attributes": {"POSITION": 1}, "indices": 3, "material": 1},
        ]}],
        "materials": [{"name": "red", "pbrMetallicRoughness": {"baseColorFactor": [1, 0, 0, 1]}},
                      {"name": "blue", "pbrMetallicRoughness": {"baseColorFactor": [0, 0, 1, 1]}}],
        "buffers": [{"byteLength": b.n}],
        "bufferViews": [bv(p0, l0, 34962), bv(p1, l1, 34962),
                        bv(i0, il0, 34963), bv(i1, il1, 34963)],
        "accessors": [acc(0, 5126, 3, "VEC3", min=bounds(t0)[0], max=bounds(t0)[1]),
                      acc(1, 5126, 3, "VEC3", min=bounds(t1)[0], max=bounds(t1)[1]),
                      acc(2, 5123, 3, "SCALAR"), acc(3, 5123, 3, "SCALAR")],
    }
    return write_glb(os.path.join(outdir, "multiprim.glb"), g, b.bytes()), \
        {"meshes": 2, "faces": 2, "vertices": 6}


# --------------------------------------------------------------------------
def fx_matrix_negscale(outdir):
    """A node `matrix` (not TRS) carrying a Z rotation and a negative X scale."""
    sx, sz = -2.0, 1.0
    m = [sx, 0.0, 0.0, 0.0,
         0.0, 1.0, 0.0, 0.0,
         0.0, 0.0, sz, 0.0,
         1.0, 2.0, 3.0, 1.0]
    b = BinBuilder()
    po, pl = b.add(f3(TRI))
    io_, il = b.add(u16([0, 1, 2]))
    g = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "MatNegScale", "mesh": 0, "matrix": m}],
        "meshes": [{"name": "mn", "primitives": [{"attributes": {"POSITION": 0},
                                                  "indices": 1}]}],
        "buffers": [{"byteLength": b.n}],
        "bufferViews": [bv(po, pl, 34962), bv(io_, il, 34963)],
        "accessors": [acc(0, 5126, 3, "VEC3", min=bounds(TRI)[0], max=bounds(TRI)[1]),
                      acc(1, 5123, 3, "SCALAR")],
    }
    return write_glb(os.path.join(outdir, "matrix_negscale.glb"), g, b.bytes()), \
        {"meshes": 1, "faces": 1, "vertices": 3}


# --------------------------------------------------------------------------
def fx_skinned(outdir):
    """Two joints, inverseBindMatrices, JOINTS_0 and WEIGHTS_0."""
    verts = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)]
    b = BinBuilder()
    po, pl = b.add(f3(verts))
    jo, jl = b.add(b"".join(struct.pack("<4H", 0, 1, 0, 0) for _ in verts))
    wo, wl = b.add(b"".join(struct.pack("<4f", 0.75, 0.25, 0.0, 0.0) for _ in verts))
    io_, il = b.add(u16([0, 1, 2, 2, 1, 3]))
    ident = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    tip = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, -1, 0, 0, 1]
    bo_, bl = b.add(struct.pack("<32f", *(ident + tip)))
    g = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0, 1, 2]}],
        "nodes": [{"name": "Skinned", "mesh": 0, "skin": 0},
                  {"name": "RootJ", "translation": [0, 1, 0]},
                  {"name": "TipJ", "translation": [0, 1, 0]}],
        "skins": [{"joints": [1, 2], "inverseBindMatrices": 4}],
        "meshes": [{"name": "sk", "primitives": [
            {"attributes": {"POSITION": 0, "JOINTS_0": 1, "WEIGHTS_0": 2}, "indices": 3}]}],
        "buffers": [{"byteLength": b.n}],
        "bufferViews": [bv(po, pl, 34962), bv(jo, jl), bv(wo, wl), bv(io_, il, 34963),
                        bv(bo_, bl)],
        "accessors": [acc(0, 5126, 4, "VEC3", min=bounds(verts)[0], max=bounds(verts)[1]),
                      acc(1, 5123, 4, "VEC4"), acc(2, 5126, 4, "VEC4"),
                      acc(3, 5123, 6, "SCALAR"), acc(4, 5126, 2, "MAT4")],
    }
    return write_glb(os.path.join(outdir, "skinned.glb"), g, b.bytes()), \
        {"meshes": 1, "faces": 2, "vertices": 4, "skins": 1, "bones": 2}


# --------------------------------------------------------------------------
def _gltf_doc(bin_len, extra_views, accessors, uri):
    return {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "G", "mesh": 0}],
        "meshes": [{"name": "g", "primitives": [{"attributes": {"POSITION": 0},
                                                  "indices": 1}]}],
        "buffers": [{"byteLength": bin_len, "uri": uri}],
        "bufferViews": extra_views,
        "accessors": accessors,
    }


def fx_embedded_gltf(outdir):
    """A .gltf file with the buffer inline as a base64 data URI."""
    b = BinBuilder()
    po, pl = b.add(f3(TRI))
    io_, il = b.add(u16([0, 1, 2]))
    raw = b.bytes()
    uri = "data:application/octet-stream;base64," + base64.b64encode(raw).decode("ascii")
    g = _gltf_doc(b.n, [bv(po, pl, 34962), bv(io_, il, 34963)],
                  [acc(0, 5126, 3, "VEC3", min=bounds(TRI)[0], max=bounds(TRI)[1]),
                   acc(1, 5123, 3, "SCALAR")], uri)
    p = os.path.join(outdir, "embedded.gltf")
    with open(p, "w") as f:
        json.dump(g, f)
    return os.path.getsize(p), {"meshes": 1, "faces": 1, "vertices": 3}


def fx_external_gltf(outdir):
    """A .gltf file whose buffer is a separate .bin on disk."""
    b = BinBuilder()
    po, pl = b.add(f3(TRI))
    io_, il = b.add(u16([0, 1, 2]))
    raw = b.bytes()
    with open(os.path.join(outdir, "external.bin"), "wb") as f:
        f.write(raw)
    g = _gltf_doc(len(raw), [bv(po, pl, 34962), bv(io_, il, 34963)],
                  [acc(0, 5126, 3, "VEC3", min=bounds(TRI)[0], max=bounds(TRI)[1]),
                   acc(1, 5123, 3, "SCALAR")], "external.bin")
    p = os.path.join(outdir, "external.gltf")
    with open(p, "w") as f:
        json.dump(g, f)
    return os.path.getsize(p), {"meshes": 1, "faces": 1, "vertices": 3}


# --------------------------------------------------------------------------
def fx_hierarchy(outdir):
    """Nested transforms: parent scale+rotation, child translation and mesh."""
    b = BinBuilder()
    po, pl = b.add(f3(TRI))
    io_, il = b.add(u16([0, 1, 2]))
    g = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "Root", "scale": [2, 2, 2],
                   "rotation": [0, 0.7071068, 0, 0.7071068], "children": [1]},
                  {"name": "Child", "mesh": 0, "translation": [1, 0, 0]}],
        "meshes": [{"name": "hi", "primitives": [{"attributes": {"POSITION": 0},
                                                  "indices": 1}]}],
        "buffers": [{"byteLength": b.n}],
        "bufferViews": [bv(po, pl, 34962), bv(io_, il, 34963)],
        "accessors": [acc(0, 5126, 3, "VEC3", min=bounds(TRI)[0], max=bounds(TRI)[1]),
                      acc(1, 5123, 3, "SCALAR")],
    }
    return write_glb(os.path.join(outdir, "hierarchy.glb"), g, b.bytes()), \
        {"meshes": 1, "faces": 1, "vertices": 3}


# --------------------------------------------------------------------------
def fx_no_materials(outdir):
    """A primitive with no `material`, alongside a mesh with no primitives."""
    size, exp = simple("no_materials", outdir, mat=False)
    g = None
    with open(os.path.join(outdir, "no_materials.glb"), "rb") as f:
        import struct as st
        d = f.read()
    off, chunks = 12, []
    while off + 8 <= len(d):
        ln, ty = st.unpack("<II", d[off:off + 8])
        chunks.append((ty, d[off + 8:off + 8 + ln]))
        off += 8 + ln
    g = json.loads(chunks[0][1].decode("utf-8"))
    g["scenes"][0]["nodes"] = [0, 1]
    g["nodes"].append({"name": "EmptyMesh", "mesh": 1})
    g["meshes"].append({"name": "broken", "primitives": []})
    size = write_glb(os.path.join(outdir, "no_materials.glb"), g, chunks[1][1])
    return size, exp


# --------------------------------------------------------------------------
def fx_extras(outdir):
    """COLOR_0, TANGENT and a KHR extension, all of which must be reported."""
    verts = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
    cols = [(1, 0, 0, 1), (0, 1, 0, 1), (0, 0, 1, 1)]
    tans = [(1, 0, 0, 1), (0, 1, 0, 1), (0, 0, 1, 1)]
    b = BinBuilder()
    po, pl = b.add(f3(verts))
    co, cl = b.add(b"".join(struct.pack("<4f", *c) for c in cols))
    to, tl = b.add(b"".join(struct.pack("<4f", *t) for t in tans))
    io_, il = b.add(u16([0, 1, 2]))
    g = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "Extras", "mesh": 0}],
        "meshes": [{"name": "ex2", "primitives": [
            {"attributes": {"POSITION": 0, "COLOR_0": 1, "TANGENT": 2}, "indices": 3,
             "extensions": {"KHR_materials_unlit": {}}}]}],
        "buffers": [{"byteLength": b.n}],
        "bufferViews": [bv(po, pl, 34962), bv(co, cl), bv(to, tl), bv(io_, il, 34963)],
        "accessors": [acc(0, 5126, 3, "VEC3", min=bounds(verts)[0], max=bounds(verts)[1]),
                      acc(1, 5126, 3, "VEC4"), acc(2, 5126, 3, "VEC4"),
                      acc(3, 5123, 3, "SCALAR")],
    }
    return write_glb(os.path.join(outdir, "extras.glb"), g, b.bytes()), \
        {"meshes": 1, "faces": 1, "vertices": 3}


# --------------------------------------------------------------------------
def fx_normals(outdir):
    """Per-vertex NORMAL, which must set the imported mesh to smooth shading."""
    size, exp = simple("normals", outdir)
    with open(os.path.join(outdir, "normals.glb"), "rb") as f:
        d = f.read()
    off, chunks = 12, []
    while off + 8 <= len(d):
        ln, ty = struct.unpack("<II", d[off:off + 8])
        chunks.append((ty, d[off + 8:off + 8 + ln]))
        off += 8 + ln
    g = json.loads(chunks[0][1].decode("utf-8"))
    binary = bytearray(chunks[1][1])
    noff = len(binary)
    binary += b"".join(struct.pack("<3f", 0, 0, 1) for _ in range(3))
    g["bufferViews"].append(bv(noff, 36))
    g["accessors"].append(acc(len(g["bufferViews"]) - 1, 5126, 3, "VEC3"))
    g["meshes"][0]["primitives"][0]["attributes"]["NORMAL"] = len(g["accessors"]) - 1
    g["buffers"][0]["byteLength"] = len(binary)
    size = write_glb(os.path.join(outdir, "normals.glb"), g, bytes(binary))
    return size, exp


# --------------------------------------------------------------------------
def fx_truncated(outdir):
    """A GLB whose header claims more bytes than the file holds."""
    b = BinBuilder()
    po, pl = b.add(f3(TRI))
    io_, il = b.add(u16([0, 1, 2]))
    g = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "T", "mesh": 0}],
        "meshes": [{"name": "t", "primitives": [{"attributes": {"POSITION": 0},
                                                  "indices": 1}]}],
        "buffers": [{"byteLength": b.n}],
        "bufferViews": [bv(po, pl, 34962), bv(io_, il, 34963)],
        "accessors": [acc(0, 5126, 3, "VEC3", min=bounds(TRI)[0], max=bounds(TRI)[1]),
                      acc(1, 5123, 3, "SCALAR")],
    }
    p = os.path.join(outdir, "truncated.glb")
    total = write_glb(p, g, b.bytes())
    with open(p, "r+b") as f:
        f.seek(8)
        f.write(struct.pack("<I", total + 4096))
    return total, {"must_fail": True}


def fx_no_asset(outdir):
    """A .gltf with no `asset` block at all."""
    p = os.path.join(outdir, "no_asset.gltf")
    with open(p, "w") as f:
        json.dump({"scene": 0, "nodes": []}, f)
    return os.path.getsize(p), {"must_fail": True}


def fx_bad_json(outdir):
    """Not JSON at all."""
    p = os.path.join(outdir, "garbage.glb")
    with open(p, "wb") as f:
        f.write(b"this is definitely not a gltf file")
    return 30, {"must_fail": True}


# --------------------------------------------------------------------------
def fx_loose_parts(outdir):
    """One primitive holding two vertex-disjoint triangles: a loose-parts case."""
    a = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
    b2 = [(5, 0, 0), (6, 0, 0), (5, 1, 0)]
    verts = a + b2
    b = BinBuilder()
    po, pl = b.add(f3(verts))
    io_, il = b.add(u16([0, 1, 2, 3, 4, 5]))
    g = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "Loose", "mesh": 0}],
        "meshes": [{"name": "lp", "primitives": [{"attributes": {"POSITION": 0},
                                                  "indices": 1}]}],
        "buffers": [{"byteLength": b.n}],
        "bufferViews": [bv(po, pl, 34962), bv(io_, il, 34963)],
        "accessors": [acc(0, 5126, 6, "VEC3", min=bounds(verts)[0], max=bounds(verts)[1]),
                      acc(1, 5123, 6, "SCALAR")],
    }
    return write_glb(os.path.join(outdir, "loose_parts.glb"), g, b.bytes()), \
        {"meshes": 1, "faces": 2, "vertices": 6}


FIXTURES = [
    ("quantized", fx_quantized),
    ("interleaved", fx_interleaved),
    ("sparse", fx_sparse),
    ("modes", fx_modes),
    ("multiprim", fx_multiprim),
    ("matrix_negscale", fx_matrix_negscale),
    ("skinned", fx_skinned),
    ("embedded_gltf", fx_embedded_gltf),
    ("external_gltf", fx_external_gltf),
    ("hierarchy", fx_hierarchy),
    ("no_materials", fx_no_materials),
    ("extras", fx_extras),
    ("normals", fx_normals),
    ("loose_parts", fx_loose_parts),
    ("truncated", fx_truncated),
    ("no_asset", fx_no_asset),
    ("garbage", fx_bad_json),
]


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "fixtures"
    os.makedirs(outdir, exist_ok=True)
    expect = {}
    for name, fn in FIXTURES:
        _, exp = fn(outdir)
        expect[name] = exp
        print("wrote %-20s expect %s" % (name, exp))
    with open(os.path.join(outdir, "expected.json"), "w") as f:
        json.dump(expect, f, indent=2)
    print("\n%d fixtures in %s" % (len(FIXTURES), outdir))


if __name__ == "__main__":
    main()
