"""Structural validation for glTF/GLB, and the budget gate that sits on top.

The container and JSON checks here are the ones an engine import has to survive
before an asset is worth publishing: a declared length that disagrees with the
file, an accessor that reads past its buffer, indices that point at vertices that
do not exist, missing normals, degenerate triangles, non-finite coordinates.

Read-only by construction: this module never rewrites the file it inspects. That
is deliberate. Detection must not mutate what the user authored, so redaction and
repair are the caller's decision, not a side effect of looking.

Standard library only, so it works with no third-party dependency installed.
"""
from __future__ import annotations

import base64
import json
import math
import struct
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import budgets as _budgets

CHUNK_JSON = 0x4E4F534A
CHUNK_BIN = 0x004E4942
COMPONENT_SIZE = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
COMPONENT_FMT = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
TYPE_COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}
MODE_NAMES = {0: "POINTS", 1: "LINES", 2: "LINE_LOOP", 3: "LINE_STRIP",
              4: "TRIANGLES", 5: "TRIANGLE_STRIP", 6: "TRIANGLE_FAN"}


@dataclass
class Finding:
    severity: str  # "error" or "warning"
    code: str
    message: str
    where: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class MeshReport:
    name: str
    vertices: int = 0
    triangles: int = 0
    has_normals: bool = False
    has_uvs: bool = False
    material: int | None = None
    non_finite: int = 0
    degenerate: int = 0
    out_of_range: int = 0


@dataclass
class Report:
    path: str
    ok: bool = True
    version: str = ""
    generator: str = ""
    declared_bytes: int = 0
    actual_bytes: int = 0
    nodes: int = 0
    meshes: list[MeshReport] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    @property
    def gate_ok(self) -> bool:
        """True only when nothing errored, including findings added later.

        `ok` is the structural verdict fixed during validation. `check_budgets`
        appends findings afterwards, so a budget error would otherwise be
        invisible to any caller reading `ok`.
        """
        return self.ok and not self.errors

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warning"]

    @property
    def total_triangles(self) -> int:
        return sum(m.triangles for m in self.meshes)

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "ok": self.ok,
            "gate_ok": self.gate_ok,
            "version": self.version,
            "generator": self.generator,
            "declared_bytes": self.declared_bytes,
            "actual_bytes": self.actual_bytes,
            "nodes": self.nodes,
            "total_triangles": self.total_triangles,
            "meshes": [asdict(m) for m in self.meshes],
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "findings": [f.as_dict() for f in self.findings],
        }


class _Doc:
    def __init__(self, gltf: dict, binary: bytes):
        self.g = gltf
        self.bin = binary

    def accessor(self, index: int):
        a = self.g["accessors"][index]
        fmt = COMPONENT_FMT.get(a["componentType"])
        csize = COMPONENT_SIZE.get(a["componentType"])
        comps = TYPE_COMPONENTS.get(a.get("type", "SCALAR"), 0)
        if csize is None or comps == 0:
            return [], 0
        elem = csize * comps
        if "bufferView" not in a:
            return [0.0] * (a["count"] * comps), comps
        bv = self.g["bufferViews"][a["bufferView"]]
        if bv.get("buffer", 0) != 0:
            return None, comps
        base = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = bv.get("byteStride") or elem
        need = (a["count"] - 1) * stride + elem if a["count"] else 0
        if base + need > len(self.bin):
            return None, comps
        out: list[float] = []
        for i in range(a["count"]):
            off = base + i * stride
            out.extend(struct.unpack_from("<" + fmt * comps, self.bin, off))
        return out, comps


def _load(path: Path, report: Report) -> _Doc | None:
    raw = path.read_bytes()
    report.actual_bytes = len(raw)
    if len(raw) >= 12 and raw[:4] == b"glTF":
        version, declared = struct.unpack("<II", raw[4:12])
        report.declared_bytes = declared
        if version != 2:
            report.findings.append(
                Finding("error", "bad_glb_version", f"glb version {version}, expected 2")
            )
            report.ok = False
            return None
        if declared > len(raw):
            report.findings.append(
                Finding(
                    "error",
                    "length_mismatch",
                    f"header declares {declared} bytes but the file is {len(raw)}",
                )
            )
            report.ok = False
            return None
        off, gltf, binary = 12, None, b""
        while off + 8 <= len(raw):
            clen, ctype = struct.unpack("<II", raw[off:off + 8])
            body = off + 8
            if body + clen > len(raw):
                report.findings.append(
                    Finding("error", "chunk_overrun", f"chunk at offset {off} overruns the file")
                )
                report.ok = False
                return None
            if ctype == CHUNK_JSON and gltf is None:
                gltf = json.loads(raw[body:body + clen].decode("utf-8"))
            elif ctype == CHUNK_BIN and not binary:
                binary = raw[body:body + clen]
            off = body + clen + ((4 - clen % 4) % 4)
        if gltf is None:
            report.findings.append(Finding("error", "no_json_chunk", "glb has no JSON chunk"))
            report.ok = False
            return None
    else:
        try:
            gltf = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            report.findings.append(Finding("error", "bad_json", f"not valid JSON: {exc}"))
            report.ok = False
            return None
        binary = b""
        bufs = gltf.get("buffers") or []
        if bufs and isinstance(bufs[0], dict):
            uri = bufs[0].get("uri", "")
            if uri.startswith("data:"):
                try:
                    binary = base64.b64decode(uri.split(",", 1)[1])
                except (ValueError, IndexError):
                    report.findings.append(
                        Finding("error", "bad_data_uri", "buffer data URI could not be decoded")
                    )
                    report.ok = False
            elif uri:
                ext = path.parent / uri
                if ext.is_file():
                    binary = ext.read_bytes()
                else:
                    report.findings.append(
                        Finding("warning", "missing_external_buffer", f"no {ext} on disk")
                    )
    asset = gltf.get("asset") or {}
    report.version = str(asset.get("version", ""))
    report.generator = str(asset.get("generator", ""))
    if not report.version.startswith("2."):
        report.findings.append(
            Finding("error", "bad_asset_version", f"asset.version is '{report.version}'")
        )
        report.ok = False
    return _Doc(gltf, binary)


