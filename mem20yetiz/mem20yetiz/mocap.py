"""Mocap Processor — native absorption of Yeti Claw motion capture processing.

Real, hermetic; no mocks:

* ``load_bvh`` — real BVH parser (HIERARCHY + MOTION), channel-order aware.
* ``forward_kinematics`` — real FK from the parsed hierarchy -> per-frame world
  joint positions / rotations.
* Pipeline steps that do real math on real data:
  ``gap_fill`` (NaN linear interpolation), ``smooth`` (moving average),
  ``filter`` (in-package Butterworth low-pass, zero-phase), ``normalize``
  (root-anchored), ``track`` (nearest-neighbour marker re-identification),
  ``retarget`` (real animation retargeting via the Retargeter on the clip
  derived from the mocap data).
* ``load_c3d`` / ``export_c3d`` — real point-only C3D binary reader/writer
  (Intel/little-endian IEEE float data) with parameter records.
* ``export_bvh`` — real BVH writer; round-trips the parsed data.
* ``mocap_to_animation`` — real conversion of joint trajectories to an
  ``AnimationClip``.

Unsupported binary formats (FBX) raise ``NotImplementedError`` explicitly
instead of pretending to succeed.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .animation import AnimationClip, AnimationCurve, Keyframe
from .rig import Bone, Rig, Skeleton

# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass
class MocapFrame:
    """Single mocap frame."""

    frame_number: int
    timestamp: float
    marker_positions: Dict[str, np.ndarray] = field(default_factory=dict)
    joint_positions: Dict[str, np.ndarray] = field(default_factory=dict)
    rigid_bodies: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class BVHJoint:
    """A node in a parsed BVH hierarchy (joint or end-site)."""

    name: str
    parent: Optional[str]
    offset: np.ndarray
    channels: List[str] = field(default_factory=list)
    children: List[str] = field(default_factory=list)
    is_end_site: bool = False
    channel_offset: int = 0

    @property
    def channel_count(self) -> int:
        return len(self.channels)


@dataclass
class MocapData:
    """Raw mocap data (marker and/or BVH-skeleton based)."""

    name: str
    frame_rate: float
    frames: List[MocapFrame] = field(default_factory=list)
    marker_names: List[str] = field(default_factory=list)
    rigid_body_names: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # BVH-skeleton fields (populated by load_bvh)
    hierarchy: Dict[str, BVHJoint] = field(default_factory=dict)
    root_joint: Optional[str] = None
    channel_names: List[str] = field(default_factory=list)
    motion: Optional[np.ndarray] = None
    joint_positions: Dict[str, np.ndarray] = field(default_factory=dict)
    joint_rotations: Dict[str, np.ndarray] = field(default_factory=dict)
    joint_world_rotations: Dict[str, np.ndarray] = field(default_factory=dict)
    local_joint_rotations: Dict[str, np.ndarray] = field(default_factory=dict)

    @property
    def num_frames(self) -> int:
        if self.frames:
            return len(self.frames)
        if self.motion is not None:
            return int(self.motion.shape[0])
        return 0

    def to_skeleton(self) -> Skeleton:
        """Build a real ``Skeleton`` from the parsed BVH hierarchy."""
        if not self.hierarchy or self.root_joint is None:
            raise ValueError("No BVH hierarchy present; cannot build skeleton")
        skeleton = Skeleton(name=self.name)
        order = topological_order(self.hierarchy, self.root_joint)
        for name in order:
            j = self.hierarchy[name]
            if j.is_end_site:
                continue
            parent = j.parent if (j.parent in self.hierarchy and not self.hierarchy[j.parent].is_end_site) else None
            bone = Bone(name=name, parent=parent, length=float(np.linalg.norm(j.offset)))
            bone.transform = _translate(*j.offset)
            skeleton.add_bone(bone)
        return skeleton

    def to_rig(self) -> Rig:
        """Build a real ``Rig`` (bind pose from BVH offsets)."""
        return Rig(f"{self.name}_rig", self.to_skeleton())

    def to_animation_clip(self) -> AnimationClip:
        """Real FK joint trajectories -> ``AnimationClip``."""
        return mocap_to_animation(self, self.to_rig())


@dataclass
class MarkerSet:
    """A definition of the markers to track (canonical setup positions)."""

    name: str
    markers: List[str]
    template: Dict[str, np.ndarray]

    def __post_init__(self) -> None:
        if len(set(self.markers)) != len(self.markers):
            raise ValueError("marker names must be unique")
        for m in self.markers:
            if m not in self.template:
                raise ValueError(f"marker {m!r} missing from template positions")


def _copy_mocap_data(data: MocapData) -> MocapData:
    out = MocapData(
        name=data.name,
        frame_rate=data.frame_rate,
        marker_names=list(data.marker_names),
        rigid_body_names=list(data.rigid_body_names),
        metadata=dict(data.metadata),
        hierarchy=dict(data.hierarchy),
        root_joint=data.root_joint,
        channel_names=list(data.channel_names),
        motion=data.motion.copy() if data.motion is not None else None,
        joint_positions={name: value.copy() for name, value in data.joint_positions.items()},
        joint_rotations={name: value.copy() for name, value in data.joint_rotations.items()},
        joint_world_rotations={name: value.copy() for name, value in data.joint_world_rotations.items()},
        local_joint_rotations={name: value.copy() for name, value in data.local_joint_rotations.items()},
    )
    for frame in data.frames:
        out.frames.append(
            MocapFrame(
                frame_number=frame.frame_number,
                timestamp=frame.timestamp,
                marker_positions={name: value.copy() for name, value in frame.marker_positions.items()},
                joint_positions={name: value.copy() for name, value in frame.joint_positions.items()},
                rigid_bodies={name: dict(value) for name, value in frame.rigid_bodies.items()},
            )
        )
    return out


@dataclass
class ProcessingPipeline:
    """A named pipeline step (real function + parameters)."""

    name: str
    function: str
    parameters: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

_ROT_CHANNEL_TO_AXIS = {"Xrotation": 0, "Yrotation": 1, "Zrotation": 2}


def _rotate_x(ang: float) -> np.ndarray:
    c, s = math.cos(ang), math.sin(ang)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


def _rotate_y(ang: float) -> np.ndarray:
    c, s = math.cos(ang), math.sin(ang)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


def _rotate_z(ang: float) -> np.ndarray:
    c, s = math.cos(ang), math.sin(ang)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def _translate(x: float, y: float, z: float) -> np.ndarray:
    m = np.eye(4)
    m[:3, 3] = (x, y, z)
    return m


def topological_order(hierarchy: Dict[str, BVHJoint], root: str) -> List[str]:
    """Return a breadth-first parent-before-child hierarchy order."""
    if root not in hierarchy:
        raise ValueError(f"BVH root {root!r} is not declared")
    seen: List[str] = []
    queue = [root]
    while queue:
        name = queue.pop(0)
        if name in seen:
            raise ValueError(f"BVH hierarchy contains a cycle at {name!r}")
        if name not in hierarchy:
            raise ValueError(f"BVH child {name!r} is not declared")
        seen.append(name)
        for child in hierarchy[name].children:
            if hierarchy[child].parent != name:
                raise ValueError(f"BVH child {child!r} has an inconsistent parent")
            queue.append(child)
    return seen


def _hierarchy_depth(hierarchy: Dict[str, BVHJoint], root: str) -> int:
    order = topological_order(hierarchy, root)
    depths = {root: 0}
    maximum = 0
    for name in order:
        depth = depths[name]
        if not hierarchy[name].is_end_site:
            maximum = max(maximum, depth)
        for child in hierarchy[name].children:
            depths[child] = depth + 1
    return maximum + 1 if order else 0


def local_rotation_from_channels(channels: List[str], angles: Dict[str, float]) -> np.ndarray:
    """Local rotation matrix per the BVH convention.

    The elementary rotations are multiplied in the order the rotation channels
    are declared in the file, each new one multiplying on the right. For
    ``CHANNELS 3 Zrotation Xrotation Yrotation`` this yields
    ``R = Rz(z) @ Rx(x) @ Ry(y)``.
    """
    m = np.eye(3)
    for ch in channels:
        if ch in _ROT_CHANNEL_TO_AXIS:
            ang = angles.get(ch, 0.0)
            axis = _ROT_CHANNEL_TO_AXIS[ch]
            m = m @ (_rotate_z(ang) if axis == 2 else (_rotate_x(ang) if axis == 0 else _rotate_y(ang)))
    return m


def matrix_to_euler_xyz(r: np.ndarray) -> np.ndarray:
    """Decompose a rotation matrix as ``R = Rx(x) @ Ry(y) @ Rz(z)``."""
    r = np.asarray(r, dtype=float)
    sy = r[0, 2]
    if sy > 0.999999:
        y = math.pi / 2.0
        x = math.atan2(r[2, 1], r[1, 1])
        z = 0.0
    elif sy < -0.999999:
        y = -math.pi / 2.0
        x = math.atan2(-r[2, 1], r[1, 1])
        z = 0.0
    else:
        y = math.asin(sy)
        x = math.atan2(-r[1, 2], r[2, 2])
        z = math.atan2(-r[0, 1], r[0, 0])
    return np.array([x, y, z])


# ---------------------------------------------------------------------------
# Real BVH parsing + forward kinematics
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> List[str]:
    tokens: List[str] = []
    for line in text.splitlines():
        line = line.split("//")[0].strip()
        if not line:
            continue
        tokens.extend(line.replace("{", " { ").replace("}", " } ").split())
    return tokens


def parse_bvh(text: str) -> MocapData:
    """Parse a BVH hierarchy and motion stream into kinematic trajectories."""
    tokens = _tokenize(text)
    position = 0

    def peek() -> str:
        return tokens[position] if position < len(tokens) else ""

    def take(expected: Optional[str] = None) -> str:
        nonlocal position
        if position >= len(tokens):
            raise ValueError("unexpected end of BVH")
        value = tokens[position]
        position += 1
        if expected is not None and value != expected:
            raise ValueError(f"expected {expected!r}, got {value!r}")
        return value

    def take_float() -> float:
        value = take()
        try:
            return float(value)
        except ValueError as exc:
            raise ValueError(f"expected a number, got {value!r}") from exc

    def take_int() -> int:
        value = take()
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"expected an integer, got {value!r}") from exc

    take("HIERARCHY")
    joints: Dict[str, BVHJoint] = {}
    channel_names: List[str] = []
    allowed_channels = {
        "Xposition",
        "Yposition",
        "Zposition",
        "Xrotation",
        "Yrotation",
        "Zrotation",
    }

    def parse_end_site(parent: BVHJoint) -> None:
        take("Site")
        take("{")
        end_name = f"{parent.name}End"
        suffix = 2
        while end_name in joints:
            end_name = f"{parent.name}End{suffix}"
            suffix += 1
        end = BVHJoint(end_name, parent.name, np.zeros(3), is_end_site=True)
        joints[end.name] = end
        saw_offset = False
        while peek() != "}":
            if take() != "OFFSET":
                raise ValueError(f"End Site {end.name!r} contains an unsupported field")
            if saw_offset:
                raise ValueError(f"End Site {end.name!r} has duplicate OFFSET")
            end.offset = np.array([take_float(), take_float(), take_float()], dtype=float)
            saw_offset = True
        take("}")
        if not saw_offset:
            raise ValueError(f"End Site {end.name!r} is missing OFFSET")
        parent.children.append(end.name)

    def parse_joint(joint_type: str, name: str, parent: Optional[str]) -> BVHJoint:
        if name in joints:
            raise ValueError(f"duplicate BVH node name {name!r}")
        joint = BVHJoint(name=name, parent=parent, offset=np.zeros(3))
        joints[name] = joint
        take("{")
        saw_offset = False
        saw_channels = False
        while peek() != "}":
            keyword = take()
            if keyword == "OFFSET":
                if saw_offset:
                    raise ValueError(f"joint {name!r} has duplicate OFFSET")
                joint.offset = np.array([take_float(), take_float(), take_float()], dtype=float)
                saw_offset = True
            elif keyword == "CHANNELS":
                if saw_channels:
                    raise ValueError(f"joint {name!r} has duplicate CHANNELS")
                count = take_int()
                if count < 0:
                    raise ValueError(f"joint {name!r} has a negative channel count")
                channels = [take() for _ in range(count)]
                unknown = [channel for channel in channels if channel not in allowed_channels]
                if unknown:
                    raise ValueError(f"joint {name!r} has unsupported channels: {unknown}")
                if len(set(channels)) != len(channels):
                    raise ValueError(f"joint {name!r} has duplicate channels")
                joint.channel_offset = len(channel_names)
                joint.channels = channels
                channel_names.extend(channels)
                saw_channels = True
            elif keyword == "JOINT":
                child = parse_joint("JOINT", take(), name)
                joint.children.append(child.name)
            elif keyword == "End":
                parse_end_site(joint)
            else:
                raise ValueError(f"unsupported hierarchy keyword {keyword!r} in {name!r}")
        take("}")
        if not saw_offset:
            raise ValueError(f"joint {name!r} is missing OFFSET")
        if not saw_channels:
            raise ValueError(f"joint {name!r} is missing CHANNELS")
        return joint

    take("ROOT")
    root_name = take()
    parse_joint("ROOT", root_name, None)
    take("MOTION")
    take("Frames:")
    frame_count = take_int()
    take("Frame")
    take("Time:")
    frame_time = take_float()
    if frame_count < 0:
        raise ValueError("BVH frame count cannot be negative")
    if frame_time <= 0:
        raise ValueError("BVH frame time must be positive")

    order = topological_order(joints, root_name)
    if len(order) != len(joints):
        disconnected = sorted(set(joints) - set(order))
        raise ValueError(f"BVH hierarchy is disconnected or cyclic: {disconnected}")
    channel_count = len(channel_names)
    if frame_count and channel_count == 0:
        raise ValueError("a multi-frame BVH must declare at least one channel")
    motion = np.empty((frame_count, channel_count), dtype=float)
    for frame_index in range(frame_count):
        for channel_index in range(channel_count):
            motion[frame_index, channel_index] = take_float()
    if position != len(tokens):
        raise ValueError(f"unexpected trailing BVH token {tokens[position]!r}")

    channel_definitions = [
        {
            "joint": name,
            "offset": int(joints[name].channel_offset),
            "channels": list(joints[name].channels),
        }
        for name in order
        if not joints[name].is_end_site
    ]
    data = MocapData(
        name=root_name,
        frame_rate=1.0 / frame_time,
        hierarchy=joints,
        root_joint=root_name,
        channel_names=channel_names,
        motion=motion,
    )
    data.metadata.update(
        {
            "source": "bvh",
            "frame_time": frame_time,
            "frame_timestamps": [index * frame_time for index in range(frame_count)],
            "n_frames": frame_count,
            "hierarchy_depth": _hierarchy_depth(joints, root_name),
            "channel_definitions": channel_definitions,
            "bone_offsets": {name: joints[name].offset.copy() for name in order},
        }
    )
    compute_fk(data)
    return data


def parse_bvh_file(path: str) -> MocapData:
    """Parse a BVH file from disk."""
    bvh_path = Path(path)
    if not bvh_path.is_file():
        raise FileNotFoundError(f"BVH file not found: {path}")
    return parse_bvh(bvh_path.read_text(encoding="utf-8", errors="strict"))


def compute_fk(data: MocapData) -> None:
    """Compute world joint transforms and frame trajectories with BVH semantics."""
    if not data.hierarchy or data.root_joint is None:
        raise ValueError("BVH hierarchy and root joint are required")
    if data.motion is None:
        raise ValueError("BVH motion matrix is required")
    if data.motion.ndim != 2:
        raise ValueError("BVH motion must be a two-dimensional matrix")
    if data.motion.shape[1] != len(data.channel_names):
        raise ValueError("BVH channel count does not match the motion matrix")
    order = topological_order(data.hierarchy, data.root_joint)
    if len(order) != len(data.hierarchy):
        raise ValueError("BVH hierarchy is disconnected or cyclic")

    frame_count = int(data.motion.shape[0])
    world_positions: Dict[str, np.ndarray] = {}
    world_rotations: Dict[str, np.ndarray] = {}
    local_rotations: Dict[str, np.ndarray] = {}
    world_matrices: Dict[str, np.ndarray] = {}

    for name in order:
        joint = data.hierarchy[name]
        local_positions = np.zeros((frame_count, 3), dtype=float)
        rotations = np.tile(np.eye(3), (frame_count, 1, 1))
        for channel_index, channel in enumerate(joint.channels):
            source_index = joint.channel_offset + channel_index
            values = data.motion[:, source_index]
            if channel.endswith("position"):
                axis = "XYZ".index(channel[0])
                local_positions[:, axis] = values
            elif channel.endswith("rotation"):
                axis = "XYZ".index(channel[0])
                angle = np.deg2rad(values)
                cosines = np.cos(angle)
                sines = np.sin(angle)
                rotation = np.tile(np.eye(3), (frame_count, 1, 1))
                if axis == 0:
                    rotation[:, 1, 1] = cosines
                    rotation[:, 1, 2] = -sines
                    rotation[:, 2, 1] = sines
                    rotation[:, 2, 2] = cosines
                elif axis == 1:
                    rotation[:, 0, 0] = cosines
                    rotation[:, 0, 2] = sines
                    rotation[:, 2, 0] = -sines
                    rotation[:, 2, 2] = cosines
                else:
                    rotation[:, 0, 0] = cosines
                    rotation[:, 0, 1] = -sines
                    rotation[:, 1, 0] = sines
                    rotation[:, 1, 1] = cosines
                rotations = rotations @ rotation
        local_positions += joint.offset
        local_matrices = np.tile(np.eye(4), (frame_count, 1, 1))
        local_matrices[:, :3, :3] = rotations
        local_matrices[:, :3, 3] = local_positions

        positions = np.empty((frame_count, 3), dtype=float)
        rotations = np.empty((frame_count, 3, 3), dtype=float)
        matrices = np.empty((frame_count, 4, 4), dtype=float)
        if joint.parent is None:
            positions[:] = local_positions
            rotations[:] = local_matrices[:, :3, :3]
            matrices[:] = local_matrices
        else:
            parent_positions = world_positions[joint.parent]
            parent_rotations = world_rotations[joint.parent]
            parent_matrices = world_matrices[joint.parent]
            positions[:] = parent_positions + np.einsum("nij,nj->ni", parent_rotations, local_positions)
            rotations[:] = np.einsum("nij,njk->nik", parent_rotations, local_matrices[:, :3, :3])
            matrices[:] = parent_matrices @ local_matrices
        world_positions[name] = positions
        world_rotations[name] = rotations
        local_rotations[name] = local_matrices[:, :3, :3].copy()
        world_matrices[name] = matrices

    data.joint_positions = world_positions
    data.joint_rotations = world_rotations
    data.joint_world_rotations = world_rotations
    data.local_joint_rotations = local_rotations
    data.metadata["joint_world_rotations"] = world_rotations
    data.metadata["world_transforms"] = world_matrices
    frame_time = float(data.metadata.get("frame_time", 1.0 / data.frame_rate if data.frame_rate else 0.0))
    data.frames = [
        MocapFrame(
            frame_number=index,
            timestamp=index * frame_time,
            joint_positions={name: world_positions[name][index].copy() for name in order},
        )
        for index in range(frame_count)
    ]


# ---------------------------------------------------------------------------
# Real C3D reader / writer (FP format, IEEE floats)
# ---------------------------------------------------------------------------

def c3d_write_string(buf: bytearray, s: str, locked: bool = False) -> None:
    """Encode a C3D name with its signed length byte."""
    encoded = s.encode("ascii")
    if not encoded or len(encoded) > 127 or b"\x00" in encoded:
        raise ValueError(f"C3D name is invalid: {s!r}")
    buf.extend(struct.pack("b", -len(encoded) if locked else len(encoded)))
    buf.extend(encoded)


def c3d_read_string(buf: bytes, off: int) -> Tuple[str, int]:
    """Decode a signed-length C3D name and return its following offset."""
    if off >= len(buf):
        raise ValueError("C3D name offset is outside the file")
    length = struct.unpack_from("b", buf, off)[0]
    name_length = abs(length)
    end = off + 1 + name_length
    if end > len(buf):
        raise ValueError("C3D name extends past the file")
    return buf[off + 1 : end].decode("ascii", errors="replace"), end


def default_marker_names(data: MocapData) -> List[str]:
    """Virtual marker names derived from FK joint names (for BVH->C3D)."""
    return sorted(set(data.joint_positions.keys()))


def write_c3d(data: MocapData, path: str) -> bool:
    """Write a standards-shaped point-only C3D file in IEEE float format."""
    markers = list(data.marker_names) or default_marker_names(data)
    if not markers or len(markers) > 255 or len(set(markers)) != len(markers):
        raise ValueError("C3D requires 1-255 unique marker labels")
    n_points = len(markers)
    n_frames = data.num_frames
    if n_frames == 0 or n_frames > 65535 or not data.frame_rate or data.frame_rate <= 0:
        raise ValueError("C3D requires 1-65535 frames and a positive frame rate")
    if not all(isinstance(marker, str) and marker for marker in markers):
        raise ValueError("C3D marker labels must be non-empty strings")

    positions: List[np.ndarray] = []
    for frame_index in range(n_frames):
        frame = data.frames[frame_index] if frame_index < len(data.frames) else None
        frame_positions: List[np.ndarray] = []
        for marker in markers:
            value = None
            if frame is not None:
                value = frame.marker_positions.get(marker)
                if value is None:
                    value = frame.joint_positions.get(marker)
            if value is None and marker in data.joint_positions:
                trajectory = np.asarray(data.joint_positions[marker], dtype=float)
                if trajectory.shape[0] > frame_index:
                    value = trajectory[frame_index]
            vector = np.asarray(value, dtype=float) if value is not None else np.full(3, np.nan)
            if vector.shape != (3,):
                vector = np.full(3, np.nan)
            frame_positions.append(vector)
        positions.append(np.asarray(frame_positions, dtype=float))
    finite_positions = np.concatenate([frame[np.all(np.isfinite(frame), axis=1)] for frame in positions])
    max_abs = float(np.max(np.abs(finite_positions))) if finite_positions.size else 0.0
    point_scale = -max(1.0, max_abs / 32000.0)
    label_width = max(4, max(len(marker.encode("ascii")) for marker in markers))
    label_bytes = b"".join(marker.encode("ascii").ljust(label_width, b" ") for marker in markers)

    def make_parameter(name: str, parameter_type: int, values: Any, dimensions: List[int], description: str) -> bytearray:
        record = bytearray()
        c3d_write_string(record, name, locked=True)
        record.append(1)
        record.extend(b"\x00\x00")
        record.extend(struct.pack("b", parameter_type))
        record.append(len(dimensions))
        record.extend(bytes(dimensions))
        if parameter_type == 2:
            record.extend(struct.pack("<" + "h" * len(values), *values))
        elif parameter_type == 4:
            record.extend(struct.pack("<" + "f" * len(values), *values))
        elif parameter_type == -1:
            record.extend(values)
        else:
            raise ValueError(f"unsupported C3D parameter type {parameter_type}")
        encoded_description = description.encode("utf-8")
        if len(encoded_description) > 255:
            raise ValueError("C3D parameter description is too long")
        record.append(len(encoded_description))
        record.extend(encoded_description)
        return record

    parameter_values = [
        ("USED", 2, [n_points], [], "number of 3D points"),
        ("FRAMES", 2, [n_frames], [], "number of 3D frames"),
        ("DATA_START", 2, [0], [], "first data block"),
        ("SCALE", 4, [point_scale], [], "3D point scale"),
        ("RATE", 4, [float(data.frame_rate)], [], "3D point rate"),
        ("LABELS", -1, label_bytes, [label_width, n_points], "3D point labels"),
    ]

    def make_section(data_start: int) -> bytearray:
        records = [make_parameter(name, ptype, values, dimensions, description) for name, ptype, values, dimensions, description in parameter_values]
        starts: List[int] = []
        cursor = 0
        for record in records:
            starts.append(cursor)
            cursor += len(record)
        for index, record in enumerate(records):
            parameter_name = parameter_values[index][0]
            pointer_offset = 2 + len(parameter_name.encode("ascii"))
            next_pointer = starts[index + 1] - starts[index] if index + 1 < len(records) else 0
            struct.pack_into("<H", record, pointer_offset, next_pointer)
        group = bytearray()
        c3d_write_string(group, "POINT")
        group.extend(struct.pack("b", -1))
        group_pointer_offset = len(group)
        group.extend(b"\x00\x00")
        group_description = b"3D point data"
        group.append(len(group_description))
        group.extend(group_description)
        first_parameter = len(group) + starts[0]
        struct.pack_into("<H", group, group_pointer_offset, first_parameter)
        section = bytearray([0, 0, 0, 1])
        section.extend(group)
        for record in records:
            section.extend(record)
        blocks = max(1, int(math.ceil(len(section) / 512.0)))
        struct.pack_into("<h", records[2], 2 + len("DATA_START") + 4, data_start)
        section = bytearray([0, 0, blocks, 1])
        section.extend(group)
        for record in records:
            section.extend(record)
        return section

    section = make_section(3)
    parameter_blocks = section[2]
    data_start = 2 + parameter_blocks
    section = make_section(data_start)
    if section[2] != parameter_blocks:
        parameter_blocks = section[2]
        data_start = 2 + parameter_blocks
        section = make_section(data_start)
    while len(section) % 512:
        section.append(0)

    body = bytearray()
    for frame in positions:
        for position in frame:
            if np.all(np.isfinite(position)):
                body.extend(struct.pack("<ffff", float(position[0]), float(position[1]), float(position[2]), 0.0))
            else:
                body.extend(struct.pack("<ffff", 0.0, 0.0, 0.0, -1.0))
    data_blocks = max(1, int(math.ceil(len(body) / 512.0)))
    while len(body) % 512:
        body.append(0)

    header = bytearray(512)
    struct.pack_into("<H", header, 0, 0x5002)
    struct.pack_into("<H", header, 2, n_points)
    struct.pack_into("<H", header, 4, 0)
    struct.pack_into("<H", header, 6, 1)
    struct.pack_into("<H", header, 8, n_frames)
    struct.pack_into("<H", header, 10, 0)
    struct.pack_into("<f", header, 12, point_scale)
    struct.pack_into("<H", header, 16, data_start)
    struct.pack_into("<H", header, 18, 0)
    struct.pack_into("<f", header, 20, float(data.frame_rate))
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        handle.write(header)
        handle.write(section)
        handle.write(body)
    data.metadata["c3d_groups"] = {
        "POINT": {
            "LABELS": markers,
            "FRAMES": n_frames,
            "USED": n_points,
            "DATA_START": data_start,
            "SCALE": point_scale,
            "RATE": float(data.frame_rate),
            "PARAMETER_BLOCKS": parameter_blocks,
            "DATA_BLOCKS": data_blocks,
        }
    }
    return True


def load_c3d(path: str) -> MocapData:
    """Read a point-only C3D file, including its parameter records."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"C3D file not found: {path}")
    raw = source.read_bytes()
    if len(raw) < 512 or raw[0] == 0 or raw[1] != 0x50:
        raise ValueError("file does not contain a C3D 3D-point header")
    parameter_block = raw[0]
    parameter_start = (parameter_block - 1) * 512
    if parameter_start + 4 > len(raw):
        raise ValueError("C3D parameter block is outside the file")
    parameter_blocks = raw[parameter_start + 2]
    processor_type = raw[parameter_start + 3]
    if processor_type != 1:
        raise NotImplementedError("only Intel/little-endian C3D files are supported")
    section_end = parameter_start + parameter_blocks * 512
    if parameter_blocks < 1 or section_end > len(raw):
        raise ValueError("C3D parameter section is invalid")

    n_points = struct.unpack_from("<H", raw, 2)[0]
    analog_count = struct.unpack_from("<H", raw, 4)[0]
    first_frame = struct.unpack_from("<H", raw, 6)[0]
    data_start = struct.unpack_from("<H", raw, 16)[0]
    if analog_count:
        raise NotImplementedError("analog C3D channels are not supported by this point reader")
    if n_points == 0 or data_start == 0:
        raise ValueError("C3D header does not declare point data")

    groups: Dict[str, Dict[str, Dict[str, Any]]] = {}
    position = parameter_start + 4

    def read_group(start: int) -> Tuple[str, int, int, int]:
        name, offset = c3d_read_string(raw, start)
        if offset >= section_end:
            raise ValueError("C3D group header is truncated")
        group_id = struct.unpack_from("b", raw, offset)[0]
        offset += 1
        pointer = struct.unpack_from("<H", raw, offset)[0]
        offset += 2
        description_length = raw[offset]
        offset += 1 + description_length
        if offset > section_end:
            raise ValueError("C3D group description is truncated")
        return name, group_id, pointer, offset

    def read_parameter(start: int) -> Tuple[str, Dict[str, Any], int, int]:
        name, offset = c3d_read_string(raw, start)
        if offset + 3 > section_end:
            raise ValueError("C3D parameter header is truncated")
        group_id = struct.unpack_from("b", raw, offset)[0]
        offset += 1
        pointer = struct.unpack_from("<H", raw, offset)[0]
        offset += 2
        parameter_type = struct.unpack_from("b", raw, offset)[0]
        offset += 1
        dimension_count = raw[offset]
        offset += 1
        if dimension_count > 7 or offset + dimension_count > section_end:
            raise ValueError("C3D parameter dimensions are invalid")
        dimensions = [int(value) for value in raw[offset : offset + dimension_count]]
        offset += dimension_count
        element_count = int(np.prod(dimensions)) if dimensions else 1
        if parameter_type == -1:
            element_size = 1
        elif parameter_type in (1, 2, 4):
            element_size = {1: 1, 2: 2, 4: 4}[parameter_type]
        else:
            raise ValueError(f"unsupported C3D parameter type {parameter_type}")
        data_end = offset + element_count * element_size
        if data_end > section_end:
            raise ValueError("C3D parameter data is truncated")
        parameter_data = raw[offset:data_end]
        offset = data_end
        if offset >= section_end:
            raise ValueError("C3D parameter description is missing")
        description_length = raw[offset]
        offset += 1 + description_length
        if offset > section_end:
            raise ValueError("C3D parameter description is truncated")
        if parameter_type == 2:
            value: Any = np.frombuffer(parameter_data, dtype="<i2").copy()
        elif parameter_type == 4:
            value = np.frombuffer(parameter_data, dtype="<f4").copy()
        else:
            value = parameter_data
        return name, {"group_id": group_id, "type": parameter_type, "dimensions": dimensions, "value": value}, pointer, offset

    while position < section_end:
        if not any(raw[position : min(position + 8, section_end)]):
            break
        group_name, group_id, group_pointer, group_end = read_group(position)
        group_parameters: Dict[str, Dict[str, Any]] = {}
        if group_pointer:
            parameter_position = position + group_pointer
            while parameter_position < section_end:
                parameter_name, parameter, next_pointer, record_end = read_parameter(parameter_position)
                group_parameters[parameter_name] = parameter
                if next_pointer == 0:
                    parameter_position = record_end
                    break
                next_position = parameter_position + next_pointer
                if next_position <= parameter_position or next_position >= section_end:
                    raise ValueError("C3D parameter pointer is invalid")
                parameter_position = next_position
            position = parameter_position
        else:
            position = group_end
        groups[group_name] = group_parameters
    point = groups.get("POINT")
    if point is None:
        raise ValueError("C3D file has no POINT group")
    for required in ("USED", "FRAMES", "DATA_START", "SCALE", "RATE", "LABELS"):
        if required not in point:
            raise ValueError(f"C3D POINT group is missing {required}")
    used = int(np.asarray(point["USED"]["value"]).reshape(-1)[0])
    frame_count = int(np.asarray(point["FRAMES"]["value"]).reshape(-1)[0])
    parameter_data_start = int(np.asarray(point["DATA_START"]["value"]).reshape(-1)[0])
    point_scale = float(np.asarray(point["SCALE"]["value"]).reshape(-1)[0])
    frame_rate = float(np.asarray(point["RATE"]["value"]).reshape(-1)[0])
    if used != n_points or parameter_data_start != data_start or frame_rate <= 0 or frame_count < 1:
        raise ValueError("C3D header and POINT parameters disagree")
    labels_data = point["LABELS"]
    label_bytes = labels_data["value"]
    dimensions = labels_data["dimensions"]
    if len(dimensions) >= 2:
        label_width, label_count = int(dimensions[0]), int(dimensions[1])
    elif len(dimensions) == 1:
        label_width, label_count = 1, int(dimensions[0])
    else:
        label_width, label_count = len(label_bytes), 1
    labels = [
        label_bytes[index * label_width : (index + 1) * label_width].decode("ascii", errors="replace").rstrip()
        for index in range(label_count)
    ]
    if len(labels) != used:
        raise ValueError("C3D LABELS count does not match POINT:USED")
    data_offset = (data_start - 1) * 512
    float_format = point_scale < 0
    point_size = 16 if float_format else 8
    if data_offset + frame_count * used * point_size > len(raw):
        raise ValueError("C3D data section is truncated")
    result = MocapData(name=source.stem, frame_rate=frame_rate, marker_names=labels)
    for frame_index in range(frame_count):
        positions: Dict[str, np.ndarray] = {}
        frame_base = data_offset + frame_index * used * point_size
        for point_index, label in enumerate(labels):
            point_base = frame_base + point_index * point_size
            if float_format:
                x, y, z, residual = struct.unpack_from("<ffff", raw, point_base)
                valid = residual >= 0.0 and np.all(np.isfinite([x, y, z]))
            else:
                x, y, z, residual = struct.unpack_from("<hhhh", raw, point_base)
                x *= point_scale
                y *= point_scale
                z *= point_scale
                valid = residual != -32767
            positions[label] = np.asarray([x, y, z], dtype=float) if valid else np.full(3, np.nan)
        result.frames.append(
            MocapFrame(
                frame_number=first_frame + frame_index,
                timestamp=frame_index / frame_rate,
                marker_positions=positions,
            )
        )
    result.metadata.update(
        {
            "source": "c3d",
            "first_frame": first_frame,
            "n_data_blocks": int(math.ceil((len(raw) - data_offset) / 512.0)),
            "data_start": data_start,
            "point_scale": point_scale,
            "c3d_float_type": "ieee-float" if float_format else "integer",
        }
    )
    return result


