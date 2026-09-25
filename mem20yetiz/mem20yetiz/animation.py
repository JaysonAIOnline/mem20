"""Animation Clip primitives — native absorption of Yeti Claw animation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np


@dataclass
class Keyframe:
    """Single keyframe."""
    time: float
    value: np.ndarray
    interpolation: str = "linear"  # linear, cubic, constant
    in_tangent: Optional[np.ndarray] = None
    out_tangent: Optional[np.ndarray] = None


@dataclass
class AnimationCurve:
    """Animation curve for a single property."""
    bone_name: str
    property_path: str  # e.g., "translate", "rotate", "scale"
    keyframes: List[Keyframe] = field(default_factory=list)

    def evaluate(self, time: float) -> np.ndarray:
        """Evaluate curve at time."""
        if not self.keyframes:
            return np.zeros(3)
        # Simple linear interpolation
        for i in range(len(self.keyframes) - 1):
            kf1 = self.keyframes[i]
            kf2 = self.keyframes[i + 1]
            if kf1.time <= time <= kf2.time:
                t = (time - kf1.time) / (kf2.time - kf1.time) if kf2.time != kf1.time else 0
                return kf1.value + t * (kf2.value - kf1.value)
        # Clamp
        if time <= self.keyframes[0].time:
            return self.keyframes[0].value
        return self.keyframes[-1].value


@dataclass
class AnimationClip:
    """Animation clip — absorption of Yeti Claw animation clip."""
    name: str
    duration: float
    frame_rate: float = 30.0
    curves: Dict[str, AnimationCurve] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_looping: bool = False

    def add_curve(self, bone_name: str, property_path: str, curve: AnimationCurve) -> None:
        """Add animation curve."""
        key = f"{bone_name}.{property_path}"
        self.curves[key] = curve

    def get_curve(self, bone_name: str, property_path: str) -> Optional[AnimationCurve]:
        """Get animation curve."""
        key = f"{bone_name}.{property_path}"
        return self.curves.get(key)

    def evaluate(self, time: float) -> Dict[str, np.ndarray]:
        """Evaluate all curves at time."""
        result = {}
        for key, curve in self.curves.items():
            result[key] = curve.evaluate(time)
        return result

    def get_duration(self) -> float:
        return self.duration

    def set_duration(self, duration: float) -> None:
        self.duration = duration

    def trim(self, start_time: float, end_time: float) -> "AnimationClip":
        """Create trimmed clip."""
        new_clip = AnimationClip(
            name=f"{self.name}_trimmed",
            duration=end_time - start_time,
            frame_rate=self.frame_rate,
            is_looping=self.is_looping,
        )
        for key, curve in self.curves.items():
            new_keyframes = [kf for kf in curve.keyframes if start_time <= kf.time <= end_time]
            if new_keyframes:
                new_curve = AnimationCurve(
                    bone_name=curve.bone_name,
                    property_path=curve.property_path,
                    keyframes=new_keyframes,
                )
                new_clip.curves[key] = new_curve
        return new_clip

    def resample(self, new_frame_rate: float) -> "AnimationClip":
        """Resample clip to new frame rate."""
        new_clip = AnimationClip(
            name=self.name,
            duration=self.duration,
            frame_rate=new_frame_rate,
            is_looping=self.is_looping,
        )
        for key, curve in self.curves.items():
            new_keyframes = []
            num_frames = int(self.duration * new_frame_rate)
            for i in range(num_frames + 1):
                t = i / new_frame_rate
                value = curve.evaluate(t)
                new_keyframes.append(Keyframe(time=t, value=value))
            new_curve = AnimationCurve(
                bone_name=curve.bone_name,
                property_path=curve.property_path,
                keyframes=new_keyframes,
            )
            new_clip.curves[key] = new_curve
        return new_clip