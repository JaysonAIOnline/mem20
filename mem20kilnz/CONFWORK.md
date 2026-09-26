# CONFWORK — verified facts only

Rule: nothing enters this file unless it was executed and observed in this
session. Doubt means it does not go in. Failed attempts go in `failures.md`.

Environment (probed 2026-09-25/26):
- Host: Linux, 4 CPU cores, 15 GB RAM
- **GPU: none.** Intel Skylake-U HD Graphics 520, no CUDA, no `/dev/nvidia*`,
  nvidia kernel module not loaded. torch 2.14.0+**cpu**. (WORKED)
- Blender 5.2.0 LTS at `/usr/local/bin/blender`; FreeCAD 1.1.3 at
  `/usr/local/bin/freecad` and `/usr/local/bin/freecadcmd`. (WORKED)
- venv `/root/.venv`; has trimesh 5.1.0, numpy-stl 4.0.0, numpy 2.5.3,
  transformers 5.15.1, torch 2.14.0+cpu. (WORKED)
- Estate convention for a subsystem: `/opt/mem20/mem20<name>z/` with
  `pyproject.toml`, package dir, `python -m <pkg>`, console script, README,
  tests, registered via `python -m toolchest refresh`. (WORKED)

Blender 5.2.0 census, via `blender --background --python probe.py` (WORKED):
- `bpy.ops` operators: **2010**, across **77** categories
- `bpy.types.ShaderNode*`: **102**
- `bpy.types.GeometryNode*`: **274**
- `bpy.types.Object*`: 9

FreeCAD 1.1.3 census, via `freecadcmd probe.py` (WORKED):
- 15 modules load headless: Part, Sketcher, PartDesign, Draft, BOPTools, Import,
  MeshPart, Mesh, Points, Robot, BIM, Path, Inspection, Measure
- `Part` exposes 103 names, 46 substantive CAD ops
- OCCT B-Rep present: Solid, CompSolid, Shell, Face, Wire, Edge, Vertex,
  BSplineSurface, BezierSurface, SurfaceOfRevolution, SurfaceOfExtrusion,
  OffsetSurface, BRepOffsetAPI, HLRBRep

KilN engine (relocated to `/opt/mem20/mem20kilnz/engine`) (WORKED):
- 9,766 LOC C++17 across 10 translation units; 68 tracked files
- Builds clean with `g++ 15.3.0 -std=c++17 -O2 -Wall -Wextra`:
  **0 warnings, 0 errors**; `make` exit 0. (WORKED)
- Binary `kiln`, 1,096,440 bytes
- **79 live ops**, confirmed by extracting `kind == "..."` from `apply_op` in
  `src/ops/ops.cpp` and cross-checked against the runtime `ping` response
  (`ops=79`) and `docs/RPC.md`. (WORKED)
- Four entry points: `--repl`, `--headless`, `--rpc`, `--gui` (CMake/Vulkan)
- `make rpc` returns valid JSON-RPC 2.0 on stdout, exit 0. (WORKED)
- `make demo` runs the English path: "add a red cube" → `created Cube`;
  named colours work (`gray`, `gold`); writes PNG + GLB, exit 0. (WORKED)
- `examples/rpc_session.py` full client session: 14 ops applied, batch of 2,
  Box 6→18 faces, render at 4x samples, export 5 nodes / 3 meshes, a deliberate
  failure returned structured `[-32000] frame: no node 'NoSuchNode'`, the
  session survived it, clean close, exit 0. (WORKED)
- `file(1)` independently confirms `PNG image data, 960 x 540, 8-bit/color
  RGBA` and `glTF binary model, version 2`. (WORKED)

**Determinism (WORKED).** The same scene generated three times in a row
produced byte-identical output both times over:
- GLB `460ed423a44d39371df21e7cc5b9baf0` ×3
- PNG `89ffa9631bb2d1ac57c8baf0a07fcf34` ×3
Those two checksums are also exactly the ones recorded in `docs/RPC.md`, so the
documentation's verification section matches the current source.

