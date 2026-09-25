"""Hermetic glTF 2.0 rig and animation export with a strict reader."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .animation import AnimationClip
from .rig import Rig

_COMPONENT_DTYPES: Dict[int, str] = {
    5120: "i1",
    5121: "u1",
    5122: "<i2",
    5123: "<u2",
    5125: "<u4",
    5126: "<f4",
}
_COMPONENT_SIZES: Dict[int, int] = {
    5120: 1,
    5121: 1,
    5122: 2,
    5123: 2,
    5125: 4,
    5126: 4,
}
_TYPE_COMPONENTS: Dict[str, int] = {
    "SCALAR": 1,
    "VEC2": 2,
    "VEC3": 3,
    "VEC4": 4,
    "MAT2": 4,
    "MAT3": 9,
    "MAT4": 16,
}


def _finite(value: float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} is not finite")
    return result


def _matrix_to_quat(rotation: np.ndarray) -> List[float]:
    matrix = np.asarray(rotation, dtype=float)
    trace = float(np.trace(matrix))
    if trace > 0.0:
        scale = math.sqrt(trace + 1.0) * 2.0
        w = 0.25 * scale
        x = (matrix[2, 1] - matrix[1, 2]) / scale
        y = (matrix[0, 2] - matrix[2, 0]) / scale
        z = (matrix[1, 0] - matrix[0, 1]) / scale
    elif matrix[0, 0] > matrix[1, 1] and matrix[0, 0] > matrix[2, 2]:
        scale = math.sqrt(1.0 + matrix[0, 0] - matrix[1, 1] - matrix[2, 2]) * 2.0
        x = 0.25 * scale
        y = (matrix[0, 1] + matrix[1, 0]) / scale
        z = (matrix[0, 2] + matrix[2, 0]) / scale
        w = (matrix[2, 1] - matrix[1, 2]) / scale
    elif matrix[1, 1] > matrix[2, 2]:
        scale = math.sqrt(1.0 + matrix[1, 1] - matrix[0, 0] - matrix[2, 2]) * 2.0
        x = (matrix[0, 1] + matrix[1, 0]) / scale
        y = 0.25 * scale
        z = (matrix[1, 2] + matrix[2, 1]) / scale
        w = (matrix[0, 2] - matrix[2, 0]) / scale
    else:
        scale = math.sqrt(1.0 + matrix[2, 2] - matrix[0, 0] - matrix[1, 1]) * 2.0
        x = (matrix[0, 2] + matrix[2, 0]) / scale
        y = (matrix[1, 2] + matrix[2, 1]) / scale
        z = 0.25 * scale
        w = (matrix[1, 0] - matrix[0, 1]) / scale
    quaternion = np.asarray([x, y, z, w], dtype=float)
    norm = float(np.linalg.norm(quaternion))
    if norm < 1e-12:
        raise ValueError("rotation matrix cannot be converted to a quaternion")
    quaternion /= norm
    return [_finite(value, "quaternion component") for value in quaternion]


def _quat_to_matrix(quaternion: List[float]) -> np.ndarray:
    values = np.asarray(quaternion, dtype=float)
    if values.shape != (4,) or not np.all(np.isfinite(values)):
        raise ValueError("glTF rotation must be a finite 4-vector")
    norm = float(np.linalg.norm(values))
    if abs(norm - 1.0) > 1e-4:
        raise ValueError("glTF rotation quaternion is not normalized")
    x, y, z, w = values / norm
    return np.asarray(
        [
            [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
            [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
            [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
        ],
        dtype=float,
    )


def _euler_xyz_to_quat(euler: np.ndarray) -> List[float]:
    values = np.asarray(euler, dtype=float)
    if values.shape != (3,) or not np.all(np.isfinite(values)):
        raise ValueError("rotation keyframe must contain three finite Euler values")
    x, y, z = values
    cx, sx = math.cos(x / 2.0), math.sin(x / 2.0)
    cy, sy = math.cos(y / 2.0), math.sin(y / 2.0)
    cz, sz = math.cos(z / 2.0), math.sin(z / 2.0)
    quaternion = np.asarray(
        [
            sx * cy * cz + cx * sy * sz,
            cx * sy * cz - sx * cy * sz,
            cx * cy * sz + sx * sy * cz,
            cx * cy * cz - sx * sy * sz,
        ],
        dtype=float,
    )
    quaternion /= np.linalg.norm(quaternion)
    return [_finite(value, "quaternion component") for value in quaternion]


def _decompose_trs(matrix: np.ndarray) -> Tuple[List[float], List[float], List[float]]:
    value = np.asarray(matrix, dtype=float)
    if value.shape != (4, 4) or not np.all(np.isfinite(value)):
        raise ValueError("node transform must be a finite 4x4 matrix")
    if not np.allclose(value[3], [0.0, 0.0, 0.0, 1.0], atol=1e-8):
        raise ValueError("node transform has an invalid homogeneous row")
    translation = [_finite(component, "translation") for component in value[:3, 3]]
    linear = value[:3, :3]
    scale = np.asarray([np.linalg.norm(linear[:, index]) for index in range(3)], dtype=float)
    if np.any(scale < 1e-12):
        raise ValueError("node transform has a singular scale")
    if np.linalg.det(linear) < 0.0:
        scale[0] *= -1.0
    rotation = linear / scale[None, :]
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-5) or not np.isclose(np.linalg.det(rotation), 1.0, atol=1e-5):
        raise ValueError("node transform contains shear")
    return translation, _matrix_to_quat(rotation), [_finite(component, "scale") for component in scale]


def _trs_matrix(translation: List[float], rotation: List[float], scale: List[float]) -> np.ndarray:
    t = np.eye(4)
    t[:3, 3] = np.asarray(translation, dtype=float)
    r = np.eye(4)
    r[:3, :3] = _quat_to_matrix(rotation)
    s = np.eye(4)
    s[:3, :3] = np.diag(np.asarray(scale, dtype=float))
    return t @ r @ s


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


def _append_float_accessor(document: Dict[str, Any], buffer: bytearray, values: np.ndarray, value_type: str) -> int:
    array = np.asarray(values, dtype=np.float32)
    if not np.all(np.isfinite(array)):
        raise ValueError("glTF accessor contains a non-finite value")
    components = _TYPE_COMPONENTS[value_type]
    if value_type == "SCALAR":
        flat = array.reshape(-1)
    else:
        flat = array.reshape(-1)
    if flat.size % components:
        raise ValueError("glTF accessor value count is not divisible by its type")
    while len(buffer) % 4:
        buffer.append(0)
    offset = len(buffer)
    raw = flat.astype("<f4", copy=False).tobytes()
    buffer.extend(raw)
    view_index = len(document["bufferViews"])
    document["bufferViews"].append({"buffer": 0, "byteOffset": offset, "byteLength": len(raw)})
    accessor = {
        "bufferView": view_index,
        "componentType": 5126,
        "count": int(flat.size // components),
        "type": value_type,
    }
    if value_type == "SCALAR":
        accessor["min"] = [float(np.min(flat))] if flat.size else [0.0]
        accessor["max"] = [float(np.max(flat))] if flat.size else [0.0]
    document["accessors"].append(accessor)
    return len(document["accessors"]) - 1


def _curve_values(curve: Any, quaternion: bool) -> np.ndarray:
    values = np.asarray([keyframe.value for keyframe in curve.keyframes], dtype=float)
    if values.ndim != 2 or values.shape[0] != len(curve.keyframes):
        raise ValueError("animation keyframe values must be vectors")
    if quaternion:
        if values.shape[1] == 4:
            result = values.copy()
            norms = np.linalg.norm(result, axis=1)
            if np.any(norms < 1e-12):
                raise ValueError("rotation quaternion has zero length")
            result /= norms[:, None]
            return result
        if values.shape[1] != 3:
            raise ValueError("rotation keyframes must have three or four components")
        return np.asarray([_euler_xyz_to_quat(value) for value in values], dtype=float)
    if values.shape[1] != 3:
        raise ValueError("translation keyframes must have three components")
    return values


def export_gltf(rig: Rig, clip: Optional[AnimationClip], path: str) -> bool:
    """Write a glTF 2.0 JSON document and its binary animation buffer."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    bones = _bone_order(rig)
    if not bones:
        raise ValueError("rig has no bones to export")
    document: Dict[str, Any] = {
        "asset": {"version": "2.0", "generator": "mem20yetiz"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [],
        "buffers": [],
        "bufferViews": [],
        "accessors": [],
    }
    node_ids: Dict[str, int] = {}
    for name in bones:
        node_id = len(document["nodes"])
        node_ids[name] = node_id
        bone = rig.skeleton.bones[name]
        translation, rotation, scale = _decompose_trs(bone.transform)
        document["nodes"].append(
            {
                "name": name,
                "translation": translation,
                "rotation": rotation,
                "scale": scale,
            }
        )
    for name in bones:
        parent = rig.skeleton.bones[name].parent
        if parent is not None and parent in node_ids:
            document["nodes"][node_ids[parent]].setdefault("children", []).append(node_ids[name])
    binary = bytearray()
    if clip is not None:
        channels: List[Dict[str, Any]] = []
        samplers: List[Dict[str, Any]] = []
        for bone in bones:
            for property_name, accessor_type, path_name in (
                ("translate", "VEC3", "translation"),
                ("rotate", "VEC4", "rotation"),
            ):
                curve = clip.get_curve(bone, property_name)
                if curve is None:
                    continue
                if not curve.keyframes:
                    continue
                times = np.asarray([keyframe.time for keyframe in curve.keyframes], dtype=float)
                if times.ndim != 1 or not np.all(np.isfinite(times)) or np.any(np.diff(times) < 0):
                    raise ValueError(f"animation times for {bone}.{property_name} must be finite and ordered")
                values = _curve_values(curve, property_name == "rotate")
                input_accessor = _append_float_accessor(document, binary, times, "SCALAR")
                output_accessor = _append_float_accessor(document, binary, values, accessor_type)
                samplers.append(
                    {
                        "input": input_accessor,
                        "output": output_accessor,
                        "interpolation": "LINEAR",
                    }
                )
                channels.append(
                    {
                        "sampler": len(samplers) - 1,
                        "target": {"node": node_ids[bone], "path": path_name},
                    }
                )
        if not channels:
            raise ValueError("animation clip has no curves for the exported rig")
        document["animations"] = [{"name": clip.name, "channels": channels, "samplers": samplers}]
    document["buffers"] = [{"uri": output.with_suffix(".bin").name, "byteLength": len(binary)}]
    binary_path = output.with_suffix(".bin")
    binary_path.write_bytes(bytes(binary))
    output.write_text(json.dumps(document, indent=2, allow_nan=False), encoding="utf-8")
    return True


def _read_accessor(document: Dict[str, Any], buffer: bytes, accessor_index: int) -> np.ndarray:
    accessors = document["accessors"]
    if not isinstance(accessor_index, int) or not 0 <= accessor_index < len(accessors):
        raise ValueError("glTF accessor index is out of range")
    accessor = accessors[accessor_index]
    component_type = accessor.get("componentType")
    if component_type not in _COMPONENT_DTYPES:
        raise ValueError(f"unsupported glTF component type {component_type!r}")
    value_type = accessor.get("type")
    if value_type not in _TYPE_COMPONENTS:
        raise ValueError(f"unsupported glTF accessor type {value_type!r}")
    count = accessor.get("count")
    if not isinstance(count, int) or count < 0:
        raise ValueError("glTF accessor count must be a non-negative integer")
    if "sparse" in accessor:
        raise ValueError("sparse glTF accessors are not supported by this reader")
    view_index = accessor.get("bufferView")
    views = document["bufferViews"]
    if not isinstance(view_index, int) or not 0 <= view_index < len(views):
        raise ValueError("glTF accessor bufferView is out of range")
    view = views[view_index]
    view_offset = int(view.get("byteOffset", 0))
    view_length = int(view.get("byteLength", 0))
    if view_offset < 0 or view_length < 0 or view_offset + view_length > len(buffer):
        raise ValueError("glTF bufferView exceeds the binary buffer")
    accessor_offset = int(accessor.get("byteOffset", 0))
    component_size = _COMPONENT_SIZES[component_type]
    components = _TYPE_COMPONENTS[value_type]
    stride = view.get("byteStride")
    if stride is None:
        stride = component_size * components
    stride = int(stride)
    if stride < component_size * components or stride % component_size:
        raise ValueError("glTF bufferView byteStride is invalid for its accessor")
    start = view_offset + accessor_offset
    required = component_size * components if count == 0 else component_size * components + stride * (count - 1)
    if accessor_offset < 0 or start + required > view_offset + view_length or start + required > len(buffer):
        raise ValueError("glTF accessor exceeds its bufferView")
    if accessor_offset % component_size or start % component_size:
        raise ValueError("glTF accessor is not component-aligned")
    dtype = np.dtype(_COMPONENT_DTYPES[component_type])
    if stride == component_size * components:
        raw = np.frombuffer(buffer, dtype=dtype, count=count * components, offset=start)
        result = raw.reshape((count, components)) if components != 1 else raw.reshape((count,))
    else:
        result = np.ndarray(
            shape=(count, components),
            dtype=dtype,
            buffer=buffer,
            offset=start,
            strides=(stride, component_size),
        ).copy()
    if accessor.get("normalized") and component_type != 5126:
        if component_type == 5120:
            result = np.maximum(result / 127.0, -1.0)
        elif component_type == 5121:
            result = result / 255.0
        elif component_type == 5122:
            result = np.maximum(result / 32767.0, -1.0)
        elif component_type == 5123:
            result = result / 65535.0
        elif component_type == 5125:
            result = result / 4294967295.0
    return np.array(result, copy=True)


def _node_matrix(node: Dict[str, Any]) -> np.ndarray:
    has_trs = any(key in node for key in ("translation", "rotation", "scale"))
    if "matrix" in node and has_trs:
        raise ValueError("glTF node cannot contain both matrix and TRS properties")
    if "matrix" in node:
        matrix = np.asarray(node["matrix"], dtype=float)
        if matrix.shape != (16,) or not np.all(np.isfinite(matrix)):
            raise ValueError("glTF node matrix must contain 16 finite values")
        return matrix.reshape((4, 4))
    translation = node.get("translation", [0.0, 0.0, 0.0])
    rotation = node.get("rotation", [0.0, 0.0, 0.0, 1.0])
    scale = node.get("scale", [1.0, 1.0, 1.0])
    return _trs_matrix(translation, rotation, scale)


def load_gltf(path: str) -> Dict[str, Any]:
    """Strictly reparse a glTF document, binary buffer, and animation samplers."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"glTF file not found: {path}")
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid glTF JSON: {source}") from exc
    if document.get("asset", {}).get("version") != "2.0":
        raise ValueError("not a glTF 2.0 document")
    for field in ("scene", "scenes", "nodes", "buffers", "bufferViews", "accessors"):
        if field not in document:
            raise ValueError(f"glTF document missing required field {field!r}")
    if not isinstance(document["scenes"], list) or not isinstance(document["nodes"], list):
        raise ValueError("glTF scenes and nodes must be arrays")
    scene_index = document["scene"]
    if not isinstance(scene_index, int) or not 0 <= scene_index < len(document["scenes"]):
        raise ValueError("glTF scene index is out of range")
    scene = document["scenes"][scene_index]
    if not isinstance(scene.get("nodes"), list) or not scene["nodes"]:
        raise ValueError("glTF scene has no root nodes")
    if len(document["buffers"]) != 1:
        raise ValueError("this reader requires exactly one external glTF buffer")
    buffer_info = document["buffers"][0]
    uri = buffer_info.get("uri")
    if not isinstance(uri, str) or not uri:
        raise ValueError("glTF buffer URI is missing")
    uri_path = Path(uri)
    if uri_path.is_absolute() or ".." in uri_path.parts:
        raise ValueError("glTF buffer URI must stay beside the document")
    buffer_path = (source.parent / uri_path).resolve()
    if not buffer_path.is_file():
        raise ValueError(f"glTF references a missing binary buffer: {uri}")
    binary = buffer_path.read_bytes()
    if int(buffer_info.get("byteLength", -1)) != len(binary):
        raise ValueError("glTF buffer byteLength does not match its binary file")
    views = document["bufferViews"]
    if not isinstance(views, list):
        raise ValueError("glTF bufferViews must be an array")
    for view in views:
        if view.get("buffer") != 0:
            raise ValueError("this reader only supports buffer zero")
        offset = int(view.get("byteOffset", 0))
        length = int(view.get("byteLength", 0))
        if offset < 0 or length < 0 or offset + length > len(binary):
            raise ValueError("glTF bufferView exceeds the binary buffer")
        if offset % 4:
            raise ValueError("glTF bufferView offset is not four-byte aligned")
    accessors = document["accessors"]
    if not isinstance(accessors, list):
        raise ValueError("glTF accessors must be an array")

    nodes = document["nodes"]
    names: List[str] = []
    local_matrices: List[np.ndarray] = []
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise ValueError("glTF node entries must be objects")
        name = node.get("name")
        if not isinstance(name, str) or not name:
            name = f"node_{index}"
        if name in names:
            raise ValueError(f"glTF node names must be unique: {name!r}")
        names.append(name)
        local_matrices.append(_node_matrix(node))
    if not names:
        raise ValueError("glTF document has no nodes")
    parents: Dict[int, Optional[int]] = {index: None for index in range(len(nodes))}
    for parent_index, node in enumerate(nodes):
        children = node.get("children", [])
        if not isinstance(children, list):
            raise ValueError("glTF node children must be an array")
        for child in children:
            if not isinstance(child, int) or not 0 <= child < len(nodes):
                raise ValueError("glTF node child index is out of range")
            if parents[child] is not None:
                raise ValueError("glTF node has multiple parents")
            parents[child] = parent_index
    for root in scene["nodes"]:
        if not isinstance(root, int) or not 0 <= root < len(nodes):
            raise ValueError("glTF scene root index is out of range")
    world_matrices: Dict[int, np.ndarray] = {}

    def resolve_world(index: int, stack: set[int]) -> np.ndarray:
        if index in world_matrices:
            return world_matrices[index]
        if index in stack:
            raise ValueError("glTF node hierarchy contains a cycle")
        stack.add(index)
        parent = parents[index]
        if parent is None:
            result = local_matrices[index].copy()
        else:
            result = resolve_world(parent, stack) @ local_matrices[index]
        stack.remove(index)
        world_matrices[index] = result
        return result

    for index in range(len(nodes)):
        resolve_world(index, set())
    node_parents = {names[index]: (names[parent] if parent is not None else None) for index, parent in parents.items()}
    node_transforms = {names[index]: local_matrices[index].copy() for index in range(len(nodes))}
    world_transforms = {names[index]: world_matrices[index].copy() for index in range(len(nodes))}

    animation_data: List[Dict[str, Any]] = []
    animation_samples: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
    for animation in document.get("animations", []):
        if not isinstance(animation, dict) or not isinstance(animation.get("channels"), list) or not isinstance(animation.get("samplers"), list):
            raise ValueError("glTF animation is missing channels or samplers")
        channels: List[Dict[str, Any]] = []
        samplers: List[Dict[str, Any]] = []
        for sampler in animation["samplers"]:
            if not isinstance(sampler, dict) or not isinstance(sampler.get("input"), int) or not isinstance(sampler.get("output"), int):
                raise ValueError("glTF animation sampler is invalid")
            times = _read_accessor(document, binary, sampler["input"])
            values = _read_accessor(document, binary, sampler["output"])
            if times.ndim != 1 or len(times) == 0 or values.shape[0] != len(times) or len(times) > 1 and np.any(np.diff(times) < 0):
                raise ValueError("glTF animation sampler input/output arrays do not agree")
            samplers.append({"input": sampler["input"], "output": sampler["output"], "interpolation": sampler.get("interpolation", "LINEAR")})
        for channel in animation["channels"]:
            if not isinstance(channel, dict) or not isinstance(channel.get("sampler"), int) or not 0 <= channel["sampler"] < len(samplers):
                raise ValueError("glTF animation channel sampler is invalid")
            target = channel.get("target")
            if not isinstance(target, dict) or not isinstance(target.get("node"), int) or not 0 <= target["node"] < len(nodes):
                raise ValueError("glTF animation target node is invalid")
            path = target.get("path")
            if path not in {"translation", "rotation", "scale", "weights"}:
                raise ValueError(f"unsupported glTF animation path {path!r}")
            sampler = samplers[channel["sampler"]]
            times = _read_accessor(document, binary, sampler["input"])
            values = _read_accessor(document, binary, sampler["output"])
            key = f"{names[target['node']]}.{path}"
            if key in animation_samples:
                raise ValueError(f"duplicate glTF animation channel {key!r}")
            animation_samples[key] = (times, values)
            channels.append({"sampler": channel["sampler"], "target": target})
        animation_name = animation.get("name", "")
        if not isinstance(animation_name, str):
            animation_name = ""
        animation_data.append({"name": animation_name, "channels": channels, "samplers": samplers})
    return {
        "valid": True,
        "names": names,
        "n_nodes": len(names),
        "n_accessors": len(accessors),
        "n_views": len(views),
        "animations": len(animation_data),
        "animation_data": animation_data,
        "animation_samples": animation_samples,
        "node_parents": node_parents,
        "node_transforms": node_transforms,
        "world_transforms": world_transforms,
        "root": names[scene["nodes"][0]],
    }


def quaternion_to_matrix(quaternion: List[float]) -> np.ndarray:
    """Convert a glTF quaternion to a 3x3 rotation matrix."""
    return _quat_to_matrix(quaternion)


def euler_xyz_to_quaternion(euler: np.ndarray) -> List[float]:
    """Convert XYZ Euler radians to a glTF quaternion."""
    return _euler_xyz_to_quat(euler)
