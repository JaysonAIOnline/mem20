# Stage C – Geometry Nodes Detail System

This is where the pipeline becomes truly expert-level.  
All high-frequency details (panels, rivets, vents, cables, greebles) live in reusable Geometry Nodes groups.

## Philosophy
- Base mesh stays relatively clean
- Details are procedural and density-controlled
- Masks come from vertex groups, curvature, ambient occlusion (via attributes), or proximity
- Everything is asset-browser ready

## Core Node Groups to Build

### 1. GN_Detail_PanelLines
**Purpose:** Inset panel lines / hard edges on surfaces.

Inputs:
- Geometry
- Panel Depth
- Panel Width
- Mask (attribute or vertex group)
- Seed

Key nodes:
- Distribute Points on Faces (or use existing edges)
- Extrude Mesh / Scale Elements
- Boolean or Join + Merge
- Or classic: dual mesh → extrude → boolean difference style

Recommended approach (clean):
Use the “Edge Paths to Selection” + Extrude method or a well-made panel node from community + customize.

### 2. GN_Detail_Rivets
**Purpose:** Scatter bolts / rivets along edges or faces.

Inputs:
- Geometry
- Density / Distance
- Rivet Scale
- Rivet Collection (or object)
- Mask
- Align to Normal / Tangent

Key technique:
- Sample Index / Sample Nearest
- Instance on Points
- Align Rotation to Vector (Normal)
- Random Value for slight rotation/scale variation

### 3. GN_Detail_VentGrille
**Purpose:** Procedural vents / grilles.

Can be pure GN (grid + extrude + boolean) or instance a well-modeled vent piece.

### 4. GN_Cable_Bundle
**Purpose:** Cable / hose runs that follow curves or surface paths.

Technique:
- Curve Line or existing curve
- Resample Curve
- Curve to Mesh (with profile)
- Or multiple curves with noise for organic bundles

### 5. GN_Greeble_Scatter
**Purpose:** General mechanical greeble scattering with collision avoidance.

Advanced features:
- Poisson Disk distribution
- Min distance
- Scale by attribute
- Multiple object collections with probability

### 6. GN_Heat_Tiles (optional for thruster)
Procedural heat-shield tile pattern on the nozzle.

## Implementation Order for Thruster

1. Create base mesh (Stage B)
2. Add vertex groups: `VG_PanelMask`, `VG_RivetMask`, `VG_VentMask`
3. Create Geometry Nodes modifier on the high-poly object
4. Build or import the node groups above
5. Expose density & scale as inputs linked to the root empty custom properties (`prop_detail_density`)
6. Use Capture Attribute + Store Named Attribute so materials can read panel IDs later

## Best Practices
- Keep node groups pure (no external object references when possible)
- Document every input with descriptions
- Version your node groups (`GN_Detail_Rivets_v02`)
- Store them in a dedicated .blend and mark as Assets
- Use “Viewer” node heavily while building

## Files in this folder
- `node_groups/` → place your .blend node group libraries here
- Future: Python scripts that generate basic versions of these groups