**Sixteen** functions are declared in `src/scene/scene.hpp` with **no definition
and no call site anywhere in the tree** — each name occurs exactly once, in its
own declaration. Verified two ways: a regex audit of all 88 declarations in
`scene.hpp` against every `.cpp` definition, then a direct grep of each
candidate (WORKED):
`import_obj`, `export_obj`, `decimate_mesh`, `catmull_clark`, `wireframe_mesh`,
`shrinkwrap_mesh`, `symmetrize_mesh`, `recalc_normals`, `separate_loose_meshes`,
`apply_frame`, `boundary_faces`, `extrude_individual`, `ik_two_bone`,
`rotate_verts`, `scale_verts`, `shear_verts`.

Note which two of those are in the animation and rigging domains: `apply_frame`
(pose a frame onto the scene) and `ik_two_bone` (two-bone IK) are declared and
never implemented, so the engine's animation and IK support is thinner than the
header implies. (WORKED)

There is also **no glTF/GLB importer at all**, not even declared — `gltf.cpp`
only writes. (WORKED)

`mesh_sync_render`, `mesh_ensure_faces`, `mesh_compact`, `vertex_normals`,
`face_normal`, `face_center` and `faces_matching` **are** implemented — in
`src/scene/edit.cpp`, not `src/scene/scene.cpp`. Do not assume the `.cpp`
sibling of a header defines its functions. (WORKED)

No `modifiers` system exists: none of the ~40 Blender modifiers are present.
(WORKED — no modifier type in the op list, no modifier field on `Node`/`Mesh`)

Proposal verification (WORKED):
- `/opt/mem20/mem20kilnz/PROPOSAL.md`, 11 sections
- `grep -cE '^- [A-L][0-9][0-9] '` → **255** novelty-tested AI-native features
- `grep -cE '^- M[0-9][0-9] '` → **62** parity-equal features
- No duplicate IDs, no malformed merged lines (WORKED)

## glTF/GLB importer (Phase 1a) — WORKED

`src/io/gltf_import.cpp`, declared in `src/io/gltf.hpp` as
`GltfImportStats import_gltf(Scene&, const std::string& path, std::string& err)`,
bound as the `import` / `import_gltf` op and reachable from the DSL as
`import <path> [replace]`.

Covers, all verified by fixture:
- GLB container (magic, version 2, JSON + BIN chunks, 4-byte chunk padding) and
  bare `.gltf`
- buffers from a GLB BIN chunk, a base64 `data:` URI, or an external `.bin`
- every accessor component type (5120/5121/5122/5123/5125/5126), `normalized`
  dequantization for signed and unsigned integers, `byteStride` interleaving, and
  sparse accessors
- primitive modes TRIANGLES, TRIANGLE_STRIP and TRIANGLE_FAN; POINTS and line
  modes are counted in `skipped_modes`, never silently dropped
- node `matrix` **and** TRS, with quaternion → matrix → XYZ-euler decomposition
  and sign-correct scale extraction for negative determinants
- multi-primitive meshes: the node stays an Empty group and each primitive
  becomes a child Mesh node, so per-primitive materials survive
- materials: `pbrMetallicRoughness` base colour / metallic / roughness, and
  `emissiveFactor` folded back into kiln's scalar `emission`
- cameras: perspective `yfov`; orthographic is reported as dropped
- skins: `joints`, `inverseBindMatrices`, `JOINTS_0`, `WEIGHTS_0`, with joint
  indices remapped from glTF joint order into kiln's `mesh.joints`
- extensions are collected and reported by name rather than ignored

**Round-trip is byte-for-byte lossless for geometry (WORKED).** Importing
`examples/demo.glb` and re-exporting produced POSITION and INDICES accessors
byte-identical to the input for all three primitives (432/72, 72/12, 19008/3168
bytes).

**Test suite: 16/16 pass (WORKED)** — `tests/make_fixtures.py` builds 16
fixtures, `tests/run_import_tests.py` checks them against `expected.json`. All 13
positive fixtures were independently confirmed to import cleanly in **Blender
5.2.0 LTS** first, so the fixtures are known-valid rather than self-certified;
the 3 negative fixtures are rejected cleanly with a named reason and no crash.

