"""
title: 3D Model Screenshots + Description
author: Jayson
version: 1.0.0
description: Takes a 3D model (GLB/OBJ/FBX/BLEND), renders multiple camera angles, and prepares a vision description prompt.
requirements: 
"""

import subprocess
import tempfile
import os
from pathlib import Path
from typing import List

BLENDER = "blender"
OUT_DIR = Path.home() / "jayson_3d" / "screenshots"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _run_blender(script: str, timeout: int = 600) -> dict:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script)
        path = f.name
    try:
        r = subprocess.run(
            [BLENDER, "--background", "--python", path],
            capture_output=True, text=True, timeout=timeout
        )
        return {
            "success": r.returncode == 0,
            "stdout": r.stdout[-2500:],
            "stderr": r.stderr[-1500:]
        }
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


class Tools:
    def render_model_angles(
        self,
        model_path: str,
        output_prefix: str = "view",
        resolution: int = 1024,
        samples: int = 48
    ) -> dict:
        """
        Import a 3D model and render 6 useful camera angles.
        Supported formats: .glb .gltf .obj .fbx .blend
        Returns list of image paths + vision prompt.
        """
        model_path = str(Path(model_path).resolve())
        if not Path(model_path).exists():
            return {"success": False, "error": f"File not found: {model_path}"}

        out_dir = OUT_DIR / Path(model_path).stem
        out_dir.mkdir(parents=True, exist_ok=True)

        cameras = [
            ("front",          (0, -4.5, 1.6)),
            ("back",           (0,  4.5, 1.6)),
            ("left",           (-4.5, 0, 1.6)),
            ("right",          (4.5, 0, 1.6)),
            ("top",            (0, 0, 6.5)),
            ("three_quarter",  (3.3, -3.3, 2.4)),
        ]

        script = f'''
import bpy
from mathutils import Vector
from pathlib import Path

# Clear scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# Import model
ext = Path(r"{model_path}").suffix.lower()
if ext in (".glb", ".gltf"):
    bpy.ops.import_scene.gltf(filepath=r"{model_path}")
elif ext == ".obj":
    bpy.ops.wm.obj_import(filepath=r"{model_path}")
elif ext == ".fbx":
    bpy.ops.import_scene.fbx(filepath=r"{model_path}")
elif ext == ".blend":
    bpy.ops.wm.open_mainfile(filepath=r"{model_path}")
else:
    print("ERROR: unsupported format")
    raise SystemExit(1)

# Basic lighting
bpy.ops.object.light_add(type='SUN', location=(5, 5, 10))
bpy.context.active_object.data.energy = 3.5
bpy.ops.object.light_add(type='AREA', location=(-4, -4, 5))
bpy.context.active_object.data.energy = 60

scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = {samples}
scene.render.resolution_x = {resolution}
scene.render.resolution_y = {resolution}
scene.render.film_transparent = True
scene.render.image_settings.file_format = 'PNG'

cameras = {cameras}
for name, loc in cameras:
    for obj in list(bpy.data.objects):
        if obj.type == 'CAMERA':
            bpy.data.objects.remove(obj, do_unlink=True)

    bpy.ops.object.camera_add(location=loc)
    cam = bpy.context.active_object
    direction = Vector((0, 0, 0.6)) - cam.location
    cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    scene.camera = cam

    out_path = r"{out_dir}/{output_prefix}_" + name + ".png"
    scene.render.filepath = out_path
    bpy.ops.render.render(write_still=True)
    print("RENDERED:" + out_path)

print("DONE")
'''
        result = _run_blender(script)
        if not result["success"]:
            return result

        images = sorted(str(p) for p in out_dir.glob(f"{output_prefix}_*.png"))
        vision_prompt = f"""You are looking at {len(images)} screenshots of a 3D model from different angles (front, back, left, right, top, three-quarter).

Write a clear, structured description:
- Overall shape and proportions
- Materials and colors
- Notable details and features
- Style / possible use case
- Any obvious improvements that could be made

Be concise but complete."""

        return {
            "success": True,
            "images": images,
            "output_dir": str(out_dir),
            "vision_prompt": vision_prompt,
            "next_step": "Send the images + vision_prompt to a vision-capable model to get the final description."
        }
