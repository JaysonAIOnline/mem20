"""
3D Model → Multi-angle Screenshots + Description Pipeline
=========================================================

Usage flow for Jayson:
1. Receive a 3D model (GLB / OBJ / FBX / .blend)
2. Import into Blender
3. Render 4–6 clean camera angles
4. (Optional) Send screenshots to a vision model for description
5. Return images + structured description

This file contains the core logic. Turn the functions into Open WebUI Tools.
"""

import subprocess
import tempfile
import os
from pathlib import Path
from typing import List, Dict, Optional

BLENDER_BIN = "blender"
OUTPUT_DIR = Path.home() / "jayson_3d" / "screenshots"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _run_blender(script: str, timeout: int = 300) -> dict:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script)
        script_path = f.name
    try:
        result = subprocess.run(
            [BLENDER_BIN, "--background", "--python", script_path],
            capture_output=True, text=True, timeout=timeout
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[-2500:],
            "stderr": result.stderr[-1500:]
        }
    finally:
        try:
            os.unlink(script_path)
        except:
            pass


def render_model_angles(
    model_path: str,
    output_prefix: str = "view",
    resolution: tuple = (1024, 1024),
    engine: str = "CYCLES",
    samples: int = 48
) -> dict:
    """
    Import a 3D model and render multiple useful angles.
    Returns list of image paths.
    """
    model_path = str(Path(model_path).resolve())
    out_dir = OUTPUT_DIR / Path(model_path).stem
    out_dir.mkdir(parents=True, exist_ok=True)

    # Camera positions: front, back, left, right, top, 3/4
    cameras = [
        ("front",  (0, -4.5, 1.5)),
        ("back",   (0,  4.5, 1.5)),
        ("left",   (-4.5, 0, 1.5)),
        ("right",  (4.5, 0, 1.5)),
        ("top",    (0, 0, 6)),
        ("three_quarter", (3.2, -3.2, 2.2)),
    ]

    script = f'''
import bpy
import math
from mathutils import Vector, Euler
from pathlib import Path

# Clean scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# Import
ext = Path(r"{model_path}").suffix.lower()
if ext == ".glb" or ext == ".gltf":
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

# Center and scale object to reasonable size
objects = [o for o in bpy.context.scene.objects if o.type == 'MESH']
if not objects:
    print("ERROR: no mesh found")
    raise SystemExit(1)

# Simple lighting
bpy.ops.object.light_add(type='SUN', location=(5, 5, 10))
sun = bpy.context.active_object
sun.data.energy = 3

bpy.ops.object.light_add(type='AREA', location=(-4, -4, 4))
area = bpy.context.active_object
area.data.energy = 50

# Render settings
scene = bpy.context.scene
scene.render.engine = "{engine}"
if "{engine}" == "CYCLES":
    scene.cycles.samples = {samples}
scene.render.resolution_x = {resolution[0]}
scene.render.resolution_y = {resolution[1]}
scene.render.film_transparent = True
scene.render.image_settings.file_format = 'PNG'

# Render each angle
cameras = {cameras}
for name, loc in cameras:
    # Remove old camera
    for obj in list(bpy.data.objects):
        if obj.type == 'CAMERA':
            bpy.data.objects.remove(obj, do_unlink=True)

    bpy.ops.object.camera_add(location=loc)
    cam = bpy.context.active_object
    cam.name = name

    # Look at origin
    direction = Vector((0, 0, 0.5)) - cam.location
    cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    scene.camera = cam

    out_path = r"{out_dir}/{output_prefix}_" + name + ".png"
    scene.render.filepath = out_path
    bpy.ops.render.render(write_still=True)
    print("RENDERED:" + out_path)

print("DONE")
'''

    result = _run_blender(script, timeout=600)
    if result["success"]:
        images = list(out_dir.glob(f"{output_prefix}_*.png"))
        result["images"] = [str(p) for p in images]
        result["output_dir"] = str(out_dir)
    return result


def describe_screenshots_with_vision(image_paths: List[str], vision_model_hint: str = "vision") -> str:
    """
    Placeholder for vision description.
    In practice Jayson will call a vision-capable model on the images
    and produce a structured description.
    """
    prompt = f"""
You are looking at {len(image_paths)} screenshots of a 3D model from different angles.
Describe the object clearly and structured:

- Overall shape and proportions
- Main materials / colors
- Notable details
- Possible use / style
- Suggested improvements if any

Be concise but complete.
"""
    return {
        "prompt_for_vision_model": prompt,
        "images": image_paths,
        "note": "Feed the images + this prompt to any vision model (Grok vision, GPT-4o, Claude, LLaVA, etc.)"
    }


# Convenience one-shot
def model_to_screenshots_and_description(model_path: str) -> dict:
    """Full pipeline entry point."""
    renders = render_model_angles(model_path)
    if not renders.get("success"):
        return renders

    description_helper = describe_screenshots_with_vision(renders.get("images", []))
    return {
        "success": True,
        "images": renders["images"],
        "output_dir": renders["output_dir"],
        "vision_prompt": description_helper["prompt_for_vision_model"],
        "next_step": "Send the images + vision_prompt to a vision model to get the final description."
    }
