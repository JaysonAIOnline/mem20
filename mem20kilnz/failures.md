# failures.md — every failure, logged

Format: date · attempt · actual error · cause (or "unknown") · next action.

---

## 2026-09-25 — Proposal claimed 263 AI-native features; real count was 212

- **Attempt:** stated "Count: 263" in `PROPOSAL.md` §6.2.
- **Actual error:** the per-family subtotals in the same paragraph summed to
  212. The 263 was not derived from anything; it was wrong.
- **Cause:** hand-summed headline figure never reconciled against the item
  list. The subtotals were correct, which is exactly why it survived a
  read-through.
- **Next action:** recounted mechanically with
  `grep -cE '^- [A-L][0-9][0-9] '`, then added family L (43 genuine
  generative-pipeline capabilities) to clear 250 honestly rather than padding.
  Now 255, verified. The document carries the verification command and the
  correction note.
- **Rule learned:** never publish a hand-summed count. Publish the grep.

## 2026-09-25 — Sixteen engine functions declared but never implemented (not nine)

- **Attempt:** report dead declarations in the engine as a Phase 1 blocker.
- **Actual error:** I first reported **nine**. The true count is **sixteen**.
  My check grepped nine names I had picked by hand and confirmed each appeared
  exactly once. It never audited the full declaration list, so seven more were
  missed: `apply_frame`, `boundary_faces`, `extrude_individual`, `ik_two_bone`,
  `rotate_verts`, `scale_verts`, `shear_verts`.
- **Cause:** sampling the header by hand instead of enumerating it. A regex
  audit of all 88 declarations in `scene.hpp` against every `.cpp` definition
  found the other seven immediately; a direct grep then confirmed each appears
  only in its own declaration.
- **Why it matters:** two of the seven are `apply_frame` and `ik_two_bone` — the
  engine's frame evaluation and two-bone IK. So animation and IK are declared
  but absent, which is invisible from the op list and would have made Phase 1
  and the rigging/animation phases under-scoped.
- **Next action:** Phase 1 implements the ingest-critical subset; the remainder
  (`apply_frame`, `ik_two_bone`, `extrude_individual`, `rotate_verts`,
  `scale_verts`, `shear_verts`, `boundary_faces`, `catmull_clark`,
  `wireframe_mesh`, `shrinkwrap_mesh`, `symmetrize_mesh`) is implemented or has
  its declaration removed. No silent dead code either way.

## 2026-09-25 — Nine engine functions declared but never implemented (superseded)

- **Attempt:** rely on `import_obj`, `decimate_mesh`, `recalc_normals` for the
  external-mesh ingest path.
- **Actual error:** all nine appear exactly once in the whole tree — the
  declaration in `src/scene/scene.hpp`. No definition, no call site. They are
  dead declarations. `import_obj` and `export_obj` included, and there is no
  glTF/GLB importer at all, not even declared.
- **Cause:** unknown. Most likely the header was written ahead of the
  implementations during the v6 work and never reconciled.
- **Impact:** the "import → re-mesh to budget → fix normals → validate →
  catalogue" path is roughly half missing. LOD generation cannot meaningfully
  reduce geometry because `decimate_mesh` does not exist.
- **Next action:** Phase 1 — implement glTF/GLB importer, OBJ read/write,
  quadric edge-collapse decimator, normal recompute, loose-part separation, and
  bind each as an op so DSL / English / JSON-RPC all reach it through the one
  dispatcher.

## 2026-09-25 — Committed `examples/demo.glb` and `demo.png` are stale

- **Attempt:** `git status` after `make demo` showed both example artifacts as
  modified.
- **Actual error:** committed vs freshly generated differ. GLB
  `150467ac…` (committed) vs `460ed423…` (current); PNG `7797f63d…` vs
  `89ffa963…`.
- **Cause:** a change to UV generation after those examples were committed. The
  JSON chunks are **byte-identical** (0 differences, verified by structural
  walk). The BIN chunk differs in 39,713 of 55,284 bytes, and every differing
  range falls inside accessor 2 — `VEC2 FLOAT`, count 36, used as
  `TEXCOORD_0` on mesh 0 primitive 0. Positions, normals and indices are
  bit-identical. The render is byte-identical because the software renderer
  uses flat PBR colours and never samples a texture, so UVs cannot affect it.
- **Severity:** benign visually, real for trust. The example corpus did not
  correspond to the source, which would make any round-trip test built on those
  files fail confusingly.