Known, deliberate limitations, reported in the op result rather than hidden:
- `TEXCOORD_0`, `TANGENT`, `COLOR_0` and `TEXCOORD_1` are **dropped**. kiln's
  `mesh_sync_render` rebuilds the render mesh from `positions` + `faces` and
  assigns synthetic per-triangle UVs, so the `Mesh` model has nowhere to keep
  them. Retaining UVs needs real per-vertex attribute storage, which does not
  exist yet.
- Split (hard-edged) normals are dropped; a mesh with per-vertex NORMAL is
  imported with `smooth` set, so shading is recomputed rather than preserved.
- glTF has no lights, so an imported Sun/Light node arrives as an Empty.
- One `Mesh` per primitive means a multi-primitive mesh duplicates its shared
  positions once per primitive.
- Draco, meshopt and quantized-position extensions are not decoded; they are
  reported by name in `unsupported_extensions`.

Defect found and fixed during this work: nlohmann's **const** `operator[]`
asserts on a missing key, and glTF omits keys freely. The first draft used
unguarded `jn["matrix"]` style access throughout and aborted on the very first
real file. All optional lookups now go through `jget`/`jint`/`jsize`/`jstr`/
`jbool` in `gltf_import.cpp`.

Three of my own fixture bugs were caught by using Blender as the oracle rather
than trusting my own generator: hardcoded `byteLength: 24` where 3 VEC3 floats
is 36 bytes, accessors pointing at non-existent bufferViews, and a sparse block
missing its required `componentType`. The importer rejected all three correctly
— the fixtures were wrong, not the reader.

## OBJ, decimation, normals, loose parts (Phase 1b/1c) — WORKED

`src/io/obj.cpp`: OBJ reader and writer. Handles `v v/vt v//vn v/vt/vn` face
tokens, negative (relative) indices, n-gon faces, `o`/`g` object grouping, and
4-component `v x y z w` with the implied divide. Rejects a face that references
a nonexistent vertex by number. Bound as `import_obj` / `export_obj`.
`ObjImportNotes` reports meshes, faces, vertices and whether `vt`/`vn` were
present, so a dropped attribute is stated rather than silent.

Verified (WORKED): a scene of `Cube` (6 faces, 8 verts) and `Ball` (288 faces,
266 verts) exports to OBJ and re-imports as **two objects with vertex counts 8
and 266 exactly preserved**; face counts become their triangulated equivalents
(12 and 528) because OBJ stores triangles. Blender 5.2 imports the written file
and reports 2 meshes / 274 verts.

`src/scene/mesh_ops.cpp`:
- `recalc_normals` — area-weighted vertex normals with BFS winding
  consistency over shared edges, flipping faces that disagree.
- `separate_loose_meshes` — connected components with per-component reindexing.
  Verified: a 1-primitive mesh holding two vertex-disjoint triangles splits into
  `Loose` (1 face, 3 verts) and `lp_part1` (1 face, 3 verts).
- `decimate_mesh` — **vertex clustering**, not quadric error metrics. Quarantises
  vertices onto a lattice sized from the requested ratio and the mesh extent,
  merges each cell onto its centroid, and rebuilds faces.

**Why clustering and not QEM (WORKED, with numbers).** A quadric edge-collapse
implementation was written first and rejected on measured evidence. It hit its
triangle targets but lost 20% of signed volume at ratio 0.5 and 79% at 0.1,
because collapsing an edge deletes the two incident triangles and leaves an
unrepaired hole; adding a link-condition retriangulation made it worse (79%
loss) and then it stopped reaching its target, converging to a fixed point at
297 faces because after the first collapse most candidate edges are no longer
interior. Clustering has no such failure mode. Measured on a 288-face sphere
(24-segment primitive, 266 verts), area drift vs the full-resolution reference:

