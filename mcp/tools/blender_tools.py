"""OPTIONAL Blender integration (shipped as a separate, pluggable module).

Blender is NOT a required dependency. These tools degrade gracefully: when Blender
is not installed (or MEM20_BLENDER_EXECUTABLE is unset), the runner returns an
informative message instead of failing. See server._run_blender_script.
"""
import os
import sys
import json
import re
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from mcp.server import Server
    from mcp.server.lowlevel.server import ServerRequestContext
    import mcp_types as mt
except ImportError:
    print("Error: mcp package not installed. Please install with: pip install mcp")
    sys.exit(1)

sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
try:
    from memory import remember, recall, status as mem_status, rebuild_index, ledger_view
    MEMORY_SYSTEM_AVAILABLE = True
except ImportError:
    MEMORY_SYSTEM_AVAILABLE = False


class BlenderToolsMixin:
    """Blender tools. Optional — requires the Blender application on PATH or MEM20_BLENDER_EXECUTABLE."""

    def register_blender_tools(self):
        self.tools["blender_create_object"] = mt.Tool(
            name="blender_create_object",
            title="Blender Create Object",
            description="Create a primitive object in Blender (CUBE, SPHERE, CYLINDER, CONE, TORUS, PLANE, ICO_SPHERE). OPTIONAL integration: Blender must be installed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "object_type": {"type": "string", "description": "Primitive type", "enum": ["CUBE", "SPHERE", "CYLINDER", "CONE", "TORUS", "PLANE", "ICO_SPHERE"], "default": "CUBE"},
                    "name": {"type": "string", "description": "Object name", "default": "Object"},
                    "location": {"type": "array", "items": {"type": "number"}, "description": "Location [x, y, z]", "default": [0, 0, 0]},
                    "scale": {"type": "array", "items": {"type": "number"}, "description": "Scale [x, y, z]", "default": [1, 1, 1]},
                    "rotation": {"type": "array", "items": {"type": "number"}, "description": "Rotation [x, y, z] in radians", "default": [0, 0, 0]},
                },
                "required": ["object_type"],
            },
        )
        self.tools["blender_add_material"] = mt.Tool(
            name="blender_add_material",
            title="Blender Add Material",
            description="Add a Principled BSDF material to an object. OPTIONAL integration: Blender must be installed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "object_name": {"type": "string", "description": "Name of the object to add material to"},
                    "color": {"type": "array", "items": {"type": "number"}, "description": "RGBA color [r, g, b, a]", "default": [0.8, 0.2, 0.1, 1.0]},
                    "metallic": {"type": "number", "description": "Metallic factor 0-1", "default": 0.0},
                    "roughness": {"type": "number", "description": "Roughness factor 0-1", "default": 0.4},
                    "emission_strength": {"type": "number", "description": "Emission strength", "default": 0.0},
                },
                "required": ["object_name"],
            },
        )
        self.tools["blender_set_camera"] = mt.Tool(
            name="blender_set_camera",
            title="Blender Set Camera",
            description="Create or move the main camera in Blender. OPTIONAL integration: Blender must be installed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "location": {"type": "array", "items": {"type": "number"}, "description": "Camera location [x, y, z]", "default": [5, -5, 3]},
                    "target": {"type": "array", "items": {"type": "number"}, "description": "Target to look at [x, y, z]", "default": [0, 0, 0]},
                    "lens": {"type": "number", "description": "Lens focal length", "default": 50},
                },
                "required": [],
            },
        )
        self.tools["blender_render"] = mt.Tool(
            name="blender_render",
            title="Blender Render",
            description="Render the current Blender scene. OPTIONAL integration: Blender must be installed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Output filename", "default": "render.png"},
                    "engine": {"type": "string", "description": "Render engine", "enum": ["CYCLES", "EEVEE", "BLENDER_EEVEE", "BLENDER_WORKBENCH"], "default": "CYCLES"},
                    "samples": {"type": "integer", "description": "Cycles samples", "default": 64},
                    "resolution": {"type": "array", "items": {"type": "integer"}, "description": "Resolution [width, height]", "default": [1280, 720]},
                },
                "required": [],
            },
        )
        self.tools["blender_export_glb"] = mt.Tool(
            name="blender_export_glb",
            title="Blender Export GLB",
            description="Export the scene as GLB (for web/Unity/Three.js). OPTIONAL integration: Blender must be installed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Output filename", "default": "model.glb"},
                },
                "required": ["filename"],
            },
        )
        self.tools["blender_run_bpy"] = mt.Tool(
            name="blender_run_bpy",
            title="Blender Run BPY",
            description="Run arbitrary Blender Python (bpy) code. OPTIONAL integration: Blender must be installed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Blender Python code to execute"},
                },
                "required": ["code"],
            },
        )
        self.tools["blender_clear_scene"] = mt.Tool(
            name="blender_clear_scene",
            title="Blender Clear Scene",
            description="Delete all objects and materials, start with clean scene. OPTIONAL integration: Blender must be installed.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        )

    async def _blender_create_object(self, args: Dict) -> str:
        object_type = args.get("object_type", "CUBE")
        name = args.get("name", "Object")
        location = args.get("location", [0, 0, 0])
        scale = args.get("scale", [1, 1, 1])
        rotation = args.get("rotation", [0, 0, 0])
        script = f'''
import bpy
from mathutils import Euler
bpy.ops.object.select_all(action='DESELECT')
bpy.ops.mesh.primitive_{object_type.lower()}_add(location={location})
obj = bpy.context.active_object
obj.name = "{name}"
obj.scale = {scale}
obj.rotation_euler = Euler({rotation}, 'XYZ')
bpy.ops.wm.save_as_mainfile(filepath="{os.environ.get("MEM20_BLENDER_WORKDIR", os.path.expanduser("~/.mem20/blender"))}/scene.blend")
print("OK:" + obj.name)
'''
        return await self._run_blender_script(script)

    async def _blender_add_material(self, args: Dict) -> str:
        object_name = args.get("object_name", "")
        color = args.get("color", [0.8, 0.2, 0.1, 1.0])
        metallic = args.get("metallic", 0.0)
        roughness = args.get("roughness", 0.4)
        emission_strength = args.get("emission_strength", 0.0)
        if not object_name:
            return "Error: object_name is required"
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
    bsdf.inputs["Base Color"].default_value = {color}
    bsdf.inputs["Metallic"].default_value = {metallic}
    bsdf.inputs["Roughness"].default_value = {roughness}
    if {emission_strength} > 0:
        bsdf.inputs["Emission Strength"].default_value = {emission_strength}
        bsdf.inputs["Emission Color"].default_value = {color}
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)
    bpy.ops.wm.save_as_mainfile(filepath="{os.environ.get("MEM20_BLENDER_WORKDIR", os.path.expanduser("~/.mem20/blender"))}/scene.blend")
    print("OK: material added")
