# RPG Recipe: Heater / Kite Shield

**Prefix:** `SHD_`  
**Scale:** ~0.7–0.9 m tall

## Base Modeling

1. **Main Body**
   - Bezier Curve for the outer silhouette (heater shape)
   - Extrude / Solidify / Screw-style to give thickness
   - Or start with a plane, shape with proportional editing + loop cuts, then Solidify
   - Add curvature (slight dome) with proportional editing or Lattice

2. **Boss (central metal piece)**
   - Curve lathed or carefully modeled dome
   - Boolean into the shield or placed on top

3. **Rim / Edge Reinforcement**
   - Curve following the outer edge → Curve to Mesh with profile
   - Or Solidify rim + Bevel

4. **Handle / Straps (back side)**
   - Modeled or GN cables/straps
   - Keep on a separate object for flexibility

## Geometry Nodes
- Rivets around the rim and boss
- Optional decorative panels or heraldic divisions (mask-driven)
- Leather straps on the back

## Materials
- Wood base (procedural or texture)
- Metal rim + boss
- Painted heraldry layer (use Attribute or Vertex Color for divisions)
- Wear around edges and boss

## Pipeline Notes
Same UV/bake/export rules. Heraldry is best handled with a separate material slot or decal system.
