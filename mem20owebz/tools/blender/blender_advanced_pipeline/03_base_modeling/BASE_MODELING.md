# Stage B – Advanced Base Modeling (Beyond Primitives)

**Core Rule:** Primitives are only temporary construction helpers. The final base mesh must be purpose-built topology.

## Recommended Construction Methods (in order of preference)

### 1. Curve + Screw / Spin (Primary for cylindrical forms)
Best for thruster body, nozzle, pipes.

Steps:
1. Add Bezier Curve → set to 2D or 3D as needed
2. Shape the profile (side view of the thruster)
3. Add Screw modifier (or use Spin tool in Edit Mode for more control)
4. Convert to mesh only when topology is approved
5. Immediately add Subdivision Surface + Edge Creases

Expert tips:
- Use even spacing of control points
- Keep the profile clean (no overlapping)
- Apply scale/rotation before converting
- After conversion: Merge by Distance, then rebuild edge flow if needed

### 2. Non-Destructive Boolean Workflow
Never apply Booleans until the design is locked.

Setup:
- Main object in `COL_THR_High`
- All cutters in `COL_THR_Cutters` (hidden, wireframe display)
- Use Boolean modifier → Solver: Exact → Operand Type: Object
- Parent cutters to the main body or to the root empty
- Name cutters: `CUT_Thruster_Vent_01`, etc.

Advanced:
- Use Boolean with Collection for many cutters
- Combine with Bevel modifier after Boolean (Order matters!)
- For clean results: add a Weld modifier after Boolean

### 3. Solidify + Bevel Weight Pipeline
Classic hard-surface:

1. Create thin shell with Solidify (Even Thickness + Rim)
2. Mark bevel weights on sharp edges (Ctrl+E → Edge Bevel Weight)
3. Bevel modifier (Weight mode, Segments 2–4, Profile 0.5–0.7)
4. Subdivision Surface after Bevel
5. Edge Crease on edges that should stay sharp under SubD

### 4. Custom Topology Discipline
- Prefer quads
- Supporting loops around every hard edge and hole
- Avoid triangles and n-gons on the final high-poly (they are acceptable on low-poly)
- Poles (E-poles, N-poles) only where necessary and away from deformation areas
- Use Knife Project, Bridge Edge Loops, Grid Fill intelligently

### 5. Secondary Forms
- Shrinkwrap modifier for adding panels that follow the main surface
- Lattice or Mesh Deform for broad shape changes late in the process
- Surface Deform for more advanced wrapping

## Practical Build Order for the Thruster

1. Main body profile curve → Screw
2. Nozzle profile curve → Screw (separate object, later joined or Booleaned)
3. Flange / mounting ring (curve or carefully modeled torus-like form)
4. Major cutouts with Boolean cutters (vents, attachment points)
5. Cooling fins (Array + Curve or individual modeling + Array)
6. Clean up topology, add supporting loops
7. Apply scale, freeze transforms
8. Only then move to Geometry Nodes detailing

## Scripts in this folder
- `curve_to_screw_helper.py` – quickly sets up a good Screw workflow
- `boolean_cleanup.py` – post-boolean mesh cleanup helpers