# ---------------------------------------------------------------------------
# BVH export
# ---------------------------------------------------------------------------


def write_bvh(data: MocapData, path: str) -> bool:
    """Write the parsed BVH skeleton + motion back out as a real BVH file."""
    if not data.hierarchy or data.root_joint is None or data.motion is None:
        raise ValueError("BVH export requires hierarchy + motion (load a BVH first)")
    lines: List[str] = ["HIERARCHY"]

    def render_joint(name: str, depth: int, is_root: bool) -> None:
        j = data.hierarchy[name]
        pad = "\t" * depth
        lines.append(f"{pad}{'ROOT' if is_root else 'JOINT'} {name}")
        lines.append(f"{pad}{{")
        off = j.offset
        lines.append(f"{pad}\tOFFSET {off[0]:.6f} {off[1]:.6f} {off[2]:.6f}")
        if j.channels:
            lines.append(f"{pad}\tCHANNELS {len(j.channels)} {' '.join(j.channels)}")
        for child in j.children:
            child_joint = data.hierarchy.get(child)
            if child_joint is None:
                raise ValueError(f"BVH hierarchy references missing child {child!r}")
            if child_joint.is_end_site:
                c_off = child_joint.offset
                lines.append(f"{pad}\tEnd Site")
                lines.append(f"{pad}\t{{")
                lines.append(f"{pad}\t\tOFFSET {c_off[0]:.6f} {c_off[1]:.6f} {c_off[2]:.6f}")
                lines.append(f"{pad}\t}}")
            else:
                render_joint(child, depth + 1, False)
        lines.append(f"{pad}}}")

    render_joint(data.root_joint, 0, True)
    lines.append("MOTION")
    lines.append(f"Frames: {data.motion.shape[0]}")
    frame_time = float(data.metadata.get("frame_time", 1.0 / data.frame_rate if data.frame_rate else 0.0))
    if frame_time <= 0:
        raise ValueError("BVH frame time must be positive")
    lines.append(f"Frame Time: {frame_time:.9f}")
    for f in range(data.motion.shape[0]):
        lines.append(" ".join(f"{v:.9f}" for v in data.motion[f]))
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Real filters (in-package signal processing)
# ---------------------------------------------------------------------------


