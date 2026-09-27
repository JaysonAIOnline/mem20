"""Describe a 3D model in plain English, from the exported file.

This exists so an agent that cannot see can still do text-to-3D. It reads the
GLB that was actually written, not the in-memory scene, so the description can
never disagree with the deliverable — the same principle the gate follows.

Everything here is measured. Dimensions come from vertex positions, not from a
requested size; relative size is a real ratio; spatial relations come from
bounding boxes. Where something genuinely cannot be computed from the file, it
says so instead of estimating. Colour names are derived from hue, saturation
and lightness, so "brown" is a computed statement about the numbers rather than
a guess from a lookup table.

What an agent gets, and why each part earns its place:

* parts, and what kind of thing each one is
* true dimensions, in the model's own units
* each part's size relative to the largest, because "is the lid the right size"
  is a comparison, not a number
* where each part sits, in words: above, below, inside, attached to
* the hierarchy, so a part can be traced to what it belongs to
* materials with colour names, plus roughness and metalness in plain terms
* overall proportions, so "is this a long thin thing or a cube" is answerable
"""

from __future__ import annotations

import colorsys
import json
from dataclasses import dataclass, field
from pathlib import Path

from .validate import _Doc, _load

#: Below this, a size difference is not worth mentioning in prose.
EPS = 1e-6

#: A part is "inside" another when its bounds fit within this fraction of the
#: container's bounds, allowing for the small overshoot a rotated child produces.
CONTAINMENT_SLACK = 1.02


# --------------------------------------------------------------------------
# colour
# --------------------------------------------------------------------------

#: Hue sectors in degrees, as (name, low, high). Derived from the standard
#: colour wheel rather than fitted to the handful of colours this project uses.
HUE_SECTORS: tuple[tuple[str, float, float], ...] = (
    ("red", 345, 360), ("red", 0, 15),
    ("orange", 15, 45),
    ("yellow", 45, 70),
    ("lime", 70, 100),
    ("green", 100, 150),
    ("teal", 150, 180),
    ("cyan", 180, 200),
    ("blue", 200, 250),
    ("indigo", 250, 275),
    ("violet", 275, 300),
    ("magenta", 300, 345),
)


def _hue_name(hue_deg: float) -> str:
    for name, low, high in HUE_SECTORS:
        if low <= hue_deg < high:
            return name
    return "grey"


def colour_name(rgb: tuple[float, float, float]) -> str:
    """A plain-English colour for linear-ish RGB.

    Grey is decided first: a near-equal triple has no meaningful hue, and calling
    a desaturated blue "blue" would mislead an agent choosing a replacement.
    """
    r, g, b = (max(0.0, min(1.0, float(c))) for c in rgb)
    h, lum, sat = colorsys.rgb_to_hls(r, g, b)
    hue = h * 360.0
    if sat < 0.08:
        if lum < 0.12:
            return "black"
        if lum > 0.92:
            return "white"
        if lum < 0.35:
            return "dark grey"
        if lum > 0.7:
            return "light grey"
        return "grey"
    base = _hue_name(hue)
    # Brown is not a hue of its own: it is a desaturated, not-bright orange-to-
    # yellow. Test the hue range directly, because the sector name at 24-40
    # degrees is "orange", not "red", and guarding on the name missed wood.
    if 15 <= hue < 48 and sat < 0.68 and lum < 0.62:
        base = "brown"
    if lum < 0.22:
        return f"very dark {base}"
    if lum < 0.4:
        return f"dark {base}"
    if lum > 0.82:
        return f"pale {base}"
    if lum > 0.66:
        return f"light {base}"
    return base


def finish_name(roughness: float, metallic: float) -> str:
    """How a surface behaves, in words rather than as two floats."""
    bits: list[str] = []
    if metallic >= 0.75:
        bits.append("fully metallic")
    elif metallic >= 0.3:
        bits.append("partly metallic")
    if roughness <= 0.2:
        bits.append("mirror-smooth")
    elif roughness <= 0.45:
        bits.append("satin")
    elif roughness <= 0.75:
        bits.append("matte")
    else:
        bits.append("very rough")
    return ", ".join(bits) if bits else "standard finish"


# --------------------------------------------------------------------------
# measurement
# --------------------------------------------------------------------------


