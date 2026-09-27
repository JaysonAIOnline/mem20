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

## Phase 3 — pipeline, provenance, catalogue, ingest (2026-09-26)

### The engine gained a journal

There was no way for a client to learn which ops a language model applied,
because those ops never arrive as separate RPC calls — the engine interprets
the brief internally. The undo stack could not help: it stores document
snapshots, not op records. So the manifest could not have been honest.

Added a real journal (WORKED):

- `Document::journal` plus `Document::record`, with a 4096-entry bound.
- `apply_op` is now a thin funnel over `apply_op_impl`, so all ~30 early
  returns are journaled, not just the paths that fall through.
- `apply_ops` calls the funnel, so a batch journals each op individually.
- New RPC method `journal`, supporting `{"clear": true}` and `{"since": n}`.
  `clear` empties the journal without touching the scene.
- The C++ build is still warning-free, the op surface is still 103 (the journal
  is a method, not an op), and both demo md5s are unchanged.

Verified: a failed op is journaled with `ok: false` rather than disappearing;
`journal --clear` leaves the scene untouched.

### brief -> asset -> receipts

`mem20kilnz/pipeline.py` (WORKED). One brief produced real geometry and its own
receipts:

    created Pillar_L; created Pillar_R; created Arch

768 triangles, 81,700-byte GLB, 41,309-byte PNG. The manifest recovered the
three ops the model invented, with their parameters, none of which the client
had sent:

    create ok=True {"albedo": [0.5, 0.5, 0.5], "metallic": 0, "name": "Pillar_L", ...}
    create ok=True {"albedo": [0.5, 0.5, 0.5], "metallic": 0, "name": "Pillar_R", ...}
    create ok=True {"albedo": [0.5, 0.5, 0.5], "metallic": 0, "name": "Arch",    ...}

`verify()` re-checks a manifest against the bytes on disk. Confirmed against
three cases: untouched (ok), one appended byte (rejected, hashes differ), and a
deleted asset (rejected, `glb missing`).

### Catalogue

`mem20kilnz/catalogue.py` (WORKED). Reads manifests only, never geometry, so
an entry cannot claim more than the build produced. A `.glb` with no manifest is
reported as `untracked_glb` rather than described from its filename. `passing()`
requires ok **and** gate_ok **and** an intact artifact, so an asset built with
`--no-gate` is not counted as passing.

### External ingest

`mem20kilnz/ingest.py` (WORKED). `probe` is read-only and measures: `demo.glb`
reports 3 meshes, 1,626 verts, 542 triangles, normals and UVs present, and the
real budget gap (542 against an LOD0 floor of 2,000). `convert` pushes the file
through the engine, keeps all 542 triangles, and writes a manifest marked
`kind: ingest` / `source: external` with both the input and output hashes, so an
imported asset is never mistaken for a generated one. `.fbx` is refused by name
with the supported list, rather than handed to the engine to fail obscurely.

### Honest limits found while building this

- The manifest only records what the engine journal holds. If the built-in
  English agent acts without going through `apply_op`, that action is not in
  the journal. The DSL and the LLM path both go through it.
- OBJ is accepted for conversion but `probe` does not measure its geometry; it
  says so in `reason` rather than reporting a triangle count of 0 as fact.
- `probe` on an unsupported extension is refused by name. It does not attempt
  FBX, which the engine cannot read.

## toolchest — phantom `find` module (2026-09-26)

`_import_candidates` did `st.get("packages", [])`. With
`[tool.setuptools.packages.find]`, `packages` is a nested table, so extending a
list with it contributed its **keys** — every such package was reported as
having a module called `find`. 24 of 36 subsystems were affected, including
`mem20kilnz` itself, which showed `importable=False` while importing fine.

Fixed at the cause: the mapping form is now read for its finder `include`
globs. A second defect surfaced immediately — `include = ["pkg", "pkg.*"]` is
the subpackage shorthand, and trimming only `*` left a module named `pkg.` —
so trailing separators are trimmed too. After the fix: 0 phantom names, and
`mem20kilnz` reports `import | mem20kilnz=y`. 6 tests added, 18 pass.

## Phase 4 — detail tiers, honest refinement, salvage (2026-09-26)

### The measured problem

A crate brief, run repeatedly against Groq `openai/gpt-oss-120b`:

- Triangle counts for the identical brief: **60, 60, 60, 92, 204, 300, 48, 36**
  over 8 runs. Reliable at producing *something*, wildly non-deterministic in
  detail. The prop floor is 2,000, so the shortfall is ~33x and retrying the
  same brief does not close it.