- **Next action:** regenerate the example corpus from the current source and
  commit it, so the binaries and the source agree.

## 2026-09-25 — Ignore file was named `gitignore`, not `.gitignore`

- **Attempt:** relied on the shipped ignore rules.
- **Actual error:** the file had no leading dot, so git never read it. Build
  output would have been committable.
- **Cause:** typo when the file was created.
- **Next action:** renamed to `.gitignore` in the baseline commit. Also needs
  `*.d` and `__pycache__/` added — the shipped rules cover `*.o` and `/kiln`
  but not the `-MMD` dependency files or Python bytecode.

## 2026-09-25 — `flip_normals` is a live op but is missing from `docs/RPC.md`

- **Attempt:** cross-checked the op list extracted from `ops.cpp` against the
  documented table.
- **Actual error:** all 79 documented names exist, and the counts agree, but
  `flip_normals` is dispatched in `apply_op` and never appears in the op
  reference table.
- **Cause:** op added without a docs update.
- **Next action:** add it to `docs/RPC.md` alongside the other 79.

## 2026-09-25 — Quadric edge-collapse decimator rejected on measured evidence

- **Attempt:** implement `decimate_mesh` as quadric error metrics with an
  optimal-position solve, boundary planes, a normal-flip guard, and a
  link-condition retriangulation.
- **Actual error:** three separate defects, each found by measuring rather than
  by reading the code.
  1. The flip guard compared `cross(b-a, p-a)` against `cross(b-a, c-a)`. The
     face normal after replacing `b` with the candidate is `cross(p-a, c-a)`.
     With the operands in the wrong order every interior quadric minimiser looks
     like a flip, so **all 552 candidates were rejected and the mesh never
     changed** — the op reported success while doing nothing.
  2. After fixing that, it segfaulted. Collapsing deleted degenerate faces and
     swapped in a compacted vector, which renumbered faces while the
     vertex→face index still held the old numbers. Restructured to a fixed face
     array with an alive flag so no index can dangle.
  3. It then hit its triangle targets but lost **20% of signed volume** at ratio
     0.5 and **79%** at 0.1, and once hole-filling was added it stopped reaching
     its target — fixed point at 297 faces, because after the first collapse
     most candidate edges are no longer interior.
- **Cause:** the link condition was being applied to n-gon faces, where "the
  vertex opposite the edge" is not well defined, and the boundary case was never
  handled at all.
- **Decision:** replaced with vertex clustering, which has no topological failure
  mode. Area drift is now 4% at ratio 0.75 and 6.7% at 0.5 with zero degenerate,
  zero non-finite and zero non-manifold geometry, measured by
  `tests/mesh_metrics.py`. QEM with proper boundary handling is recorded as the
  planned replacement, not silently dropped.
- **Lesson:** a decimator that hits its triangle count while destroying the shape
  is worse than a simpler one that preserves it. Count targets are not quality.

## 2026-09-25 — OBJ exporter wrote every face index one too high

- **Attempt:** round-trip a scene through OBJ.
- **Actual error:** my own importer rejected kiln's export with "face references
  vertex 275 but only 274 vertices exist". Blender accepted the file anyway.
- **Cause:** `int base = 1;` combined with writing `base + v + 1`, so the first
  mesh's indices started at 2 instead of 1.
- **Why it survived:** nothing round-tripped OBJ through kiln before, and
  Blender is lenient about a trailing out-of-range index.
- **Next action:** `base` initialised to 0. The importer caught it; that is the
  argument for having an importer at all.

## 2026-09-25 — OBJ importer collapsed every object into one mesh

- **Attempt:** re-import kiln's own OBJ export.
- **Actual error:** two objects (`Cube`, `Ball`) came back as a single mesh
  named `Ball`.
- **Cause:** the `o`/`g` name was read into one variable while parsing, so by
  grouping time it held only the *last* object name. Fixed by recording the
  object name per face as it is parsed.

## 2026-09-25 — Advertised op count drifted from the real dispatch table

- **Attempt:** report the op surface after adding five ops.
- **Actual error:** `ping` still answered `ops: 79` when 87 were dispatched.
- **Cause:** `src/core/rpc.hpp` holds an advisory op table for capability
  reporting and typo suggestions, and nothing in C++ ties it to `apply_op`. It
  had already drifted once before this session.
- **Next action:** synced the table, and added `tests/check_op_sync.py`, which
  reads `apply_op`'s dispatch, the advisory table, the live `ping` count and the
  live `initialize` list, and fails on any mismatch in either direction. All four
  now agree at 87.

