# Text / Image → 3D Pipeline (Enhanced)

Extra effort path for turning text or pictures into usable 3D assets.

## Recommended order (2026)

### A. Text → 3D
1. Write a precise prompt (shape, materials, style, “single clean object, centered”).
2. Call the **Text & Image to 3D** tool (`text_to_3d`) with provider:
   - **Luma** (Dream Machine / Genie) – cinematic quality
   - **Meshy** – dedicated 3D, good retopo
   - **Tripo** – fast characters/objects
3. Download `.glb`
4. Refine in Blender (Jayson Blender tools)
5. Run **3D Screenshots** tool for multi-angle review
6. Iterate prompt or sculpt until good enough
7. Optional: import to Unity

### B. Image → 3D
1. Upload image (or describe it clearly)
2. Call `image_to_3d` on the same tool
3. Same refinement loop as above

## Provider keys (add to `.env` or tool valves)

```bash
LUMA_API_KEY=
MESHY_API_KEY=
TRIPO_API_KEY=
```

## Quality tips
- One main subject per generation
- Mention topology hopes (“clean quad mesh”, “game ready”)
- Always review with screenshots before declaring done
- Multiple iterations beat one perfect first try

## Related tools
- `tools/openwebui_tools/text_image_to_3d_tool.py`
- `tools/openwebui_tools/3d_screenshots_tool.py`
- `tools/blender/blender_tools.py`
- `tools/unity/unity_tools.py`