- Asking for more parts does not help: 8 named objects came to 96 triangles,
  because a cube costs 12.
- A richer, budget-aware prompt made the model return malformed JSON.

### Why subdivision was rejected, with evidence

Subdivision reaches the budget — one pass took a crate from 204 to 2,892
triangles, in budget. The render shows a single rounded box: the bands and
panel are gone, merged into a blob. A second measurement on the same brief hit
2,028 triangles, also in budget, also a featureless rounded box.

Measured side by side on the identical scene, both inside the standard band:

| method | triangles | render |
| --- | --- | --- |
| `subsurf` x2 | 2,028 | one rounded box, bands dissolved |
| `bevel` refine | 3,876 | box with chamfered edges, bands and panel intact |

Both pass the gate. Only one is better. `subsurf` is therefore excluded from
the refine stage by construction, not by convention (`ALLOWED_OPS`).

### Detail tiers

`blockout`, `standard`, `hero` (WORKED). The roadmap budgets are authored-asset
budgets, so they are the `standard` tier and are **unchanged** — asserted by a
test that walks every family. `blockout` is derived, not invented: `(1, floor-1)`,
because a blockout is by definition geometry that has not yet reached the
authored floor. `hero` is the roadmap band, only defined for `player` and
`boss`.

The guard works in both directions, which is the point:

- the real 60-triangle crate **passes** as `blockout` and **fails** as `standard`
- 5,000 triangles **fails** as `blockout`, so a blockout cannot masquerade as
  finished
- 0 triangles fails even as `blockout`

Default is `standard` everywhere, so no existing caller changed behaviour. The
manifest records `requested_tier`, `achieved_tier` (measured from the exported
file, never from the request) and `tier_met`.

### Refinement

`mem20kilnz/refine.py` (WORKED). Real crate, `prop`/standard: **60 → 220 → 940 →
3,820** in three passes, five nodes bevelled per pass, gate passing.

Every step is measured by exporting and re-reading the file. The loop stops on
the first step that adds no triangles, so it terminates even when the target is
unreachable.

**Overshoot guard.** A first run exploded to **1,557,860** triangles, 260x over
the 6,000 ceiling: one pass can multiply the count far past the budget, and
stopping the loop is not enough because the asset would still ship over budget.
The pass is now undone, and the export that follows is inside the ceiling.
Deterministic repro pinned in tests: 10 cubes at 2 segments.

### Partial work is no longer discarded

A brief whose ops included a failing `bevel` aborted the whole build, throwing
away five good ops and their geometry — the model emitted the bad op, and
`apply_ops` returned on the first failure. `apply_ops` and `m_ops` now report
`"2 of 4 ops applied, then failed: bevel: no edges"` with the good ops intact.

Measured effect: 3/6 crates shipped before these fixes, **7/8 after**, with zero
overshoots and no stray files.

Failed briefs no longer leave litter: the pipeline exports to a scratch path to
measure, and publishes the real GLB only once geometry exists.

### Salvaging truncated model output

The malformed-JSON failures were truncation: the model ran out of tokens
mid-array, and `extract_json_array` required a closing bracket, so every
complete op before the cut was thrown away. `salvage_truncated_ops` walks the
text with a brace stack and keeps every object that parses and carries an `op`.
It refuses to guess at a half-written op.

- truncated after 2 ops → 2 recovered, both applied, reported as partial
- truncated inside the first op → still fails, correctly
- complete list → unchanged, no salvage involved

3 briefs x 3 runs after the change: 8 succeeded, 1 op failure, **0 malformed
JSON**.

## Phase 5 — plain-English description, for an agent that cannot see (2026-09-26)

`mem20kilnz/describe.py` (WORKED). Reads the **exported GLB**, not the in-memory
scene, so the description cannot disagree with the bytes that ship — the same
principle the gate follows. Written into every export manifest, exposed as
`mem20kilnz describe <file>`, and reachable from inside a session via the
`describe` verb (which already existed; it now reports more).