## 2026-09-26 — Validator decoded accessors with a size, not a format

- **Attempt:** validate a quantized glTF from `validate.py`.
- **Actual error:** `TypeError: can only concatenate str (not "int") to str`.
- **Cause:** `_Doc.accessor` set `fmt` from `COMPONENT_SIZE`, which maps a glTF
  component type to a *byte count*, then used that integer as a `struct` format
  string (`"<" + fmt * comps`). Every accessor read was wrong.
- **Cause of the silent part:** a wrong accessor read would have produced
  plausible-looking garbage rather than a crash, had the concatenation not
  failed. Only the type error made it visible.
- **Next action:** added `COMPONENT_FMT` and decode through it. 43 tests pass.

## 2026-09-26 — Relative output paths resolved against the engine's own directory

- **Attempt:** `mem20kilnz build ... --out ktest` from `/tmp/opencode`.
- **Actual error:** `kiln: [-32004] cannot write ktest/SM_Crate.glb`, even
  though the client had created the directory.
- **Cause, two bugs deep:**
  1. The engine runs with its own working directory (the source tree), so a
     relative path sent by a caller elsewhere resolved to a directory that does
     not exist there.
  2. `_build_one` created the output directory *after* calling `export`.
- **Next action:** the client now resolves every path field to absolute
  (`PATH_FIELDS` in `rpc.py`) before it reaches the engine, and the directory is
  created first. Two regression tests added. Verified from a foreign directory.

## 2026-09-26 — `validate` and `gate` were the same call

- **Attempt:** read a structurally perfect file with `mem20kilnz validate`.
- **Actual error:** reported `FAIL` because of a *budget* warning, and
  `validate --gate` exited `0` on a file that missed the budget.
- **Cause:** `cmd_validate` called `_validate.gate`, conflating structure with
  budget, and discarded the list that `check_budgets` returns instead of
  appending it. `Report.ok` is fixed during validation, so later findings never
  reached it.
- **Next action:** `validate` is structural; `--gate` adds budget findings; a
  derived `gate_ok` accounts for findings added after validation; a real `gate`
  subcommand exists. Exit-code matrix covered by `tests/test_validate.py`.

## 2026-09-26 — The default model id did not exist

- **Attempt:** the first real end-to-end `build`.
- **Actual error:** `LLM error: {"code":"model_not_found", ... The model
  `llama-3.3-70b-versatile` does not exist or you do not have access to it.}`
- **Cause:** the default was a plausible model id, never verified against the
  provider. The engine's own error is what caught it.
- **Next action:** probed candidates through the engine; `openai/gpt-oss-120b`
  verified working and is now the default. The other ids are listed in
  CONFWORK.md so they are not retried blindly.
- **Note:** probes must go through the engine. Direct Python HTTPS to Groq is
  Cloudflare-blocked on this host (403, `error code: 1010`).

## 2026-09-26 — An empty scene was reported as a built asset

- **Attempt:** build a brief the engine could not act on.
- **Actual error:** none. `exit=2` and a JSON report reading
  `"glb_bytes": 240, "triangles": 0, "ok": false`, with `error` empty. The
  export had succeeded, so the pipeline reported a *gate refusal* for a file
  containing no geometry at all.
- **Cause:** success was inferred from the export and the gate, neither of which
  knows whether the brief was satisfied. The engine answers `no ops` and writes
  a valid, geometry-free GLB; the gate then correctly complains about 0
  triangles, which is a budget complaint, not the real problem.
- **Why it matters:** this is the exact shape of a fake success. A caller
  reading `ok: false` and a gate finding would conclude "under budget, needs
  more detail", when the truth is "nothing was built".
- **Next action:** the pipeline now measures the exported file and treats zero
  triangles as a failure with a named reason
  (`engine produced no geometry (message: no ops)`), regardless of the gate.
  Covered by `test_empty_scene_is_a_failure_not_a_gate_refusal`, which uses
  `create camera` — a valid op that yields a node and no triangles, so the
  build and export both succeed and only the geometry check can catch it.

## 2026-09-26 — toolchest reported 24 subsystems as having a module named `find`

- **Attempt:** confirm `mem20kilnz` was importable in the toolchest inventory.
- **Actual error:** `import | find=n`, `importable=False`, for a package that
  imports without complaint.
