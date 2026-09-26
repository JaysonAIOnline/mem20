# KilNZ — Proposal

**Status:** awaiting Jayson's review. Nothing in this document is implemented.
**Date:** 2026-09-25
**Supersedes:** the 6-layer plan agreed earlier in session (that plan is the
Phase 0–5 spine; this document widens the target and is now the source of truth
for scope).

---

## 1. The thesis

**AI first, human second. Blender's ceiling, MSPaint's floor. Cleanroom.**

Three commitments, each one falsifiable:

- **AI first** — the primary user is an agent. Every capability is a callable op
  with a machine-readable schema, a structured result, and a failure mode that
  names the fix. The GUI is a debugging lens, not the product.
- **MSPaint's floor** — a human should go from blank canvas to a finished,
  exported asset without learning a modifier stack. One surface, one prompt box,
  one export button. Full depth available, but never required, and never in the
  way. No jargon walls, no mode-switching, no modal operators.
- **Cleanroom** — implementations written from published specifications and
  documented behaviour. No copied source, no lifted algorithms from Blender or
  FreeCAD internals. Formats are implemented against their public specs.

The 2,010-operator surface of Blender is a *coverage* target, not a *design*
target. We are not rebuilding Blender's GUI. We are rebuilding its capability
surface and putting an agent protocol on top of it that Blender does not have
and, structurally, cannot have — because Blender was designed around a human
sitting in front of it.

---

## 2. Measured ground truth

These numbers come from probing the binaries actually installed on this box, not
from documentation. Reproducible via `/opt/mem20/mem20kilnz/bench/probe_*.py`.

| Surface | Measured |
|---|---|
| Blender version | 5.2.0 LTS |
| Blender operators (`bpy.ops`) | **2,010** across 77 categories |
| Blender shader node types | **102** |
| Blender geometry node types | **274** |
| Blender object types | 9 |
| FreeCAD version | 1.1.3 |
| FreeCAD `Part` kernel surface | 103 names, 46 substantive CAD ops |
| FreeCAD headless modules loading | 15 (Part, Sketcher, PartDesign, Draft, BOPTools, Mesh, MeshPart, Points, Robot, BIM, Path, Inspection, Measure, Import) |
| OCCT B-Rep primitives present | Solid, CompSolid, Shell, Face, Wire, Edge, Vertex, BSplineSurface, BezierSurface, SurfaceOfRevolution, SurfaceOfExtrusion, OffsetSurface, BRepOffsetAPI, HLRBRep |
| KilN C++ engine today | 9,766 LOC, **79 live ops**, 4 entry points |
| KilN declared-but-unimplemented | **9 functions** (see §3.4) |
| GPU on this box | **none** (driver absent; torch is CPU-only) |

**Addressable parity units.** Counting operators, node types, object types,
modifiers, brushes, editors, physics systems and file formats as discrete
addressable capabilities, Blender plus FreeCAD plus full animation lands at
**order 4,000–5,000 units**. Blender's 2,010 operators are the dominant term and
are directly measured; the rest is a defensible estimate with the method stated.
We should treat 4,000–5,000 as the coverage denominator, not 2,010.

---

## 3. The architectural consequence

This is the single most important thing in this document.

**Blender is polygon-only. FreeCAD is solid-exact. "100% of both" therefore
forces KilN to be multi-representation.** Neither reference product is a superset
of the other:

| | Blender | FreeCAD | Neither has |
|---|---|---|---|
| Polygon mesh, edit mode, sculpt | yes | limited | — |
| Exact B-Rep solids, booleans, fillets | no | **yes** (OCCT) | — |
| Parametric sketch + constraints | no | **yes** | — |
| NURBS/B-spline surfaces | no | **yes** | — |
| Node-based procedural geometry | yes (274 nodes) | no | — |
| Node-based shading | yes (102 nodes) | no | — |
| Rigging, skinning, shape keys | yes | no | — |
| Animation, drivers, NLA | yes | no | — |
| Physics: cloth, fluid, particles | yes | no | — |
| Path/CAM, Robot, BIM, Inspection | no | **yes** | — |
| Cycles path tracer, EEVEE | yes | no | — |
| **Polygon ↔ exact-solid round trip** | no | no | **yes — this is KilN's own** |
| **Agent protocol over geometry** | no | no | **yes — this is KilN's own** |

The last two rows are where KilN is not a port of anything. They are the
differentiators, and they are the reason to build this rather than wrap Blender.

### 3.1 Proposed kernel architecture

Five representations behind one op layer, one scene, one undo journal:

1. **Poly** — triangles and n-gons, edit modes, sculpt-equivalent vertex ops.
2. **Solid** — exact B-Rep: solids, shells, faces, edges, booleans, fillets,
   chamfers, thickness, offset surfaces. Tessellates for display, evaluates
   exactly for measurement.
3. **Curve/Surface** — NURBS and Bézier, control-point and knot editing, loft,
   sweep, revolve, extrude-along-path.
4. **Sketch** — 2D parametric sketch with a real constraint solver, exactly as a
   CAD user expects, because FreeCAD users expect it and CAD without constraints
   is a toy.
5. **Volume/Cloud** — voxels, point clouds, heightfields, image-to-geometry.

Conversion between them is a first-class op, not a one-way export:
`tessellate`, `reconstruct`, `solids_from_mesh`, `mesh_from_solids`, and
round-trip verification that proves the conversion did not silently change the
shape.

### 3.2 Why the GUI stays small

An agent does not need a viewport, a node editor, or an outliner. It needs
`describe`, `render`, `export`, and a schema. The Vulkan/ImGui surface that
already exists stays as a *debug lens* — a human watches the agent work and
intervenes if it looks wrong. That is the correct amount of GUI, and it is why
the MSPaint floor is achievable rather than a fantasy.

### 3.3 Blender as honest external fallback

A handful of Blender capabilities are enormous and low-value to reimplement
cleanroom (Mantaflow fluid simulation, hair, Cycles' full path-tracing feature
surface, motion tracking). For those, KilN will expose a **labelled external
fallback**: a real call into the installed Blender, recorded in provenance as
external, never presented as native. This is honest, it saves months, and it is
what "trumps all in conflict" should mean — KilNZ's word is final on what is
native versus delegated.

### 3.4 The sixteen dead declarations — fix first

`scene.hpp` declares **sixteen** functions that have **no definition and no call
site** anywhere in the tree. Each appears exactly once: the declaration. Found by
auditing all 88 declarations in the header against every `.cpp` definition, then
confirming each candidate with a direct grep.

`import_obj`, `export_obj`, `decimate_mesh`, `recalc_normals`, `catmull_clark`,
`wireframe_mesh`, `shrinkwrap_mesh`, `symmetrize_mesh`, `separate_loose_meshes`,
`apply_frame`, `ik_two_bone`, `extrude_individual`, `rotate_verts`,
`scale_verts`, `shear_verts`, `boundary_faces`

Two of those are the sting: **`apply_frame`** (pose a frame onto the scene) and
**`ik_two_bone`** (two-bone IK) are declared and never implemented, so the
engine's animation and IK support is materially thinner than its own header
implies — and neither is visible from the op list. The first draft of this
document said nine; that was a hand-picked sample, not an audit. The correct
number is sixteen, and `failures.md` records the error.