| ratio | faces | verts | surface area | non-finite | degenerate | non-manifold |
|-------|-------|-------|--------------|------------|------------|--------------|
| 0.75  | 116   | 88    | **-4.0%**    | 0          | 0          | 0            |
| 0.50  | 82    | 63    | **-6.7%**    | 0          | 0          | 0            |
| 0.25  | 32    | 29    | -17.8%       | 0          | 0          | 0            |
| 0.10  | 8     | 8     | -53.7%       | 0          | 0          | 0            |

Clustering overshoots the requested vertex reduction (88 rather than ~199 at
ratio 0.75) — inherent to the technique, and stated rather than hidden. QEM with
proper boundary handling is the planned replacement for silhouette-aware
quality-preserving reduction. Both facts are recorded in the source comment.

Note: the `watertight` figure reported by `tests/mesh_metrics.py` is **not
meaningful on kiln's own exports**, because `mesh_sync_render` expands every
triangle to its own three vertices, so no two triangles ever share an index and
every edge reads as a boundary edge. Closedness must be judged on `Mesh::faces`
inside the engine, not on an exported file. Recorded so nobody later mistakes
it for a pass.

## Op surface integrity

`src/core/rpc.hpp` carries an advisory op table that nothing in C++ ties to
`apply_op`; it had already drifted once. `tests/check_op_sync.py` now reads both
plus the live `ping` count and the live `initialize` list, and fails on any
difference in either direction. All four surfaces agree at **87** ops
(WORKED): 79 original plus `import`, `import_gltf`, `import_obj`, `export_obj`,
`decimate`, `recalc_normals`, `separate_parts`, `separate_loose`.

## The remaining eleven dead declarations — WORKED

**Zero dead declarations remain.** A regex audit of all 88 declarations in
`src/scene/scene.hpp` against every `.cpp` definition now reports 0 with no
definition (WORKED). Nine went into `src/scene/mesh_ops.cpp`, two into the new
`src/scene/rig_ops.cpp`.

Measured behaviour:

| Function | Evidence |
|---|---|
| `catmull_clark` | sphere 288 faces / 266 verts → 1104 / 1372 at level 1, 4416 / 6874 at level 2. Levels outside 1–4 rejected by name. |
| `wireframe_mesh` | cube 6 faces → 72 faces: 12 edges × (4 sides + 2 caps). Zero thickness rejected. |
| `boundary_faces` | closed cube → **0** boundary faces; open plane → **1**. |
| `symmetrize_mesh` | sphere offset to +x → 288 faces / 266 verts becomes 388 faces after mirroring and welding. |
| `shrinkwrap_mesh` | 266 verts wrapped onto a target plane; same-mesh target rejected. |
| `extrude_individual` | one selected face → new cap plus 4 side quads, per-face own vertices; zero amount and empty selection both rejected. |
| `rotate_verts` / `scale_verts` / `shear_verts` | 4 verts on a plane, each reporting the exact factor applied. Zero scale component rejected. |
| `apply_frame` | sets `s.frame`, lerps each bone's `pose_rot`/`pose_loc` between the two nearest keys, and reverts unkeyed bones to rest. |
| `ik_two_bone` | see below. |

**Two-bone IK verified end to end, not just by its return value (WORKED).** A rig
plus a bound mesh was solved toward a target and the exported skinned geometry
measured: the mesh centroid moved **0.511 units** with **cos(angle between the
movement and the target direction) = 0.9878**. So the chain actually rotates
toward the target rather than merely reporting success.

One honest caveat on that measurement: glTF stores mesh positions in the node's
**local** frame with the node transform written separately, so the exported
positions sit at the local origin. The direction comparison is only valid
because that particular node carries a translation and no rotation. A future
test that measures IK on a rotated node must compose the node transform first.

`aim_bone` inverts the parent's world matrix and the bone's own rest rotation to
leave exactly the pose delta to store, reusing the same `local = rest * pose`
composition that `Scene::world_matrix` already applies — so IK cannot drift out
of step with how posing works.

