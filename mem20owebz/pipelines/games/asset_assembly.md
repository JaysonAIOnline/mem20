# Asset Assembly & Management Pipeline

**Goal:** After a successful production run, turn scattered AI outputs into a **clean, installable game**—not 30,000 loose files and not 300 assets dumped in one folder.

## Core principle

```
idea → production package → pipelines → staged assets → assembled project → build → installable package
```

Every asset gets an **ID**, a **home folder**, and a **manifest entry** before it is allowed near a build.

---

## 1. Canonical project layout

Use this tree (engine-agnostic). Map folders into Unity/Unreal/Godot as needed.

```
projects/<game_name>/
├── PRODUCTION_PACKAGE.md          # source of truth
├── manifests/
│   ├── assets_master.csv          # every asset ID, path, status
│   ├── scenes_index.json
│   └── build_manifest.json
├── design/
│   ├── narrative/
│   ├── systems/
│   ├── levels/
│   └── ui/
├── art/
│   ├── characters/
│   ├── creatures/
│   ├── props/
│   ├── weapons/
│   ├── vehicles/
│   ├── environments/
│   │   └── <region_id>/
│   ├── materials/
│   ├── textures/
│   ├── ui/
│   ├── vfx/
│   └── _incoming/                 # quarantine for new AI dumps
├── audio/
│   ├── voice/<character_id>/
│   ├── music/
│   ├── sfx/
│   └── _incoming/
├── levels/
│   └── <level_id>/
│       ├── blockout/
│       ├── art/
│       └── data/
├── code/ or engine_project/       # actual game project
├── builds/
│   ├── windows/
│   ├── linux/
│   ├── android/
│   └── quest/
├── qa/
│   ├── reports/
│   └── playtest_notes/
└── release/
    ├── installer/                 # final installable artifacts
    └── notes/
```

**Rule:** Nothing goes straight into `engine_project` from a generator. It lands in `_incoming/`, gets IDed, validated, then moved.

---

## 2. Asset ID scheme

Format: `<TYPE>_<NAME>_<VARIANT>`

| Prefix | Type |
|--------|------|
| CH_ | Character |
| CR_ | Creature |
| PR_ | Prop |
| WP_ | Weapon |
| VH_ | Vehicle |
| ENV_ | Environment kit piece |
| MAT_ | Material |
| TEX_ | Texture set |
| UI_ | UI element |
| FX_ | VFX |
| VO_ | Voice line set |
| MUS_ | Music track |
| SFX_ | Sound effect |
| LVL_ | Level |
| SCN_ | Scene |

Example: `CH_PC1_HERO_A`, `PR_CRATE_METAL_01`, `LVL_DOCKS_01`

---

## 3. Master manifest (`assets_master.csv`)

Required columns:

```
asset_id,type,name,path,source,package_section,priority,status,qa_status,notes
```

Statuses: `incoming` → `validated` → `integrated` → `ship` | `cut`

**Pipeline step:** every generator output must append/update a row before handoff.

---

## 4. Assembly stages

### Stage A — Intake
1. Drop AI outputs into `art/_incoming` or `audio/_incoming`
2. Run naming pass (assign asset_id)
3. Deduplicate (same mesh renamed 12 times → one canonical)
4. Record in manifest as `incoming`

### Stage B — Validate
1. QA Art/3D or QA Audio on each P0 item
2. Check scale, origin, poly budget, naming
3. Status → `validated` or back to rework

### Stage C — Integrate
1. Move to canonical folder under `art/` / `audio/` / `levels/`
2. Import into engine project **via script or documented steps**
3. Hook into scene / prefab / data table
4. Status → `integrated`

### Stage D — Scene assembly
1. Build scenes only from **integrated** assets
2. Update `scenes_index.json`
3. Vertical-slice scene must boot with P0 only

### Stage E — Build packaging
1. Engine build → `builds/<platform>/`
2. Strip debug/dev-only content
3. Write `build_manifest.json` (version, commit, asset set hash)
4. QA Build + QA Export

### Stage F — Installable release
| Platform | Package form |
|----------|----------------|
| Windows | Installer (e.g. NSIS/Inno) or portable zip + README |
| Linux | AppImage or tar.gz + launch script |
| Android | Signed APK/AAB |
| Quest | Store package / sideload APK per Meta process |

Output goes to `release/installer/` with:
- `README_PLAYER.md` (how to install/play)
- `KNOWN_ISSUES.md`
- version number matching production milestone

---

## 5. Agents / tools for assembly

| Role | Job |
|------|-----|
| IntakeLibrarian | Sort `_incoming`, assign IDs, update CSV |
| Deduper | Find duplicate assets |
| IntegrationTech | Move validated → engine, wire references |
| SceneAssembler | Compose levels from integrated assets only |
| BuildEngineer | Produce platform builds |
| ReleaseManager | Create installable package + player-facing docs |
| QAGateCaptain | Block release if manifest has open Criticals |

Use Tight Agent Loop on each stage; Final Polish before Stage F.

---

## 6. Anti-chaos rules (non-negotiable)

1. **No flat folders** of hundreds of files  
2. **No build from `_incoming`**  
3. **P0 assets only** in vertical slice builds  
4. **Manifest is law** — if it’s not in the CSV, it doesn’t ship  
5. **One owner path per asset_id**  
6. **Human signs** production package + final release checklist  

---

## 7. Success definition: “Idea to game”

You are done when:

- [ ] Production package [HUMAN] sections signed  
- [ ] Vertical slice criteria met  
- [ ] Final polish ≥ 94% fidelity, 0 Criticals  
- [ ] `assets_master.csv` has every shipped asset  
- [ ] Installable package exists under `release/installer/`  
- [ ] A cold player can install and complete the critical path using only `README_PLAYER.md`  