- **Cause:** `_import_candidates` did `candidates += st.get("packages", [])`.
  Under `[tool.setuptools.packages.find]`, `packages` is a nested table, and
  extending a list with a dict contributes its keys. So the finder key `find`
  became the module name.
- **Blast radius:** 24 of 36 subsystems, i.e. every package using the most
  common setuptools idiom.
- **Next action:** read the mapping form for its finder `include` globs. A
  second defect then appeared: `include = ["pkg", "pkg.*"]` is the subpackage
  shorthand, and trimming only `*` produced a module named `pkg.`; trailing
  separators are now trimmed as well. 0 phantom names remain.

## 2026-09-26 — The manifest could not have been honest

- **Attempt:** write a provenance manifest listing the ops behind a generated
  asset.
- **Actual error:** not an error — an absence. The engine exposed no way to
  ask what it had done.
- **Cause:** ops a language model invents are applied inside the engine during
  `command`; they never arrive from the client as separate RPC calls, so the
  client cannot know them. The undo stack does not help: `Document::undo` holds
  document snapshots, not op records.
- **Next action:** added `Document::journal` and a `journal` RPC method, with
  `apply_op` turned into a funnel over `apply_op_impl` so every early return is
  recorded. A manifest written before this would have listed the prompt and
  nothing else, which would have looked like complete provenance.

## 2026-09-26 — `probe` reported a budget verdict it had not measured

- **Attempt:** report OBJ geometry in `probe`.
- **Actual error:** would have reported `triangles: 0` for every OBJ.
- **Cause:** the structural validator asserts against a single glTF/GLB file and
  has nothing to check an OBJ against.
- **Next action:** OBJ is accepted for conversion, and `probe` states
  `geometry not measured by this probe` in `reason` rather than presenting 0 as
  a measurement.

## 2026-09-26 — A test wrote a file into the repository

- **Attempt:** run the suite and check `git status`.
- **Actual error:** none. An unexplained `broken.glb`, 200 bytes, kept reappearing
  in the project root after each run.
- **Cause:** `test_truncated_file_fails_structurally` built its fixture with
  `pathlib.Path("broken.glb")`, a path relative to the working directory,
  instead of using the `tmp_path` fixture. It also reached for the file via
  `importorskip("pathlib")` rather than importing pathlib properly.
- **Why it matters:** a 200-byte truncated GLB sitting in the repo looks like a
  real artifact, and it survived a debris cleanup before its cause was found.
- **Next action:** the test now takes `tmp_path` and writes inside it. Verified
  by running the suite and confirming the working tree stays clean.

## 2026-09-26 — Ruff regression introduced while fixing the debris test

- **Attempt:** replace `pytest.importorskip("pathlib")` with a proper import and
  move the fixture into `tmp_path`.
- **Actual error:** `tests/test_validate.py:10:8: F401 'pytest' imported but
  unused` and `I001` on the import block.
- **Cause:** `importorskip` was the only reason that file imported pytest. The
  fix removed the call but left the import, and I committed before re-running
  lint — the suite passed, so the tests did not catch it.
- **Why it matters:** a green test suite is not evidence of a clean lint. The
  two checks have to be run separately, and run *after* the last edit rather
  than before it.
- **Next action:** removed the unused import. `ruff check` clean, 87 tests pass.
- **Process fix:** the post-commit verification now lints and tests as separate
  steps, after the final edit, and the result is read rather than assumed.

## 2026-09-26 — Refinement could ship an asset 260x over budget

- **Attempt:** add real edge detail until the triangle budget is met.
- **Actual error:** none reported. One of six builds came out at **1,557,860**
  triangles against a 6,000 ceiling, and the gate correctly refused it.
- **Cause:** the loop checked the tier *before* each pass, so a pass that
  multiplied the count far past the ceiling was still allowed to stand. Stopping
  the loop afterwards is not enough, because the asset would ship over budget.
- **Why it matters:** a refinement stage that can overshoot by 260x is worse than
  no stage, because the triangle number is the thing being optimised.
- **Next action:** the ceiling is checked after every pass, and an overshooting
  pass is rolled back through the engine's undo stack, so what ships is inside
  the budget. `overshot` is reported rather than hidden. Deterministic repro
  pinned in tests (10 cubes, 2 segments).

## 2026-09-26 — A brief that failed partway threw away its geometry

- **Attempt:** build a crate.
- **Actual error:** `exit=1`, `error: "bevel: no edges"`, and no asset, even
  though the model had already created five objects.