@dataclass
class Box:
    """An axis-aligned bounding box."""

    min: tuple[float, float, float] = (0.0, 0.0, 0.0)
    max: tuple[float, float, float] = (0.0, 0.0, 0.0)

    @property
    def size(self) -> tuple[float, float, float]:
        return (self.max[0] - self.min[0], self.max[1] - self.min[1],
                self.max[2] - self.min[2])

    @property
    def centre(self) -> tuple[float, float, float]:
        return tuple((self.min[i] + self.max[i]) / 2.0 for i in range(3))  # type: ignore[return-value]

    @property
    def volume(self) -> float:
        sx, sy, sz = self.size
        return max(0.0, sx) * max(0.0, sy) * max(0.0, sz)

    def contains(self, other: Box, slack: float = CONTAINMENT_SLACK) -> bool:
        return all(
            self.min[i] - EPS <= other.min[i] and other.max[i] <= self.max[i] + EPS * slack
            for i in range(3)
        )

    def union(self, other: Box) -> Box:
        return Box(
            tuple(min(self.min[i], other.min[i]) for i in range(3)),  # type: ignore[arg-type]
            tuple(max(self.max[i], other.max[i]) for i in range(3)),  # type: ignore[arg-type]
        )


def _fmt(value: float) -> str:
    """Round for prose without lying about precision."""
    if abs(value) < 1e-9:
        return "0"
    if abs(value) >= 100:
        return f"{value:.0f}"
    if abs(value) >= 10:
        return f"{value:.1f}"
    return f"{value:.2f}"


@dataclass
class Part:
    """One node, measured."""

    name: str
    kind: str
    box: Box
    triangles: int = 0
    vertices: int = 0
    material: str = ""
    colour: str = ""
    roughness: float = 0.0
    metallic: float = 0.0
    parent: str = ""
    translation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    children: list[str] = field(default_factory=list)
    measured: bool = True
    note: str = ""

    @property
    def size(self) -> tuple[float, float, float]:
        return self.box.size

    @property
    def volume(self) -> float:
        return self.box.volume


@dataclass
class Description:
    """Everything measured about a model, plus the prose rendering."""

    path: str
    ok: bool = True
    reason: str = ""
    parts: list[Part] = field(default_factory=list)
    total_triangles: int = 0
    total_vertices: int = 0
    overall: Box = field(default_factory=Box)
    sentences: list[str] = field(default_factory=list)
    not_computable: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "ok": self.ok,
            "reason": self.reason,
            "summary": self.text(),
            "sentences": self.sentences,
            "total_triangles": self.total_triangles,
            "total_vertices": self.total_vertices,
            "overall_size": [_fmt(v) for v in self.overall.size],
            "not_computable": self.not_computable,
            "parts": [
                {
                    "name": p.name,
                    "kind": p.kind,
                    "size": [_fmt(v) for v in p.size],
                    "centre": [_fmt(v) for v in p.box.centre],
                    "relative_size": p.note or "",
                    "triangles": p.triangles,
                    "vertices": p.vertices,
                    "material": p.material,
                    "colour": p.colour,
                    "finish": finish_name(p.roughness, p.metallic),
                    "parent": p.parent,
                    "children": p.children,
                    "measured": p.measured,
                }
                for p in self.parts
            ],
        }

    def text(self) -> str:
        """The whole description as one block of plain English."""
        return " ".join(self.sentences)



# --------------------------------------------------------------------------
# transforms
# --------------------------------------------------------------------------

#: A world transform as a row-major 4x4 matrix.
#:
#: Deliberately not collapsed back into a translation/quaternion/scale triple.
#: A glTF node is T*R*S, and composing two of them gives T*R*S*T*R*S, where the
#: inner translation has nowhere to go in a single TRS. Doing the arithmetic by
#: hand for a parent at x=1 scaled 2x with a child offset 0.5, the point at
#: child-local 0.5 is at world x=2.0; the TRS collapse reports 3.0. Since this is
#: the backbone of every measurement reported, it is a matrix.
Matrix4 = tuple  # 16 floats, row-major

IDENTITY4: Matrix4 = (
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)


def mat_mul(a: Matrix4, b: Matrix4) -> Matrix4:
    out = [0.0] * 16
    for r in range(4):
        for c in range(4):
            out[r * 4 + c] = sum(a[r * 4 + k] * b[k * 4 + c] for k in range(4))
    return tuple(out)


def mat_apply_point(m: Matrix4, p) -> tuple[float, float, float]:
    x, y, z = p
    return (
        m[0] * x + m[1] * y + m[2] * z + m[3],
        m[4] * x + m[5] * y + m[6] * z + m[7],
        m[8] * x + m[9] * y + m[10] * z + m[11],
    )


def mat_translate(t) -> Matrix4:
    return (1.0, 0.0, 0.0, t[0],
            0.0, 1.0, 0.0, t[1],
            0.0, 0.0, 1.0, t[2],
            0.0, 0.0, 0.0, 1.0)


