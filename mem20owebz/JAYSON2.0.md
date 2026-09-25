# Jayson 2.0 — Working Branch

**All new edits go into 2.0 until we advance to 3.0.**

| Version | Zip | Role |
|---------|-----|------|
| 1.0 | `jayson-1.0.zip` | Frozen snapshot |
| **2.0** | `jayson-2.0.zip` | **Active development** |
| 3.0 | (future) | Next milestone — cloud assembly / Resource Bridge |
| 4.0 | (future) | **Unreal Engine pipeline** after a dedicated SSD (256–512 GB typical; 1 TB only for fat workstation) |

---

## 2.0 policy

1. Edit `jayson-openwebui/` → repack **`jayson-2.0.zip` only**
2. Leave `jayson-1.0.zip` frozen
3. Log changes in **Changelog** below
4. “Advance to 3.0” freezes 2.0 and opens 3.0
5. **Unreal is 4.0** — do not pull it into 2.0 or 3.0

---

## Changelog

### 2.0-beta1 — Integration beta
- Unified `INTEGRATION.md` + rewritten START_HERE / README / pipeline indexes / system prompt
- Extras: save/settings, localization, accessibility, store listing, modding/DLC, analytics
- Scripts: `lint_manifest.py`, `status_dashboard.py`
- CI sketch: Godot headless export
- Resource Bridge **catalog** (config + tool; FastAPI service stays 3.0)
- New tools: accessibility, store listing, status dashboard, resource bridge
- Version stamp: `VERSION` = `2.0-beta1`
- Artifact: **`jayson-2.0-beta1.zip`**

### 2.0.7 — Unreal disk size corrected
- Unreal is **not** ~1 TB by default
- Binary editor typically **40–70 GB** (trimmed) or **~100–130 GB** during default install
- Source builds **~160–350 GB**; 1 TB is a **full workstation** (multiple versions + DDC + fat projects), not the engine

### 2.0.6 — Unreal pushed to 4.0
- Unreal Engine pipeline **deferred to 4.0** (was 3.0)
- 3.0 stays cloud assembly / Resource Bridge / heavier integration

### 2.0.5 — Cloud assembly plan
- Added `CLOUD_ASSEMBLY.md`: free-tier inventory, best practices, interweave architecture, Jayson Resource Bridge (2nd bridge)

### 2.0.4 — Godot export pipeline investigation
- Added `pipelines/games/godot_export.md` (CLI, templates, Android/Quest, credentials, CI)
- Maps Jayson export matrix → real Godot 4 presets

### 2.0.3 — Unreal deferred (now superseded by 2.0.6 → 4.0)
- Originally tracked for 3.0; **moved to 4.0**
- 2.0 engines: Godot, Unity, Blender DCC

### 2.0.2 — Engine required on production package
- `PRODUCTION_PACKAGE_TEMPLATE.md`: **primary engine is REQUIRED** (§1.6 + §11.1)
- Production run Stage 0 PACKAGE_LOCK checks engine selection before ASSEMBLY

### 2.0.1 — Godot + roadmap
- **Godot 4.x integration:** `tools/godot/godot_tools.py`, `pipelines/games/godot_pipeline.md`
- Same asset_assembly / production_run binding as Unity path
- Documented high-value 2.0 addition candidates (below)

### 2.0.0 — Branch opened
- Copied from 1.0 + this policy file

---

## Engine matrix (current)

| Engine / DCC | Status |
|--------------|--------|
| Blender | Tools + 3D refine pipelines (2.0) |
| Unity | Tools + import notes (2.0) |
| **Godot 4** | Skeleton, import plan, export presets, slice checklist (2.0) |
| Unreal | **Deferred to 4.0** — dedicated SSD; not a free-tier fit |

---

## High-value additions for 2.0 (priority order)

### Already strong from 1.0
Production package, production run orchestrator, QA + 94% polish, assembly→installable, genres, bridge/router.

### Add next (recommended)

1. **Save/load + settings schema** pipeline (data tables the TechLead always reinvents)  
3. **Localization pack** pipeline (string tables, VO per locale)  
4. **Accessibility pass** agent (colorblind, subtitles, remapping, comfort)  
5. **CI build script templates** (Godot headless + Unity batchmode smoke builds)  
6. **Analytics/event dictionary** (optional — design events before code)  
7. **Modding / data-only DLC layout** (if you want post-ship content without full rebuild)  
8. **Automated manifest linter** (script: CSV paths exist, P0 all `validated`)  
9. **Store listing pack** (icons, screenshots, short/long description from package)  
10. **One-click “status dashboard” markdown** generator (stage, fidelity scores, blockers)

### 3.0 territory
- Cloud assembly execution (provision primary VM + block, R2 releases)
- Jayson Resource Bridge (2nd bridge for storage/compute)
- Heavier multi-cloud integration

### 4.0 territory
- **Unreal Engine pipeline** (skeleton, content rules, packing, export)
- Disk: **256–512 GB SSD** is enough for one binary editor + a slice; **~1 TB** only if source + multiple versions + DDC + fat content
- Full console cert automation (needs NDAs/SDKs on your hardware)
- Fully autonomous multi-day runs without human gates
- Real-time collaborative multi-user production board

### Storage note (Unreal — measured, not folklore)

| Setup | Typical disk |
|-------|----------------|
| Binary editor, Windows-only, trimmed | **40–70 GB** installed |
| Default launcher install (extra platforms) | **~100–130 GB** (download + extract overlap) |
| Source build of one version | **~160–350 GB** |
| Full workstation (2–3 versions + DDC + samples + projects) | Can approach **~1 TB** |

Epic’s installer reports the size of **checked components**. Community guidance: put the editor on a **256–512 GB SSD**.

Unreal stays **4.0** because it still wants a **dedicated fast disk + serious RAM/GPU**, not because the engine itself is 1 TB. Use Godot/Unity for 2.0 / 3.0. When a suitable SSD is mounted, say **advance to 4.0**.

---

## How to use Godot path

1. Production run → Stage 4 ASSEMBLY  
2. Call / follow `godot_project_skeleton`  
3. Import only **validated** assets (`godot_import_plan`)  
4. Slice scene checklist → QA Build  
5. `godot_export_presets` for your platform matrix  
6. Continue Stage 5–6 polish + release  

See `pipelines/games/godot_pipeline.md`.

---

## Read order

1. `START_HERE.md`  
2. `JAYSON2.0.md` (this file)  
3. `JAYSON1.0.md`  
4. `DEPENDENCIES.md` / `CREDITS.md`  
5. `FIRST_GAME_WALKTHROUGH.md`  
6. `pipelines/games/production_run.md`

---

## Standing goals (do not drop)

1. **Work on Jayson always** — product line stays active; 2.0 is the working tree until 3.0
2. **Cloud assembly** — see **`CLOUD_ASSEMBLY.md`**. **Owner has 2 Azure keys + 2 OCI keys.**
3. **Jayson 3.0** — cloud assembly / Resource Bridge
4. **Jayson 4.0** — Unreal pipeline after a dedicated SSD exists (256–512 GB typical)

When prioritising work: Jayson product first, cloud when needed to unblock engines/builds, Unreal only at 4.0.
