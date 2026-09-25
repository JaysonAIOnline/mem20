# Full Pipeline Overview – Advanced Hard-Surface

## 1. Project Philosophy

This is **not** a beginner “start with a cube” workflow.  
Every stage assumes professional intent:

- Design can change late
- Multiple artists can work on the same asset
- Output must serve both real-time (games) and offline (film/VFX)
- Details are procedural so art direction remains flexible

## 2. Asset Definition (D)

**Primary Example Asset:** Modular Sci-Fi Thruster Assembly

Components:
- Main thruster body (cylindrical + flared)
- Nozzle / exhaust bell
- Attachment ring / mounting flange
- Cooling fins / radiators
- Cable bundles & hose runs
- Panel lines, rivets, vents, warning labels area
- Optional heat-shield tiles (GN)

This asset is perfect because it forces:
- Curve-based revolving geometry
- Boolean cuts for mechanical details
- Clean cylindrical topology
- High density of procedural greebles
- Interesting UV challenges (cylindrical + planar)
- Strong material contrast (metal, ceramic, painted, burnt)

## 3. Stage Breakdown

### Stage A – Project Setup
- Correct units (Metric, 1.0 scale)
- Collection hierarchy
- Viewport display settings
- Custom properties on the root empty
- Asset Browser catalog setup

### Stage B – Base Modeling (No Final Primitives)
Techniques used:
1. Bezier / NURBS curves → Screw / Spin / Lathe
2. Non-destructive Boolean (Exact solver + parented cutters)
3. Solidify + Bevel Weight workflow
4. Edge Crease + Subdivision Surface
5. Shrinkwrap for secondary forms
6. Manual topology refinement (knife, bridge, loop cuts with correct flow)

### Stage C – Geometry Nodes Detail System
Reusable node groups:
- `GN_Panel_Lines`
- `GN_Rivets_Bolts`
- `GN_Vent_Grilles`
- `GN_Cable_Bundle`
- `GN_Greeble_Scatter`
- `GN_Heat_Tiles`

All driven by:
- Vertex groups / attributes
- Proximity / curvature
- Custom properties on the object

### Stage D – Example Build
The thruster is built following every rule in this pipeline so you can reverse-engineer the decisions.

## 4. Success Metrics

| Metric                    | Target                                      |
|---------------------------|---------------------------------------------|
| Final polycount (high)    | 80k–150k tris (before GN instances)         |
| Game LOD0                 | < 25k tris                                  |
| UV distortion             | < 2.5% average                              |
| Texel density             | 10.24 px/cm (or project standard)           |
| Non-destructive stages    | Base + Details stay live until final export |
| Reusability               | All GN groups + materials as assets         |

## 5. Tools You Should Have Enabled

- Node Wrangler
- Bool Tool (or use native Exact)
- UV Packmaster / UV Toolkit (optional but recommended)
- Quad Remesher or Instant Meshes (for emergency retopo)
- Asset Browser + catalogs
