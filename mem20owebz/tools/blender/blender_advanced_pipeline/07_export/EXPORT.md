# Stage 7 – Export Pipeline

## Targets

| Target          | Format     | Notes                                      |
|-----------------|------------|--------------------------------------------|
| Game Engines    | glTF 2.0 / FBX | LODs, correct scale, applied transforms |
| VFX / Film      | Alembic    | High poly + animation if any               |
| USD (optional)  | USD / USDA | Full scene hierarchy                       |
| Asset Browser   | .blend     | Marked assets                              |

## Pre-Export Checklist
- [ ] All scales applied (Ctrl+A → Scale)
- [ ] Rotation applied
- [ ] Origin at logical pivot (usually root empty or base of thruster)
- [ ] LODs generated and named correctly
- [ ] Materials are Principled BSDF compatible
- [ ] No Ngons on low poly if engine is strict
- [ ] Custom properties cleaned or kept as needed

## LOD Strategy
- LOD0: Full detail (or slightly reduced GN)
- LOD1: 50% tris
- LOD2: 25% tris
- LOD3: Very low (silhouette only)

Use Decimate (Planar or Collapse) carefully or manual retopo for hero LODs.

## Export Scripts
See `scripts/export_gltf.py` and `scripts/export_fbx.py` for automated exports that respect the naming conventions and collections.
