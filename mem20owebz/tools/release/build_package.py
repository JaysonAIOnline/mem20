#!/usr/bin/env python3
"""
Release Package Generator
Builds the game and creates distributable package.

This script only reports "completed" when a REAL Unity player build exists.
If Unity is unavailable or no real build output is present, it fails loudly
and writes an honest release report instead of shipping a placeholder.
"""

import os
import json
import subprocess
import shutil
import zipfile
import sys
from datetime import datetime
from pathlib import Path

PROJECT = "unreliable_prophecy"
PROJECT_ROOT = os.environ.get(
    "MEM20OWEBZ_PROJECT_ROOT",
    str(Path(__file__).resolve().parent.parent.parent / "projects"),
)
BASE = f"{PROJECT_ROOT}/{PROJECT}"
ENGINE = f"{BASE}/engine_project"
RELEASE = f"{BASE}/release"
BUILD = f"{RELEASE}/build"

# Unity StandaloneWindows64 produces <PROJECT>.exe + <PROJECT>_Data/
# StandaloneLinux64 produces <PROJECT>, macOS produces <PROJECT>.app
REAL_BUILD_OUTPUTS = [
    os.path.join(BUILD, f"{PROJECT}.exe"),
    os.path.join(BUILD, PROJECT),
    os.path.join(BUILD, f"{PROJECT}.app"),
]

UNITY_PATHS = [
    '/home/jayson/Unity/Hub/Editor/6000.5.9f1/Editor/Unity',
    '/home/jayson/Unity/Hub/Editor/6000.3.22f1/Editor/Unity',
    '/opt/Unity/Editor/Unity',
    '/usr/local/unity/Editor/Unity',
    '/Applications/Unity/Unity.app/Contents/MacOS/Unity',
]


def check_unity_installation():
    """Return the path to an installed Unity Editor, or None."""
    for path in UNITY_PATHS:
        if os.path.exists(path):
            print(f"✓ Unity found at: {path}")
            return path

    result = subprocess.run(['which', 'unity'], capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip():
        print(f"✓ Unity CLI available: {result.stdout.strip()}")
        return result.stdout.strip()

    print("✗ Unity not found in expected locations")
    return None


def find_real_build_output():
    """Return the path of a real Unity player build, or None."""
    for candidate in REAL_BUILD_OUTPUTS:
        if os.path.isfile(candidate):
            return candidate
    return None


def create_build_config():
    """Create build configuration file."""
    config = {
        "project_name": PROJECT,
        "version": "0.5.0",
        "build_date": datetime.now().isoformat(),
        "target_platform": "StandaloneWindows64",
        "scenes": [
            "Boot",
            "MainMenu",
            "Quietvale",
            "BureaucracyHills"
        ],
        "output_name": f"{PROJECT}_v0.5.0",
        "compression": "LZ4HC",
        "dev_build": False,
        "build_available": True,
    }

    config_path = f"{BUILD}/build_config.json"
    os.makedirs(BUILD, exist_ok=True)

    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)

    print(f"✓ Build config: {config_path}")
    return config


def copy_assets_for_release():
    """Copy all assets needed for release."""
    print("\nPackaging assets...")

    incoming = f"{BASE}/_incoming"
    release_assets = f"{BUILD}/{PROJECT}/assets"
    os.makedirs(release_assets, exist_ok=True)

    if not os.path.isdir(incoming):
        print("✗ No _incoming asset directory found")
        return 0

    copied = 0
    for f in os.listdir(incoming):
        if f.endswith('.glb'):
            src = os.path.join(incoming, f)
            dst = os.path.join(release_assets, f)
            shutil.copy2(src, dst)
            copied += 1
            print(f"  ✓ {f}")

    return copied


def create_license_and_docs():
    """Create license and documentation files."""
    print("\nCreating documentation...")

    # LICENSE
    license_content = f'''The Unreliable Prophecy - Game License
Copyright (c) 2026 Jayson

Permission is hereby granted, free of charge, to any person obtaining a copy
of this game and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''

    license_path = f"{BUILD}/{PROJECT}/LICENSE.txt"
    with open(license_path, 'w') as f:
        f.write(license_content)
    print(f"  ✓ LICENSE.txt")

    # README
    readme = f'''# {PROJECT} v0.5.0 (Vertical Slice)