There is also no glTF/GLB **importer** at all, declared or otherwise. So the
external-mesh ingest path — import, re-mesh to budget, fix normals, validate,
catalogue — rests almost entirely on code that does not exist.

---

## 4. Parity inventory

Status key: **LIVE** = works today · **PARTIAL** = some coverage · **DEAD** =
declared, unimplemented · **ABSENT** = does not exist.

### 4.1 Blender parity

| Domain | Units | Status | Notes |
|---|---|---|---|
| Primitives | 11 | PARTIAL | 6 (cube, plane, sphere, cylinder, cone, torus). Missing: circle, icosphere, grid, monkey, curve, text, metaball. |
| Object ops | ~180 | PARTIAL | 79 ops total across all categories. |
| Mesh edit mode | ~120 | PARTIAL | extrude, inset, bevel, loopcut, subdivide, bridge, fill, spin, bisect, mirror, solidify, array, poke, dissolve, weld, smooth, snap, split, connect present. Missing: knife, rip, spin-off, edge split, bridge edge loops (partial), proportional edit, face sets. |
| Modifiers | ~40 | DEAD | **Not one modifier stack exists.** wireframe, shrinkwrap, symmetrize, catmull_clark declared-dead. Blender's whole modifier system is absent. |
| Curves | ~60 | ABSENT | No curve object type. No Bézier, no NURBS, no bevel-depth, no taper/twist. |
| Surfaces | ~25 | ABSENT | No surface object type. |
| Metaballs | ~15 | ABSENT | — |
| Text objects | ~20 | ABSENT | — |
| Volume / VDB | ~15 | ABSENT | — |
| Grease Pencil 2D | ~90 | ABSENT | — |
| Sculpting | ~120 | ABSENT | No sculpt system, no brushes, no dynamic topology, no voxel remesh. |
| Retopology | ~25 | ABSENT | No quad retopo, no shrinkwrap, no face sets. |
| UV | ~90 | PARTIAL | Vertices carry UVs and glTF export writes them. **No unwrap operator at all** — UVs only exist if a primitive made them. |
| Materials / shading | ~250 | PARTIAL | Flat PBR: albedo, roughness, metallic, emission per material. **No node graph, no procedural shading, no image textures, no baking.** |
| Texturing / painting | ~80 | ABSENT | No image painting, no UV/Image editor, no bake. |
| Lighting | ~25 | PARTIAL | Sun and point. Missing: spot, area, IES, light linking, portals. |
| Camera | ~35 | PARTIAL | Perspective + fov + lookat/frame. Missing: ortho, panoramic, DOF, motion blur, constraints, markers. |
| Render engines | ~200 | PARTIAL | CPU software rasteriser with supersampling, contact shadows, AO. **No path tracer, no EEVEE, no volumes, no SSS, no hair.** |
| Compositing | ~90 | ABSENT | — |
| Sequencer / VSE | ~120 | ABSENT | — |
| Animation (all of it) | ~300 | PARTIAL | AnimKey + frame + `apply_frame` + `pose` + shape keys. **No curves, no interpolation, no easing, no drivers, no NLA, no action editor, no retargeting, no motion capture.** |
| Physics | ~150 | ABSENT | No cloth, soft body, fluid, particles, rigid body, collision, force fields. |
| Motion tracking | ~40 | ABSENT | — |
| Rigging | ~120 | PARTIAL | Biped, quadruped, face rigs; skinning; 2-bone IK; shape keys. Missing: constraints, custom shapes, control rig, Rigify-equivalent, weight painting, bone heat, drivers on bones. |
| Animation rigging glue | ~80 | PARTIAL | No FK/IK snapping, no pole vector, no foot planting, no ground alignment. |
| Geometry nodes | 274 | ABSENT | Blender's procedural graph. **KilNZ's op algebra in §6 is the agent-native replacement, not a port.** |
| Metaball / point cloud | ~30 | ABSENT | — |
| File formats | ~45 | PARTIAL | glTF/GLB **export** + KilN JSON. OBJ declared-dead. **No import at all**, no FBX, no USD, no Alembic, no STL, no PLY, no Collada. |
| Editors / UI | ~25 | PARTIAL | REPL + RPC + headless + Vulkan/ImGui GUI. |
| Scripting | ~30 | PARTIAL | Python client + JSON-RPC. No in-process API, no drivers' expressions. |
| 3D print toolbox | ~15 | ABSENT | — |

### 4.2 FreeCAD parity

| Domain | Units | Status | Notes |
|---|---|---|---|
| B-Rep solid modelling | ~46 | ABSENT | No solid kernel. This is the single largest gap and the highest-value addition. |
| Part primitives | ~20 | ABSENT | No box/sphere/cylinder/cone/torus solids, no compound, no compsolid. |
| Boolean ops | ~10 | ABSENT | No union/difference/intersect. |
| Fillet / chamfer / offset | ~12 | ABSENT | BRepOffsetAPI absent. |
| Loft / sweep / revolve / extrude | ~15 | ABSENT | No surface-of-revolution, no extrusion surface. |
| Sketcher + constraints | ~60 | ABSENT | No 2D sketch, no constraint solver. |
| PartDesign (pad/pocket/etc.) | ~40 | ABSENT | — |
| Draft workbench | ~90 | ABSENT | 2D drafting, annotations, arrays, dimensions. |
| Mesh / MeshPart | ~27 | PARTIAL | 20 Mesh names in FreeCAD; KilN has none of this surface. |
| Points / clouds | ~15 | ABSENT | — |
| Path / CAM | ~80 | ABSENT | Toolpaths, G-code, post-processors. |
| Robot | ~40 | ABSENT | — |
| BIM | ~60 | ABSENT | — |
| Inspection / Measure | ~25 | ABSENT | — |
| Import / STEP / IGES | ~15 | ABSENT | No STEP, no IGES. |
| HLRBRep hidden-line | ~5 | ABSENT | — |

### 4.3 The four you called out

| Ask | Reality | Path |
|---|---|---|
| **Rigging** | PARTIAL — 3 rig types, skinning, 2-bone IK, shape keys. No constraints, no control rig, no weight painting, no FK/IK blending, no retargeting, no foot planting. | Phase 4 |
| **PBR** | PARTIAL — flat per-material PBR floats only. No node graph, no image textures, no procedural shading, no baking, no IBL. | Phase 5 |
| **LOD** | PARTIAL — `lod` op exists, `decimate_mesh` is DEAD so LOD generation cannot actually reduce anything meaningful. | Phase 3 (unblocks via the decimator) |
| **FBX** | ABSENT. No import, no export, no SDK. | Phase 3 — needs a cleanroom FBX 7.x binary/ascii reader+writer, both directions, with a round-trip gate. |

---

## 5. MSPaint mandate — acceptance criteria

The floor, written so it can be failed:

1. Blank canvas → finished exported asset in **under 5 interactions**.
2. Zero vocabulary required. No "modifier", "vertex", "UV" in any default path.
3. One prompt box that accepts a description and returns a visible result.
4. Every failure states the problem in a sentence a 12-year-old understands, then
   offers the fix as a single click.
5. Full depth always one step away, never more than one menu away, and never
   required to finish.
6. Undo is total and free, and says what it undid in plain words.
7. The agent path and the human path produce **byte-identical** assets from the
   same spec. No second-class output.
