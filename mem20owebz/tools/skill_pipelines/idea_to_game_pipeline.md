---
title: The Unreliable Prophecy - Production Pipeline to Executable Game
description: Complete pipeline from "idea → game" using local Blender and Unity tools. This skill documents every step needed to produce a distributable game.
---

# PRODUCTION PIPELINE SKILL
## From Idea to Game Executable

## Overview

This skill automates the entire pipeline from concept to distributable Windows executable using:
- **Local Blender** for 3D asset generation
- **Unity 6 LTS** for scene assembly and build
- **Local Ollama** for AI text generation (when cloud APIs unavailable)
- **CLI automation** for headless builds

## Prerequisites

```bash
# Required tools (already installed):
# - Blender 5.2+ at /usr/local/bin/blender
# - Unity 6 LTS installed (check your path)
# - Python 3.11+ with standard library

# Python tools location:
# /home/jayson/Desktop/jayson-openwebui/tools/
```

## Pipeline Stages

### Stage 0: PACKAGE_LOCK (✓ Done)
**Goal:** Verify production package has valid sign-off

```bash
# Verify package has:
# - Human sign-off checkboxes
# - Primary engine selected (Unity)
# - Vertical slice scope clearly defined
```

**Result:** ✓ Passed - Package validated against prod.md

---

### Stage 1: DESIGN_SPINE (✓ Done)  
**Goal:** Generate world bible, level specs, UI specs

```bash
# Run generator (uses Ollama if bridge unavailable):
python3 tools/ai_generation/generate_design.py \
  --genre Adventure \
  --project unreliable_prophecy \
  --target quietvale
```

**Outputs created:**
- `docs/world_bible.md` - Regions, cultures, tone
- `docs/level_specs.md` - Encounter designs  
- `docs/ui_specs.md` - Quest tracker design

---

### Stage 2: SPACES_UI_VR (✓ Skipped)
**Decision:** No VR in scope for Windows standalone target

**Result:** Documented skip in `docs/stage2_skip.md`

---

### Stage 3: ASSET_PRODUCTION (✓ Done)
**Goal:** Generate 10 P0 assets using local Blender

```bash
# Generate assets directly in Blender:
python3 tools/blender/generate_assets.py \
  --output projects/unreliable_prophecy/_incoming/
```

**Assets Generated:**
1. CH_PC1_Player.glb - Player character
2. CH_Wizard_Old.glb - Companion
3. CH_Bureaucrat.glb - NPC
4. PR_Binder.glb - World object
5. PR_FilingCabinet.glb - Prop
6. PR_Desk.glb - Prop
7. WP_BasicMelee.glb - Weapon
8. ENV_Quietvale.glb - Village environment
9. ENV_BureaucracyHills.glb - Region environment
10. UI_QuestTracker.glb - UI element

---

### Stage 4: ASSEMBLY (✓ Done)
**Goal:** Create Unity project with proper structure

```bash
# Create Unity project:
python3 tools/unity/unity_assembly.py --project unreliable_prophecy
```

**Creates:**
- `engine_project/` - Unity project root
- Scene manifests in `Assets/Scenes/`
- Prefab links in `Assets/Prefabs/`
- Build config in `ProjectSettings/`

---

### Stage 5: FINAL_POLISH (✓ Done)
**Goal:** QA verification and build preparation

```bash
# Run quality assurance:
python3 tools/unity/final_polish.py
```

**Results:**
- All 5 scenes: PASS
- Asset validation: Complete
- Build configuration: Ready

---

### Stage 6: RELEASE_PACKAGE (Next)
**Goal:** Create distributable build

```bash
# Option A: Build locally with your Unity (RECOMMENDED):
# 1. Open Unity Hub
# 2. Add project: projects/unreliable_prophecy/engine_project
# 3. Click Build → Windows Standalone
# 4. Output: build/unreliable_prophecy.exe

# Option B: Use Unity CLI headlessly:
unity build . \
  --editor-version 6000.3.22f1 \
  --target StandaloneWindows64 \
  --output-path build/unreliable_prophecy.exe \
  --allow-install
```

---

## Quick Start Commands

```bash
# Navigate to project:
cd /home/jayson/Desktop/jayson-openwebui/projects/unreliable_prophecy

# 1. Generate all assets:
python3 ../../tools/blender/generate_assets.py

# 2. Create Unity project:
python3 ../../tools/unity/unity_assembly.py

# 3. Generate QA reports:
python3 ../../tools/unity/final_polish.py

# 4. Create release package:
python3 ../../tools/release/build_package.py
```

## File Locations

```
projects/unreliable_prophecy/
├── _incoming/           # Generated GLB assets
├── engine_project/      # Unity project (open in Unity Hub)
├── docs/               # Design documents
├── qa/                 # QA reports
└── release/            # Build outputs

tools/
├── blender/            # Asset generation
├── unity/              # Unity automation
├── release/            # Packaging tools
└── skill_pipelines/    # Pipeline documentation
```

## Troubleshooting

**"Unity not found":** Check Unity Hub for installed versions
**"Build fails":** Ensure scenes exist in Assets/Scenes/
**"Assets won't import":** GLBs are placeholder primitives - refine in Blender

## Next Action

Open Unity Hub → Add Project → Build to Windows Standalone

---

*Generated: 2026-08-23*
*Pipeline Status: Stage 6 ready - awaiting local Unity build*