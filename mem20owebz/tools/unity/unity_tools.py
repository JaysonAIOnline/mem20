"""
Jayson Unity Tools
==================
Practical tools for Unity integration.

Unity is heavier than Blender. Best workflow:
1. Create / refine assets in Blender
2. Export GLB / FBX
3. Import into a Unity project via these tools
4. Optional: run Unity in batch mode for simple tasks
"""

import subprocess
import os
from pathlib import Path
from typing import Optional

# Change these to match your system
UNITY_BIN = "unity"          # or full path to Unity Editor
# Example: "/Applications/Unity/Hub/Editor/6000.0.0f1/Unity.app/Contents/MacOS/Unity"
DEFAULT_PROJECT = Path.home() / "jayson_3d" / "UnityProjects" / "JaysonProject"
DEFAULT_PROJECT.mkdir(parents=True, exist_ok=True)


def create_project(project_path: Optional[str] = None) -> dict:
    """Create a new Unity project (batch mode)."""
    path = Path(project_path) if project_path else DEFAULT_PROJECT
    path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        UNITY_BIN,
        "-batchmode",
        "-nographics",
        "-createProject", str(path),
        "-quit"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return {
            "success": result.returncode == 0,
            "project": str(path),
            "stdout": result.stdout[-1500:],
            "stderr": result.stderr[-1500:]
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def import_asset(asset_path: str, project_path: Optional[str] = None) -> dict:
    """
    Copy an asset (GLB/FBX/PNG...) into the Unity project's Assets folder.
    This is the most reliable way to get Blender models into Unity.
    """
    project = Path(project_path) if project_path else DEFAULT_PROJECT
    assets_dir = project / "Assets" / "JaysonImports"
    assets_dir.mkdir(parents=True, exist_ok=True)

    src = Path(asset_path)
    if not src.exists():
        return {"success": False, "error": f"File not found: {asset_path}"}

    dest = assets_dir / src.name
    try:
        import shutil
        shutil.copy2(src, dest)
        return {
            "success": True,
            "imported_to": str(dest),
            "message": f"Copied {src.name} into Unity project. Open the project to see it."
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def open_project(project_path: Optional[str] = None) -> dict:
    """Open Unity project in the Editor (non-batch)."""
    project = Path(project_path) if project_path else DEFAULT_PROJECT
    if not project.exists():
        return {"success": False, "error": "Project does not exist"}

    cmd = [UNITY_BIN, "-projectPath", str(project)]
    try:
        # Don't wait — just launch
        subprocess.Popen(cmd)
        return {"success": True, "message": f"Launched Unity with project {project}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_editor_script(script_content: str, project_path: Optional[str] = None) -> dict:
    """
    Advanced: execute a C# Editor script via Unity batch mode.
    Requires the script to be placed correctly and a custom execute method.
    """
    # This is more complex and project-specific.
    # For most users the import_asset + open_project workflow is better.
    return {
        "success": False,
        "message": "Custom C# Editor scripts need to be set up per project. Use import_asset for now."
    }