def fill_gap(array: np.ndarray, max_gap: int) -> Tuple[np.ndarray, int, int]:
    """Interpolate finite-bounded NaN runs and return array, filled, remaining."""
    if max_gap < 0:
        raise ValueError("max_gap must be non-negative")
    values = np.array(array, dtype=float, copy=True)
    if values.ndim != 1:
        raise ValueError("fill_gap expects one-dimensional data")
    filled_count = 0
    remaining_count = 0
    index = 0
    while index < values.size:
        if np.isfinite(values[index]):
            index += 1
            continue
        end = index
        while end < values.size and not np.isfinite(values[end]):
            end += 1
        run_length = end - index
        before = values[index - 1] if index > 0 and np.isfinite(values[index - 1]) else None
        after = values[end] if end < values.size and np.isfinite(values[end]) else None
        if run_length > max_gap or (before is None and after is None):
            remaining_count += run_length
        elif before is not None and after is not None:
            fractions = np.arange(1, run_length + 1, dtype=float) / (run_length + 1)
            values[index:end] = before + fractions * (after - before)
            filled_count += run_length
        elif before is not None:
            values[index:end] = before
            filled_count += run_length
        else:
            values[index:end] = after
            filled_count += run_length
        index = end
    return values, filled_count, remaining_count


def moving_average(signal: np.ndarray, window: int) -> np.ndarray:
    """Apply a centered moving average with finite-window boundary handling."""
    if window < 1:
        raise ValueError("window must be at least one")
    values = np.asarray(signal, dtype=float)
    if values.ndim != 1:
        raise ValueError("moving_average expects one-dimensional data")
    if values.size == 0:
        return values.copy()
    if window == 1:
        return values.copy()
    output = np.empty_like(values)
    left_radius = (window - 1) // 2
    right_radius = window - 1 - left_radius
    for index in range(values.size):
        start = max(0, index - left_radius)
        end = min(values.size, index + right_radius + 1)
        output[index] = float(np.mean(values[start:end]))
    return output


