# Example Asset: Modular Sci-Fi Thruster Assembly

This document walks through the complete build using every stage of the pipeline.

## Concept
A heavy, industrial sci-fi thruster suitable for a large spaceship or mech.
Real-world scale: approximately 1.8 m tall, 0.9 m diameter at widest point.

## Build Sequence (Follow Exactly)

### Phase 1 – Setup (A)
1. Run `01_project_setup/setup_scene.py`
2. Save file as `THR_Thruster_Assembly_v001.blend`
3. Set root empty custom properties

### Phase 2 – Base Mesh (B)
1. Create Bezier Curve for main body profile (side view)
2. Run `curve_to_screw_helper.py` or manually add Screw modifier (32–48 steps)
3. Create second curve for nozzle / exhaust bell
4. Create mounting flange (can start from a carefully edited cylinder or curve)
5. Place Boolean cutters for major vents and mechanical cutouts
6. Add cooling fins using Array + Simple Deform or individual modeling
7. Clean topology: supporting loops, merge by distance, correct edge flow
8. Add Bevel Weight + Edge Crease where needed
9. Subdivision Surface (levels 1–2 for viewport)

**Do not apply modifiers yet.**

### Phase 3 – Procedural Details (C)
1. Create vertex groups for masks
2. Add Geometry Nodes modifier
3. Build or append:
   - Panel lines
   - Rivets along selected edges/faces
   - Vent grilles in cutout areas
   - Cable bundles running along the body
4. Link density to `prop_detail_density` on the root empty (via driver or input)

### Phase 4 – UV & Bake Prep (5)
1. Duplicate high poly → apply all modifiers (or realize instances) → move to bake collection
2. Create clean low poly version (retopo or careful decimate + cleanup)
3. Create cage
4. Unwrap both with consistent texel density
5. Bake Normal, AO, Curvature, etc.

### Phase 5 – Materials (6)
1. Create the five core materials
2. Use attributes from GN for wear and panel variation
3. Add heat gradient near the nozzle

### Phase 6 – Export (7)
1. Create LODs
2. Move final objects to `COL_THR_Export`
3. Run export scripts
4. Validate in target engine / DCC

## Design Notes for Realism
- Heavy bevels on the flange and major edges
- Subtle surface irregularities via displacement or normal
- Clear visual hierarchy: large forms first, then medium panels, then micro rivets
- Heat discoloration strongest at the nozzle exit and fading upward

This asset should take an experienced hard-surface artist 1–2 days following this pipeline strictly.