- **Cause:** the model emitted a `bevel` op that failed, and `apply_ops` returned
  on the first failure. The client saw a failed command and discarded
  everything, including real geometry that was already in the scene.
- **Why it matters:** this is the inverse of the earlier empty-scene bug. There,
  nothing was built but it was reported as a build; here, something real was
  built but it was reported as nothing.
- **Next action:** `apply_ops` and `m_ops` now report how far a batch got
  (`"2 of 4 ops applied, then failed: bevel: no edges"`) and keep the successful
  ops. The pipeline marks such builds `partial` and keeps the geometry.

## 2026-09-26 — Truncated model output discarded every complete op

- **Attempt:** get ops from the model for a complex brief.
- **Actual error:** `LLM did not return ops JSON`, with the content ending
  mid-object (`{"op":"c`).
- **Cause:** the model ran out of tokens part-way through the array, and
  `extract_json_array` required a closing `]`, so the whole response was thrown
  away — including the ops that were already complete and valid.
- **Next action:** `salvage_truncated_ops` walks the text with a brace stack and
  keeps every object that parses and has an `op` key. It will not guess at a
  half-written op: truncated inside the first op still fails, deliberately.

## 2026-09-26 — A salvage implementation that deleted the functions after it

- **Attempt:** replace a C++ function body using a brace-counting script.
- **Actual error:** `error: 'apply_and_reply' was not declared in this scope`,
  and the diff showed `dsl_command` and more had been removed.
- **Cause:** the script counted braces without skipping string literals, so its
  match ran past the intended function and deleted everything up to the next
  coincidental brace balance.
- **Why it matters:** this was an unreviewed destructive edit to a 1,478-line
  file. The compiler caught it immediately, but only because the project builds
  with warnings as errors on unused symbols; the fix was `git checkout` on that
  one file and redoing the edit by hand.
- **Next action:** used the editor's exact-match replacement instead of
  computed offsets. `git diff` reviewed for deletions before rebuilding.

## 2026-09-26 — Test expectations that were wrong, not the code

- **Attempt:** pin tier behaviour in tests.
- **Actual error:** three assertion failures that looked like defects.
- **Cause:** all three were my expectations, not the implementation:
  `achieved_tier('player', 9000)` is `blockout` because 9,000 is under the
  player floor of 15,000; `achieved_tier('player', 15000)` is `hero` because
  for a hero-scale family the standard and hero bands coincide and the function
  reports the highest satisfied tier; and a prose-prefixed line does not start
  with `[`, so it routes to the English agent and never reaches the JSON
  salvage path.
- **Next action:** corrected the expectations and documented why each value is
  right, so the next reader does not "fix" them back.

## 2026-09-26 — The description was colourless and measured in the wrong space

- **Attempt:** build a plain-English description of an exported model.
- **Actual error:** no exception. The output was fluent and entirely wrong: every
  part came out with no colour, and a model with a band raised above its crate
  was reported as 1.00 units tall when the true extent was 1.15.
- **Cause, two independent bugs:**
  1. The exporter writes the material on the mesh *primitive*, but the code read
     `node.material`, which does not exist. The colour-naming logic was written,
     correct, and never received any input.
  2. The exporter writes untransformed positions, so bounding boxes came out in
     each node's local space and offsets were lost.
- **Why it matters:** this is the worst failure shape for a description feature.
  It reads well, it is confidently wrong, and its entire purpose is to let an
  agent act without seeing. A wrong measurement is worse than no description.
- **Next action:** material read from the primitive; world-space bounds via the
  transform chain. Both covered by tests asserting measured values, including
  the overall height that the local-space bug got wrong.

## 2026-09-26 — The transform chain was mathematically wrong

- **Attempt:** compose a parent's and a child's node transform.
- **Actual error:** silent. A point came out on the wrong side of the origin.
- **Cause:** a glTF node is `T*R*S`, and composing two of them gives
  `T*R*S*T*R*S`. That is not expressible as a single translation/quaternion/scale
  triple, because the inner translation has nowhere to go. The code collapsed the
  chain into one triple, which is only correct when rotations are absent.
- **Evidence:** parent with a 90-degree rotation and a 2x non-uniform scale, child
  with its own 90-degree rotation and an offset. The true chain gives
  `(0, 2, 0)`; the collapsed triple gives `(0, -2, 0)`.
- **Why it matters:** this is the backbone of every measurement reported, and it
  would have been wrong for exactly the cases that matter — rotated sub-parts
  under a scaled parent, which is what a detailed asset is made of.
