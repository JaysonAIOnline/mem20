# mem20kilnz

A cleanroom, agent-first 3D subsystem for mem20: a C++ geometry kernel driven
over JSON-RPC, wrapped in a Python package with budgets, a read-only glTF
validator, and a CLI that turns a written brief into a real asset.

The human surface is deliberately secondary. The primary caller is an agent.

## What is actually implemented

Everything below is exercised by the test suite or the CLI in this repo. It is
not a roadmap.

- **103 ops** on the C++ kernel, with an automated drift guard
  (`tests/check_op_sync.py`) that fails if the advertised list and the
  dispatcher ever disagree.
- **glTF 2.0 / GLB import and export.** Geometry (positions, indices) round-trips
  without loss. 17 fixtures are covered; malformed files are rejected with a
  reason rather than crashing.
- **OBJ import and export.**
- **Mesh operations** including decimation, normals, booleans, remesh, smoothing,
  subdivision (loop, Catmull-Clark), wireframe, shrinkwrap, symmetrize, extrude,
  bevel, and per-vertex transform ops.
- **Rig operations** including two-bone inverse kinematics, parenting, skinning,
  and pose application.
- **A natural-language and JSON-RPC agent surface.** The engine prefers, in
  order: literal JSON, the kiln DSL, a built-in English intent handler, then an
  LLM.
- **A provenance journal.** Every applied op is recorded with its verdict,
  including the ones a language model invents internally and which never arrive
  as client calls. `build` writes those into a manifest beside the asset, and
  `verify` re-checks the manifest against the file's actual hash.
- **An asset catalogue** that reads manifests only, so an entry cannot claim
  more than the build produced, and reports untracked GLBs rather than
  describing them from their filename.
- **External mesh ingest** with a read-only `probe` and a `convert` that marks
  imported assets as `source: external` with both input and output hashes.
- **JAIRF budgets and naming validation** enforced as a read-only gate.
- **Live engine builds** from source, so the binary is never a mystery artifact.

## Install

```bash
pip install -e /opt/mem20/mem20kilnz
```

The C++ engine is built on demand; no separate build step is required to call
the Python API.

## Use

```python
from mem20kilnz import Kiln

with Kiln() as k:
    k.command("create cube Base size 1 1 1")
    k.op({"op": "create", "primitive": "sphere", "name": "Knob",
          "pos": [0, 0, 0.6], "r": 0.25})
    k.export("/tmp/asset.glb")
```

From a brief, through a language model, with the gate applied:

```bash
mem20kilnz build "a weathered wooden crate with iron bands" \
    --out ./out --name SM_Crate --preview
```

The command prints a JSON report and exits non-zero if the gate fails.

## CLI

| Command | What it does |
| --- | --- |
| `mem20kilnz doctor` | Engine presence, compiler, source tree, credential availability |
| `mem20kilnz build-engine` | Rebuild the C++ engine from source |
| `mem20kilnz ops` | List ops from a live engine |
| `mem20kilnz validate <file>` | Read-only structural validation of a glTF/GLB |
| `mem20kilnz validate <file> --gate` | Structural check plus budget findings |
| `mem20kilnz gate <file>` | Budget and naming gate for a glTF/GLB |
| `mem20kilnz budgets` | The active JAIRF budgets |
| `mem20kilnz build` | Brief to asset, preview, manifest, and gate verdict |
| `mem20kilnz batch` | Many briefs in one engine session, each with a manifest |
| `mem20kilnz verify <manifest>` | Re-check a manifest against the bytes on disk |
| `mem20kilnz probe <file>` | Measure an external mesh without modifying it |
| `mem20kilnz ingest <files...>` | Import external meshes with provenance records |
| `mem20kilnz catalogue <root>` | Index built assets from their manifests |

`doctor`, `budgets`, `build`, and `batch` emit JSON by default. `ops`,
`validate`, and `gate` print a human report by default and take `--json` for
machine output. Every command's exit code is meaningful: `0` for pass, `1` for
a finding, `2` for a usage error.

## Credentials

Credentials are read only from `/opt/mem20/secrets/.env` (or the path in
`KILNZ_SECRETS`). Nothing is read from ambient environment variables except an
explicit `KILNZ_API_KEY`, and no credential is ever printed, logged, or written
into an asset.

`mem20kilnz doctor` reports which providers are configured. Resolution follows
the estate policy: Groq primary, NVIDIA fallback, xAI disallowed. If no
credential is present the engine still runs, using its built-in English and DSL
handlers, and the CLI says so on stderr rather than pretending a model ran.

## Known limitations

These are real and currently unfixed. They are listed so nothing here reads as
more capable than it is.

- **Export writes a triangle soup.** `mesh_sync_render` expands every triangle
  into its own three vertices, so an exported mesh has no vertex sharing. Vertex
  counts therefore do not survive a round trip; triangle counts do.
- **UVs, tangents, vertex colors, and split normals are dropped on import.**
  Import reports them; it does not carry them through.
- **`decimate_mesh` is vertex clustering, not quadric edge collapse.** A quadric
  implementation was written and rejected on measured evidence: a wrong face-flip
  test, a stale-index segfault, volume loss, and failure to reach the target
  ratio. Measured area drift is about -4% at ratio 0.75 and -6.7% at ratio 0.5.
- **Generated assets are frequently under-detailed.** A language model asked for
  a "weathered crate with iron bands" will often return a handful of primitives
  well under the triangle budget. The gate rejects these. This is the gate
  working, not a bug.
- **`probe` does not measure OBJ geometry.** The structural validator asserts
  against a single glTF/GLB and has nothing to check an OBJ against, so `probe`
  reports `geometry not measured by this probe` instead of claiming zero
  triangles.
- **FBX cannot be read.** `.fbx` is refused by name, listing the formats the
  importer does handle.
- **No neural text-to-3D or text-to-video backends run on this host.** There is
  no CUDA device. Those paths report a named `blocked:` reason instead of
  pretending to infer.

## Tests

```bash
python -m pytest tests/ -q      # 87 tests
python tests/check_op_sync.py engine engine/kiln
```

## License

Cleanroom implementation. No third-party asset, mesh, or code is copied.