'''
        return await self._run_blender_script(script)

    async def _blender_set_camera(self, args: Dict) -> str:
        location = args.get("location", [5, -5, 3])
        target = args.get("target", [0, 0, 0])
        lens = args.get("lens", 50)
        script = f'''
import bpy
from mathutils import Vector
for obj in list(bpy.data.objects):
    if obj.type == 'CAMERA':
        bpy.data.objects.remove(obj, do_unlink=True)
bpy.ops.object.camera_add(location={location})
cam = bpy.context.active_object
cam.name = "JaysonCamera"
cam.data.lens = {lens}
direction = Vector({list(target)}) - cam.location
cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
bpy.context.scene.camera = cam
bpy.ops.wm.save_as_mainfile(filepath="{os.environ.get("MEM20_BLENDER_WORKDIR", os.path.expanduser("~/.mem20/blender"))}/scene.blend")
print("OK: camera set")
'''
        return await self._run_blender_script(script)

    async def _blender_render(self, args: Dict) -> str:
        filename = args.get("filename", "render.png")
        engine = args.get("engine", "CYCLES")
        samples = args.get("samples", 64)
        resolution = args.get("resolution", [1280, 720])
        out = f"{os.environ.get("MEM20_BLENDER_WORKDIR", os.path.expanduser("~/.mem20/blender"))}/{filename}"
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
        return await self._run_blender_script(script, timeout=300)

    async def _blender_export_glb(self, args: Dict) -> str:
        filename = args.get("filename", "model.glb")
        out = f"{os.environ.get("MEM20_BLENDER_WORKDIR", os.path.expanduser("~/.mem20/blender"))}/{filename}"
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
        return await self._run_blender_script(script)

    async def _blender_run_bpy(self, args: Dict) -> str:
        code = args.get("code", "")
        if not code:
            return "Error: code is required"
        script = f'''
import bpy
from mathutils import Vector, Euler, Matrix
{code}
bpy.ops.wm.save_as_mainfile(filepath="{os.environ.get("MEM20_BLENDER_WORKDIR", os.path.expanduser("~/.mem20/blender"))}/scene.blend")
print("OK: script finished")
'''
        return await self._run_blender_script(script, timeout=300)

    async def _blender_clear_scene(self, args: Dict) -> str:
        script = f'''
import bpy
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for block in bpy.data.meshes:
    bpy.data.meshes.remove(block)
for block in bpy.data.materials:
    bpy.data.materials.remove(block)
bpy.ops.wm.save_as_mainfile(filepath="{os.environ.get("MEM20_BLENDER_WORKDIR", os.path.expanduser("~/.mem20/blender"))}/scene.blend")
print("OK: scene cleared")
'''
        return await self._run_blender_script(script)
