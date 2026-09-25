# mem20-orchestration

Blender operator orchestration for the mem20 estate.

A wrong `bpy.ops` name is a runtime `AttributeError` deep inside a live Blender
session, usually minutes after a long build has already started. This tool
validates an entire op sequence against the real captured catalog first, so the
mistake becomes an immediate, specific report.

## The catalog

`data/blender_ops.json` is the genuine `bpy.ops` surface captured from
**Blender 5.2.0 LTS**: 2 498 operators across 77 modules. `Catalog.exists()` is
a fact about Blender, not a guess. Tests assert the module counts sum to the
declared total, so a truncated or corrupted catalog fails the suite rather
than silently validating bad plans.

## Install

```bash
/root/.venv/bin/pip install -e /opt/mem20/mem20-orchestration
```

## Use

```bash
# what the catalog contains
mem20-orchestration ops
mem20-orchestration modules

# find and inspect operators
mem20-orchestration ops --search cube_add
mem20-orchestration ops --module mesh
mem20-orchestration ops --show bpy.ops.mesh.primitive_cube_add

# validate a sequence before it reaches Blender
mem20-orchestration new-plan \
    bpy.ops.mesh.primitive_cube_add \
    bpy.ops.mesh.primitive_uv_sphere_add \
    --out plan.json
mem20-orchestration validate plan.json
```

Add `--json` to any subcommand for machine-readable output.

## What validation catches

| Input | Result |
|---|---|
| `bpy.ops.mesh.primitive_cube_add` | valid |
| `bpy.ops.mesh.not_a_real_op` | error: unknown operator |
| `bpy.ops.totallyfake.thing` | error: names the non-existent module |
| `mesh.primitive_cube_add` | error: missing `bpy.ops.` prefix |
| `{"params": {}}` | error: step has no op name |
| the same op twice | warning: repeated ops can be non-idempotent |

Findings carry the step index, so a failure points at the exact entry in the
plan rather than "something went wrong".

## Plan format

Either a bare JSON list of op names:

```json
["bpy.ops.mesh.primitive_cube_add", {"op": "bpy.ops.object.select_all"}]
```

or an object with a `steps` list, which is what `new-plan` writes:

```json
{ "blender_version": "5.2.0 LTS", "steps": ["bpy.ops.mesh.primitive_cube_add"] }
```

Steps may be plain strings or objects with an `op`, `name`, or `operator` key.

## Exit codes

`0` valid · `1` plan invalid · `2` the check could not run

## Limits

- Validation checks operator **existence and shape only**. It does not know
  whether a given op will succeed against the current scene, selection, or
  mode; that still requires Blender.
- The catalog is pinned to Blender 5.2.0 LTS. Ops added or removed in another
  version will validate against the wrong surface. Regenerate the JSON from
  your target Blender before relying on it.
- This does not execute operators. Running them is Blender's job, via the
  Blender MCP tools.

## Verification

```
$ python -m pytest -q
40 passed
```
