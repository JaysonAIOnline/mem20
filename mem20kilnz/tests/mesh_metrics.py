#!/usr/bin/env python3
"""Geometric quality metrics for a glTF/GLB mesh, read with the standard library.

Reports what a triangle count cannot: whether the mesh is watertight, whether any
coordinate went non-finite during processing, whether faces degenerated, and how
far signed volume and surface area drifted from a reference.

Usage:
    python3 mesh_metrics.py <file.glb> [reference.glb]
"""

import json
import math
import struct
import sys

COMP = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2),
        5125: ("I", 4), 5126: ("f", 4)}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def load(path):
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"glTF":
        g = json.loads(data.decode("utf-8"))
        bin_ = b""
        uri = g.get("buffers", [{}])[0].get("uri", "")
        if uri.startswith("data:"):
            import base64
            bin_ = base64.b64decode(uri.split(",", 1)[1])
        return g, bin_
    off, g, bin_ = 12, None, b""
    while off + 8 <= len(data):
        ln, ty = struct.unpack("<II", data[off:off + 8])
        body = data[off + 8:off + 8 + ln]
        if ty == 0x4E4F534A and g is None:
            g = json.loads(body.decode("utf-8"))
        elif ty == 0x004E4942 and not bin_:
            bin_ = body
        off += 8 + ln
    if g is None:
        raise ValueError("no JSON chunk")
    return g, bin_


def read_accessor(g, bin_, idx):
    a = g["accessors"][idx]
    fmt, size = COMP[a["componentType"]]
    comps = NCOMP[a["type"]]
    if "bufferView" not in a:
        return [0.0] * (a["count"] * comps)
    bv = g["bufferViews"][a["bufferView"]]
    base = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = bv.get("byteStride") or size * comps
    out = []
    for i in range(a["count"]):
        p = base + i * stride
        out.extend(struct.unpack_from("<" + fmt * comps, bin_, p))
    return out


def triangles(path):
    g, bin_ = load(path)
    verts, tris = [], []
    for m in g.get("meshes", []):
        for pr in m.get("primitives", []):
            if pr.get("mode", 4) != 4:
                continue
            pos = read_accessor(g, bin_, pr["attributes"]["POSITION"])
            nv = len(pos) // 3
            base = len(verts)
            for i in range(nv):
                verts.append((pos[i * 3], pos[i * 3 + 1], pos[i * 3 + 2]))
            idx = read_accessor(g, bin_, pr["indices"]) if "indices" in pr \
                else list(range(nv))
            for i in range(0, len(idx) - 2, 3):
                tris.append((base + int(idx[i]), base + int(idx[i + 1]),
                             base + int(idx[i + 2])))
    return verts, tris


def metrics(path):
    v, t = triangles(path)
    m = {}
    m["vertices"] = len(v)
    m["triangles"] = len(t)
    m["non_finite_verts"] = sum(1 for p in v
                                for c in p if not math.isfinite(c))
    m["degenerate_tris"] = sum(1 for a, b, c in t if a == b or b == c or a == c)
    m["out_of_range_tris"] = sum(1 for a, b, c in t
                                 if max(a, b, c) >= len(v) or min(a, b, c) < 0)

    edges = {}
    area = 0.0
    vol = 0.0
    for a, b, c in t:
        if max(a, b, c) >= len(v):
            continue
        pa, pb, pc = v[a], v[b], v[c]
        u = (pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2])
        w = (pc[0] - pa[0], pc[1] - pa[1], pc[2] - pa[2])
        n = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2],
             u[0] * w[1] - u[1] * w[0])
        ln = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2)
        area += 0.5 * ln
        vol += (pa[0] * (pb[1] * pc[2] - pb[2] * pc[1])
                - pa[1] * (pb[0] * pc[2] - pb[2] * pc[0])
                + pa[2] * (pb[0] * pc[1] - pb[1] * pc[0])) / 6.0
        for e in ((a, b), (b, c), (c, a)):
            k = (min(e), max(e))
            edges[k] = edges.get(k, 0) + 1
    m["surface_area"] = area
    m["signed_volume"] = vol
    m["boundary_edges"] = sum(1 for c in edges.values() if c == 1)
    m["nonmanifold_edges"] = sum(1 for c in edges.values() if c > 2)
    m["watertight"] = m["boundary_edges"] == 0 and m["nonmanifold_edges"] == 0
    if v:
        m["bbox"] = [min(p[i] for p in v) for i in range(3)] + \
                    [max(p[i] for p in v) for i in range(3)]
    return m


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    m = metrics(sys.argv[1])
    ref = metrics(sys.argv[2]) if len(sys.argv) > 2 else None
    keys = ["vertices", "triangles", "non_finite_verts", "degenerate_tris",
            "out_of_range_tris", "boundary_edges", "nonmanifold_edges", "watertight",
            "surface_area", "signed_volume"]
    for k in keys:
        val = m[k]
        extra = ""
        if ref and k in ref and isinstance(val, float) and ref[k]:
            d = (val - ref[k]) / abs(ref[k]) * 100.0
            extra = "   (%+.2f%% vs reference)" % d
        print("%-18s %s%s" % (k, val, extra))
    if "bbox" in m:
        print("%-18s %s" % ("bbox", ["%.4f" % c for c in m["bbox"]]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