8. A human and an agent must be able to hand a session to each other mid-task
   with no state loss.

---

## 6. The 250 — genuinely AI-native, absent from Blender and FreeCAD

### 6.1 The novelty test, stated so it can be audited

A capability counts **only** if a Blender power-user working entirely through
Blender's own features — *including* Geometry Nodes, the `bpy` Python API,
drivers' expressions, and headless mode — could not build it. If they could, it
is parity and it lives in §4, not here.

**What this test killed.** Three large families of "AI-native" ideas were
rejected because Blender already has them: procedural generation (Geometry Nodes,
274 types), scripted automation (`bpy` + drivers), and headless batch
processing (`blender -b`). Also rejected: "nodes for materials" (102 shader
nodes), "asset browser", "undo/redo", and "Python console". None of those count.

The dividing line: **Blender can be scripted, but it cannot see, judge,
conclude, or prove.** Every one of the 250 below is a capability about
intent, verification, provenance, or negotiation — the things a script cannot do
and an agent can. That is not a coincidence; it is the entire thesis.

### 6.2 The 250

**Family A — Intent compilation (A01–A16).** Turning words into geometry, and
being honest when the words are insufficient.

- A01 `intent.compile` — natural-language brief → typed op plan, with every
  inferred parameter reported.
- A02 `intent.clarify` — detect underspecified briefs and emit the *minimal* set
  of blocking questions.
- A03 `intent.conformance` — score the built asset against the brief, clause by
  clause, 0–1 per clause.
- A04 `intent.deviate` — report exactly which clauses the asset violates.
- A05 `intent.infer_params` — derive size, proportion, count, placement and
  style from adjectives.
