"""Rig primitives — native absorption of Yeti Claw rigging."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np


@dataclass
class Bone:
    """Bone in a skeleton."""
    name: str
    parent: Optional[str] = None
    transform: np.ndarray = field(default_factory=lambda: np.eye(4))
    length: float = 1.0
    children: List[str] = field(default_factory=list)


@dataclass
class Skeleton:
    """Skeleton hierarchy."""
    name: str
    bones: Dict[str, Bone] = field(default_factory=dict)
    root_bone: Optional[str] = None

    def add_bone(self, bone: Bone):
        self.bones[bone.name] = bone
        if bone.parent is None and self.root_bone is None:
            self.root_bone = bone.name
        if bone.parent and bone.parent in self.bones:
            self.bones[bone.parent].children.append(bone.name)

    def get_bone_chain(self, start: str, end: str) -> List[str]:
        """Get bone chain from start to end."""
        # Simple implementation - walk up from end to start
        chain = []
        current = end
        while current and current != start:
            chain.append(current)
            if current in self.bones:
                current = self.bones[current].parent
            else:
                break
        if current == start:
            chain.append(start)
        return list(reversed(chain))

    def get_bone_global_transform(self, bone_name: str) -> np.ndarray:
        """Get global transform of a bone."""
        if bone_name not in self.bones:
            return np.eye(4)
        bone = self.bones[bone_name]
        if bone.parent is None:
            return bone.transform
        parent_transform = self.get_bone_global_transform(bone.parent)
        return parent_transform @ bone.transform


class Rig:
    """Rig — native absorption of Yeti Claw rigging."""

    def __init__(self, name: str, skeleton: Skeleton):
        self.name = name
        self.skeleton = skeleton
        self.controls: Dict[str, Dict[str, Any]] = {}
        self.constraints: List[Dict[str, Any]] = []

    def add_control(self, name: str, bone: str, control_type: str = "transform",
                    shape: str = "cube", color: tuple = (1, 0, 0)) -> None:
        """Add control to rig."""
        self.controls[name] = {
            "bone": bone,
            "type": control_type,
            "shape": shape,
            "color": color,
        }

    def add_constraint(self, constraint_type: str, target: str, source: str,
                       maintain_offset: bool = True, weight: float = 1.0) -> None:
        """Add constraint between bones."""
        self.constraints.append({
            "type": constraint_type,
            "target": target,
            "source": source,
            "maintain_offset": maintain_offset,
            "weight": weight,
        })

    def get_bind_pose(self) -> Dict[str, np.ndarray]:
        """Get bind pose transforms."""
        return {name: self.skeleton.get_bone_global_transform(name) for name in self.skeleton.bones}

    def set_pose(self, pose: Dict[str, np.ndarray]) -> None:
        """Set rig pose."""
        for bone_name, transform in pose.items():
            if bone_name in self.skeleton.bones:
                # Decompose transform to local space
                if self.skeleton.bones[bone_name].parent:
                    parent_name = self.skeleton.bones[bone_name].parent
                    if parent_name is None:
                        continue
                    parent_transform = self.skeleton.get_bone_global_transform(parent_name)
                    self.skeleton.bones[bone_name].transform = np.linalg.inv(parent_transform) @ transform
                else:
                    self.skeleton.bones[bone_name].transform = transform

    def export_fbx(self, path: str) -> bool:
        """FBX export is not currently supported by mem20yetiz.

        Raising instead of silently exporting avoids shipping fake data.
        Use real export paths instead: glTF 2.0, OBJ, BVH, or C3D via
        :class:`mem20yetiz.exporter.Exporter`.
        """
        raise NotImplementedError(
            "FBX export is not supported by mem20yetiz; use gltf, obj, bvh, or c3d"
        )