## Description
A 3D adventure game about a reluctant prophet navigating a celestial bureaucracy.

## System Requirements
- Windows 10 or later (64-bit)
- DirectX 11 compatible GPU
- 2 GB VRAM minimum

## Controls
- WASD: Move
- Mouse: Look/Camera
- Left Click: Interact/Attack
- Escape: Menu

## Contents
- `{PROJECT}.exe` - Main executable
- `assets/` - All GLB 3D assets
- `LICENSE.txt` - This license file

## Credits
- Design: Jayson
- Engine: Unity 6 LTS
- Audio: Kokoro TTS

## Playtest
This is a vertical slice. Report bugs to jayson@jayson.online
'''
    readme_path = f"{BUILD}/{PROJECT}/README.md"
    with open(readme_path, 'w') as f:
        f.write(readme)
    print(f"  ✓ README.md")


def create_zip_package():
    """Create the final ZIP package."""
    print("\nCreating distribution package...")

    zip_path = f"{RELEASE}/{PROJECT}_v0.5.0.zip"

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(BUILD):
            for file in files:
                full_path = os.path.join(root, file)
                arc_name = os.path.relpath(full_path, BUILD)
                zf.write(full_path, arc_name)

    size = os.path.getsize(zip_path)
    print(f"✓ Package: {zip_path}")
    print(f"  Size: {size/1024/1024:.2f} MB")

    return zip_path, size


def write_report(report, status, build_available):
    """Write an honest release report reflecting the true build state."""
    report.update({
        "generated_at": datetime.now().isoformat(),
        "status": status,
        "build_available": build_available,
    })
    report_path = f"{RELEASE}/release_report.json"
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\n{'✓' if build_available else '✗'} Release report: {report_path}")
    return report_path


def main():
    print("=== Stage 6: RELEASE_PACKAGE ===\n")

    # Create directories FIRST
    os.makedirs(BUILD, exist_ok=True)
    os.makedirs(RELEASE, exist_ok=True)
    os.makedirs(f"{BUILD}/{PROJECT}", exist_ok=True)
    os.makedirs(f"{BUILD}/{PROJECT}/assets", exist_ok=True)

    base_report = {
        "stage": "Stage 6 - RELEASE_PACKAGE",
        "project_root": BASE,
        "next_stage": "Stage 7 - DONE",
    }

    if not os.path.isdir(BASE):
        print(f"✗ Project root not found: {BASE}")
        print("  Set MEM20OWEBZ_PROJECT_ROOT to the projects directory containing this game.")
        write_report(base_report, "failed", False)
        print("\n✗ RELEASE_PACKAGE FAILED: project root missing.")
        return 1

    # Check Unity
    unity = check_unity_installation()
    if unity is None:
        print("\n✗ RELEASE_PACKAGE FAILED: Unity Editor not found.")
        print("  Install Unity 6 LTS, or run a real Unity build first and place the")
        print(f"  player output in {BUILD}/.")
        write_report(base_report, "failed", False)
        return 1

    real_build = find_real_build_output()
    if real_build is None:
        print(f"\n✗ RELEASE_PACKAGE FAILED: no real Unity player build found.")
        print(f"  Run a real Unity build (see tools/release/local_build.py) so that the")
        print(f"  player output exists in {BUILD}/.")
        write_report(base_report, "failed", False)
        return 1

    print(f"✓ Real player build found: {real_build}")

    # Create build config
    config = create_build_config()

    # Copy assets (now directories exist)
    asset_count = copy_assets_for_release()
    print(f"  Total assets: {asset_count}")

    # Create docs
    create_license_and_docs()

    # Create ZIP
    zip_path, size = create_zip_package()

    # Generate release report - completed ONLY because a real build exists
    report = dict(base_report)
    report.update({
        "output": {
            "package_path": zip_path,
            "package_size_mb": round(size/1024/1024, 2),
            "asset_count": asset_count,
            "scenes_included": config['scenes'],
            "version": config['version'],
            "player_build": real_build,
        },
    })
    write_report(report, "completed", True)

    print("\n✓ RELEASE PACKAGE COMPLETED")
    return 0


if __name__ == '__main__':
    sys.exit(main())