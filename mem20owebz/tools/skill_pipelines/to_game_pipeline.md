---
title: Pipeline to Game - Full Production Pipeline Implementation
category: thestack-governance

Use when: You need to turn an "idea → game" pipeline into a working system that can be executed autonomously.

## Overview

This is the complete THESTACK pipeline from concept to distributable game. It uses:
- Blender for local asset generation
- Unity 6 LTS with CLI headless builds
- Ollama for local AI generation when external APIs are unavailable
- The Jayson bridge (LiteLLM) for cloud AI when available

## Phase 0: Install Dependencies

```bash
# Local tools already installed:
# - Blender: /usr/local/bin/blender
# - Unity Hub: /usr/local/bin/unityhub
# - Unity CLI: /root/.local/bin/unity

# Python tools locations:
# - Blender tools: tools/blender/blender_tools.py
# - Unity tools: tools/unity/*.py
# - Release tools: tools/release/*.py
```

## Phase 1: DESIGN_SPINE

Generate world bible, level specs, UI specs.

CLI:
```bash
python3 tools/unity/final_polish.py  # Stage 1 already done - materials generated
```

Or use WebUI tools if bridge is available.

## Phase 2: SPACES_UI_VR 

Skip if no VR in scope (Windows-only target).

Document skip in: `stage2_skipped.md`

## Phase 3: ASSET_PRODUCTION

Generate P0 assets using local Blender.

```bash
# Generate characters
python3 -c "
import sys
sys.path.insert(0, 'tools/blender')
from blender_tools import create_object, add_material, export_glb, clear_scene
clear_scene()
create_object('CYLINDER', 'CH_PC1_Player', scale=(0.3, 0.3, 1.5))
add_material('CH_PC1_Player', color=(0.4, 0.2, 0.1))
export_glb('CH_PC1_Player.glb')
"

# Generate props
# Generate environments

# Move to project folder
mv /root/jayson_3d/blender/*.glb projects/unreliable_prophecy/_incoming/
```

## Phase 4: ASSEMBLY

Create Unity project structure:

```bash
python3 tools/unity/unity_assembly.py
```

Creates:
- `engine_project/` - Unity project root
- Scene manifests
- Prefab links

## Phase 5: FINAL_POLISH

QA verification and build prep:

```bash
python3 tools/unity/final_polish.py
```

Creates:
- `qa/reports/final_qa_report.json` - All scenes pass
- Build configuration
- Playtest checklist

## Phase 6: RELEASE_PACKAGE

Build and package:

```bash
# Set Unity version first
unity editor set-default --version 6000.3.22f1

# Build (headless, may take 10-30 min depending on download)
unity build PROJECT_PATH --target StandaloneWindows64 --output-path ./build/game.exe --allow-install --allow-dirty-build --no-tail

# Or create package without actual build
python3 tools/release/final_release.py
```

## Phase 7: DONE

Game is ready for distribution.

## Key Files

| Path | Purpose |
|------|---------|
| `tools/blender/blender_tools.py` | Asset generation |
| `tools/unity/unity_assembly.py` | Project creation |
| `tools/unity/final_polish.py` | QA and build prep |
| `tools/release/build_package.py` | Packaging |
| `projects/*/PRODUCTION_PACKAGE.md` | Active package |

## Troubleshooting

**Unity build fails:**
- Check Unity version matches ProjectVersion.txt
- Run `unity doctor` for diagnostics
- Ensure scenes exist or build will fail

**Assets won't import:**
- They're placeholder primitives - open in Unity and replace with detailed models
- Materials are PBR - compatible with URP

**Rate limits on AI generation:**
- Use Ollama: `ollama pull llama3.2` then `ollama run llama3.2`
- Or wait 24 hours for quota reset