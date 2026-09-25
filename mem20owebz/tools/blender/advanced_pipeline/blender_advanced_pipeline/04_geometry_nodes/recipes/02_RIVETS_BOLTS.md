# Geometry Nodes Recipe: Rivets / Bolts Scatter

**Goal:** Scatter realistic rivets or bolts along edges or on faces with proper alignment and variation.

## Inputs
- Geometry
- Density / Distance Min (float)
- Rivet Scale (float)
- Scale Random (float 0–1)
- Rotation Random (float)
- Rivet Object / Collection (object or collection)
- Mask (field)
- Align to Face Normal (bool)
- Align to Edge Tangent (bool) – for edge-running rivets
- Seed

## Node Flow

1. **Group Input**
2. **Mesh to Points** or **Distribute Points on Faces** (Poisson Disk for even spacing)
   - Or better for edges: **Edge Vertices** → **Mesh to Curve** → **Resample Curve** → **Curve to Points**
3. **Instance on Points**
4. **Align Rotation to Vector**
   - Vector = Normal (from Capture Attribute) or Tangent
5. **Random Value** (Vector / Float) for scale & rotation offset
6. **Scale Instances** + **Rotate Instances**
7. **Join Geometry** (original mesh + instances) or replace
8. **Group Output**

## Edge-Running Rivets (common on armor / weapons)
- Convert boundary or selected edges to curves
- Resample with even length (e.g. every 0.03–0.06 m)
- Instance rivet at points
- Align Y-axis to curve tangent, Z to surface normal

## Performance
- Use Collection of 3–5 slightly different rivet meshes for variation
- Realize Instances only when needed (bake / export)
- For very dense: use lower density on LODs

## RPG / Fantasy Note
Same system works perfectly for rivets on armor, sword guards, shield bosses, chest hardware, etc. Just swap the instance object to a more ornate bolt or stud.
