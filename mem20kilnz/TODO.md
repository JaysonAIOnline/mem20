# TODO — KilNZ

Source of truth for scope is `PROPOSAL.md`. Phases are in the mem20 roadmap
`kilnz`. This file is the checkable item list with evidence.

Status key: `[x]` done with evidence · `[ ]` open · `[~]` in progress

---

## Phase 0 — Verify the engine as received

- [x] Relocate `Kiln1_v6` → `/opt/mem20/mem20kilnz/engine`, same filesystem so
      the move was atomic. 68 files, 2,304,392 bytes before and after.
      Evidence: git `7cb00f5`.
- [x] Fix the misnamed ignore file (`gitignore` → `.gitignore`) and add the
      missing `*.d` / `__pycache__/` rules.
- [x] Build clean. `g++ 15.3.0 -std=c++17 -O2 -Wall -Wextra`: **0 warnings,
      0 errors**, `make` exit 0. Binary 1,096,440 bytes.
- [x] Confirm the op count independently. Extracted `kind == "…"` from
      `apply_op` in `src/ops/ops.cpp` → **79**; runtime `ping` → `ops=79`;
      `docs/RPC.md` claims 79. All three agree.
- [x] `make rpc` — valid JSON-RPC 2.0 on stdout, exit 0.
- [x] `make demo` — English path works ("add a red cube" → `created Cube`),
      named colours resolve, PNG + GLB written, exit 0.
- [x] `examples/rpc_session.py` — full client session, 14 ops, Box 6→18 faces,
      render 4x, export 5 nodes / 3 meshes, deliberate failure returned
      `[-32000] frame: no node 'NoSuchNode'` and the session survived, exit 0.
- [x] Independent artifact validation via `file(1)`: `PNG image data, 960 x 540,
      8-bit/color RGBA` and `glTF binary model, version 2`.
- [x] Determinism: same scene generated 3× → byte-identical GLB
      `460ed423a44d39371df21e7cc5b9baf0` and PNG
      `89ffa9631bb2d1ac57c8baf0a07fcf34`. Both match `docs/RPC.md` exactly.
- [x] Diagnose + fix the stale example corpus. Root cause: a UV-generation
      change after the examples were committed. Divergence confined to accessor
      2 (`VEC2 FLOAT` = `TEXCOORD_0`); positions, normals, indices bit-identical.
      Regenerated; evidence git `fac9fd0`.
- [x] Write `CONFWORK.md` (verified facts only) and `failures.md` (5 entries).
- [x] Record the proposal in the mem20 roadmap `kilnz` (18 phases).

**Phase 0 complete.**

---

## Phase 1 — Close the sixteen dead declarations

**Five of sixteen closed.** 1a, 1b and 1c below are done; the remaining eleven
are queued and listed explicitly so none can be forgotten.

- [x] `import_gltf` — real glTF 2.0 / GLB **importer**. Container, JSON + BIN
      chunks, buffers from a BIN chunk / base64 data URI / external `.bin`, all
      six accessor component types with normalized dequantization, `byteStride`
      interleaving, sparse accessors, TRIANGLES / STRIP / FAN, node `matrix` and
      TRS with quaternion decomposition and negative-determinant scale,
      multi-primitive meshes, PBR materials, perspective cameras, skins with
      inverseBindMatrices and JOINTS_0/WEIGHTS_0.
      Evidence: geometry round-trip byte-for-byte lossless; 17/17 fixtures pass,
      every positive fixture first validated in Blender 5.2.
- [x] `import_obj` / `export_obj` — OBJ reader and writer. `v v/vt v//vn v/vt/vn`
      tokens, negative indices, n-gons, `o`/`g` grouping, 4-component `v`.
      Evidence: `Cube` 8 verts and `Ball` 266 verts preserved exactly through a
      round trip; Blender reads the written file.
- [x] `decimate_mesh` — **vertex clustering**. Rejected quadric edge collapse on
      measured evidence (20-79% volume loss, could not reach target); see
      `failures.md`. Area drift 4.0% at ratio 0.75, 6.7% at 0.5, zero degenerate
      and zero non-manifold. QEM is the recorded upgrade.