- **Next action:** replaced with a row-major 4x4 matrix. A test now asserts the
  distinguishing case so the shortcut cannot come back.
- **Note on the investigation:** my first hand-computed "expected" value was also
  wrong (2.0 instead of 3.0) because I forgot that the child's own translation
  moves the point. The code was right; the expectation was not. Recorded because
  the same trap would mislead the next reader.

## 2026-09-26 — A wide thin band was described only by how wide it was

- **Attempt:** report a band's size relative to the chest.
- **Actual error:** `105% of the width of Chest`.
- **Cause:** relative size was a single width ratio, and judged against volume for
  small parts. A band is genuinely wider than the chest it wraps, so the number
  was true and carried no information; the useful fact, that it is a thin strip,
  was discarded.
- **Next action:** width and thinness are now judged independently — width
  against the largest part, thinness against the part's own smallest side. A
  2.1 x 0.05 x 0.1 band now reads as "a very thin sheet or sliver, wider than
  ChestBody, and 2% as thick as it is wide".

## 2026-09-26 — Wood was named "orange"

- **Attempt:** colour naming from hue and lightness.
- **Actual error:** RGB (0.7, 0.5, 0.3) — a wood tone, and the crate's actual
  colour — came out as "orange".
- **Cause:** the brown special case was guarded on the *sector name* being
  `"red"`, but hues of 24-40 degrees fall in the `"orange"` sector, so the branch
  never ran.
- **Next action:** keyed on the hue range directly, and widened, since brown is
  not a hue but a desaturated, not-bright orange-to-yellow. Regression-tested
  against both a vivid orange, which must stay orange, and a wood brown.

## 2026-09-27 — QEM, second attempt: refused rather than shipped broken

- **Attempt:** replace vertex clustering with quadric error metrics, addressing
  all three defects recorded in the 2026-09-26 entry above.
- **What was fixed and verified:**
  - the flip guard now uses `cross(p-a, c-a)`, the actual post-collapse normal,
    so candidates stop being rejected wholesale;
  - nothing is compacted mid-loop. Faces carry an `alive` flag, vertices a
    `dead` flag, and remapping happens once at the end, so no index can dangle.
    The old segfault is gone;
  - the loop is a priority queue with lazy validation instead of a rescan.
    Measured 11.52s -> 0.12s at 8,832 faces, and 35,328 faces in 0.12s, so it
    scales where the first version did not.
- **What still failed, measured on a watertight 528-triangle sphere:**

  | attempt | result |
  | --- | --- |
  | boundary quadrics computed once | 100-140 boundary edges, -93% volume at ratio 0.1 |
  | boundary quadrics refreshed per collapse | 140 boundary edges, no better |
  | link condition checked after collapsing | 564 triangles out of 528 in, +3% area, still holed |
  | link condition checked before collapsing | 564 triangles out, unchanged |
  | triangulate first, then collapse | **1,470 triangles out of 528, +2457% area** |

- **Cause of the last row, and of the whole line:** the hole left by a collapse
  must be retriangulated from the *hole boundary*, and the loop was being built
  from every neighbour of the surviving vertex. That adds more faces than the
  collapse removed, so the mesh grows. Two earlier lessons from this file were
  repeated along the way: the link condition is undefined on n-gons, so the mesh
  must be triangulated first, and boundary edges created by a dying face must be
  protected at the moment they appear.
- **Decision:** `decimate` defaults to `cluster`, the only method measured to
  preserve the surface (watertight, 0 degenerate, 0 non-manifold). `method:
  "qem"` refuses with that reason rather than returning a larger mesh. A
  decimator that hits its triangle count while destroying the shape is worse
  than a simpler one that preserves it, and one that returns 278% of the input
  is not a decimator at all.
- **What carries forward:** the quadric, the corrected flip test, the
  priority-queue driver and the incremental boundary bookkeeping are all sound
  and reusable. The missing piece is a correct link-condition boundary walk.
  `decimate_qem` in `src/scene/decimate_qem.cpp` is the place to resume.

## 2026-09-27 — A sphere exported as a topologically open mesh

- **Attempt:** check the export after welding corners on (position, normal, uv).
- **Actual error:** the exported sphere had 1,104 boundary edges and only 18% of
  its edges shared. A sphere is closed; this measured as `watertight=False`.