def one_pole_lowpass(signal: np.ndarray, cutoff_hz: float, fs: float) -> np.ndarray:
    """Apply a causal one-pole low-pass filter."""
    if fs <= 0:
        raise ValueError("sampling frequency must be positive")
    if not 0.0 < cutoff_hz < fs / 2.0:
        raise ValueError("cutoff frequency must be between zero and Nyquist")
    values = np.asarray(signal, dtype=float)
    alpha = 1.0 - math.exp(-2.0 * math.pi * cutoff_hz / fs)
    output = np.empty_like(values)
    state = float(values[0]) if values.size else 0.0
    for index, value in enumerate(values):
        state += alpha * (value - state)
        output[index] = state
    return output


def butterworth_sos(order: int, cutoff_hz: float, fs: float) -> List[np.ndarray]:
    """Design a stable digital Butterworth low-pass as normalized SOS sections."""
    if fs <= 0:
        raise ValueError("sampling frequency must be positive")
    if not 0.0 < cutoff_hz < fs / 2.0:
        raise ValueError(f"cutoff {cutoff_hz} Hz must be in (0, {fs / 2.0}) Hz")
    if int(order) < 1:
        raise ValueError("filter order must be at least one")
    order = int(order)
    warped = math.tan(math.pi * cutoff_hz / fs)
    poles = [
        warped * complex(math.cos(math.pi * (2 * index + order + 1) / (2 * order)),
                         math.sin(math.pi * (2 * index + order + 1) / (2 * order)))
        for index in range(order)
    ]
    sections: List[np.ndarray] = []
    used = [False] * order
    for index, pole in enumerate(poles):
        if used[index]:
            continue
        if abs(pole.imag) < 1e-12:
            used[index] = True
            digital_pole = (2.0 + pole) / (2.0 - pole)
            a1 = -float(digital_pole.real)
            b0 = (1.0 + a1) / 2.0
            sections.append(np.array([b0, b0, 1.0, a1, 0.0], dtype=float))
            continue
        conjugate_index = next(
            (candidate for candidate, value in enumerate(poles)
             if not used[candidate] and candidate != index and abs(value - np.conj(pole)) < 1e-9),
            None,
        )
        if conjugate_index is None:
            raise ValueError("Butterworth pole set is not conjugate-symmetric")
        used[index] = True
        used[conjugate_index] = True
        digital_pole = (2.0 + pole) / (2.0 - pole)
        a1 = -2.0 * float(digital_pole.real)
        a2 = float(abs(digital_pole) ** 2)
        b0 = (1.0 + a1 + a2) / 4.0
        sections.append(np.array([b0, 2.0 * b0, b0, a1, a2], dtype=float))
    return sections