- [x] `recalc_normals` — area-weighted normals with BFS winding consistency.
- [x] `separate_loose_meshes` — connected components. Verified splitting a
      2-triangle disjoint mesh into 2 pieces.
- [x] Every new function bound as an op in `ops.cpp` plus a DSL verb, so all four
      entry points reach it through the one dispatcher. Op surface 79 → 87.
- [x] `tests/check_op_sync.py` — fails if the advertised op surface ever drifts
      from `apply_op` again. All four surfaces agree at 87.
- [x] `tests/mesh_metrics.py` — geometric quality metrics (non-finite,
      degenerate, non-manifold, area, signed volume) with reference comparison.

- [x] `apply_frame` — sets the frame, lerps each bone's pose between the two
      nearest keys, reverts unkeyed bones to rest.
- [x] `ik_two_bone` — verified end to end: a bound mesh moves 0.511 units with
      cos 0.9878 to the target direction.
- [x] `catmull_clark` — 288 faces to 1104 at level 1, 4416 at level 2.
- [x] `wireframe_mesh` — cube 6 faces to 72 (12 edges x 6 quads).
- [x] `shrinkwrap_mesh`, `symmetrize_mesh` — 266 verts wrapped; mirroring and
      welding verified.
- [x] `extrude_individual`, `rotate_verts`, `scale_verts`, `shear_verts`.
- [x] `boundary_faces` — closed cube reports 0, open plane reports 1.
- [x] **Zero dead declarations remain.** Audit of all 88 declarations in
      `scene.hpp` against every `.cpp` definition reports 0 unimplemented.
- [x] All of them bound as ops plus DSL verbs. Op surface 79 -> 103, and
      `tests/check_op_sync.py` confirms all four op surfaces agree.
- [ ] Add `flip_normals` to `docs/RPC.md` — live but undocumented.

## Phase 2 — `mem20kilnz` package

- [x] `pyproject.toml`, package dir, `python -m mem20kilnz`, console script,
      README claiming only what is verified, dev extras, ruff config.
- [x] Hardened RPC client (`rpc.py`): absolute path resolution, `KILNZ_BINARY`
      honoured, engine location in one place.
- [x] Engine build harness so the Python package owns its own kernel
      (`engine.py`, `mem20kilnz build-engine`).
- [x] Keys read from `/opt/mem20/secrets/.env` only. `secrets.engine_env()` is
      the sole path to the engine environment.
- [x] Provider resolution following estate policy (Groq primary, NVIDIA
      fallback, xAI disallowed). `openai/gpt-oss-120b` verified live.
- [x] `validate` / `gate` separation with a derived verdict and a tested
      exit-code matrix. 43 tests pass, ruff clean.

## Phase 3 — Pipeline, gate, catalogue

- [x] prompt → GLB + preview PNG + manifest, with the op journal embedded.
      Required an engine journal first, since model-invented ops are invisible
      to the client. Zero-geometry builds are failures, not gate refusals.
- [x] `gate.validate` — real GLB structural validation, promoted to a shipped
      tool with tests, and separated from the budget gate.
- [x] `verify` — re-check a manifest against the bytes on disk.
- [x] Asset catalogue over manifests, with untracked/unreadable reporting.
- [x] External mesh ingest: read-only `probe` plus `convert` with manifests
      marked `source: external`.
- [x] Detail tiers: `blockout` / `standard` / `hero`. The roadmap budgets are
      the `standard` tier unchanged; `blockout` is derived, `hero` is restricted
      to hero-scale families. Guards both ways.
- [x] Refine stage that only adds real geometry: `bevel` with an explicit
      region, measured every step, with a ceiling guard that rolls back an
      overshooting pass. `subsurf` is excluded by construction.
- [x] Manifest records `requested_tier` / `achieved_tier` / `tier_met`, measured
      from the exported file rather than the request.
