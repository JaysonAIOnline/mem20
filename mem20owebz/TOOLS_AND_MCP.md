# Jayson — Tools + MCP (Streamable HTTP) Guide

This file gives you everything needed to activate the tools and connect modern MCP servers.

---

## 1. How to add MCP Servers (New Streamable HTTP Protocol)

Open WebUI has **native MCP support** (v0.6.31+).

### Steps

1. Go to **Admin Panel → Settings → Integrations** (sometimes called External Tools / Tool Servers)
2. Click **+ Add Server**
3. Set these values carefully:

| Field | Value |
|-------|-------|
| **Type** | `MCP (Streamable HTTP)`  ← **important** |
| **URL** | `http://your-mcp-server:port/mcp` |
| **Auth** | None / Bearer / OAuth 2.1 (as required) |
| **ID** | short lowercase name (e.g. `blender`, `filesystem`) |
| **Name** | Human readable name |

4. Save. Restart Open WebUI if prompted.

> **Common mistake:** Choosing "OpenAPI" instead of **"MCP (Streamable HTTP)"**.  
> Always pick the MCP Streamable HTTP type for modern MCP servers.

### Example URLs

- Local MCP server running on host: `http://host.docker.internal:8000/mcp`
- Another container on same network: `http://mcp-blender:8000/mcp`
- Remote: `https://your-domain.com/mcp`

You can add as many MCP servers as you want.  
They appear as tools the model can call.

---

## 2. Recommended MCP Servers to add

You can connect any Streamable HTTP MCP server. Useful ones for Jayson:

- Filesystem MCP
- GitHub MCP
- Browser / Playwright MCP
- Database MCP
- Custom Blender MCP (if you build one)
- Any official or community MCP that speaks Streamable HTTP

---

## 3. Native Open WebUI Tools (Blender + 3D + Video)

These are Python Tools/Functions you paste directly into Open WebUI.

### How to install a Tool

1. Admin Panel → **Functions** or **Tools**
2. Create new
3. Paste the code below
4. Enable it
5. Make sure the model has tool calling enabled

---

### Tool A — Blender Control (Core)

```python
"""
title: Blender Control
author: Jayson
version: 1.0.0
description: Create objects, materials, cameras, render and export from Blender
requirements: 
"""

import subprocess
import tempfile
import os
from pathlib import Path

BLENDER = "blender"
OUT = Path.home() / "jayson_3d" / "blender"
OUT.mkdir(parents=True, exist_ok=True)

def run_blender(code: str, timeout=180):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        path = f.name
    try:
        r = subprocess.run([BLENDER, "--background", "--python", path],
                           capture_output=True, text=True, timeout=timeout)
        return {"success": r.returncode == 0, "stdout": r.stdout[-2000:], "stderr": r.stderr[-1000:]}
    finally:
        os.unlink(path)

class Tools:
    def create_cube(self, name: str = "Cube", size: float = 2.0) -> str:
        """Create a cube in Blender"""
        code = f'''
import bpy
bpy.ops.mesh.primitive_cube_add(size={size})
bpy.context.active_object.name = "{name}"
bpy.ops.wm.save_as_mainfile(filepath=r"{OUT}/scene.blend")
print("Created {name}")
'''
        return str(run_blender(code))

    def render_scene(self, filename: str = "render.png") -> str:
        """Render the current Blender scene"""
        out = OUT / filename
        code = f'''
import bpy
bpy.context.scene.render.filepath = r"{out}"
bpy.ops.render.render(write_still=True)
print("Rendered to {out}")
'''
        return str(run_blender(code, timeout=300))

    def export_glb(self, filename: str = "model.glb") -> str:
        """Export current scene as GLB"""
        out = OUT / filename
        code = f'''
import bpy
bpy.ops.export_scene.gltf(filepath=r"{out}", export_format='GLB')
print("Exported {out}")
'''
        return str(run_blender(code))

    def run_bpy(self, python_code: str) -> str:
        """Run arbitrary Blender Python (bpy) code. Full power."""
        code = f'''
import bpy
from mathutils import Vector, Euler
{python_code}
bpy.ops.wm.save_as_mainfile(filepath=r"{OUT}/scene.blend")
print("Script finished")
'''
        return str(run_blender(code, timeout=300))
```

---

### Tool B — 3D Model → Screenshots + Description

Use the more complete version from `pipelines/3d_screenshots/pipeline.py`.  
You can wrap the main function `model_to_screenshots_and_description` as a Tool the same way.

---

### Tool C — Video Understanding

Wrap `full_video_understanding` from `pipelines/video_understanding/pipeline.py` the same way.

---

## 4. Blender API + Unity API style

The tools above already expose a clean “API” that Jayson can call:

**Blender side**
- `create_cube`, `render_scene`, `export_glb`, `run_bpy` (full bpy access)

**Unity side**
- Use the `import_asset` tool to bring any GLB/FBX into a Unity project
- Then open the project

This is the practical way to give Jayson both Blender and Unity power without needing a live running Editor API.

---

## 5. Quick Checklist

- [ ] Start full stack (`docker-compose.full.yml`)
- [ ] Add MCP servers via **Admin → Integrations → MCP (Streamable HTTP)**
- [ ] Install the Blender Tool above
- [ ] (Optional) Install 3D screenshots + Video tools
- [ ] Enable tool calling on your main model
- [ ] Test: “Create a red metallic cube and render it”

Jayson is now ready for modern MCP servers + real 3D tool use.