def _lfilter(sos: List[np.ndarray], values: np.ndarray) -> np.ndarray:
    """Run normalized second-order sections using transposed direct form II."""
    output = np.array(values, dtype=float, copy=True)
    for section in sos:
        b0, b1, b2, a1, a2 = (float(value) for value in section)
        state1 = 0.0
        state2 = 0.0
        filtered = np.empty_like(output)
        for index, sample in enumerate(output):
            current = b0 * sample + state1
            state1 = b1 * sample - a1 * current + state2
            state2 = b2 * sample - a2 * current
            filtered[index] = current
        output = filtered
    return output


def butterworth_filter(signal: np.ndarray, cutoff_hz: float, order: int, fs: float) -> np.ndarray:
    """Apply a zero-phase Butterworth low-pass with reflected edge padding."""
    values = np.asarray(signal, dtype=float)
    if values.ndim != 1:
        raise ValueError("butterworth_filter expects one-dimensional data")
    if values.size == 0:
        return values.copy()
    sections = butterworth_sos(order, cutoff_hz, fs)
    padding = min(values.size - 1, 3 * (2 * len(sections) + 1))
    if padding:
        padded = np.concatenate([values[1:padding + 1][::-1], values, values[-padding - 1:-1][::-1]])
    else:
        padded = values
    forward = _lfilter(sections, padded)
    backward = _lfilter(sections, forward[::-1])[::-1]
    return backward[padding:padding + values.size].copy()


