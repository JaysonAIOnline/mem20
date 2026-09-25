# Jayson ↔ Blender Integration

Goal: Let Jayson fully manipulate Blender (create objects, materials, lighting, cameras, render, export).

## Architecture (Recommended)

```
User → Jayson (Open WebUI)
         ↓
   Tool / Function call
         ↓
   Python script generated
         ↓
   Blender headless (--background --python script.py)
         ↓
   Result (render image / .glb / .blend / log)
         ↓
   Back to chat
```

## Requirements on the host machine

1. **Blender 4.x** installed and available in PATH
   ```bash
   blender --version
   ```

2. Preferably a GPU for faster rendering (Cycles/EEVEE)

3. Open WebUI must be able to execute commands on the host  
   (easiest via **Open Terminal** feature or custom tools that call `subprocess`)

## How Jayson will control Blender

### Method 1 – High-level Tools (Recommended)
We create specific tools such as:

- `blender_create_object`
- `blender_add_material`
- `blender_set_camera`
- `blender_render`
- `blender_export_glb`
- `blender_run_script` (raw Python power)

### Method 2 – Free-form Python
Jayson writes full `bpy` scripts and executes them.  
This gives almost complete control.

### Method 3 – Open Terminal
If you enable Open Terminal / Computer feature, Jayson can directly run:
```bash
blender --background --python /tmp/scene.py
```

## Current Limitations

- No real-time interactive viewport streaming (yet)
- Complex animations and physics need careful scripting
- Very large scenes can be slow without GPU

## Next Steps I can build for you

1. Ready-to-install Open WebUI **Tools / Functions** for Blender
2. A library of high-level commands
3. Automatic screenshot + description after every major change
4. GLB / FBX / USD export helpers
5. Material and lighting presets

Tell me how deep you want to go and I will generate the actual tool code.
