"""Retargeter — native absorption of Yeti Claw animation retargeting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from .animation import AnimationClip, AnimationCurve, Keyframe
from .rig import Rig


@dataclass
class BoneMapping:
    """Mapping between source and target bones."""
    source_bone: str
    target_bone: str
    scale_factor: float = 1.0
    offset: Optional[np.ndarray] = None


@dataclass
class RetargetConfig:
    """Retargeting configuration."""
    bone_mappings: List[BoneMapping] = field(default_factory=list)
    root_bone_source: str = "Hips"
    root_bone_target: str = "Hips"
    preserve_root_motion: bool = True
    scale_correction: bool = True


class Retargeter:
    """Animation retargeter — absorption of Yeti Claw retargeter."""

    def __init__(self, source_rig: Rig, target_rig: Rig, config: Optional[RetargetConfig] = None):
        self.source_rig = source_rig
        self.target_rig = target_rig
        self.config = config or RetargetConfig()
        self._build_bone_map()

    def _build_bone_map(self):
        """Build bone mapping dictionary."""
        self.bone_map = {m.source_bone: m.target_bone for m in self.config.bone_mappings}

    def retarget_animation(self, source_clip: AnimationClip) -> AnimationClip:
        """Retarget animation clip from source to target rig."""
        target_clip = AnimationClip(
            name=f"{source_clip.name}_retargeted",
            duration=source_clip.duration,
            frame_rate=source_clip.frame_rate,
            is_looping=source_clip.is_looping,
        )

        for key, curve in source_clip.curves.items():
            # Parse bone and property
            parts = key.split(".", 1)
            if len(parts) != 2:
                continue
            source_bone, prop = parts

            # Find target bone
            target_bone = self.bone_map.get(source_bone)
            if not target_bone:
                continue

            # Create new curve for target
            new_curve = AnimationCurve(
                bone_name=target_bone,
                property_path=curve.property_path,
                keyframes=[Keyframe(kf.time, np.asarray(kf.value, dtype=float).copy()) for kf in curve.keyframes],
            )

            # Apply scale correction if enabled
            if self.config.scale_correction:
                source_bone_obj = self.source_rig.skeleton.bones.get(source_bone)
                target_bone_obj = self.target_rig.skeleton.bones.get(target_bone)
                if source_bone_obj and target_bone_obj:
                    # Simple scale correction
                    scale = target_bone_obj.length / source_bone_obj.length if source_bone_obj.length > 0 else 1.0
                    if "translate" in curve.property_path:
                        for kf in new_curve.keyframes:
                            kf.value = kf.value * scale

            target_clip.curves[f"{target_bone}.{curve.property_path}"] = new_curve

        return target_clip

    def retarget_multiple(self, source_clips: List[AnimationClip]) -> List[AnimationClip]:
        """Retarget multiple clips."""
        return [self.retarget_animation(clip) for clip in source_clips]

    def create_mapping_from_names(self, source_names: List[str], target_names: List[str],
                                  prefix_map: Optional[Dict[str, str]] = None) -> List[Any]:
        """Auto-generate bone mappings from naming conventions."""
        mappings = []
        prefix_map = prefix_map or {}

        for s_name in source_names:
            # Try exact match
            if s_name in target_names:
                mappings.append(BoneMapping(s_name, s_name))
                continue

            # Try prefix mapping
            for src_prefix, tgt_prefix in prefix_map.items():
                if s_name.startswith(src_prefix):
                    tgt_name = tgt_prefix + s_name[len(src_prefix):]
                    if tgt_name in target_names:
                        mappings.append(BoneMapping(s_name, tgt_name))
                        break

            # Try without prefix
            if s_name not in [m.source_bone for m in mappings]:
                for t_name in target_names:
                    if s_name.lower() == t_name.lower():
                        mappings.append(BoneMapping(s_name, t_name))
                        break

        return mappings