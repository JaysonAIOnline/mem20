# The Unreliable Prophecy - Unity Project

**Version:** 0.5.0_VerticalSlice  
**Engine:** Unity 6 LTS (6000.0.52f1) + URP  
**Target:** Windows Standalone x86_64 + Linux x86_64

## Project Structure

```
Assets/
├── Scripts/          # C# gameplay scripts
├── Scenes/           # Unity scenes (Boot, MainMenu, Quietvale, BureaucracyHills, CombatTest)
├── Prefabs/          # Prefabs for player, companions, NPCs, enemies, props, UI
├── Materials/        # URP materials (from UP_Materials.blend)
├── Models/           # Imported GLB assets
│   ├── Characters/
│   ├── Creatures/
│   ├── Props/
│   ├── Weapons/
│   └── Environments/
├── UI/               # UI prefabs and assets
├── Resources/        # Runtime-loadable assets
├── Audio/            # VO, Music, SFX
├── Animation/        # Animation clips and controllers
├── Shaders/          # Custom shaders
├── VFX/              # Particle effects
└── Editor/           # Editor scripts (BuildProject.cs)

ProjectSettings/
├── ProjectVersion.txt
└── build_config.json
```

## Vertical Slice Content (v0.5.0)

**Scenes:**
1. **Boot** - Manager initialization
2. **MainMenu** - Title screen with save slots (3 slots, "Empty – Awaiting Documentation.")
3. **Quietvale** - Tutorial village (10 steps: wake → exit → square → Bureaucrat → Binder → path → first enemy → ability → tracker → leave gate)
4. **BureaucracyHills** - First region (critical path + 1 side quest + 1 amendment delivery)
5. **CombatTest** - Enemy testing

**P0 Assets (Generated via Blender Advanced Pipeline):**
- **Characters (4):** CH_PC1, CH_Wizard, CH_Companion2, CH_Bureaucrat
- **Creatures (2):** CR_MisfiledSkeleton, CR_InkBlot
- **Props (4):** PR_Binder, PR_FilingCabinet, PR_Desk, PR_Forms
- **Weapons (1):** WP_BasicMelee
- **Environments (2):** ENV_Quietvale, ENV_Hills

**Systems Implemented:**
- PlayerController (3rd person, KBM + gamepad, sprint, jump, abilities, interaction)
- QuestManager (Quest Tracker live updates, main/side quests, amendments)
- SaveManager (3 slots, autosave, round-trip, version migration)
- InventoryManager (≥5 distinct items, procedural loot)
- BinderManager (Prophecy Binder UI, amendments, Guidebook entries)
- CompanionManager (Follow + banter, cooldown 90-120s, ≥3 lines each)
- EnemyAI (Idle→Detect→Chase→Attack→Paperwork Barrage→Flee, Compliance inspects first)
- InteractionSystem (Talk, Inspect, Use, Collect, Sign, Deliver, OpenBinder, Amendment)

## Build Instructions

### Option 1: Unity Editor (Recommended)
1. Open Unity Hub
2. Click "Add" → Browse to `engine_project/`
3. Open project (Unity 6000.0.52f1 or compatible LTS)
4. Run **Tools → Unreliable Prophecy → Setup Project** to import assets and create scenes/prefabs
5. Build: **Tools → Unreliable Prophecy → Build Windows** or **Build Linux** or **Build Both**

### Option 2: Command Line (Headless/Batch Mode)
```bash
# From engine_project directory

# Setup project (import assets, create scenes/prefabs)
/Applications/Unity/Hub/Editor/6000.0.52f1/Unity.app/Contents/MacOS/Unity \
  -batchmode \
  -projectPath . \
  -executeMethod BuildProject.SetupProject \
  -quit

# Build Windows x64
/Applications/Unity/Hub/Editor/6000.0.52f1/Unity.app/Contents/MacOS/Unity \
  -batchmode \
  -projectPath . \
  -executeMethod BuildProject.BuildWindows \
  -quit

# Build Linux x64
/Applications/Unity/Hub/Editor/6000.0.52f1/Unity.app/Contents/MacOS/Unity \
  -batchmode \
  -projectPath . \
  -executeMethod BuildProject.BuildLinux \
  -quit

# Build Both (Windows + Linux)
/Applications/Unity/Hub/Editor/6000.0.52f1/Unity.app/Contents/MacOS/Unity \
  -batchmode \
  -projectPath . \
  -executeMethod BuildProject.BuildBoth \
  -quit
```

### Option 3: Batch Script (Linux/macOS)
```bash
# From project root
chmod +x ../build_both.sh
../build_both.sh both    # Build both Windows and Linux
../build_both.sh windows # Windows only
../build_both.sh linux   # Linux only
```

## Acceptance Criteria (Production Package §12.2)

1. ✅ New Game → finish Quietvale → Binder + tutorial flags correct
2. ✅ Hills → amendment → side quest → loot procedural item
3. ✅ Save → quit → load → state intact (position, quests, inventory, amendments)
4. ✅ ≥3 companion/Guidebook lines fire
5. ✅ Die once, respawn correctly
6. ✅ Reach end of Hills critical path with zero critical console errors

## Known Issues / Out of Scope (v0.5.0)

- Forest of Unhelpful Trees, City of Forms, Overflow Archives, Ruins, Final Zone
- Full companion roster and personal quests
- New Game+, secret ending, departmental reputation UI
- Full music implementation, heavy VFX polish
- Accessibility beyond basic subtitles
- Multiplayer, VR, mobile, console ports

## Asset Pipeline

All 3D assets generated via **Blender Advanced Pipeline** (from 33.zip):
- `tools/blender/blender_advanced_pipeline/` - Geometry Nodes, materials, export, RPG recipes
- `tools/blender/generate_p0_assets.py` - P0 asset generation script
- Materials: `art/materials/UP_Materials.blend` (Parchment, Wood, MetalStamp, Ink, Skin, Robes, Bone, InkCreature)

## Manifest

`manifests/assets_master.csv` - 25 assets tracked, 16 P0 validated, rest P1/P2 incoming.

## QA Checklist

`qa/checklist.json` - 4 critical path items, 4 quality gates, 3 sign-offs.