# ---------------------------------------------------------------------------
# Real marker tracking
# ---------------------------------------------------------------------------


def track_markers(data: MocapData, marker_set: MarkerSet) -> MocapData:
    """Associate observed marker points with canonical labels across frames."""
    if not data.frames:
        raise ValueError("cannot track on empty data")
    canonical = list(marker_set.markers)
    if not canonical:
        raise ValueError("marker set must contain at least one marker")
    template = np.asarray([marker_set.template[name] for name in canonical], dtype=float)
    if template.shape != (len(canonical), 3) or not np.all(np.isfinite(template)):
        raise ValueError("marker template positions must be finite 3D vectors")

    observation_names = list(data.marker_names)
    if not observation_names:
        for frame in data.frames:
            for name in frame.marker_positions:
                if name not in observation_names:
                    observation_names.append(name)
    tracked: Dict[str, List[Optional[np.ndarray]]] = {name: [] for name in canonical}
    previous: Dict[str, Optional[np.ndarray]] = {name: None for name in canonical}
    velocity: Dict[str, Optional[np.ndarray]] = {name: None for name in canonical}
    extent = float(np.linalg.norm(template.max(axis=0) - template.min(axis=0)))
    threshold = 1.5 * extent + 0.5

    for frame in data.frames:
        observations: List[np.ndarray] = []
        for name in observation_names:
            value = frame.marker_positions.get(name)
            if value is None:
                continue
            vector = np.asarray(value, dtype=float)
            if vector.shape == (3,) and np.all(np.isfinite(vector)):
                observations.append(vector)
        observed = np.asarray(observations, dtype=float) if observations else np.empty((0, 3))
        predictions: List[np.ndarray] = []
        for index, name in enumerate(canonical):
            if previous[name] is None:
                predictions.append(template[index])
            else:
                last = previous[name]
                assert last is not None
                predictions.append(last + (velocity[name] if velocity[name] is not None else 0.0))
        candidates = []
        for marker_index, prediction in enumerate(predictions):
            for observation_index, observation in enumerate(observed):
                distance = float(np.linalg.norm(observation - prediction))
                if distance <= threshold:
                    candidates.append((distance, marker_index, observation_index))
        assignments: Dict[int, int] = {}
        used_observations: set[int] = set()
        for _, marker_index, observation_index in sorted(candidates):
            if marker_index in assignments or observation_index in used_observations:
                continue
            assignments[marker_index] = observation_index
            used_observations.add(observation_index)
        for marker_index, name in enumerate(canonical):
            observation_index = assignments.get(marker_index)
            if observation_index is None:
                tracked[name].append(None)
                previous[name] = None
                velocity[name] = None
                continue
            position = observed[observation_index].copy()
            if previous[name] is not None:
                velocity[name] = position - previous[name]
            else:
                velocity[name] = None
            previous[name] = position
            tracked[name].append(position)

    out = _copy_mocap_data(data)
    out.marker_names = canonical
    out.frames = []
    for index, frame in enumerate(data.frames):
        positions: Dict[str, np.ndarray] = {}
        for name in canonical:
            tracked_position = tracked[name][index]
            positions[name] = tracked_position.copy() if tracked_position is not None else np.full(3, np.nan)
        out.frames.append(
            MocapFrame(
                frame_number=frame.frame_number,
                timestamp=frame.timestamp,
                marker_positions=positions,
                joint_positions={name: value.copy() for name, value in frame.joint_positions.items()},
                rigid_bodies={name: dict(value) for name, value in frame.rigid_bodies.items()},
            )
        )
    out.metadata["marker_set"] = marker_set.name
    out.metadata["tracked"] = True
    out.metadata["tracking_observations"] = observation_names
    return out


# ---------------------------------------------------------------------------
# Mocap -> animation (real)
# ---------------------------------------------------------------------------