- **Cause:** primitives were flat-shaded, so each face carried its own normal
  and no two corners could ever match the weld key. Welding could not help,
  because the inputs genuinely differed. This was not a welding bug: the
  baseline itself was wrong, and it is why a decimator measured against it gave
  nonsense volume drift.
- **Also found:** there was no way to ask for smooth shading at all. `m.smooth`
  was set only by Catmull-Clark, so every primitive was flat. A sphere is
  smooth, and it rendered faceted too.
- **Next action:** curved primitives (sphere, cylinder, cone, torus) are
  smooth-shaded at creation; `shade_smooth` and `shade_flat` ops were added.
  Measured after: sphere 1,104 -> 266 vertices, 0 boundary edges, watertight;
  cylinder 146 -> 50; torus 1,152 -> 288. `shade_flat` on a sphere restores
  1,104, so the opt-in still works.

## 2026-09-27 — QEM fixed: the hole boundary needed an *order*, not a set

- **Attempt:** third run at the QEM hole retriangulation.
- **Change:** the hole loop was being built as a *set* of the surviving vertex's
  neighbours. A set has no order, and a fan over an unordered loop produces
  overlapping triangles. It now walks the 1-ring of each endpoint in cyclic
  order -- through the face fan, which is the only place adjacency survives --
  and builds the boundary as: `c`, b's remaining neighbours, `d`, then a's
  remaining neighbours coming back the other way.
- **Result, on a watertight 528-triangle sphere:**

  | method | ratio | triangles | hit | area drift | volume drift | boundary | degenerate | watertight |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | qem | 0.75 | 396 | 75% | +3.10% | **-1.32%** | 0 | 0 | yes |
  | cluster | 0.75 | 172 | 33% | -4.02% | -8.20% | 0 | 0 | yes |
  | qem | 0.50 | 264 | 50% | +7.92% | **-0.60%** | 0 | 0 | yes |
  | cluster | 0.50 | 122 | 23% | -6.65% | -13.19% | 0 | 0 | yes |
  | qem | 0.25 | 132 | 25% | +60.01% | -8.80% | 0 | 0 | yes |
  | qem | 0.10 | 52 | 10% | +13.97% | -56.42% | 0 | 0 | yes |

  QEM hits the target exactly, stays closed, and drifts 6-20x less volume than
  clustering at realistic ratios. Clustering cannot reach the target at all.
  Confirmed on sphere, cylinder and torus.
- **Decision:** `qem` is now the default. `cluster` remains available.
- **Added guard:** decimation refuses a mesh that is not a closed surface, with
  the actual boundary and non-manifold edge counts. A decimator run on a holed
  or non-manifold input returns confident nonsense, so it says no instead. This
  is reachable today because of the subdivision defect below.

## 2026-09-27 — Subdivision produced a mesh with zero volume and holes (partly fixed)

- **Attempt:** measure QEM on a subdivided sphere. Every quality number was
  nonsense, so the baseline itself was investigated.
- **Actual error:** a subdivided sphere had 1,104 boundary edges, 1,370
  non-manifold edges, and a signed volume of **exactly 0.000000** on a shape
  whose true volume is about 4.19.
- **Cause 1, fixed:** the new quad was built as
  `(edge_pt, nxt, v_pt[nxt], v_pt[cur])`, putting the *original*, unsmoothed
  vertex index into a face whose position array had already been replaced.
  Neighbouring faces therefore referenced different vertices for the same
  corner, and the inconsistent normals cancelled exactly. The quad is now
  `(v_pt[cur], edge_pt[cur->nxt], v_pt[nxt], edge_pt[prev->cur])`.
- **Cause 2, fixed:** the triangle branch emitted corner triangles as
  `(v_pt[cur], edge_pt[cur->nxt], v_pt[nxt])`, using the next vertex point
  where the preceding edge point belongs, so consecutive corner triangles shared
  no edge. It is now `(v_pt[cur], edge_pt[cur->nxt], edge_pt[prev->cur])` plus a
  centre triangle.
- **Cause 3, NOT fixed:** subdivision is still not watertight. Boundary edges
  went 1,104 -> 960 after the two fixes, and the volume is now sane
  (-4.07 -> -3.94 -> -3.22 across levels) instead of zero, but the mesh still has
  holes. The quad branch was hand-checked and its sub-quads do share edges
  correctly, so the remaining cause is not yet identified.
- **Consequence, and why it matters:** `subsurf` output cannot currently be fed
  to boolean, remesh or decimation, because the manifold precheck correctly
  refuses it. That is the guard doing its job, but it means subdivision is not
  finished. Recorded rather than papered over, because a subdivided mesh that
  exports with holes and looks plausible in a render is exactly the kind of
  defect that survives.

