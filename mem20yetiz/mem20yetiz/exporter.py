"""Exporter — real export/import for glTF 2.0, OBJ, BVH and C3D.

Dispatch table drives export by format; each format has a real, hermetic
writer and (for glTF/OBJ/BVH/C3D) a matching reader used for roundtrip
validation. C3D is limited to point-only Intel/little-endian IEEE files.
Unsupported formats (FBX, USD) raise ``NotImplementedError`` explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from . import gltf, obj
from .animation import AnimationClip
from .mocap import MocapData, load_c3d, parse_bvh_file, write_bvh, write_c3d
from .rig import Rig


@dataclass
class ExportSettings:
    """Real export settings."""
    format: str = "gltf"  # gltf, obj, bvh, c3d
    version: str = "2.0"
    include_animation: bool = True
    include_materials: bool = True
    include_textures: bool = False
    axis_conversion: str = "auto"  # auto, maya, blender, unreal, unity
    unit_scale: float = 1.0
    apply_modifiers: bool = True
    export_selected_only: bool = False

    @staticmethod
    def available_formats() -> List[str]:
        return ["gltf", "obj", "bvh", "c3d"]


class Exporter:
    """Exporter — real dispatch over the real writers/readers."""

    def __init__(self, settings: Optional[ExportSettings] = None):
        self.settings = settings or ExportSettings()
        if self.settings.format not in ExportSettings.available_formats():
            raise NotImplementedError(
                f"export format {self.settings.format!r} is not supported; "
                f"real formats are {ExportSettings.available_formats()}"
            )

    def export_rig(self, rig: Rig, path: str, settings: Optional[ExportSettings] = None) -> bool:
        """Export a rig to the configured format."""
        s = settings or self.settings
        kind = _path_format(path, s.format)
        if kind == "gltf":
            return gltf.export_gltf(rig, None, path)
        if kind == "obj":
            return obj.write_obj_rig(rig, None, path)
        if kind == "bvh":
            raise ValueError("BVH export requires mocap motion data; use export_mocap on a BVH-loaded MocapData")
        if kind == "c3d":
            raise ValueError("C3D export requires marker data; use export_mocap on a MocapData")
        raise NotImplementedError(f"export format {kind!r} is not implemented")

    def export_animation(self, clip: AnimationClip, path: str, settings: Optional[ExportSettings] = None) -> bool:
        """Export an animation clip (glTF embeds it; OBJ embeds a skeleton view)."""
        s = settings or self.settings
        kind = _path_format(path, s.format)
        if kind == "gltf":
            if not clip.curves:
                raise ValueError("animation clip has no curves to export")
            rig = _rig_from_clip(clip)
            return gltf.export_gltf(rig, clip if s.include_animation else None, path)
        if kind == "obj":
            rig = _rig_from_clip(clip)
            return obj.write_obj_rig(rig, clip, path)
        raise ValueError(f"animation export to {kind!r} requires a skeleton; use gltf or obj")

    def export_mocap(self, data: MocapData, path: str, settings: Optional[ExportSettings] = None) -> bool:
        """Export mocap data: glTF (skeleton+animation), OBJ, BVH, or C3D."""
        s = settings or self.settings
        kind = _path_format(path, s.format)
        if kind == "bvh":
            return write_bvh(data, path)
        if kind == "c3d":
            return write_c3d(data, path)
        if kind == "gltf":
            rig = data.to_rig()
            clip = data.to_animation_clip() if s.include_animation else None
            return gltf.export_gltf(rig, clip, path)
        if kind == "obj":
            if data.joint_positions and len(data.frames) > 0:
                return obj.write_obj_from_positions(data.name, data.joint_positions, path, data.hierarchy)
            rig = data.to_rig()
            return obj.write_obj_rig(rig, None, path)
        raise NotImplementedError(f"export format {kind!r} is not implemented")

    def export_batch(self, items: List[Any], output_dir: str, settings: Optional[ExportSettings] = None) -> Dict[str, bool]:
        """Export each item to ``output_dir/{name}.{format}``."""
        s = settings or self.settings
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        results: Dict[str, bool] = {}
        for item in items:
            name = getattr(item, "name", "export")
            path = f"{output_dir}/{name}.{s.format}"
            if isinstance(item, Rig):
                results[name] = self.export_rig(item, path, s)
            elif isinstance(item, AnimationClip):
                results[name] = self.export_animation(item, path, s)
            elif isinstance(item, MocapData):
                results[name] = self.export_mocap(item, path, s)
            else:
                results[name] = False
        return results

    def convert_format(self, input_path: str, output_path: str,
                       input_format: Optional[str] = None, output_format: Optional[str] = None) -> bool:
        """Convert between real formats by loading then re-exporting.

        Supported real pairs:
          * bvh  -> gltf, obj, c3d (markers derived from FK joints)
          * c3d  -> gltf, obj      (rig = first-frame marker bind pose)
          * gltf -> obj            (line skeleton from node tree)
        Anything FBX/USD and unsupported pairings raise explicitly.
        """
        src = Path(input_path)
        if not src.exists():
            raise FileNotFoundError(f"conversion input not found: {input_path}")
        in_fmt = (input_format or src.suffix.lstrip(".")).lower()
        out_fmt = (output_format or Path(output_path).suffix.lstrip(".")).lower()

        if in_fmt == "bvh":
            data = parse_bvh_file(str(src))
            return self.export_mocap(data, output_path, ExportSettings(format=out_fmt))
        if in_fmt == "c3d":
            data = load_c3d(str(src))
            if out_fmt == "obj":
                if not data.frames:
                    raise ValueError("C3D has no frames to export")
                names = data.marker_names
                jp = {m: np.stack([f.marker_positions[m] for f in data.frames if m in f.marker_positions]) for m in names}
                jp = {m: v for m, v in jp.items() if v.ndim == 2 and v.shape[0] > 0}
                return obj.write_obj_from_positions(data.name, jp, output_path)
            if out_fmt == "gltf":
                rig = _rig_from_markers(data)
                return gltf.export_gltf(rig, None, output_path)
            raise NotImplementedError(f"c3d -> {out_fmt} is not implemented")
        if in_fmt == "gltf":
            if out_fmt == "obj":
                info = gltf.load_gltf(str(src))
                positions = {
                    name: info["world_transforms"][name][:3, 3].copy()
                    for name in info["names"]
                }
                parents = {
                    name: info["node_parents"][name]
                    for name in info["names"]
                    if info["node_parents"].get(name) is not None
                }
                return obj.write_obj_from_positions(info["root"], positions, output_path, parents)
            raise NotImplementedError(f"gltf -> {out_fmt} is not implemented")
        raise NotImplementedError(f"conversion from {in_fmt!r} is not implemented")

    def validate_export(self, path: str) -> Dict[str, Any]:
        """Validate an exported file the real way: read it back and sanity-check."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"file not found: {path}")
        suffix = p.suffix.lstrip(".").lower()
        warnings: List[str] = []
        if suffix == "gltf":
            info = gltf.load_gltf(str(p))
            if not info.get("valid"):
                raise ValueError("glTF reparse did not validate")
            return {
                "valid": True,
                "format": "gltf",
                "file_size": p.stat().st_size,
                "warnings": warnings,
                "n_nodes": info["n_nodes"],
                "animations": info["animations"],
            }
        if suffix == "obj":
            info = obj.load_obj(str(p))
            if info["n_vertices"] == 0:
                raise ValueError("OBJ has no vertices")
            if info["n_lines"] == 0:
                warnings.append("OBJ has no line elements")
            return {"valid": True, "format": "obj", "file_size": p.stat().st_size, "warnings": warnings}
        if suffix == "bvh":
            data = parse_bvh_file(str(p))
            if data.num_frames == 0:
                raise ValueError("BVH has no frames")
            return {"valid": True, "format": "bvh", "file_size": p.stat().st_size, "warnings": warnings}
        if suffix == "c3d":
            data = load_c3d(str(p))
            if not data.marker_names:
                warnings.append("C3D declares no point labels")
            return {"valid": True, "format": "c3d", "file_size": p.stat().st_size, "warnings": warnings}
        raise NotImplementedError(f"validation for {suffix!r} is not implemented")


