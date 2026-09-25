# Jayson Tools

## Blender Tools
Location: `tools/blender/blender_tools.py`

Available functions:
- `create_object` — primitives
- `add_material`
- `set_camera`
- `render`
- `export_glb`
- `run_bpy` — full raw Blender Python power
- `clear_scene`

## Unity Tools
Location: `tools/unity/unity_tools.py`

Available functions:
- `create_project`
- `import_asset` (most useful — brings Blender GLB/FBX into Unity)
- `open_project`

## Image-to-3D Pipeline
See: `pipelines/image_to_3d.md`

## How to activate in Open WebUI

1. Open Admin Panel → Tools / Functions
2. Create new Tool / Function
3. Paste the relevant Python code
4. Give it a clear name and description so Jayson knows when to use it
5. Enable it for the models that should have access

For full power, also enable **Open Terminal** so Jayson can run Blender/Unity commands directly when needed.


## Godot (2.0)
- `tools/godot/godot_tools.py` — project skeleton, import plan, export presets, slice checklist
- Pipeline: `pipelines/games/godot_pipeline.md`
- Use with asset_assembly + production_run (same as Unity path)
