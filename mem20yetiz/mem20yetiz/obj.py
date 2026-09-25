"""Hermetic Wavefront OBJ rig and motion export with a strict reader."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from .animation import AnimationClip
from .rig import Rig


def _bone_order(rig: Rig) -> List[str]:
    bones = rig.skeleton.bones
    root = rig.skeleton.root_bone or next(iter(bones), None)
    if root is None:
        return []
    order: List[str] = []
    queue = [root]
    while queue:
        name = queue.pop(0)
        if name in order:
            raise ValueError(f"rig hierarchy contains a cycle at {name!r}")
        if name not in bones:
            raise ValueError(f"rig child {name!r} is not declared")
        order.append(name)
        queue.extend(bones[name].children)
    if len(order) != len(bones):
        raise ValueError("rig hierarchy is disconnected")
    return order


def _positions_from_rig(rig: Rig, clip: Optional[AnimationClip]) -> Dict[str, np.ndarray]:
    order = _bone_order(rig)
    if not order:
        raise ValueError("rig has no bones to export")
    local: Dict[str, np.ndarray] = {
        name: np.asarray(rig.skeleton.bones[name].transform, dtype=float).copy() for name in order
    }
    if clip is not None:
        time = 0.0
        for curve in clip.curves.values():
            if curve.keyframes:
                time = float(curve.keyframes[0].time)
                break
        for name in order:
            translate_curve = clip.get_curve(name, "translate")
            rotate_curve = clip.get_curve(name, "rotate")
            transform = np.asarray(rig.skeleton.bones[name].transform, dtype=float).copy()
            if translate_curve is not None and translate_curve.keyframes:
                translation = np.asarray(translate_curve.evaluate(time), dtype=float).reshape(3)
                transform[:3, 3] = translation
            if rotate_curve is not None and rotate_curve.keyframes:
                from .gltf import _euler_xyz_to_quat, _quat_to_matrix

                rotation = _quat_to_matrix(_euler_xyz_to_quat(np.asarray(rotate_curve.evaluate(time), dtype=float)))
                transform[:3, :3] = rotation
            local[name] = transform
    world: Dict[str, np.ndarray] = {}
    for name in order:
        parent = rig.skeleton.bones[name].parent
        world[name] = world[parent] @ local[name] if parent in world else local[name].copy()
    return {name: world[name][:3, 3].copy() for name in order}


def write_obj_rig(rig: Rig, clip: Optional[AnimationClip], path: str) -> bool:
    """Write joint vertices and parent-child line elements."""
    positions = _positions_from_rig(rig, clip)
    order = _bone_order(rig)
    index = {name: number + 1 for number, name in enumerate(order)}
    lines = [f"# OBJ exported by mem20yetiz (rig={rig.name})"]
    for name in order:
        position = np.asarray(positions[name], dtype=float)
        if position.shape != (3,) or not np.all(np.isfinite(position)):
            raise ValueError(f"rig joint {name!r} has a non-finite export position")
        lines.append(f"o {name}")
        lines.append(f"v {position[0]:.9f} {position[1]:.9f} {position[2]:.9f}")
    for name in order:
        parent = rig.skeleton.bones[name].parent
        if parent in index:
            lines.append(f"l {index[parent]} {index[name]}")
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def _first_position(value: np.ndarray) -> np.ndarray:
    array = np.asarray(value, dtype=float)
    if array.shape == (3,):
        array = array.reshape(1, 3)
    if array.ndim != 2 or array.shape[1] != 3 or array.shape[0] == 0:
        raise ValueError("joint positions must have shape (frames, 3) or (3,)")
    if not np.all(np.isfinite(array[0])):
        raise ValueError("joint positions contain a non-finite first-frame value")
    return array[0]


def _hierarchy_edges(hierarchy: Any, names: List[str]) -> List[tuple[str, str]]:
    if hierarchy is None:
        return [(first, second) for first, second in zip(names, names[1:])]
    if hasattr(hierarchy, "values"):
        edges: List[tuple[str, str]] = []
        for joint in hierarchy.values():
            name = getattr(joint, "name", None)
            parent = getattr(joint, "parent", None)
            if name in names and parent in names and not getattr(joint, "is_end_site", False):
                edges.append((parent, name))
        return edges
    if isinstance(hierarchy, dict):
        return [
            (str(parent), str(name))
            for name, parent in hierarchy.items()
            if name in names and parent in names
        ]
    raise TypeError("hierarchy must be a BVH hierarchy or a name-to-parent mapping")


def write_obj_from_positions(
    name: str,
    joint_positions: Dict[str, np.ndarray],
    path: str,
    hierarchy: Any = None,
) -> bool:
    """Write first-frame joint positions and the supplied bone edges."""
    if not joint_positions:
        raise ValueError("no joint positions to export")
    names = list(joint_positions)
    positions = {joint: _first_position(joint_positions[joint]) for joint in names}
    edges = _hierarchy_edges(hierarchy, names)
    index = {joint: number + 1 for number, joint in enumerate(names)}
    lines = [f"# OBJ exported by mem20yetiz (capture={name})"]
    for joint in names:
        position = positions[joint]
        lines.append(f"o {joint}")
        lines.append(f"v {position[0]:.9f} {position[1]:.9f} {position[2]:.9f}")
    for parent, joint in edges:
        lines.append(f"l {index[parent]} {index[joint]}")
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def _resolve_index(value: str, vertex_count: int) -> int:
    index = int(value.split("/", 1)[0])
    if index == 0:
        raise ValueError("OBJ indices are one-based")
    return index - 1 if index > 0 else vertex_count + index


def load_obj(path: str) -> Dict[str, Any]:
    """Parse OBJ vertices, object names, and validated line elements."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"OBJ file not found: {path}")
    vertices: List[List[float]] = []
    lines: List[List[int]] = []
    vertex_names: List[str] = []
    objects: List[str] = []
    current_object: Optional[str] = None
    for raw in source.read_text(encoding="utf-8", errors="strict").splitlines():
        parts = raw.strip().split()
        if not parts or parts[0].startswith("#"):
            continue
        if parts[0] == "v":
            if len(parts) < 4:
                raise ValueError("OBJ vertex needs three coordinates")
            position = [float(value) for value in parts[1:4]]
            if not np.all(np.isfinite(position)):
                raise ValueError("OBJ vertex contains a non-finite coordinate")
            if current_object is not None and current_object not in objects:
                objects.append(current_object)
            vertices.append(position)
            vertex_names.append(current_object or f"vertex_{len(vertices)}")
        elif parts[0] == "o":
            if len(parts) < 2:
                raise ValueError("OBJ object declaration needs a name")
            current_object = parts[1]
        elif parts[0] == "l":
            if len(parts) < 3:
                raise ValueError("OBJ line needs at least two vertices")
            resolved = [_resolve_index(value, len(vertices)) for value in parts[1:]]
            if any(index < 0 or index >= len(vertices) for index in resolved):
                raise ValueError("OBJ line references an unknown vertex")
            lines.append(resolved)
    return {
        "vertices": vertices,
        "lines": lines,
        "n_vertices": len(vertices),
        "n_lines": len(lines),
        "vertex_names": vertex_names,
        "objects": objects,
    }
