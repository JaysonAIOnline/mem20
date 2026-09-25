# Godot Pipeline (Jayson 2.0)

Parallel to Unity/Blender paths — same assembly rules, Godot 4.x as the engine.

## When to choose Godot
- 2D, 3D, or hybrid without license fees
- Fast iteration, one executable editor
- Desktop + Android (+ Quest via Android) exports

## Binding to production run
| Stage | Godot action |
|-------|----------------|
| ASSET_PRODUCTION | Still use `_incoming` → validate → manifest |
| ASSEMBLY | `godot_project_skeleton` → import validated only → slice scene |
| RELEASE_PACKAGE | `godot_export_presets` → `builds/<platform>/` → installer notes |

## Steps
1. Tool: `godot_project_skeleton`
2. Create Godot 4 project under `projects/<game>/engine_project/`
3. `godot_import_plan` for P0 asset IDs from `assets_master.csv`
4. Build vertical slice scene (`godot_slice_scene_checklist`)
5. QA Build (cold critical path)
6. Export presets per platform matrix
7. Final polish + production_run_advance

## CLI hints
```bash
godot --path projects/<game>/engine_project --editor
godot --path projects/<game>/engine_project --headless --quit
```

## Does not replace
- Platform SDKs for console / store signing  
- Asset_assembly quarantine rules  


## Export deep-dive
See **`godot_export.md`** for templates, CLI, Android/Quest, credentials, and CI notes investigated for 2.0.
