"""
Example high-level Blender tools for Jayson.
These are meant to be turned into Open WebUI Tools / Functions.

Usage pattern:
1. Jayson decides what to do
2. Calls one of these functions with parameters
3. Function writes a temporary .py script
4. Executes: blender --background --python /tmp/jayson_blender.py
5. Returns render path or export path or success message
"""

import subprocess
import tempfile
import os
from pathlib import Path

BLENDER_BIN = "blender"  # change if needed
OUTPUT_DIR = Path("/tmp/jayson_blender_output")
OUTPUT_DIR.mkdir(exist_ok=True)


def run_blender_script(script_content: str, timeout: int = 120) -> dict:
    """Execute a Blender Python script headless and return result."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script_content)
        script_path = f.name

    try:
        result = subprocess.run(
            [BLENDER_BIN, "--background", "--python", script_path],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[-2000:],  # last part
            "stderr": result.stderr[-2000:],
            "returncode": result.returncode
        }
    finally:
        os.unlink(script_path)


# ========== HIGH LEVEL TOOLS ==========

def create_primitive(object_type: str = "CUBE", name: str = "Object", location=(0, 0, 0), scale=(1, 1, 1)):
    """
    Create a primitive object in Blender.
    object_type: CUBE, SPHERE, CYLINDER, CONE, TORUS, PLANE
    """
    script = f'''
import bpy
bpy.ops.object.select_all(action='DESELECT')
bpy.ops.mesh.primitive_{object_type.lower()}_add(location={location})
obj = bpy.context.active_object
obj.name = "{name}"
obj.scale = {scale}
bpy.ops.wm.save_as_mainfile(filepath="{OUTPUT_DIR}/scene.blend")
print("CREATED:", obj.name)
'''
    return run_blender_script(script)


def add_material(object_name: str, color=(0.8, 0.2, 0.1, 1.0), metallic=0.0, roughness=0.4):
    """Add a simple Principled BSDF material to an object."""
    script = f'''
import bpy
obj = bpy.data.objects.get("{object_name}")
if obj:
    mat = bpy.data.materials.new(name="JaysonMaterial")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = {color}
    bsdf.inputs["Metallic"].default_value = {metallic}
    bsdf.inputs["Roughness"].default_value = {roughness}
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)
    bpy.ops.wm.save_as_mainfile(filepath="{OUTPUT_DIR}/scene.blend")
    print("MATERIAL ADDED")
else:
    print("OBJECT NOT FOUND")
'''
    return run_blender_script(script)


def render_scene(output_name: str = "render.png", engine: str = "CYCLES", samples: int = 64):
    """Render the current scene to an image."""
    output_path = OUTPUT_DIR / output_name
    script = f'''
import bpy
bpy.context.scene.render.engine = "{engine}"
bpy.context.scene.cycles.samples = {samples}
bpy.context.scene.render.filepath = r"{output_path}"
bpy.ops.render.render(write_still=True)
print("RENDERED:", r"{output_path}")
'''
    return run_blender_script(script)


def export_glb(output_name: str = "model.glb"):
    """Export the scene as GLB (great for web / Three.js)."""
    output_path = OUTPUT_DIR / output_name
    script = f'''
import bpy
bpy.ops.export_scene.gltf(
    filepath=r"{output_path}",
    export_format='GLB',
    use_selection=False
)
print("EXPORTED:", r"{output_path}")
'''
    return run_blender_script(script)


def run_raw_script(python_code: str):
    """
    Most powerful tool: let Jayson write any Blender Python (bpy) code.
    Use with care.
    """
    return run_blender_script(python_code)


# Example usage (for testing)
if __name__ == "__main__":
    print(create_primitive("CUBE", "MyCube", location=(0, 0, 1)))
    print(add_material("MyCube", color=(0.1, 0.5, 0.9, 1.0), metallic=0.8))
    print(render_scene("test_render.png"))
    print(export_glb("test_model.glb"))
