# Jayson 2.0-beta1 — Integration map

How the pieces lock together. If a doc disagrees with this file, **this file + `JAYSON2.0.md` win**.

## Version line

| Artifact | Role |
|----------|------|
| `jayson-1.0.zip` | Frozen 1.0 |
| `jayson-2.0.zip` | Working tree |
| **`jayson-2.0-beta1.zip`** | This integrated beta |

3.0 = cloud Resource Bridge service. 4.0 = Unreal (256–512 GB SSD typical).

## Control plane vs muscle

```
Human
  → Production Package (HUMAN sections)
    → Production Run Orchestrator (stages 0–7, QA to advance)
      → Genre / Godot / Unity / Blender / creative tools
        → asset_assembly (manifest is law)
          → Final polish (≥94%)
            → builds/ → release/installer/
              → Resource Bridge publishes to R2 (3.0)
```

Jayson chat UI can live on **OCI Always Free**. Engines need a **dedicated SSD**. Object storage (R2) is for **releases**, not Unreal DDC.

## Stage extras (optional, do not skip spine)

| When | Extra pipeline |
|------|----------------|
| Design | save_load_settings, analytics_events |
| Spaces | accessibility (esp. VR) |
| Assets | localization (if extra locales) |
| Assembly | `scripts/lint_manifest.py` |
| Polish | accessibility_tool + final_polish |
| Release | store_listing, godot_export, status dashboard |

## Engines (2.0-beta1)

Godot + Unity + Blender. Unreal = **4.0**.

## Hard rules

1. No stage skip without QA PASS  
2. No build from `_incoming`  
3. Manifest CSV is the only ship list  
4. Engine choice is required on the package  
5. Do not merge free-tier disks into one volume  