`quat_to_mat`, `mat_to_euler_xyz`, `mat_rotation_part` and `basis_from_x` were
promoted from private copies inside the glTF importer into `src/core/math.hpp`,
because frame evaluation and IK both need them and duplicating matrix
decomposition three times is how they drift apart.

## Bugs found while wiring the DSL (all real, all fixed)

- `symmetrize axis x` did not skip the literal word `axis`, so the axis parsed as
  the string "axis" and the command fell through to the English path.
- `scale_verts` built its array under the key `rotation`, then erased `rotation`
  and read `rotation` again to fill `scale` — so **every** scale call silently
  reported and applied `1,1,1`, and a zero-scale request was never rejected.
  That is the worst class of bug here: it succeeded while doing nothing.
- `ops.cpp` had no `lower_copy`; it was private to `agent.cpp`.

## Op surface

79 → **103**. `tests/check_op_sync.py` confirms `apply_op`'s dispatch, the
advisory table in `rpc.hpp`, the live `ping` count and the live `initialize` list
all agree (WORKED). The new names are `subsurf`, `subdivide_surface`,
`catmull_clark`, `wireframe`, `shrinkwrap`, `symmetrize`, `mirror_symmetry`,
`boundary`, `extrude_individual`, `rotate_verts`, `scale_verts`, `shear_verts`,
`frame_at`, `set_frame`, `ik`, `ik_two_bone`, plus the eight added in 1a–1c.

No regression: `examples/demo.glb` and `examples/demo.png` md5s are unchanged,
the glTF geometry round trip is still byte-for-byte lossless, 17/17 fixtures
pass, and the OBJ round trip still returns 2 meshes / 274 verts.

## Phase 2 — the `mem20kilnz` package (2026-09-26)

Installed as an editable package into the estate venv; the console script
`mem20kilnz` resolves and runs (WORKED).

- `pip install -e . --no-deps` succeeds; `mem20kilnz doctor`, `build-engine`,
  `budgets`, `ops --json`, `validate`, and `gate` all run.
- `43` tests pass (`python -m pytest tests/ -q`). `ruff check mem20kilnz tests`
  is clean.
- Exit-code contract holds: `0` pass, `1` a finding, `2` a usage error.
  Measured on `engine/examples/demo.glb` (structurally valid, under budget) and
  on a 200-byte truncated copy (structurally broken).
- `tests/check_op_sync.py` still reports `ping reports count 103` and
  `OK: advertised op surface matches apply_op exactly`.

### The agent path is real, not a stub

A brief really does reach a language model and come back as geometry
(WORKED). Through the engine, with credentials from `/opt/mem20/secrets/.env`:

    mem20kilnz build "a weathered wooden crate with iron bands" \
        --out out --name SM_Crate --preview

produced `created Crate; created Band_Top; created Band_Bottom; Band_Top
parented to Crate; Band_Bottom parented to Crate` — a 7,124-byte GLB and a
44,959-byte preview PNG, from one sentence, with parenting.

The gate then **refused** that asset: 36 triangles against an LOD0 floor, and
`Crate`/`Band_Top`/`Band_Bottom` carrying no roadmap prefix. That is the gate
working. The language model undershoots geometry budgets, so most briefs fail
the gate on first attempt.

### Provider resolution

`GROQ_API_KEY` is present; the model id the file implies is not. Probed through
the engine, because Python's own HTTPS is Cloudflare-blocked (HTTP 403,
`error code: 1010`) on this host.

- **Works:** `openai/gpt-oss-120b` (chosen as the default), `openai/gpt-oss-20b`.
- **Refused by the API:** `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`,
  `llama-4-scout-17b-16e-instruct`, `llama-4-maverick-17b-128e-instruct`,
  `qwen/qwen3-32b`, `moonshotai/kimi-k2-instruct` — all `model_not_found`.
  `deepseek-r1-distill-llama-70b` is `model_decommissioned`.

7 providers are configured in the estate secrets file: groq, nvidia, together,
deepseek, mistral, openrouter, cerebras. xAI stays disallowed by policy.
