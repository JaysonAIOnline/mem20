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