def mat_scale(s) -> Matrix4:
    return (s[0], 0.0, 0.0, 0.0,
            0.0, s[1], 0.0, 0.0,
            0.0, 0.0, s[2], 0.0,
            0.0, 0.0, 0.0, 1.0)


def mat_quat(q) -> Matrix4:
    """Column-major quaternion to a rotation matrix, per the glTF spec."""
    x, y, z, w = q
    return (
        1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), 0.0,
        2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), 0.0,
        2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), 0.0,
        0.0, 0.0, 0.0, 1.0,
    )


def _node_matrix(node: dict) -> Matrix4:
    def triple(v, default):
        try:
            return (float(v[0]), float(v[1]), float(v[2]))
        except (TypeError, ValueError, IndexError):
            return default

    t = node.get("translation") or [0.0, 0.0, 0.0]
    s = node.get("scale") or [1.0, 1.0, 1.0]
    q = node.get("rotation") or [0.0, 0.0, 0.0, 1.0]
    rot = (0.0, 0.0, 0.0, 1.0)
    try:
        rot = (float(q[0]), float(q[1]), float(q[2]), float(q[3]))
    except (TypeError, ValueError, IndexError):
        pass
    m = mat_translate(triple(t, (0.0, 0.0, 0.0)))
    m = mat_mul(m, mat_quat(rot))
    return mat_mul(m, mat_scale(triple(s, (1.0, 1.0, 1.0))))


def _world_box(local: Box, m: Matrix4) -> Box:
    """World bounds of a local box: transform all eight corners and re-fit."""
    if local.volume == 0.0 and local.min == local.max == (0.0, 0.0, 0.0):
        return local
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    for cx in (local.min[0], local.max[0]):
        for cy in (local.min[1], local.max[1]):
            for cz in (local.min[2], local.max[2]):
                wx, wy, wz = mat_apply_point(m, (cx, cy, cz))
                xs.append(wx)
                ys.append(wy)
                zs.append(wz)
    return Box((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))


def _mesh_material(doc: _Doc, mesh_index: int) -> int | None:
    """The material index, read from the mesh primitive.

    The exporter writes it there, not on the node, so reading `node.material`
    silently yields nothing and every part comes out colourless.
    """
    try:
        prims = doc.g["meshes"][mesh_index].get("primitives", [])
    except (KeyError, IndexError, TypeError):
        return None
    for prim in prims or []:
        if isinstance(prim, dict) and isinstance(prim.get("material"), int):
            return prim["material"]
    return None


# --------------------------------------------------------------------------
# glTF reading
# --------------------------------------------------------------------------


def _mesh_box(doc: _Doc, mesh_index: int) -> tuple[Box, int, bool]:
    """Bounding box, triangle count, and whether it was actually measurable."""
    try:
        mesh = doc.g["meshes"][mesh_index]
    except (KeyError, IndexError):
        return Box(), 0, False
    for prim in mesh.get("primitives", []):
        if "POSITION" not in (prim.get("attributes") or {}):
            continue
        try:
            acc_index = prim["attributes"]["POSITION"]
        except (KeyError, TypeError):
            continue
        values, comps = doc.accessor(acc_index)
        if not values or comps != 3 or values is None:
            continue
        xs = values[0::3]
        ys = values[1::3]
        zs = values[2::3]
        if not xs:
            continue
        count = 0
        if "indices" in prim:
            idx, ic = doc.accessor(prim["indices"])
            if idx and ic == 1:
                count = len(idx) // 3
        else:
            count = len(xs) // 3
        return (
            Box((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))),
            count,
            True,
        )
    return Box(), 0, False


def _node_translation(node: dict) -> tuple[float, float, float]:
    t = node.get("translation") or [0.0, 0.0, 0.0]
    try:
        return (float(t[0]), float(t[1]), float(t[2]))
    except (TypeError, ValueError, IndexError):
        return (0.0, 0.0, 0.0)


def _materials(doc: _Doc) -> dict[int, tuple[str, str, float, float]]:
    out: dict[int, tuple[str, str, float, float]] = {}
    for i, mat in enumerate(doc.g.get("materials", []) or []):
        pbr = mat.get("pbrMetallicRoughness", {}) or {}
        factor = pbr.get("baseColorFactor", [1.0, 1.0, 1.0, 1.0])
        try:
            rgb = (float(factor[0]), float(factor[1]), float(factor[2]))
        except (TypeError, ValueError, IndexError):
            rgb = (1.0, 1.0, 1.0)
        rough = pbr.get("roughnessFactor", 1.0)
        metal = pbr.get("metallicFactor", 1.0)
        out[i] = (
            str(mat.get("name") or f"material_{i}"),
            colour_name(rgb),
            float(rough) if isinstance(rough, (int, float)) else 1.0,
            float(metal) if isinstance(metal, (int, float)) else 1.0,
        )
    return out