- A06 `intent.negatives` — parse and enforce negative constraints ("no sharp
  edges", "not glossy", "avoid cylinders").
- A07 `intent.multimodal` — accept text + reference image + reference mesh +
  rough sketch as one spec.
- A08 `intent.spec_diff` — semantic diff between two verbal specs.
- A09 `intent.to_tests` — compile a brief into an executable conformance suite.
- A10 `intent.from_doc` — extract modelling requirements from a design document.
- A11 `intent.completeness` — score how complete a brief is before building.
- A12 `intent.assumptions` — record every assumption made where the spec was
  silent, and surface it.
- A13 `intent.decompose` — split one brief into an ordered asset subtask DAG.
- A14 `intent.expand_set` — "a medieval street" → buildings, props, ground,
  lamps, and a layout.
- A15 `intent.ambiguity_report` — name the ambiguous words and the readings taken.
- A16 `intent.style_lock` — bind a style signature and enforce it on every
  subsequent asset in a set.

**Family B — Self-verification (B01–B20).** The capability Blender structurally
cannot have: seeing its own output.

- B01 `verify.render_critique` — render, show a vision model, apply corrections,
  repeat to convergence.
- B02 `verify.silhouette` — score readable silhouette from the alpha channel.
- B03 `verify.proportion` — score plausibility against learned human proportions.
- B04 `verify.conform` — closed loop: does the render match the words.
- B05 `verify.multi_view` — critique across front/side/three-quarter/top.
- B06 `verify.topology_health` — detect every defect class and report.
- B07 `verify.repair_plan` — emit the ordered fix-op list for detected defects.
- B08 `verify.adversarial` — try to break your own asset and report what broke.
- B09 `verify.confidence` — calibrated per-asset confidence with reasons.
- B10 `verify.uncertainty` — surface "I am 60% sure this matches" honestly.
- B11 `verify.hallucination_guard` — detect ops the agent claimed but did not
  apply.
- B12 `verify.convergence` — stop iterating on measured improvement, not a guess.
- B13 `verify.contact_sheet` — multi-angle sheet for one-shot review.
- B14 `verify.material_critique` — judge PBR plausibility from renders.
- B15 `verify.render_classify` — classify render failures by class, not by vibe.
- B16 `verify.oracle_synth` — author the pass/fail oracle for a new asset type.
- B17 `verify.evidence` — bundle renders, metrics, spec and op journal per asset.
- B18 `verify.self_diff` — detect unintended geometry change between builds.
- B19 `verify.regression_gate` — block a change that degrades a known-good asset.
- B20 `verify.spec_oracle_run` — execute a compiled conformance suite and report.

**Family C — Provenance and determinism (C01–C20).** Assets that can rebuild
themselves, byte for byte.

- C01 `prov.seed` — embed generation seed in GLB extras.
- C02 `prov.recipe` — embed the full op journal in the exported file.
- C03 `prov.replay` — rebuild any asset from its own embedded recipe.
- C04 `prov.stamp` — spec hash + engine version + op-set version.
- C05 `prov.environment` — capture engine build, flags and platform.
- C06 `prov.rng_isolation` — independent deterministic RNG stream per asset.
- C07 `prov.determinism_check` — verify two builds are byte-identical.
- C08 `prov.cross_machine` — verify determinism across machines.
- C09 `prov.vertex_lineage` — trace which op produced which vertex.
- C10 `prov.scene_graph_lineage` — prompt → op → node → mesh, as a graph.
- C11 `prov.change_journal` — attributed change log with actor and reason.
- C12 `prov.rebuild_verify` — full reproducible-build check.
- C13 `prov.tamper_detect` — detect catalog or recipe tampering.
- C14 `prov.lineage_through_edit` — follow provenance across later human edits.
- C15 `prov.semantic_diff` — diff a scene against its own history, meaningfully.
- C16 `prov.intent_diff` — separate what the human changed from what the agent did.
- C17 `prov.braid_commit` — content-addressed lineage commit to the mem20 braid.
- C18 `prov.recipe_portable` — verify a recipe runs on another machine.
- C19 `prov.recipe_minimize` — reduce an op journal to the smallest reproducing set.
- C20 `prov.honest_origin` — mark generated vs authored vs imported, always.

**Family D — Agent protocol (D01–D30).** Everything needed for many agents to
share one scene safely.

- D01 `proto.schema` — emit JSON Schema for every op, automatically.
- D02 `proto.cap_negotiate` — capability handshake; a client learns what exists.
- D03 `proto.gap_report` — when asked for something absent, say so precisely and
  name the nearest thing that does exist.
- D04 `proto.transaction` — atomic op batches with guaranteed rollback.
- D05 `proto.dry_run` — predict the effect of ops without applying them.
- D06 `proto.idempotency` — idempotency keys so a retried op cannot double-apply.
- D07 `proto.preconditions` — declare and enforce op preconditions.
- D08 `proto.postconditions` — declare and verify op postconditions.
- D09 `proto.invariants` — scene-level invariant system plus linter.
- D10 `proto.readonly` — read-only sessions for safe exploration.
- D11 `proto.fork` — fork a session; branch and merge divergent work.
- D12 `proto.lock` — multi-agent scene write locks.
- D13 `proto.lease` — leased claims with expiry, no deadlock.
- D14 `proto.cost_estimate` — estimate cost before spending it.
- D15 `proto.budget_plan` — plan an op sequence to fit a poly/texture budget.
- D16 `proto.constraint_solve` — solve for parameters that satisfy all budgets.
- D17 `proto.parallel_partition` — split ops into provably independent sets.
- D18 `proto.partial_failure` — report exactly which ops applied before failure.
- D19 `proto.checkpoint` — resumable batches.
- D20 `proto.job_handle` — long-running jobs with progress and cancellation.
- D21 `proto.stream` — incremental streamed results, not one big blob.
- D22 `proto.dep_resolve` — resolve op dependencies and execute in order.
- D23 `proto.error_taxonomy` — structured, classifiable errors.
- D24 `proto.self_describing_error` — every error carries its own fix op.
- D25 `proto.status_honest` — never report ok without a verified surface.
- D26 `proto.namespace` — agent-scoped subtrees within one scene.
- D27 `proto.receipt` — content-addressed signed receipts for every mutation.
- D28 `proto.plan_apply` — reviewable plan, then apply, as two distinct steps.
- D29 `proto.cost_benefit` — score op sequences and pick the cheaper route.
- D30 `proto.opset_version` — detect when the op set changed under a client.

**Family E — Generation strategy (E01–E20).** Search and portfolio thinking that
no node graph does.

- E01 `gen.seed_search` — search seed space using render critique as fitness.
- E02 `gen.population` — generate a population, score, keep the best.
- E03 `gen.novelty` — novelty search for genuine design diversity.
- E04 `gen.quarantine` — auto-quarantine failures instead of silently retrying.
- E05 `gen.budget_first` — generate inside a hard budget from the start.
- E06 `gen.family` — variants of one approved design.
- E07 `gen.style_transfer` — learn style from one asset, apply to another.
- E08 `gen.set_coherence` — enforce scale, palette and style across a set.
- E09 `gen.diversity` — prevent 50 near-identical assets in one batch.
- E10 `gen.coverage` — plan which asset types a set is missing, then fill gaps.
- E11 `gen.gap_drive` — generate from catalogue gaps rather than from a list.
- E12 `gen.cluster_prompts` — detect and merge redundant prompts.
- E13 `gen.retry_strategy` — on failure change strategy, do not just repeat.
- E14 `gen.learn_prompt` — adjust prompts from recorded failure causes.
- E15 `gen.category_templates` — per-category generation templates.
- E16 `gen.negative_prompt` — first-class negative prompting.
- E17 `gen.weight_schedule` — scheduled weighting across a generation run.
- E18 `gen.curriculum` — simple-to-complex generation order.
- E19 `gen.reference_lock` — pin a reference asset as a style anchor.
- E20 `gen.batch_scoring` — score a whole batch aesthetically, not per item.

**Family F — Verification as a service (F01–F20).** The gate other tools call.

- F01 `gate.validate` — validate any external mesh through the same gate.
- F02 `gate.budget` — enforce poly, texture and material budgets.
- F03 `gate.report` — machine-readable conformance report, not prose.
- F04 `gate.preflight` — pre-flight an asset for Unity, Godot or Unreal.
- F05 `gate.import_sim` — predict what the target engine will do to this asset.
- F06 `gate.perf_predict` — predict draw calls, triangles, texture memory.
- F07 `gate.texture_budget` — texture memory and dimension budget checks.
- F08 `gate.shader_variants` — estimate shader variant explosion.
- F09 `gate.lod_chain` — verify each LOD actually reduces and stays valid.
- F10 `gate.collision_proxy` — verify collision proxies enclose the visual mesh.
- F11 `gate.material_count` — material and slot budget checks.
- F12 `gate.uv_overlap` — UV overlap detection with a spatial heatmap.
- F13 `gate.texel_density` — texel-density variance report.
- F14 `gate.normal_strength` — normal-map strength validation.
- F15 `gate.nonmanifold` — non-manifold report with locations.
- F16 `gate.degenerate` — degenerate geometry report.
- F17 `gate.scale_consistency` — scale coherence across an asset set.
- F18 `gate.naming` — naming-convention conformance.
- F19 `gate.interpenetration` — detect mesh interpenetration in a scene.
- F20 `gate.fixable` — every finding carries the op that fixes it.

**Family G — Novel geometry intelligence (G01–G20).** Analysis and self-repair
that mesh editors do not do.

- G01 `geo.explain` — describe a mesh in words: what it is, what's odd about it.
- G02 `geo.defect_survey` — full defect census by class, with locations.
- G03 `geo.mesh_diff` — semantic diff between two meshes.
- G04 `geo.canonicalize` — align two meshes into a shared shape space.
- G05 `geo.curvature_budget` — report where curvature is concentrated.
- G06 `geo.poly_attribution` — which feature of the model costs which triangles.
- G07 `geo.cost_per_pixel` — cost-per-visible-pixel analysis.
- G08 `geo.silhouette_decimate` — decimate to preserve outline, not uniform area.
- G09 `geo.lod_autorepair` — detect and fix holes and flips in generated LODs.
- G10 `geo.symmetry_detect` — detect an asset's real symmetry plane.
- G11 `geo.symmetry_repair` — enforce detected symmetry.
- G12 `geo.anomaly` — spikes, pinches, self-intersection, flipped normals.
- G13 `geo.health_score` — one asset health number, with itemised reasons.
- G14 `geo.budget_allocate` — spend a triangle budget where it is visible.
- G15 `geo.detail_allocate` — spend texels where they are seen.
- G16 `geo.engine_breakage` — predict exactly what Unity will complain about.
- G17 `geo.pack_feedback` — UV packing that iterates on measured overlap.
- G18 `geo.rig_from_image` — propose a rig and bone map from a single reference image.
- G19 `geo.retopo_agent` — quad retopology driven by measured defect feedback.
- G20 `geo.complexity_map` — emit an agent-readable complexity map.

**Family H — Cross-engine interop (H01–H18).** Format handling as intent
preservation, not file shuffling.

- H01 `interop.intent_preserving` — convert and report what was lost, in intent
  terms, not byte terms.
- H02 `interop.lossy_predict` — predict loss before converting.
- H03 `interop.auto_format` — choose the right format for a target engine.
- H04 `interop.multi_target` — one asset, validated for Unity and Godot and
  Unreal in a single call.
- H05 `interop.roundtrip_gate` — round-trip verification as a standard gate.
- H06 `interop.extension_aware` — Draco, meshopt, KTX2 detection and handling.
- H07 `interop.unit_normalize` — auto-normalize scale, units and axis on import.
- H08 `interop.material_intent` — preserve material intent across formats.
- H09 `interop.rig_map_infer` — auto-infer a bone map between two rigs.
- H10 `interop.retarget_foot` — retarget animation preserving foot contacts.
- H11 `interop.axis_convert` — Y-up / Z-up / handedness conversion, verified.
- H12 `interop.bake_transforms` — bake transform hierarchies safely.
- H13 `interop.fbx_write` — cleanroom FBX 7.x writer, both ASCII and binary.
- H14 `interop.fbx_read` — cleanroom FBX reader, both ASCII and binary.
- H15 `interop.step` — STEP and IGES read/write for CAD interop.
- H16 `interop.usd` — USD and USDZ read/write.
- H17 `interop.alembic` — Alembic geometry-cache read/write.
- H18 `interop.compat_report` — full compatibility report for a target engine.

**Family I — Rigging and animation intelligence (I01–I18).** The animation
domain, taken seriously.

- I01 `rig.from_proportions` — generate a rig from measured proportions.
- I02 `rig.rig_family` — biped, quadruped, avian, insect, serpent, fish rigs.
- I03 `rig.digitigrade` — digitigrade and plantigrade variants.
- I04 `rig.facial` — face and ear rigs.
- I05 `rig.control_rig` — generate a control rig over a deform rig.
- I06 `rig.map_infer` — infer a bone map between two unrelated rigs.
- I07 `rig.retarget` — retarget motion with foot-contact preservation.
- I08 `rig.foot_slide` — detect and remove foot sliding.
- I09 `rig.ground_align` — plant and align a character to ground geometry.
- I10 `rig.pole_vector` — solve pole vectors and twist correctly.
- I11 `rig.fk_ik_blend` — principled FK/IK blending.
- I12 `rig.weight_norm` — normalise and clean skin weights automatically.
- I13 `rig.mocap_import` — motion-capture import and cleanup.
- I14 `rig.motion_blend` — pose and motion blending with contact awareness.
- I15 `rig.procedural_gait` — generate walk, run and idle cycles.
- I16 `rig.motion_plan` — plan a motion that satisfies a stated goal.
- I17 `rig.validate` — validate a rig and report every problem.
- I18 `rig.solve_report` — explain which solver produced a pose and why.

**Family J — mem20 substrate integration (J01–J20).** Novel because mem20 is
the substrate.

- J01 `mem.toolchest` — register KilNZ so any agent can discover it.
- J02 `mem.catalog` — memory-backed asset catalogue.
- J03 `mem.braid` — content-addressed lineage in the mem20 braid.
- J04 `mem.skill_capture` — learn a successful op sequence as a reusable skill.
- J05 `mem.crew_fanout` — fan out batch generation across a crew.
- J06 `mem.task_split` — decompose asset work for subagents.
- J07 `mem.cross_tool` — chain KilNZ with mem20yetiz and other organs.
- J08 `mem.fallback_label` — honestly label external-tool output as external.
- J09 `mem.roadmap_report` — report progress against a mem20 roadmap.
- J10 `mem.confidence_handoff` — pass confidence and uncertainty between agents.
- J11 `mem.capability_advertise` — advertise capabilities to the orchestrator.
- J12 `mem.failure_log` — propagate failures into the mem20 failures log.
- J13 `mem.recipe_share` — share prompt-to-op recipes across the fleet.
- J14 `mem.dedup` — estate-wide asset deduplication.
- J15 `mem.request_queue` — other agents request assets; KilNZ fulfils them.
- J16 `mem.request_protocol` — a structured asset-request schema.
- J17 `mem.quota` — per-agent quotas and fair scheduling.
- J18 `mem.lifecycle` — draft, review, publish states for assets.
- J19 `mem.release_bundle` — reproducible release bundles with provenance.
- J20 `mem.trump` — KilNZ's decision is final on native-vs-delegated, recorded.

**Family K — The MSPaint floor (K01–K10).** Novel because Blender is
explicitly not simple. Each is a measured interaction guarantee.

- K01 `ux.single_canvas` — everything on one surface, zero modes.
- K02 `ux.plain_errors` — every error in a plain sentence with one fix offered.
- K03 `ux.prompt_to_asset` — one prompt box, one visible result.
- K04 `ux.nl_select` — natural-language selection: "pick the round thing".
- K05 `ux.progressive` — simple by default, full depth one step away.
- K06 `ux.assumption_prompt` — plain-language assumption check before building.
- K07 `ux.explain_undo` — undo that says what it undid, in words.
- K08 `ux.canvas_markers` — visual error markers on the canvas itself.
- K09 `ux.plain_diff` — "show me what changed" in plain language.
- K10 `ux.plain_confidence` — confidence shown in words, not decimals.

**Family L — Generative pipeline layer (L01–L43).** Novel because Blender has no
generative layer at all. Every item is about *routing, gating, verifying or
proving* a neural generation step — the parts that are missing from every
tutorial and every ComfyUI workflow. Research basis in §8.

- L01 `gen.provider_registry` — one registry of every generation backend with its
  capabilities, licence, VRAM floor and output formats.
- L02 `gen.hardware_preflight` — check a host against a model's real requirements
  and fail with the named reason, never a vague error.
- L03 `gen.licence_gate` — refuse or warn on providers whose licence forbids the
  intended use, per region and revenue band.
- L04 `gen.checkout_provenance` — record checkpoint id, revision hash, licence and
  runtime for every generated artifact.
- L05 `gen.revision_pin` — pin exact model revisions so a rerun reproduces.
- L06 `gen.worker_dispatch` — queue a job to a GPU host and collect the result.
- L07 `gen.capability_route` — pick the cheapest backend that meets the budget.
- L08 `gen.cost_estimate` — estimate GPU-seconds and currency before spending.
- L09 `gen.weight_prefetch` — fetch and integrity-check weights ahead of a job.
- L10 `gen.pipeline_graph` — declare a multi-stage generation as one graph op.
- L11 `gen.stage_lineage` — trace image → mesh → texture → video across stages.
- L12 `gen.cross_modal_verify` — does the mesh match the prompt *and* the source
  image, checked independently.
- L13 `gen.degradation_report` — report features a model silently dropped.
- L14 `gen.fallback_chain` — ordered fallbacks, with the reason for each hop.
- L15 `gen.plan_dryrun` — full generation plan with cost and time, applied
  separately.
- L16 `gen.gpu_budget` — hard ceiling on GPU-seconds per asset or per batch.
- L17 `gen.batch_shard` — split a batch across heterogeneous workers.
- L18 `gen.quarantine_class` — quarantine a failure with its class attached.
- L19 `gen.cross_host_replay` — reproduce a generation on a different host and
  compare.
- L20 `gen.weight_verify` — content-addressed verification of downloaded weights.
- L21 `gen.latent_roundtrip` — VAE encode/decode round-trip loss measurement.
- L22 `gen.seed_derive` — derive a seed from the prompt, so the same brief is
  reproducible without storing the seed.
- L23 `gen.negative_report` — prove the negative prompt was honoured, or say it
  was not measurable.
- L24 `gen.multiview_consistency` — measure agreement across generated views.
- L25 `gen.camera_path` — synthesise a camera trajectory as a first-class artifact.
- L26 `gen.gp_buffer` — emit a Gaussian-primitive buffer (colour, depth, normals,
  opacity) from KilN geometry.
- L27 `gen.novelview_video` — render a novel-view video from KilN's own geometry.
- L28 `gen.interp_validate` — frame interpolation with motion-vector validation.
- L29 `gen.video_to_4d` — reconstruct a 4D asset from video using a mesh-plus-
  Gaussian hybrid.
- L30 `gen.unified_raster` — single-pass mesh and Gaussian rasterization with
  correct transparency and occlusion.
- L31 `gen.keyframe_sheet` — auto-generate turntables and contact sheets for
  review.
- L32 `gen.video_gate` — duration, fps, resolution and codec budget enforcement.
- L33 `gen.av_sync_verify` — verify audio-video synchronisation, measured.
- L34 `gen.temporal_score` — score temporal consistency across frames.
- L35 `gen.flicker_detect` — detect and localise temporal flicker.
- L36 `gen.geometry_video_roundtrip` — video back to 3D, compared against the
  source asset.
- L37 `gen.prompt_route` — choose a model from the prompt's characteristics.
- L38 `gen.auto_escalate` — escalate to a stronger model when the cheap one fails
  the gate, and record that it happened.
- L39 `gen.confidence_propagate` — carry per-modality confidence downstream.
- L40 `gen.prompt_cache` — content-addressed prompt/result cache.
- L41 `gen.review_report` — a human-reviewable generation report.
- L42 `gen.stage_contract` — declare and enforce the input/output contract
  between stages.
- L43 `gen.repro_bundle` — ship a generation as a reproducible bundle: prompts,
  seeds, revisions, weights hashes and outputs.

**Family M — Parity-equal capabilities (M01–M62).** **These are NOT part of the
255.** Blender and FreeCAD both have equivalents; they failed the §6.1 novelty
test. Jayson's directive is to include them anyway, which is correct — they are
real capabilities that must exist — so they are tracked here as their own family
with an honest label rather than being allowed to inflate the novelty count.

**M1 — Procedural generation (M01–M33).** Blender's Geometry Nodes is 274 node
types. This is the agent-native equivalent: a declarative graph, but composable,
deterministic, replayable and inspectable as ops.

- M01 `proc.graph` — a declarative procedural graph as a first-class, inspectable op.
- M02 `proc.field` — the attribute/field system, the backbone of everything else.
- M03 `proc.position` / `proc.normal` / `proc.velocity` — standard fields.
- M04 `proc.capture` — capture an attribute for later use.
- M05 `proc.store` — store a named attribute on a domain.
- M06 `proc.mix` / `proc.switch` — blend and branch between values.
- M07 `proc.random` — seeded per-element randomness, reproducible.
- M08 `proc.noise` — noise textures exposed as fields.
- M09 `proc.instance_on_points` — instancing on points, faces or volumes.
- M10 `proc.distribute` — scatter/distribute across a surface.
- M11 `proc.join` / `proc.transform` — combine and transform geometry streams.
- M12 `proc.set_position` — write positions procedurally.
- M13 `proc.delete_by_selection` — selection-driven deletion.
- M14 `proc.curve_to_mesh` — sweep a profile along a curve.
- M15 `proc.mesh_to_curve` — extract an edge or boundary curve.
- M16 `proc.curve_line` / `proc.curve_circle` / `proc.curve_star` — procedural curves.
- M17 `proc.resample` / `proc.trim` / `proc.fill_curve` — curve operations.
- M18 `proc.extrude` / `proc.revolve` — geometric extrusion and revolution.
- M19 `proc.grid` / `proc.point_cloud` — generated domains.
- M20 `proc.sample_index` / `proc.sample_curve` — indexed and curve sampling.
- M21 `proc.nearest` / `proc.proximity` — spatial queries as fields.
- M22 `proc.bounds` — bounding information as a field.
- M23 `proc.interpolate` — domain-to-domain interpolation.
- M24 `proc.spline_parameter` — parametric access along a curve.
- M25 `proc.curve_length` / `proc.curve_factor` — arc-length parameterisation.
- M26 `proc.boolean` — boolean as a graph node, not a modifier.
- M27 `proc.duplicate_elements` — instanced duplication.
- M28 `proc.split_edges` / `proc.merge_by_distance` — topology as graph ops.
- M29 `proc.set_material` — assign materials procedurally.
- M30 `proc.set_shade_smooth` — shading as a field.
- M31 `proc.node_group` — reusable, nestable, versioned subgraphs.
- M32 `proc.eval_inspect` — inspect the evaluated result of a graph, not just the inputs.
- M33 `proc.graph_diff` — semantic diff between two procedural graphs.

**M2 — Scripted automation (M34–M48).** Blender has `bpy` and drivers. So does
this, with the agent-facing differences called out.

- M34 `api.in_process` — embeddable op API with no subprocess round trip.
- M35 `api.driver` — expression driver bound to any property.
- M36 `api.driver_namespace` — a safe namespace for driver expressions.
- M37 `api.custom_property` — arbitrary typed properties on any datablock.
- M38 `api.property_ui` — declared min/max/step/tooltip/description for a property.
- M39 `api.handler` — lifecycle handlers with declared scopes.
- M40 `api.register_op` — register a new op at runtime.
- M41 `api.register_modifier` — register a node in the procedural graph.
- M42 `api.node_group` — author and load reusable subgraphs.
- M43 `api.scripted_asset` — an asset that carries its own generation script.
- M44 `api.sandbox` — run untrusted scripts under stated limits.
- M45 `api.eval` — evaluate an expression or script in a session.
- M46 `api.docs_from_schema` — generate reference docs from the op schemas.
- M47 `api.test_harness` — in-process test runner for op sequences.
- M48 `api.orchestrator` — a program that composes many ops into a pipeline.

**M3 — Headless batching (M49–M62).** Blender has `blender -b`. So does this,
with farm-scale semantics.

- M49 `batch.mode` — full headless operation from a file or manifest.
- M50 `batch.manifest` — a declarative batch manifest as a first-class format.
- M51 `batch.farm` — distribute assets or frames across workers.
- M52 `batch.queue` — prioritised job queue.
- M53 `batch.resume` — resume an interrupted batch from its last checkpoint.
- M54 `batch.shard` — deterministic sharding by stable key.
- M55 `batch.retry` — retry policy distinct from blind repetition.
- M56 `batch.dry_run` — validate and cost a batch without executing it.
- M57 `batch.progress` — machine-readable progress events.
- M58 `batch.job_timeout` — per-job timeout with a named reason on expiry.
- M59 `batch.worker_determinism` — prove two workers produced identical output.
- M60 `batch.cache` — content-addressed render and mesh cache.
- M61 `batch.watch` — watch a directory for new manifests.
- M62 `batch.report` — structured per-item batch report, no prose summary.

**Counts.** AI-native novelty-tested: **255** (families A–L). Parity-equal,
added by directive: **62** (family M). Total tracked capability: **317**.

> **Count discipline.** Both numbers are mechanically verifiable:
> `grep -cE '^- [A-L][0-9][0-9] '` → 255, and `grep -cE '^- M[0-9][0-9] '` → 62.
> The 255 is the answer to "at least 250 features Blender does not have". The 62
> is tracked separately on purpose, so a future reader can always tell which
> claim is which. If either grep disagrees with this line, the grep is right.

> **Verification note — corrected.** The first draft of this document claimed
> 263. That number was wrong. The per-family subtotals were correct and summed to
> 212; the headline figure was not derived from them. It has been recounted
> mechanically from the ID lines — `grep -cE '^- [A-KL][0-9]{2}'` over §6.2 — and
> family L was added to clear the 250 requirement with capabilities that are
> genuinely absent from Blender rather than padding. The verified total is
> **255**. Re-run that grep before trusting this document as a tracker; if the
> number and the list ever disagree, the list is the truth.

---

## 7. Phasing

Sequenced by dependency, not by excitement. Each phase ends with something that
runs and is verified.

| Phase | Name | Delivers | Depends on |
|---|---|---|---|
| 0 | **Verify** | Engine builds clean, 79 ops proven, RPC proven, GLB/PNG validated, checksums recorded, git baseline | — |
| 1 | **Close the dead declarations** | glTF/GLB importer, OBJ read/write, quadric decimator, normal recompute, loose-part separation, all bound as ops | 0 |
| 2 | **mem20kilnz package** | pyproject, console script, hardened RPC client, engine build harness, keys from the secrets file only | 0 |
| 3 | **Interop** | FBX read/write, STL, PLY, USD, Alembic, round-trip gate, loss prediction, multi-target export | 1, 2 |
| 4 | **Rigging** | Rig families, control rigs, constraints, retargeting, foot planting, weight cleanup, motion capture | 1 |
| 5 | **Materials and PBR** | Node-graph shading, image textures, procedural textures, baking, IBL, PBR export compliance | 2 |
| 6 | **Animation** | Curves, interpolation, easing, drivers, NLA, procedural gaits, motion planning | 4 |
| 7 | **Solid and CAD** | B-Rep kernel, booleans, fillets, NURBS surfaces, loft/sweep/revolve, sketch constraint solver, tessellation bridge | 1 |
| 8 | **Curves, text, metaballs, volumes, clouds** | The remaining primitive representations | 7 |
| 9 | **Modifiers and node system** | Modifier stack, geometry-node-equivalent op algebra, evaluated-outcome inspection | 1, 7 |
| 10 | **Retopology, UV, sculpt, texturing** | Quad retopo, full unwrap, sculpt brushes, image painting, bake | 9 |
| 11 | **Render** | Path tracer, EEVEE-class raster features, volumes, SSS, compositing, denoise | 5, 9 |
| 12 | **Physics** | Cloth, soft body, particles, rigid body, collision, force fields | 9 |
| 13 | **The 250** | Families A–F, G, H, J, K — the AI-native layer, on top of a stable kernel | 1–5 |
| 14 | **Sequencer and tracking** | VSE, motion tracking, camera solving | 11 |
| 15 | **FreeCAD tail** | Draft, Path/CAM, Robot, BIM, Inspection, Measure, STEP/IGES depth | 7, 3 |
| 16 | **MSPaint floor** | The eight acceptance criteria in §5, measured | all |

**Critical path:** 0 → 1 → 7 → 9 → 11. Everything else branches off it.
**The 250 are not on the critical path** — they need a stable kernel, not a
finished one, so Phase 13 can start as soon as Phases 1–5 land.

---

## 8. Generative pipelines

Five pipelines: **text→3D, image→3D, text→video, image→video, 3D→video.** Plus
**3D→4D** and **video→3D** as the round-trip returns.

### 8.1 The hard constraint, stated first

Every neural backend below needs a CUDA GPU. Measured on this host:

| | |
|---|---|
| GPU | **none** — Intel Skylake-U HD Graphics 520 (2015), no CUDA |
| `/dev/nvidia*` | absent |
| nvidia driver | not loaded, no kernel module |
| CPU / RAM | 4 cores / 15 GB |
| torch build | 2.14.0+**cpu** |

The smallest serious backend is TripoSR at ~6 GB VRAM. Nothing on that list runs
here, and no optimisation changes that. So the pipeline layer is built as
**hardware-gated providers**, not as fake integrations:

- Every provider declares its real requirements — compute backend, VRAM floor,
  licence, supported inputs and outputs.
- `preflight` checks the host and **fails loudly with the named reason** —
  `blocked: TRELLIS.2 requires CUDA GPU with >=24GB VRAM; this host has Intel
  HD 520, no CUDA` — never a stub, never a silent fallback.
- A **Tier 0** path runs on this host today with no GPU at all: KilN's own
  parametric generation. That is genuine text→3D, it produces clean quad
  topology, and it hands the agent an asset it can keep editing with ops. It is
  not a consolation prize — it is the only 3D path that yields a *modifiable*
  asset.

### 8.2 Architecture

One declarative pipeline graph, one provider interface, one artifact store.

```
spec ──▶ intent.compile ──▶ plan (dry-run: cost, VRAM, time, licences)
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
        Tier 0 parametric     Tier 1 GPU-hosted     Tier 2 external SaaS
        (runs here now)       (worker dispatch)      (labelled, recorded)
              └────────────────────┴────────────────────┘
                                   ▼
                          artifact + lineage
                                   ▼
                          gate.validate ──▶ publish / repair / quarantine
```

Every stage declares an input/output contract (`gen.stage_contract`), and
`gen.stage_lineage` traces image → mesh → texture → video so a bad result is
attributed to the stage that caused it rather than guessed at.

### 8.3 3D generation backends

| Backend | Input | Output | VRAM | Licence | Note |
|---|---|---|---|---|---|
| **TRELLIS.2** (Microsoft, Dec 2025, 4B) | single image | mesh + PBR incl. opacity; GLB/OBJ/STL | ~24 GB, ~8 GB quantized | **MIT** | O-Voxel sparse voxels. Published 3 s @512³, 17 s @1024³, 60 s @1536³ on H100. **Image only — no text checkpoint.** Fidelity leader. |
| **TRELLIS** (original) | **text + image** | radiance field / 3D Gaussians / mesh | ~16 GB | **MIT** | SLAT structured latents. text-base 342M, text-large 1.1B, text-xlarge 2.0B. **The open text→3D option.** |
| **Hunyuan3D-2.1** (Tencent, Jun 2025) | image, multi-view | holeless mesh + PBR paint; GLB/OBJ | ~10 GB shape, ~29 GB full | Community — **excludes EU/UK/South Korea** | Two-stage Shape 3.3B → Paint 2B, texture-only mode. Text path chains a text-to-image model in front. |
| **TripoSR** | single image | mesh, vertex colours; OBJ/GLB | ~6 GB, CPU fallback | **MIT** | <0.5 s on A100. Lightest usable option. No PBR. |
| **SF3D / Stable Fast 3D** (Stability) | single image | UV-unwrapped mesh + material params + normal map; GLB | ~6 GB | check repo | 0.5 s. Illumination disentanglement. Built-in remesh: none / triangle / quad. |
| **PartCrafter** (NeurIPS 2025) | single image | **part-level** multi-part mesh | GPU | check repo | Decomposes assets into separately editable parts. Builds on TripoSG; compatible with Hunyuan3D-2.1. |
| **PartPacker** (NVIDIA) | single image | part-level, dual-volume packing | GPU | **non-commercial** | Research use only. |
| **Meshy T2** (Aug 2026) | single image | native multi-part mesh, flow matching | GPU | announced | 2–6 s median. **Weights were "to be open-sourced shortly" as of the Aug 2026 post — treat as unavailable until the weights exist.** |

**Agent-relevant note.** Part-level output — PartCrafter, PartPacker, Meshy T2 —
is the most important trend in that table for us, because a mesh arriving as
named separable parts is a mesh an agent can then edit per part with ops. A
single fused 300k-triangle blob is not editable no matter how good it looks.
That is a gate criterion, not a preference.

### 8.4 Video generation backends

| Backend | Modes | VRAM | Licence | Note |
|---|---|---|---|---|
| **Wan 2.2** (Alibaba) | T2V, I2V, S2V, Animate | 5B: 24 GB · 14B MoE (27B total, 14B active): 6–8 GB quantized, 54–65 GB FP16, repo asks 80 GB | **Apache 2.0** | TI2V-5B does 720p@24 fps in <9 min on a 4090. VAE compression 4×16×16. **Cleanest licence in the field.** |
| **Wan 2.1** | T2V, I2V, FLF2V, VACE, T2I | 1.3B: 8.2 GB · 14B: 40 GB+ FP16, ~24 GB quantized | **Apache 2.0** | 480p/720p, 81 frames. In Diffusers. |
| **LTX-2.3** (Lightricks) | T2V, I2V, **native synced audio** | 80 GB+ standard · 32 GB FP8 distilled · 8 GB GGUF | LTX-2 Community — **$10M revenue threshold triggers a paid licence** | 22B (14B video + 5B audio over 48 shared blocks). Only open model generating audio and video in one pass. Distilled: 8 steps, ~4 s on H100. |
| **HunyuanVideo 1.5** (8.3B, Nov 2025) | T2V, I2V | ~14 GB with offloading | Tencent Community — **excludes EU/UK/South Korea** | 75 s for 480p on a 4090, step-distilled. **Do not confuse with the original 13B, which needs 60–80 GB @720p.** |
| **CogVideoX** 2B / 5B | T2V, I2V | 24 GB | 2B Apache 2.0 / 5B custom | Short clips. |
| **Mochi 1** (10B) | T2V | 60 GB; <20 GB via ComfyUI | **Apache 2.0** | 480p. |
| **Open-Sora 2.0** (11B) | T2V | 60.3 GB on one H100 | **Apache 2.0** | Research tier. |
| **Helios** | T2V | 80 GB (H100) | check | Real-time 19.5 fps on one H100. Speed reference. |
| **RIFE** | frame interpolation | low | open | Real post-stage: 81 @16 fps → 162 @30 fps. |

**Licensing is a first-class gate, not a footnote.** Only Wan 2.2, Wan 2.1,
Mochi 1 and Open-Sora 2.0 are cleanly Apache 2.0. Hunyuan excludes three
jurisdictions. LTX-2 requires a paid agreement past $10M revenue. And a finding
worth recording: **pages advertising "Wan 2.7" open weights are SEO
fabrications — official Wan open weights stop at 2.2.** A `gen.licence_gate`
that blocks on region and revenue band is therefore a real feature, not
paperwork.

*Confidence note:* the VRAM figures come from multiple independent secondary
sources and **disagree with one another** in places — LTX-2.3 appears variously
as "24 GB", "80 GB+" and "8 GB GGUF" depending on variant and precision. Treat
them as tiers and let `preflight` measure rather than trust a table. Claims that
LTX 2.5 and MiniMax H3 are the current September-2026 frontier rest on a single
source and are **not** relied on here; the table sticks to checkpoints whose
weights are verifiably published.

### 8.5 3D→video: where KilNZ is genuinely novel

Nobody has a good answer here, which is exactly why it is worth owning. The
published frontier is 3D *Gaussian* → video, and the strongest result is
**GaussFusion** (CVPR 2026): it rasterises a Gaussian-primitive buffer encoding
**colour, depth, normals, opacity and covariance**, then feeds that to a video
generator on a **Wan DiT backbone** with interleaved Geometry Adapter blocks,
lifting reconstruction from PSNR 17.27 to 21.53 with a 16 fps real-time variant.

A mesh-native tool emits that representation *exactly*, because a mesh already
has authoritative depth and normals — no optimisation, no floaters, no covariance
guesswork. So the KilNZ pipeline is:

```
KilN geometry (exact mesh, exact normals, exact depth)
  └─▶ camera path synthesis             (gen.camera_path)
        └─▶ multiview render             (KilN software renderer — exists today)
              └─▶ GP-Buffer emission      (gen.gp_buffer: colour+depth+normals+opacity)
                    └─▶ video-to-video refinement   (Wan / LTX backend)
                          └─▶ frame interpolation    (RIFE)
                                └─▶ gate: temporal score, flicker, av-sync
```

Also worth owning: **video→3D→4D** through a mesh-plus-Gaussian hybrid
(DreamMesh4D's LBS+DQS skinning is the reference), and unified single-pass
mesh+Gaussian rasterization with correct nested transparency (UniMGS) — which
no current tool has, because no current tool is both mesh-native *and*
radiance-native.

### 8.6 What "in place" honestly means

| | Status once this plan is built |
|---|---|
| Pipeline graph, provider interface, preflight, licences, lineage, gates, cache, cost, replay | **Real, built, tested on this host** |
| Tier 0 text→3D (KilN parametric) | **Real, runs here now** |
| Tier 1 adapters: TRELLIS.2, TRELLIS, Hunyuan3D, TripoSR, SF3D, Wan, LTX | **Code complete, hardware-gated, verified blocked on this host with a named reason** |
| Actually running the neural weights | **Blocked. No GPU. Unblocks the moment a CUDA host is attached.** |
| 3D→video novel-view + GP-Buffer path | KilN half real; the video-refinement half inherits the same GPU gate |

I will not claim a single generated mesh or video frame from a model that cannot
run on this hardware. What I will deliver is the complete, tested, honestly
labelled machine — plus the one pipeline that genuinely works here.

---

## 9. Honest scale

I am not going to dress this up.

- **The parity target is 4,000–5,000 addressable units.** Blender's 2,010
  operators are measured; the rest is a stated estimate. At a realistic,
  honest pace for one agent working with review gates, this is **multi-year**,
  not multi-session. Phase 0 through Phase 5 is achievable in a small number of
  focused working days. Phase 11 and beyond is not.
- **The 263 AI-native features are the tractable, high-value part** and can be
  built incrementally against a stable-enough kernel. This is where KilNZ beats
  Blender rather than matching it.
- **The CAD kernel is the single biggest chunk.** OCCT-class B-Rep is years of
  work. The honest options are: implement a real but smaller B-Rep kernel
  ourselves, or use FreeCAD's OCCT as an explicitly-labelled external engine
  behind KilNZ's op interface. My recommendation is the second — it is the same
  pattern as §3.3, it is honest, and it buys years.
- **No GPU on this box.** Neural text-to-3D remains blocked. If a GPU appears,
  that is a new phase, not part of this estimate.
- **Review gates matter more than throughput here.** A 4,000-unit port built
  without gates produces 4,000 plausible-looking untested units, which is worse
  than useless. Every phase must be verified before the next begins.

---

## 10. Verification standard

Unchanged from the standing rules, restated because it is the whole game at
this scale:

1. No capability is called done until it is written, integrated, compiles, and
   has a real test with real output shown.
2. Every op gets a real round-trip test, not a smoke test.
3. No "supported" claim without a demonstrated artifact and a checksum.
4. Failures get logged, not retried silently.
5. Detection never mutates anything the user authored.
6. If a capability is stubbed, it is labelled as such in the code, in the docs
   and in this file — never as a finished feature.

---

## 11. What happens when you get back

1. Read this. Tell me what to cut, and confirm the sequencing in §7.
2. I execute Phase 0 immediately — build, prove, record checksums, git baseline.
3. Phase 1 closes the nine dead declarations and lands the glTF/GLB importer.
4. Then the mem20kilnz package, the pipeline, the gate, the catalogue, the
   skills, and the toolchest registration.

Phase 0 needs no decisions from you beyond this document. Everything after
Phase 1 has at least one genuine fork, and I will stop and ask at each one
rather than guess.