def mocap_to_animation(data: MocapData, rig: Optional[Rig] = None) -> AnimationClip:
    """Convert world FK trajectories into local animation curves."""
    if not data.joint_positions:
        raise ValueError("mocap data has no joint trajectories")
    if not data.frames:
        raise ValueError("mocap data has no frames")
    if data.root_joint is None or data.root_joint not in data.joint_positions:
        raise ValueError("mocap data has no root trajectory")
    frame_count = len(data.frames)
    frame_rate = data.frame_rate or 30.0
    frame_times = [float(frame.timestamp) for frame in data.frames]
    if not frame_times:
        frame_times = [index / frame_rate for index in range(frame_count)]
    duration = frame_times[-1] if len(frame_times) > 1 else 0.0
    if rig is not None:
        bone_names = [name for name in rig.skeleton.bones if name in data.joint_positions]
    elif data.hierarchy:
        bone_names = [name for name in topological_order(data.hierarchy, data.root_joint) if not data.hierarchy[name].is_end_site]
    else:
        bone_names = list(data.joint_positions)
    clip = AnimationClip(
        name=data.name,
        duration=duration,
        frame_rate=frame_rate,
        metadata={"source_mocap": data.name, "frame_times": frame_times},
    )
    for name in bone_names:
        trajectory = np.asarray(data.joint_positions[name], dtype=float)
        if trajectory.shape != (frame_count, 3):
            continue
        parent_name = data.hierarchy[name].parent if data.hierarchy and name in data.hierarchy else None
        local_translations = np.empty_like(trajectory)
        for index in range(frame_count):
            if parent_name is None:
                root_offset = data.hierarchy[data.root_joint].offset if data.hierarchy else np.zeros(3)
                local_translations[index] = trajectory[index] - root_offset
            else:
                parent_position = data.joint_positions[parent_name][index]
                parent_rotation = data.joint_world_rotations[parent_name][index]
                local_translations[index] = parent_rotation.T @ (trajectory[index] - parent_position)
        translation_keys = [
            Keyframe(time=frame_times[index], value=local_translations[index].copy())
            for index in range(frame_count)
        ]
        clip.add_curve(
            name,
            "translate",
            AnimationCurve(bone_name=name, property_path="translate", keyframes=translation_keys),
        )
        rotations = data.local_joint_rotations.get(name)
        if rotations is not None:
            rotation_keys = [
                Keyframe(time=frame_times[index], value=matrix_to_euler_xyz(rotations[index]))
                for index in range(frame_count)
            ]
            clip.add_curve(
                name,
                "rotate",
                AnimationCurve(bone_name=name, property_path="rotate", keyframes=rotation_keys),
            )
    return clip


# ---------------------------------------------------------------------------
# The processor
# ---------------------------------------------------------------------------


