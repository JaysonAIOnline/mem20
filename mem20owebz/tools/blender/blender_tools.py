"""
Jayson Blender Tools
====================
Ready to be turned into Open WebUI Tools / Functions.

Requirements:
- Blender 4.x installed and in PATH
- Run on the same machine (or accessible via Open Terminal)
"""

import subprocess
import tempfile
import os
import json
from pathlib import Path
from typing import Optional, List, Tuple

BLENDER_BIN = "blender"
OUTPUT_DIR = Path.home() / "jayson_3d" / "blender"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _run(script: str, timeout: int = 180) -> dict:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script)
        path = f.name
    try:
        result = subprocess.run(
            [BLENDER_BIN, "--background", "--python", path],
            capture_output=True, text=True, timeout=timeout
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[-3000:],
            "stderr": result.stderr[-2000:],
            "code": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Blender timed out"}
    finally:
        try:
            os.unlink(path)
        except:
            pass


def create_object(
    object_type: str = "CUBE",
    name: str = "Object",
    location: Tuple[float, float, float] = (0, 0, 0),
    scale: Tuple[float, float, float] = (1, 1, 1),
    rotation: Tuple[float, float, float] = (0, 0, 0)
) -> dict:
    """Create a primitive (CUBE, SPHERE, CYLINDER, CONE, TORUS, PLANE, ICO_SPHERE)."""
    script = f'''
import bpy
from mathutils import Euler
bpy.ops.object.select_all(action='DESELECT')
bpy.ops.mesh.primitive_{object_type.lower()}_add(location={list(location)})
obj = bpy.context.active_object
obj.name = "{name}"
obj.scale = {list(scale)}
obj.rotation_euler = Euler({list(rotation)}, 'XYZ')
bpy.ops.wm.save_as_mainfile(filepath=r"{OUTPUT_DIR}/scene.blend")
print("OK:" + obj.name)
'''
    return _run(script)


def add_material(
    object_name: str,
    color: Tuple[float, float, float, float] = (0.8, 0.2, 0.1, 1.0),
    metallic: float = 0.0,
    roughness: float = 0.4,
    emission_strength: float = 0.0
) -> dict:
    """Add Principled BSDF material."""
    script = f'''
import bpy
obj = bpy.data.objects.get("{object_name}")
if not obj:
    print("ERROR: object not found")
else:
    mat = bpy.data.materials.new(name="JaysonMat")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = {list(color)}
    bsdf.inputs["Metallic"].default_value = {metallic}
    bsdf.inputs["Roughness"].default_value = {roughness}
    if {emission_strength} > 0:
        bsdf.inputs["Emission Strength"].default_value = {emission_strength}
        bsdf.inputs["Emission Color"].default_value = {list(color)}
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)
    bpy.ops.wm.save_as_mainfile(filepath=r"{OUTPUT_DIR}/scene.blend")
    print("OK: material added")
'''
    return _run(script)


def set_camera(location=(5, -5, 3), target=(0, 0, 0), lens=50) -> dict:
    """Create or move the main camera."""
    script = f'''
import bpy
from mathutils import Vector
# Remove old cameras
for obj in list(bpy.data.objects):
    if obj.type == 'CAMERA':
        bpy.data.objects.remove(obj, do_unlink=True)
bpy.ops.object.camera_add(location={list(location)})
cam = bpy.context.active_object
cam.name = "JaysonCamera"
cam.data.lens = {lens}
# Point at target
direction = Vector({list(target)}) - cam.location
cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
bpy.context.scene.camera = cam
bpy.ops.wm.save_as_mainfile(filepath=r"{OUTPUT_DIR}/scene.blend")
print("OK: camera set")
'''
    return _run(script)


def render(
    filename: str = "render.png",
    engine: str = "CYCLES",
    samples: int = 64,
    resolution: Tuple[int, int] = (1280, 720)
) -> dict:
    """Render current scene."""
    out = OUTPUT_DIR / filename
    script = f'''
import bpy
scene = bpy.context.scene
scene.render.engine = "{engine}"
if "{engine}" == "CYCLES":
    scene.cycles.samples = {samples}
scene.render.resolution_x = {resolution[0]}
scene.render.resolution_y = {resolution[1]}
scene.render.filepath = r"{out}"
bpy.ops.render.render(write_still=True)
print("OK:" + r"{out}")
'''
    result = _run(script, timeout=300)
    result["file"] = str(out) if result.get("success") else None
    return result


def export_glb(filename: str = "model.glb") -> dict:
    """Export as GLB (best for web / Unity / Three.js)."""
    out = OUTPUT_DIR / filename
    script = f'''
import bpy
bpy.ops.export_scene.gltf(
    filepath=r"{out}",
    export_format='GLB',
    use_selection=False,
    export_apply=True
)
print("OK:" + r"{out}")
'''
    result = _run(script)
    result["file"] = str(out) if result.get("success") else None
    return result


def run_bpy(code: str) -> dict:
    """
    Full power tool.
    Jayson can write any Blender Python (bpy) code.
    """
    full = f'''
import bpy
from mathutils import Vector, Euler, Matrix
{code}
bpy.ops.wm.save_as_mainfile(filepath=r"{OUTPUT_DIR}/scene.blend")
print("OK: script finished")
'''
    return _run(full, timeout=300)


def clear_scene() -> dict:
    """Delete everything and start clean."""
    script = '''
import bpy
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for block in bpy.data.meshes:
    bpy.data.meshes.remove(block)
for block in bpy.data.materials:
    bpy.data.materials.remove(block)
bpy.ops.wm.save_as_mainfile(filepath=r"''' + str(OUTPUT_DIR / "scene.blend") + '''")
print("OK: scene cleared")
'''
    return _run(script)