## 2026-09-27 — The manifest described the blockout, not the shipped asset

- **Attempt:** replay a build's journal and compare the bytes.
- **Actual error:** the replay produced 1,720 bytes with 24 vertices where the
  original was 161,772 bytes with 5,952. Diffs were confined to the accessor
  counts, so the geometry itself differed, not just the encoding.
- **Cause:** the journal was read immediately after the brief, before the refine
  stage ran. The six bevel passes refine applies were therefore absent from the
  manifest, which recorded the ops that produced the *blockout* while the file on
  disk was the refined asset. Replaying the manifest faithfully rebuilt the wrong
  thing -- faithfully, and wrongly.
- **Why it matters:** this is worse than having no journal. A manifest that
  looks complete and replays cleanly is trusted; one that is quietly truncated is
  not.
- **Next action:** the journal is read after every stage. A separate count is
  taken right after the brief so the refine guard is unaffected. A full 30-op
  build with refine now replays byte-identically. The refactor also needed
  `entries` initialised before the early-return paths, which write a manifest.

## 2026-09-27 — subsurf holes: the quad had no face point, then a shared diagonal

- **Attempt:** close the last subdivision defect, which was leaving 960 boundary
  edges and blocking decimation, booleans and remesh on subdivided meshes.
- **Actual error, and the chain of causes:**
  1. The sub-quad for original edge (a, b) was
     `(v_a, e_ab, v_b, e_da)`. A quad cannot be tiled by four quads without a
     face point, and its closing edge `(v_b, e_da)` belonged to no other face, so
     the surface was open along every original corner. **The face point was
     computed at the top of the function and never used.**
  2. With the face point added, boundary edges went to 0 but 456 non-manifold
     edges remained, all with face count 4, forming a cycle of the original
     corners. Fanning each sub-quad from its first corner makes the diagonal
     `(v_cur, v_nxt)`, and the quad on the *other* side of that same original
     edge has the same two corners in the same order, so it picks the same
     diagonal. Every interior diagonal was then used by four triangles.
  3. Fixed by emitting the sub-quads as triangles fanned from the **edge
     point**, so the diagonal runs edge-point -> face-point. The face point is
     unique to its face, so a diagonal through it can never coincide with a
     neighbour's.
- **Result, measured:**

  | primitive | level 0 | level 1 | level 2 |
  | --- | --- | --- | --- |
  | sphere | watertight | watertight | watertight |
  | torus | watertight | watertight | watertight |
  | cylinder | watertight | watertight | watertight |
  | cone | watertight | watertight | watertight |

  0 boundary edges and 0 non-manifold edges at every level, and volume converges
  instead of collapsing (sphere -4.07 -> -3.99 -> -3.97).
- **Downstream unblocked:** a subdivided sphere can now be decimated, measured at
  2,112 -> 2,016 triangles, still watertight with zero defects.
- **Still not clean:** a `plane` gains non-manifold edges when subdivided (an
  open surface has no closed-volume guarantee), and a `cube` shrinks hard
  because one Catmull-Clark level on a 6-quad mesh rounds the corners severely
  (8.0 -> 3.33 -> 2.92 volume). That is characteristic of the scheme on a coarse
  mesh rather than a defect, but it is a large change and is recorded.

## 2026-09-27 — Correction: booleans and remesh do not exist

- **What I said earlier in this session:** that the mesh operations included
  "booleans" and "remesh". That was wrong, and it was not a slip I verified --
  I carried it forward from my own earlier summary instead of checking the op
  surface.
- **Actual state, checked against the live op list (106 ops):** no `boolean`,
  no `union`, no `difference`, no `intersect`, no `remesh`, no `voxel`, and no
  `displace`. `skin` is also absent, though a skinned mesh is imported from
  FBX and glTF, so the data is carried but there is no op to author or edit it.
  Animation has `frame` and `set_frame` for the scene cursor and no clip or
  keyframe op at all.
- **Why it matters:** booleans and remesh were named as the reason subdivision
  needed fixing, and that reasoning was wrong. Subdivision was still worth
  fixing -- it produced holes and a signed volume of exactly zero -- but the
  justification cited capabilities that do not exist.
- **Next action:** the op surface is now the authoritative statement in
  CONFWORK.md, and the missing capabilities are listed as gaps rather than
  implied.