def _node_names(doc: _Doc) -> list[str]:
    return [str(n.get("name") or f"node_{i}")
            for i, n in enumerate(doc.g.get("nodes", []) or [])]


# --------------------------------------------------------------------------
# relations
# --------------------------------------------------------------------------


def _vertical_relation(a: Part, b: Part) -> str:
    """How `a` sits relative to `b` on the vertical axis, in words."""
    a_top, b_top = a.box.max[2], b.box.max[2]
    a_bot, b_bot = a.box.min[2], b.box.min[2]
    tall = max(a.size[2], b.size[2], EPS)
    if a_bot >= b_top - EPS:
        return "entirely above"
    if a_top <= b_bot + EPS:
        return "entirely below"
    if a.centre[2] > b.centre[2] + tall * 0.2:
        return "mostly above"
    if a.centre[2] < b.centre[2] - tall * 0.2:
        return "mostly below"
    return "at the same height as"


def _relative_size(a: Part, largest: Part) -> str:
    """How big a part is, against the largest one.

    Two independent facts, because either alone misleads. Width against the
    largest part says whether a part is a real component or an afterthought. But
    thinness has to be judged against the part's *own* smallest side: a band is
    wider than the chest it wraps, so a width ratio alone reports "105%" and
    loses the one thing an agent most wants to know, which is that it is a
    thin strip. Volume is not used for either judgement, because a small cube
    has a tiny volume share while being a visible part.
    """
    if a is largest:
        return "the largest part"

    mine, big = max(a.size), max(largest.size)
    thin = min(a.size)
    flat_ratio = (thin / mine) if mine > EPS else 0.0

    if big <= EPS:
        return "size not comparable: the largest part has no measurable extent"

    width = mine / big
    if flat_ratio < 0.2:
        kind = "a very thin sheet or sliver"
    elif flat_ratio < 0.4:
        kind = "a thin strip or panel"
    elif width < 0.2:
        kind = "a small protruding part"
    elif width < 0.4:
        kind = "a secondary part"
    else:
        kind = "a main part"

    detail = (f"{width:.2f} times the width of {largest.name}" if width < 1.0
              else f"wider than {largest.name}")
    if flat_ratio < 0.4:
        detail += f", and {flat_ratio * 100:.0f}% as thick as it is wide"
    return f"{kind}, {detail}"


