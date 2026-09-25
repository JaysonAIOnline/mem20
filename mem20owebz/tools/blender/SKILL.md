---
name: local-3d-asset-generation
description: Generate 3D assets locally with Blender when cloud APIs unavailable.
tags: [blender, 3d, assets, generation]
related_skills: [agent-task-orchestration]
---

# Local 3D Asset Generation with Blender

When cloud APIs (Tripo, Meshy, Luma) are rate-limited, quota-exceeded, or unavailable, use local Blender for 3D asset generation.

## Prerequisites
- Blender 4.x installed and in PATH (`which blender` returns path)
- Python environment with access to blender_tools

## Tool Locations
- `/tools/blender/blender_tools.py` - Core Blender API wrapper
- `/tools/blender/generate_assets.py` - Main asset generator script

## Asset Pipeline

```
1. Prepare asset list (from production package)
2. Run: python3 /tools/blender/generate_assets.py
3. Move outputs from /root/jayson_3d/blender/ to <project>/_incoming/
4. Update <project>/manifests/assets_master.csv with "generated" status
5. Set QA column to "yes" for valid import-ready models
```

## Blender Tools Reference

| Function | Purpose | Returns |
|----------|---------|---------|
| `create_object(type, name, location, scale)` | Create primitive | GLB file |
| `add_material(obj_name, color, metallic, roughness)` | Apply material | Texture map |
| `set_camera(location, target, lens)` | Setup camera | Viewport |
| `render(filename, engine, samples, resolution)` | Render image | PNG/JPG |
| `export_glb(filename)` | Export for Unity | GLB file |
| `run_bpy(python_code)` | Full scripting power | Custom result |

## Output Locations
- **Default**: `/root/jayson_3d/blender/`
- **Target**: `<project>/_incoming/`
- **GLB files**: ~1.5-2KB (placeholder primitives)

## Known Gotchas
- Blender saves to HOME directory, not project directory - **always move files after generation**
- Generated GLBs are basic primitives (boxes, cylinders) - placeholders need refinement
- No texture baking by default - materials are simple colors

## Example Usage
```bash
# Generate all P0 assets
python3 /tools/blender/generate_assets.py

# Check output
ls -la /root/jayson_3d/blender/*.glb

# Move to project
mv /root/jayson_3d/blender/*.glb <project>/_incoming/
```

## Quality Notes
These generated assets are low-poly placeholders suitable for:
- Prototyping
- Visual validation
- Unity scene assembly
- Early testing

Postpone detailed artist work until after vertical slice validation.