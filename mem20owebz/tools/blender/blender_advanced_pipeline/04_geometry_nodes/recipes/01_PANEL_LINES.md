# Geometry Nodes Recipe: Panel Lines / Inset Panels

**Goal:** Non-destructive panel lines and inset mechanical panels on any hard-surface mesh.

## Inputs (Group Inputs)
- Geometry
- Panel Depth (float, default -0.008)
- Panel Width (float, default 0.004)
- Mask Attribute (string or Boolean field) – where panels appear
- Seed (int)
- Use Existing Edges (bool) – prefer marked edges or generate new

## Recommended Node Flow (Blender 4.2+)

1. **Group Input**
2. **Store Named Attribute** (optional – capture original position)
3. **Separate Geometry** (by Mask) → only process masked faces
4. **Mesh to Curve** (or Edge Paths to Curves if using selections)
5. Alternative clean method (preferred for quality):

**Modern clean approach:**
- Distribute Points on Faces (Density controlled by mask) **or**
- Use “Edges of Vertex” / selection of boundary edges
- Better: Mark freestyle edges or use Bevel Weight as mask source
- Convert selected edges to curves
- Fillet Curve or Resample
- Curve to Mesh with a rectangular profile (width = Panel Width, height = small)
- Extrude or join back with Boolean Difference for true inset
- Or use Extrude Mesh on a dual-mesh approach

**Practical production recipe (simpler & stable):**

```
Geometry Input
  → Capture Attribute (Normal)
  → Set Position (slight inset along normal * depth where mask)
  → Extrude Mesh (Individual faces, offset = depth, scale edges inward for width)
  → Join Geometry (original + extruded)
  → Merge by Distance
  → Group Output
```

For true panel lines (grooves):

1. Select edge loops that should become panels (or generate via GN)
2. Convert to Curve
3. Curve to Mesh (profile = thin rectangle)
4. Boolean Difference against the main mesh (Exact)
5. Or use the “Inset Faces” logic with scale elements

## Pro Tips
- Drive Mask from Vertex Group or from curvature (Geometry Proximity + Map Range)
- Expose Panel Depth & Width as inputs linked to root empty custom props
- After GN, use a Bevel modifier on the result for clean edges
- For performance: realize only at bake time

## Python Generator
See `generate_panel_lines_group.py` for a script that creates a basic version of this node group automatically.