def _path_format(path: str, default: str) -> str:
    suffix = Path(path).suffix.lstrip(".").lower()
    return suffix or default


def _rig_from_clip(clip: AnimationClip) -> Rig:
    """Create a valid container rig when a clip has no source skeleton."""
    from .rig import Bone, Skeleton

    skeleton = Skeleton(name=f"{clip.name}_skeleton")
    root_name = f"{clip.name}_root"
    skeleton.add_bone(Bone(root_name, None, length=0.0))
    parent_map = clip.metadata.get("bone_parents", {})
    for key in clip.curves:
        bone_name = key.split(".", 1)[0]
        if bone_name in skeleton.bones:
            continue
        parent = parent_map.get(bone_name, root_name)
        if parent not in skeleton.bones:
            parent = root_name
        bone = Bone(bone_name, parent, length=0.0)
        translation_curve = clip.get_curve(bone_name, "translate")
        if translation_curve is not None and translation_curve.keyframes:
            bone.transform[:3, 3] = np.asarray(translation_curve.keyframes[0].value, dtype=float).reshape(3)
        skeleton.add_bone(bone)
    return Rig(f"{clip.name}_rig", skeleton)


def _rig_from_markers(data: MocapData) -> Rig:
    """Create a root container for marker positions from a C3D capture."""
    from .rig import Bone, Skeleton

    if not data.frames:
        raise ValueError("C3D has no frames to build a rig from")
    skeleton = Skeleton(name=f"{data.name}_skeleton")
    root_name = f"{data.name}_root"
    skeleton.add_bone(Bone(root_name, None, length=0.0))
    first = data.frames[0]
    names = [name for name in data.marker_names if name in first.marker_positions]
    if not names:
        raise ValueError("C3D has no markers in the first frame")
    for name in names:
        bone = Bone(name, root_name, length=0.0)
        position = np.asarray(first.marker_positions[name], dtype=float)
        if position.shape != (3,) or not np.all(np.isfinite(position)):
            raise ValueError(f"C3D marker {name!r} has an invalid first-frame position")
        bone.transform[:3, 3] = position
        skeleton.add_bone(bone)
    return Rig(f"{data.name}_rig", skeleton)