class MocapProcessor:
    """Mocap processor — real pipeline over real mocap data."""

    def __init__(self, rig: Optional[Rig] = None):
        self.rig = rig
        self.pipelines: List[ProcessingPipeline] = []

    def add_pipeline_step(self, name: str, function: str, parameters: Optional[Dict[str, Any]] = None) -> None:
        self.pipelines.append(ProcessingPipeline(name=name, function=function, parameters=parameters or {}))

    # -- loading ------------------------------------------------------------
    def load_bvh(self, path: str) -> MocapData:
        return parse_bvh_file(path)

    def load_c3d(self, path: str) -> MocapData:
        return load_c3d(path)

    def load_fbx(self, path: str) -> MocapData:
        raise NotImplementedError(
            "FBX mocap loading is not implemented; no real in-package FBX reader exists. "
            "Use the real BVH (load_bvh) or C3D (load_c3d) paths."
        )

    # -- pipeline ------------------------------------------------------------
    def apply_pipeline(self, data: MocapData) -> MocapData:
        processed = data
        for step in self.pipelines:
            processed = self._apply_step(processed, step)
        return processed

    def _apply_step(self, data: MocapData, step: ProcessingPipeline) -> MocapData:
        func, params = step.function, step.parameters
        if func == "gap_fill":
            return self._gap_fill(data, params.get("max_gap", 10))
        if func == "smooth":
            return self._smooth(data, params.get("window", 5))
        if func == "filter":
            return self._filter(data, params.get("cutoff", 10.0), params.get("order", 4))
        if func == "normalize":
            return self._normalize(data, params.get("root_bone", "Hips"))
        if func == "track":
            return track_markers(data, params["marker_set"])
        if func == "retarget":
            target = params.get("target_rig")
            if target is None:
                raise ValueError("retarget step requires a 'target_rig' parameter")
            return self._retarget(data, target, params.get("config"))
        raise ValueError(f"unknown pipeline function {func!r}")

    def _gap_fill(self, data: MocapData, max_gap: int) -> MocapData:
        out = _copy_mocap_data(data)
        frame_count = len(data.frames)
        if frame_count == 0:
            out.metadata["gap_fill"] = {"filled": 0, "remaining": 0}
            return out
        marker_names = list(data.marker_names)
        if not marker_names:
            for frame in data.frames:
                for name in frame.marker_positions:
                    if name not in marker_names:
                        marker_names.append(name)
        joint_names = list(data.joint_positions)
        if not joint_names:
            for frame in data.frames:
                for name in frame.joint_positions:
                    if name not in joint_names:
                        joint_names.append(name)
        marker_values: Dict[str, np.ndarray] = {}
        joint_values: Dict[str, np.ndarray] = {}
        totals = {"filled": 0, "remaining": 0}
        for name in marker_names:
            values = np.full((frame_count, 3), np.nan, dtype=float)
            for index, frame in enumerate(data.frames):
                value = frame.marker_positions.get(name)
                if value is not None and np.asarray(value).shape == (3,):
                    values[index] = value
            for axis in range(3):
                values[:, axis], filled, remaining = fill_gap(values[:, axis], max_gap)
                totals["filled"] += filled
                totals["remaining"] += remaining
            marker_values[name] = values
        for name in joint_names:
            values = np.array(data.joint_positions.get(name, np.full((frame_count, 3), np.nan)), dtype=float, copy=True)
            if values.shape != (frame_count, 3):
                values = np.full((frame_count, 3), np.nan, dtype=float)
                for index, frame in enumerate(data.frames):
                    value = frame.joint_positions.get(name)
                    if value is not None and np.asarray(value).shape == (3,):
                        values[index] = value
            for axis in range(3):
                values[:, axis], filled, remaining = fill_gap(values[:, axis], max_gap)
                totals["filled"] += filled
                totals["remaining"] += remaining
            joint_values[name] = values
        out.marker_names = marker_names
        out.joint_positions = joint_values
        out.frames = []
        for index, source_frame in enumerate(data.frames):
            out.frames.append(
                MocapFrame(
                    frame_number=source_frame.frame_number,
                    timestamp=source_frame.timestamp,
                    marker_positions={name: marker_values[name][index].copy() for name in marker_names},
                    joint_positions={name: joint_values[name][index].copy() for name in joint_names},
                    rigid_bodies={name: dict(value) for name, value in source_frame.rigid_bodies.items()},
                )
            )
        out.metadata["gap_fill"] = totals
        return out

    def _smooth(self, data: MocapData, window: int) -> MocapData:
        out = self._gap_fill(data, max_gap=len(data.frames) if data.frames else 0)
        if not out.frames:
            out.metadata["smoothed"] = {"window": window}
            return out
        for name in out.marker_names:
            values = np.asarray(out.joint_positions.get(name, np.full((len(out.frames), 3), np.nan)), dtype=float)
            if name in out.frames[0].marker_positions:
                values = np.asarray([frame.marker_positions[name] for frame in out.frames], dtype=float)
            smoothed = np.column_stack([moving_average(values[:, axis], window) for axis in range(3)])
            out.frames = [
                MocapFrame(
                    frame_number=frame.frame_number,
                    timestamp=frame.timestamp,
                    marker_positions={**frame.marker_positions, name: smoothed[index].copy()},
                    joint_positions={joint: value.copy() for joint, value in frame.joint_positions.items()},
                    rigid_bodies={body: dict(value) for body, value in frame.rigid_bodies.items()},
                )
                for index, frame in enumerate(out.frames)
            ]
        for name, values in list(out.joint_positions.items()):
            if values.shape != (len(out.frames), 3):
                continue
            out.joint_positions[name] = np.column_stack(
                [moving_average(values[:, axis], window) for axis in range(3)]
            )
        out.frames = [
            MocapFrame(
                frame_number=frame.frame_number,
                timestamp=frame.timestamp,
                marker_positions={key: value.copy() for key, value in frame.marker_positions.items()},
                joint_positions={
                    name: out.joint_positions[name][index].copy()
                    for name in out.joint_positions
                    if name in out.joint_positions and index < len(out.joint_positions[name])
                },
                rigid_bodies={body: dict(value) for body, value in frame.rigid_bodies.items()},
            )
            for index, frame in enumerate(out.frames)
        ]
        out.metadata["smoothed"] = {"window": window}
        return out

    def _filter(self, data: MocapData, cutoff: float, order: int) -> MocapData:
        out = self._gap_fill(data, max_gap=len(data.frames) if data.frames else 0)
        if not out.frames:
            out.metadata["butterworth"] = {"cutoff": cutoff, "order": order, "fs": data.frame_rate}
            return out
        sample_rate = data.frame_rate or 100.0
        for name in out.marker_names:
            values = np.asarray([frame.marker_positions[name] for frame in out.frames], dtype=float)
            values = np.column_stack([butterworth_filter(values[:, axis], cutoff, order, sample_rate) for axis in range(3)])
            for index, frame in enumerate(out.frames):
                out.frames[index].marker_positions[name] = values[index].copy()
        for name, values in list(out.joint_positions.items()):
            if values.shape != (len(out.frames), 3):
                continue
            out.joint_positions[name] = np.column_stack(
                [butterworth_filter(values[:, axis], cutoff, order, sample_rate) for axis in range(3)]
            )
        for index, frame in enumerate(out.frames):
            for name, values in out.joint_positions.items():
                if name in frame.joint_positions and values.shape[0] > index:
                    frame.joint_positions[name] = values[index].copy()
        out.metadata["butterworth"] = {"cutoff": cutoff, "order": order, "fs": sample_rate}
        return out

    def _normalize(self, data: MocapData, root_bone: str) -> MocapData:
        out = _copy_mocap_data(data)
        if not out.frames:
            raise ValueError("normalize requires frames")
        for frame in out.frames:
            reference = frame.joint_positions.get(root_bone)
            if reference is None:
                reference = frame.marker_positions.get(root_bone)
            if reference is None or not np.all(np.isfinite(reference)):
                raise ValueError(f"normalize: reference {root_bone!r} not found in frame {frame.frame_number}")
            frame.marker_positions = {
                name: value - reference for name, value in frame.marker_positions.items()
            }
            frame.joint_positions = {
                name: value - reference for name, value in frame.joint_positions.items()
            }
        if out.joint_positions:
            for name, values in list(out.joint_positions.items()):
                if values.shape[0] != len(out.frames):
                    continue
                root_values = np.asarray(
                    [frame.joint_positions.get(root_bone, frame.marker_positions.get(root_bone, np.full(3, np.nan))) for frame in out.frames],
                    dtype=float,
                )
                out.joint_positions[name] = values - root_values
        out.metadata["normalized"] = {"root_bone": root_bone}
        return out

    def _retarget(self, data: MocapData, target_rig: Rig, config: Any = None) -> MocapData:
        source_rig = data.to_rig()
        clip = mocap_to_animation(data, source_rig)
        from .retargeter import RetargetConfig, Retargeter

        retargeter = Retargeter(source_rig, target_rig)
        if config is None:
            source_names = sorted(source_rig.skeleton.bones)
            target_names = sorted(target_rig.skeleton.bones)
            mappings = retargeter.create_mapping_from_names(source_names, target_names)
            config = RetargetConfig(bone_mappings=mappings)
        retargeter.config = config
        retargeter._build_bone_map()
        target_clip = retargeter.retarget_animation(clip)
        if not data.frames:
            raise ValueError("retarget requires mocap frames")
        target_order: List[str] = []
        visited: set[str] = set()

        def visit(name: str) -> None:
            if name in visited:
                return
            if name not in target_rig.skeleton.bones:
                return
            visited.add(name)
            target_order.append(name)
            for child in target_rig.skeleton.bones[name].children:
                visit(child)

        roots = [name for name, bone in target_rig.skeleton.bones.items() if bone.parent is None]
        for root in roots:
            visit(root)
        for name in target_rig.skeleton.bones:
            visit(name)

        output = _copy_mocap_data(data)
        output.name = f"{data.name}_retargeted"
        output.joint_positions = {}
        output.joint_rotations = {}
        output.joint_world_rotations = {}
        output.local_joint_rotations = {}
        output.frames = []
        frame_times = [frame.timestamp for frame in data.frames]
        for frame_index, frame_time in enumerate(frame_times):
            world_positions: Dict[str, np.ndarray] = {}
            world_rotations: Dict[str, np.ndarray] = {}
            local_rotations: Dict[str, np.ndarray] = {}
            for bone_name in target_order:
                bone = target_rig.skeleton.bones[bone_name]
                local = np.eye(4)
                bind = np.asarray(bone.transform, dtype=float)
                local[:3, :3] = bind[:3, :3]
                local[:3, 3] = bind[:3, 3]
                translate_curve = target_clip.get_curve(bone_name, "translate")
                rotate_curve = target_clip.get_curve(bone_name, "rotate")
                if translate_curve is not None and translate_curve.keyframes:
                    local[:3, 3] = np.asarray(translate_curve.evaluate(frame_time), dtype=float).reshape(3)
                if rotate_curve is not None and rotate_curve.keyframes:
                    euler = np.asarray(rotate_curve.evaluate(frame_time), dtype=float).reshape(3)
                    local[:3, :3] = _rotate_x(euler[0]) @ _rotate_y(euler[1]) @ _rotate_z(euler[2])
                parent = bone.parent
                if parent in world_positions:
                    parent_matrix = np.eye(4)
                    parent_matrix[:3, :3] = world_rotations[parent]
                    parent_matrix[:3, 3] = world_positions[parent]
                    world = parent_matrix @ local
                else:
                    world = local.copy()
                world_positions[bone_name] = world[:3, 3].copy()
                world_rotations[bone_name] = world[:3, :3].copy()
                local_rotations[bone_name] = local[:3, :3].copy()
            frame = MocapFrame(
                frame_number=data.frames[frame_index].frame_number,
                timestamp=frame_time,
                marker_positions={name: value.copy() for name, value in data.frames[frame_index].marker_positions.items()},
                joint_positions=world_positions,
                rigid_bodies={name: dict(value) for name, value in data.frames[frame_index].rigid_bodies.items()},
            )
            output.frames.append(frame)
            for name in target_order:
                output.joint_positions.setdefault(name, []).append(world_positions[name])
                output.joint_world_rotations.setdefault(name, []).append(world_rotations[name])
                output.local_joint_rotations.setdefault(name, []).append(local_rotations[name])
        output.joint_positions = {name: np.asarray(values) for name, values in output.joint_positions.items()}
        output.joint_rotations = {name: np.asarray(values) for name, values in output.joint_world_rotations.items()}
        output.joint_world_rotations = {name: np.asarray(values) for name, values in output.joint_world_rotations.items()}
        output.local_joint_rotations = {name: np.asarray(values) for name, values in output.local_joint_rotations.items()}
        output.metadata["retargeted_clip"] = target_clip
        return output

    def mocap_to_animation(self, data: MocapData, rig: Optional[Rig] = None) -> List[AnimationClip]:
        rig = rig or self.rig
        if rig is None:
            raise ValueError("a rig is required to convert mocap to animation")
        return [mocap_to_animation(data, rig)]

    # -- export -------------------------------------------------------------
    def export_bvh(self, data: MocapData, path: str) -> bool:
        return write_bvh(data, path)

    def export_c3d(self, data: MocapData, path: str) -> bool:
        return write_c3d(data, path)