def _describe_part(part: Part, parts: list[Part], largest: Part) -> str:
    sx, sy, sz = part.size
    bits = [
        f"{part.name} is a {part.kind} measuring {_fmt(sx)} by {_fmt(sy)} by "
        f"{_fmt(sz)} "
    ]
    bits.append(f"({_relative_size(part, largest)})")
    if part.material:
        bits.append(f", coloured {part.colour}")
        bits.append(f", with a {finish_name(part.roughness, part.metallic)} surface")
    if part.parent:
        bits.append(f", attached to {part.parent}")
    for other in parts:
        if other is part or other.name == part.name:
            continue
        if part.box.contains(other.box):
            bits.append(f", enclosing {other.name}")
            break
        if other.box.contains(part.box):
            bits.append(f", sitting inside {other.name}")
            break
    return "".join(bits)


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def describe(path: str | Path) -> Description:
    """Measure a GLB and describe it in plain English."""
    p = Path(path)
    out = Description(path=str(p), ok=False)
    if not p.is_file():
        out.reason = f"no file at {p}"
        out.not_computable.append("the file does not exist")
        return out

    from .validate import Report

    report = Report(path=str(p))
    doc = _load(p, report)
    if doc is None:
        out.reason = "; ".join(f.message for f in report.errors) or "unreadable glTF"
        out.not_computable.append("the file could not be parsed as glTF")
        return out

    names = _node_names(doc)
    mats = _materials(doc)

    # Which node is the parent of which, so a part can be traced to its owner.
    parent_of: dict[int, str] = {}
    children_of: dict[int, list[str]] = {}
    for i, node in enumerate(doc.g.get("nodes", []) or []):
        for child in node.get("children", []) or []:
            if isinstance(child, int) and 0 <= child < len(names):
                parent_of[child] = names[i]
                children_of.setdefault(i, []).append(names[child])

    # World transforms, so a child is measured where it actually sits rather
    # than in its own local space. Without this, "is this part the right size
    # and in the right place" is answered wrongly.
    nodes = doc.g.get("nodes", []) or []
    local_matrix = [_node_matrix(n) for n in nodes]
    world_matrix: list[Matrix4] = [IDENTITY4 for _ in nodes]

    def resolve(i: int, seen: frozenset[int] = frozenset()) -> Matrix4:
        if i in seen or not (0 <= i < len(nodes)):
            return IDENTITY4
        parent = -1
        for pi, pn in enumerate(nodes):
            if i in (pn.get("children") or []):
                parent = pi
                break
        if parent < 0:
            world_matrix[i] = local_matrix[i]
        else:
            world_matrix[i] = mat_mul(resolve(parent, seen | {i}), local_matrix[i])
        return world_matrix[i]

    for i in range(len(nodes)):
        resolve(i)

    parts: list[Part] = []
    unmeasured = 0
    for i, node in enumerate(nodes):
        mesh_index = node.get("mesh")
        name = names[i]
        if not isinstance(mesh_index, int):
            continue
        local, tris, measured = _mesh_box(doc, mesh_index)
        box = _world_box(local, world_matrix[i]) if measured else local
        if not measured:
            unmeasured += 1
        mat_name, colour, rough, metal = ("", "", 0.0, 0.0)
        mat_index = _mesh_material(doc, mesh_index)
        if mat_index is not None:
            mat_name, colour, rough, metal = mats.get(mat_index, ("", "", 0.0, 0.0))
        verts = 0
        try:
            prims = doc.g["meshes"][mesh_index].get("primitives", [])
            if prims and "POSITION" in (prims[0].get("attributes") or {}):
                values, _ = doc.accessor(prims[0]["attributes"]["POSITION"])
                verts = len(values) // 3 if values else 0
        except (KeyError, IndexError, TypeError):
            verts = 0
        parts.append(
            Part(
                name=name,
                kind="mesh",
                box=box,
                triangles=tris,
                vertices=verts,
                material=mat_name,
                colour=colour,
                roughness=rough,
                metallic=metal,
                parent=parent_of.get(i, ""),
                translation=box.centre,
                children=children_of.get(i, []),
                measured=measured,
                note="" if measured else "dimensions not computable: no POSITION accessor",
            )
        )

    if not parts:
        out.reason = "the file contains no mesh nodes"
        out.not_computable.append("there is nothing measurable in the scene")
        return out

    out.ok = True
    out.parts = parts
    out.total_triangles = sum(p.triangles for p in parts)
    out.total_vertices = sum(p.vertices for p in parts)

    overall = parts[0].box
    for p in parts[1:]:
        overall = overall.union(p.box)
    out.overall = overall

    measurable = [p for p in parts if p.measured]
    largest = max(measurable, key=lambda p: p.volume) if measurable else parts[0]

    # ---- prose ----
    s = out.sentences
    s.append(
        f"This model has {len(parts)} "
        + ("part" if len(parts) == 1 else "parts")
        + f" and {out.total_triangles} triangles in total."
    )
    ox, oy, oz = overall.size
    s.append(
        f"Taken together it measures {_fmt(ox)} by {_fmt(oy)} by {_fmt(oz)} units."
    )
    longest = max(ox, oy, oz, EPS)
    shortest = min(ox, oy, oz)
    if shortest <= EPS:
        s.append("It is completely flat: it has no thickness in one direction.")
    elif longest / shortest >= 4.0:
        s.append(
            f"It is a long, thin shape: its longest side is "
            f"{longest / shortest:.0f} times its shortest."
        )
    elif longest / shortest <= 1.4:
        s.append("It is close to a cube in proportion, with all sides similar in length.")
    else:
        s.append("It is an oblong shape, wider or longer than it is deep.")

    for p in parts:
        line = _describe_part(p, parts, largest)
        s.append(line[:-1] if line.endswith("..") else line)
        s[-1] = s[-1].rstrip(".") + "."

    if unmeasured:
        out.not_computable.append(
            f"{unmeasured} node(s) had no measurable geometry, so their "
            "dimensions are not reported"
        )
    # Honest about the limit of reading geometry: this cannot tell an agent
    # whether the shape reads as the thing it was asked to be.
    out.not_computable.append(
        "shape likeness to the brief cannot be determined from geometry alone; "
        "this describes measurements, not whether the object looks like its subject"
    )
    return out


def describe_json(path: str | Path) -> str:
    """The description as JSON, for an agent that wants the numbers not the prose."""
    return json.dumps(describe(path).as_dict(), indent=2, sort_keys=True)