def validate(path: str | Path) -> Report:
    """Validate a glTF/GLB. Read-only: the file is never modified."""
    p = Path(path)
    report = Report(path=str(p))
    if not p.is_file():
        report.findings.append(Finding("error", "not_found", f"no such file: {p}"))
        report.ok = False
        return report
    doc = _load(p, report)
    if doc is None:
        return report
    g = doc.g
    report.nodes = len(g.get("nodes") or [])

    meshes = g.get("meshes") or []
    for mi, mesh in enumerate(meshes):
        name = str(mesh.get("name") or f"mesh_{mi}")
        mr = MeshReport(name=name)
        for pi, prim in enumerate(mesh.get("primitives") or []):
            mode = prim.get("mode", 4)
            where = f"{name}[{pi}]"
            if mode not in MODE_NAMES:
                report.findings.append(
                    Finding("error", "bad_mode", f"unknown primitive mode {mode}", where)
                )
                report.ok = False
                continue
            if mode in (0, 1, 2, 3):
                report.findings.append(
                    Finding(
                        "warning", "non_triangle_mode",
                        f"mode is {MODE_NAMES[mode]}, which renders no triangles", where,
                    )
                )
                continue
            attrs = prim.get("attributes") or {}
            if "POSITION" not in attrs:
                report.findings.append(
                    Finding("error", "no_position", "primitive has no POSITION attribute", where)
                )
                report.ok = False
                continue
            pos, comps = doc.accessor(attrs["POSITION"])
            if pos is None:
                report.findings.append(
                    Finding("error", "position_unreadable", "POSITION accessor overruns its buffer",
                           where)
                )
                report.ok = False
                continue
            mr.vertices = len(pos) // max(comps, 1)
            mr.non_finite = sum(1 for c in pos if not math.isfinite(c))
            if mr.non_finite:
                report.findings.append(
                    Finding("error", "non_finite",
                            f"{mr.non_finite} non-finite coordinate value(s)", where)
                )
                report.ok = False
            mr.has_normals = "NORMAL" in attrs
            mr.has_uvs = "TEXCOORD_0" in attrs
            if not mr.has_normals:
                report.findings.append(
                    Finding("warning", "no_normals",
                            "no NORMAL attribute; shading will be flat or engine-derived", where)
                )
            if "indices" in prim:
                idx, _ = doc.accessor(prim["indices"])
                if idx is None:
                    report.findings.append(
                        Finding("error", "indices_unreadable", "index accessor overruns its buffer",
                               where)
                    )
                    report.ok = False
                    continue
                count = len(idx)
            else:
                count = mr.vertices
                report.findings.append(
                    Finding("warning", "no_indices",
                            "primitive is non-indexed; the engine import will triangulate it",
                            where)
                )
            if mode == 4:
                mr.triangles += count // 3
                for i in range(0, count - 2, 3):
                    a, b, c = int(idx[i]), int(idx[i + 1]), int(idx[i + 2])
                    if max(a, b, c) >= mr.vertices or min(a, b, c) < 0:
                        mr.out_of_range += 1
                    elif a == b or b == c or a == c:
                        mr.degenerate += 1
            elif mode in (5, 6):
                mr.triangles += max(0, count - 2)
            if prim.get("material") is not None:
                mats = g.get("materials") or []
                if not 0 <= prim["material"] < len(mats):
                    report.findings.append(
                        Finding("error", "bad_material_index",
                                f"material {prim['material']} is out of range", where)
                    )
                    report.ok = False
                else:
                    mr.material = prim["material"]
        if mr.degenerate:
            report.findings.append(
                Finding("error", "degenerate", f"{mr.degenerate} triangle(s) repeat a vertex", name)
            )
            report.ok = False
        if mr.out_of_range:
            report.findings.append(
                Finding("error", "index_out_of_range",
                        f"{mr.out_of_range} triangle(s) index a vertex that does not exist", name)
            )
            report.ok = False
        report.meshes.append(mr)

    if not report.meshes:
        report.findings.append(Finding("warning", "no_meshes", "file contains no triangle meshes"))
    return report


def check_budgets(report: Report, family: str | None = None, require_prefix: bool = False,
                  lod: int = 0, tier: str = "standard") -> list[Finding]:
    """Budget and naming findings, derived from the validated report."""
    out: list[Finding] = []
    fam = family or _budgets.infer_family(Path(report.path).stem)
    verdict = _budgets.check_triangles(fam, report.total_triangles, lod, tier=tier)
    if not verdict.ok:
        out.append(Finding("error", "budget", verdict.reason, fam))
    for mr in report.meshes:
        ok, why = _budgets.check_name(mr.name)
        if not ok and require_prefix:
            out.append(Finding("error", "naming", why, mr.name))
        elif not ok:
            out.append(Finding("warning", "naming", why, mr.name))
    return out


def gate(path: str | Path, family: str | None = None, require_prefix: bool = False,
         lod: int = 0, tier: str = "standard") -> Report:
    """Validate, then apply budgets. Non-zero-worthy findings are errors."""
    report = validate(path)
    for f in check_budgets(report, family, require_prefix, lod, tier):
        report.findings.append(f)
        if f.severity == "error":
            report.ok = False
    return report
