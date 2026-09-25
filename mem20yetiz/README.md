# mem20yetiz

`mem20yetiz` is a native Python 3D animation package for real rig data, BVH motion capture, and standards-based export. It has no mock readers, canned motion generator, placeholder exporter, or network dependency.

## Real capabilities

- BVH parsing reads `HIERARCHY`, node offsets, channel order, `MOTION`, frame count, and frame timing.
- Forward kinematics computes world transforms, per-frame joint positions, and per-frame local and world rotations.
- Cleanup operates on marker and BVH joint trajectories: bounded NaN interpolation, centered moving average, and an in-package Butterworth low-pass filter.
- Marker tracking associates observed points with canonical marker identities using template and velocity prediction.
- `AnimationClip` conversion uses local joint translations and rotations, so exported animation can be applied to the exported hierarchy.
- glTF 2.0 export writes JSON plus a real external `.bin` buffer with node hierarchy and animation samplers. `mem20yetiz.gltf.load_gltf` strictly reparses and decodes the file.
- OBJ export writes real joint vertices and parent-child line elements. `mem20yetiz.obj.load_obj` reparses and validates the file.
- BVH export writes the parsed hierarchy and motion back to a valid BVH stream.
- C3D support is point-only, Intel/little-endian, IEEE-float data with real parameter records; unsupported analog or byte-order variants fail explicitly.

The OBJ representation is a static first-frame skeleton. Animated output is written in glTF 2.0. FBX, USD, and other unsupported formats fail explicitly rather than returning success.

## Install

The package requires Python 3.11 or newer, NumPy, and PyYAML. In the root mem20 virtual environment:

```text
/root/.venv/bin/python -m pip install -e /opt/mem20/mem20yetiz --no-deps
```

For a clean environment, install the package normally and add the test tools with the `dev` extra. `trimesh` is an optional `verify` extra used only as an additional external importer check; the package's strict readers do not depend on it.

## Verify

```text
cd /opt/mem20/mem20yetiz
/root/.venv/bin/python -m pytest -q
/root/.venv/bin/ruff check mem20yetiz
```

The tests use a hand-authored BVH fixture at `mem20yetiz/tests/fixtures/biped_test.bvh` and temporary directories only. They assert hierarchy depth, frame timing, channel data, known FK positions, cleanup behavior, marker identity, glTF binary roundtrips, and OBJ hierarchy roundtrips.

## Python example

```python
from mem20yetiz import Exporter, ExportSettings, mocap_to_animation, parse_bvh_file

capture = parse_bvh_file("capture.bvh")
rig = capture.to_rig()
clip = mocap_to_animation(capture, rig)
Exporter(ExportSettings(format="gltf")).export_mocap(capture, "capture.gltf")
Exporter(ExportSettings(format="obj")).export_mocap(capture, "capture.obj")
```

The glTF file is accompanied by `capture.bin`. Both exports are validated by re-importing the generated files.