Measured on a real build, brief "a wooden treasure chest with iron bands and a
lock", tier blockout, 6 parts / 1,848 triangles:

    ChestBody is a mesh measuring 2.00 by 1.00 by 1.00 (the largest part),
      coloured dark orange, with a matte surface, enclosing BandBottom.
    ChestLid is a mesh measuring 2.00 by 0.20 by 1.00 (a very thin sheet or
      sliver, wider than ChestBody, and 10% as thick as it is wide), ...
    BandBottom ... (a very thin sheet or sliver, 0.54 times the width of
      ChestBody, and 5% as thick as it is wide), coloured grey, with a fully
      metallic, satin surface, attached to ChestBody, sitting inside ChestBody.
    Lock is a mesh measuring 0.20 by 0.20 by 0.10 (a small protruding part,
      0.10 times the width of ChestBody), ...

A text-only agent can now answer "is the lock the right size", "are the bands
bands or blocks", and "what is attached to what", without seeing anything.

### Measured, not estimated

- dimensions from vertex positions, in world space
- colour names from hue, saturation and lightness (`colour_name`), not a lookup
  table; brown is computed as a desaturated not-bright orange-to-yellow
- finish from roughness and metalness, in words
- thinness judged against each part's own smallest side
- explicitly **not** claimed: whether the shape resembles its subject. That is
  stated in `not_computable` on every run, because geometry cannot answer it.

### Four defects found by writing it, two of which would have made it lie

1. **Materials were invisible.** The exporter writes the material on the mesh
   primitive, not the node, so reading `node.material` yielded nothing and every
   part came out colourless. Now read from the primitive.
2. **Dimensions were in local space.** The description reported a model with a
   raised band as 1.00 tall when the true extent was 1.15. The exporter writes
   untransformed positions, so the transform chain must be walked.
3. **The transform chain was mathematically wrong.** A glTF node is `T*R*S`, and
   composing two of them gives `T*R*S*T*R*S`, which is *not* a TRS — the inner
   translation has nowhere to go. The original single-triple collapse was
   replaced with a row-major 4x4 matrix. Demonstrated: with a rotation on both
   nodes and a non-uniform parent scale, the collapse returns `(0, -2, 0)` and
   the matrix returns `(0, 2, 0)`.
4. **Relative size was judged on volume.** A 0.2 lock on a 2.0 chest is 0.4% of
   the volume, which reads as a "sliver", while being a tenth of the chest's
   width, which is a real part. Now judged on width, with thinness reported
   separately, because a band is *wider* than the chest it wraps and a width
   ratio alone loses the only fact worth knowing.

Also: a colour bug where wood read as "orange", because the brown check was
guarded on the sector name `"red"` while 24-40 degrees is the `"orange"` sector.
Keyed on hue range instead.

### The engine side

`describe_scene` now also reports, for every node: parent name, scale, measured
local bounds, and material with albedo, roughness and metallic. Measurement
lives in the engine for the live scene and in `describe.py` for the exported
file; the prose rendering exists only in `describe.py`, deliberately, so there
is one implementation of the English rather than two that can drift.

## 2026-09-27 — Shading, welding, and the decimator decision

### Curved primitives are now smooth-shaded (WORKED)

Welding corners on (position, normal, uv) cannot help a flat-shaded mesh,
because every face has its own normal and no two corners ever match. The
baseline was wrong, not the weld:

| primitive | verts before | verts after | boundary edges | watertight |
| --- | --- | --- | --- | --- |
| sphere | 1,104 | **266** | 1,104 -> **0** | **yes** |
| cylinder | 146 | **50** | -> 0 | **yes** |
| torus | 1,152 | **288** | -> 0 | **yes** |
| cube | 24 | 24 | 24 | no (correct: flat-shaded) |

`shade_smooth` and `shade_flat` ops added; a sphere is smooth by default and
`shade_flat` still puts it back to 1,104, so the opt-in works. Op surface
104 -> 106.

### QEM: implemented, measured, and refused

`src/scene/decimate_qem.cpp` is real and three of its four defects are fixed.
The priority-queue rewrite took it from 11.52s to **0.12s at 8,832 faces** and
35,328 faces in 0.12s. The flip test now uses the real post-collapse normal, and
nothing is compacted mid-loop.

It is still not shippable, and the measurements are in failures.md. The
outstanding defect is the hole retriangulation: the loop is built from every
neighbour of the surviving vertex instead of the hole boundary, so it adds faces
faster than collapses remove them and a 528-triangle sphere returns as **1,470**.

`decimate` therefore defaults to `cluster`, the only method measured to keep
the mesh watertight with zero degenerate and zero non-manifold faces, and
`method: "qem"` refuses with that reason. The code is kept because the quadric,
the flip test, the queue and the boundary bookkeeping all transfer; the missing
piece is a correct link-condition boundary walk.
