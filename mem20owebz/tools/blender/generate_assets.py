#!/usr/bin/env python3
"""
Local placeholder asset generator (DEV-ONLY) - Uses Blender directly for 3D primitives.

This tool generates COARSE PLACEHOLDER primitives (cubes/cylinders/planes) to be
refined later. It is explicitly gated as dev-only:

  * every manifest entry is marked "placeholder": true, "dev_only": true, and
    "status": "placeholder" (never "generated" / never valid final art)
  * nothing here is a real asset; pipeline integration must never consume these
    placeholders as validated art (see production_run_orchestrator_tool.py:
    "Never integrate from _incoming without validate")
  * a manifest entry is only recorded when the exported file was VERIFIED on disk

Project layouts are resolved through MEM20OWEBZ_PROJECT_ROOT (same env knob used by
tools/release/build_package.py). The tools path is resolved relative to this file -
no foreign absolute paths.
"""

import os
import sys
import json
from pathlib import Path
import shutil

# Resolve the tools package relative to this file (no hardcoded /home/... leak).
TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from blender.blender_tools import create_object, add_material, export_glb, clear_scene

# Default to the mem20owebz repo-local projects directory. Override with
# MEM20OWEBZ_PROJECT_ROOT when this project lives elsewhere. Never a foreign
# machine's home path.
PROJECT_ROOT = os.environ.get(
    "MEM20OWEBZ_PROJECT_ROOT",
    str(Path(__file__).resolve().parent.parent.parent / "projects"),
)
OUT_DIR = Path(PROJECT_ROOT) / "unreliable_prophecy" / "_incoming"
CHARS_DIR = OUT_DIR / "characters"
PROPS_DIR = OUT_DIR / "props"
ENV_DIR = OUT_DIR / "environments"
UI_DIR = OUT_DIR / "ui"


def _verified_export(name: str, subdir: Path) -> dict:
    """Export the current scene as GLB, copy the real file into OUT_DIR, and
    verify it exists on disk. Returns the manifest record or raises."""
    export = export_glb(filename=f"{name}.glb")
    if not export.get("success"):
        raise RuntimeError(f"blender export failed: {export.get('stderr', export)}")
    src = Path(export["file"])
    if not src.is_file():
        raise RuntimeError(f"blender claimed {src} but the file does not exist")

    subdir.mkdir(parents=True, exist_ok=True)
    dest = subdir / f"{name}.glb"
    shutil.copyfile(src, dest)
    if not dest.is_file() or dest.stat().st_size == 0:
        raise RuntimeError(f"copied asset missing or empty at {dest}")
    return {
        "id": name,
        "file": str(dest),
        "size_bytes": dest.stat().st_size,
        "status": "placeholder",
        "placeholder": True,
        "dev_only": True,
    }


def generate_character(name, style="fantasy", scale=1.0):
    """Generate a BASIC PLACEHOLDER character from primitives."""
    print(f"Generating placeholder character: {name}")
    clear_scene()

    create_object("CYLINDER", f"{name}_body", location=(0, 0, 1), scale=(0.3 * scale, 0.3 * scale, 1.5 * scale))
    add_material(f"{name}_body", color=(0.4, 0.2, 0.1, 1.0))  # Brown robes

    create_object("CUBE", f"{name}_head", location=(0, 0, 2), scale=(0.25 * scale, 0.25 * scale, 0.25 * scale))
    add_material(f"{name}_head", color=(0.7, 0.5, 0.3, 1.0))  # Skin tone

    return _verified_export(name, CHARS_DIR)


def generate_prop(name, prop_type="box", color=(0.5, 0.5, 0.5)):
    """Generate a prop PLACEHOLDER."""
    print(f"Generating placeholder prop: {name}")
    clear_scene()

    type_map = {
        "box": "CUBE",
        "cylinder": "CYLINDER",
        "sphere": "SPHERE",
        "plane": "PLANE",
    }

    obj_type = type_map.get(prop_type, "CUBE")
    create_object(obj_type, name, location=(0, 0, 0))
    add_material(name, color=color + (1.0,))

    return _verified_export(name, PROPS_DIR)


def generate_environment(name, size="medium"):
    """Generate an environment PLACEHOLDER."""
    print(f"Generating placeholder environment: {name}")
    clear_scene()

    create_object("PLANE", f"{name}_ground", scale=(10, 10, 1))
    add_material(f"{name}_ground", color=(0.3, 0.6, 0.3, 1.0))  # Grass green

    create_object("CUBE", f"{name}_building", location=(3, 0, 0.5), scale=(2, 1, 1))
    add_material(f"{name}_building", color=(0.5, 0.4, 0.3, 1.0))  # Building stone

    return _verified_export(name, ENV_DIR)


def main():
    print("=== Local Placeholder Asset Generation (DEV-ONLY) ===\n")

    if shutil.which("blender") is None:
        print("✗ blender not found in PATH. Placeholder generation requires a blender install.")
        return 1

    for d in [CHARS_DIR, PROPS_DIR, ENV_DIR, UI_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    results = []

    chars = [
        ("CH_PC1_Player", 1.0),
        ("CH_Wizard_Old", 0.8),
        ("CH_Bureaucrat", 0.7),
    ]
    for name, scale in chars:
        try:
            record = generate_character(name, scale=scale)
            results.append(record)
            print(f"  ✓ {name}: {record['file']} ({record['size_bytes']} bytes)\n")
        except Exception as e:
            results.append({"id": name, "file": None, "status": "error", "error": str(e)})
            print(f"  ✗ {name}: {e}\n")

    props = [
        ("PR_Binder", "box", (0.8, 0.7, 0.6)),
        ("PR_FilingCabinet", "cylinder", (0.4, 0.4, 0.4)),
        ("PR_Desk", "box", (0.6, 0.4, 0.2)),
        ("WP_BasicMelee", "cylinder", (0.7, 0.7, 0.7)),
    ]
    for name, ptype, color in props:
        try:
            record = generate_prop(name, ptype, color)
            results.append(record)
            print(f"  ✓ {name}: {record['file']} ({record['size_bytes']} bytes)\n")
        except Exception as e:
            results.append({"id": name, "file": None, "status": "error", "error": str(e)})
            print(f"  ✗ {name}: {e}\n")

    envs = [
        ("ENV_Quietvale", "small"),
        ("ENV_BureaucracyHills", "medium"),
    ]
    for name, size in envs:
        try:
            record = generate_environment(name, size)
            results.append(record)
            print(f"  ✓ {name}: {record['file']} ({record['size_bytes']} bytes)\n")
        except Exception as e:
            results.append({"id": name, "file": None, "status": "error", "error": str(e)})
            print(f"  ✗ {name}: {e}\n")

    manifest_path = OUT_DIR / 'generation_results.json'
    with open(manifest_path, 'w') as f:
        json.dump(results, f, indent=2)

    ok = [r for r in results if r.get("status") == "placeholder"]
    errs = [r for r in results if r.get("status") == "error"]

    print(f"=== Manifest saved to {manifest_path} ===")
    print(f"Placeholders written: {len(ok)}/{len(results)}; errors: {len(errs)}\n")
    print("NOTE: these are DEV-ONLY placeholder primitives (status=placeholder).")
    print("They must be validated/refined before any real pipeline integration.")

    return 0 if errs == [] else 2


if __name__ == '__main__':
    sys.exit(main())