- [x] Partial builds keep the geometry they managed to create, and failed
      briefs leave no artifact on disk.
- [x] Salvage complete ops from a truncated model response instead of
      discarding the whole reply.
- [x] Plain-English description of the exported model, so a text-only agent can
      do text-to-3D: world-space dimensions, width and thinness per part,
      containment and parentage, hue-derived colour names, proportions. Written
      into every manifest, plus a `describe` command and verb.
- [x] FBX import via assimp, with real hierarchy, materials, cameras and lights.
      18 of 19 real files import, zero face mismatches against an independent
      assimp oracle using identical post-processing flags.
- [x] Vertex sharing: the render mesh welds on (position, normal, uv), so an
      export is no longer a triangle soup. Curved primitives are smooth-shaded
      so they can weld at all.
- [x] UVs and normals survive import and export. TEXCOORD_0 is omitted when a
      mesh has no real UVs instead of publishing the old fabricated ramp.
- [x] QEM decimation, now the default. The hole boundary must be walked in
      *cyclic order* through the face fan, not collected as a set. Hits the
      requested ratio exactly, stays closed with zero degenerate faces, and
      drifts 6-20x less volume than clustering (-0.6% vs -13.2% at ratio 0.5).
      Decimation refuses a mesh that is not a closed surface, with real counts.
- [x] `subsurf` fixed: the quad sub-faces needed the face point, and the
      triangulation had to fan from the edge point so diagonals cannot coincide
      across an original edge. Sphere, torus, cylinder and cone are watertight
      with 0 boundary and 0 non-manifold edges at every level, and subdivided
      meshes can now be decimated.
- [ ] Mesh boolean (union / difference / intersect) does not exist. It was named
      in an earlier summary of mine; it is absent from the 106-op surface.
- [ ] `remesh` does not exist.
- [ ] `displace` does not exist, so there is no way to add surface detail.
- [ ] No `skin` op, so imported skin weights cannot be authored or edited.
- [ ] No clip or keyframe op: animation is a scene cursor only.
- [x] Determinism: `replay` and `reproduce` rebuild an asset from its journal
      and compare SHA-256, so a manifest is verified rather than trusted. A
      30-op build with refine replays byte-identically. This also caught the
      journal being read before refine, so manifests described the blockout.
- [ ] Animation: clips, authoring pipeline, retargeting.
- [ ] Procedural generation: real node-graph authoring.
- [ ] Poly / texture / material budgets from the `jairf-tech-budgets` roadmap,
      and naming-convention enforcement (`SM_` `SK_` `M_` `T_` `PF_` `A_`).
- [ ] Ingest path: import external mesh → re-mesh to budget → fix normals →
      validate → catalogue.
- [ ] Disk catalogue where every asset records the prompt and ops that made it,
      so output is reproducible rather than orphaned.

## Phase 4 — Skills and registration

- [ ] Skill: how to drive KilNZ (ops DSL, RPC, budgets, worked examples).
- [ ] Skill: the production pipeline for a game, carrying the `jairf-art-style`
      keyword discipline and the `jairf-tech-budgets` limits.
- [ ] `python -m toolchest refresh` then confirm with `show`.
- [ ] Wire as the 3D backbone under the `jairf-assets` roadmap.

## Phase 5 — Honest close

- [ ] Real pytest suite green against the real binary.
- [ ] Real generated assets with recorded checksums.
- [ ] Control files in sync with reality.
- [ ] Written list of everything still missing.

---

## Queued defects found during Phase 0

- [ ] `flip_normals` live but absent from `docs/RPC.md`.
- [ ] No `modifiers` system at all — none of Blender's ~40 modifiers exist, and
      that is invisible from the op list alone. Needs stating in the README.
- [ ] Examples regenerated, but the rest of the example corpus
      (`bevel.glb`, `edit.glb`, `model.glb`, and ~15 PNGs) has not been checked
      for the same UV-generation staleness. Audit them the same way before
      trusting any of them as fixtures.
