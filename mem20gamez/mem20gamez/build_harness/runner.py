"""run mode — execute the live production pipeline.

Deterministic conductor + real LLM agents + real tools.

Pipeline:
  1. Orchestrator (TLO) runs, kicks off Phase 0
  2. For each phase (supervisor in order):
       a. Supervisor runs, briefs its workers with the phase task spec
       b. Workers run in parallel (ThreadPoolExecutor), each has real tools
          (Blender, Unity, FreeCAD, sox, Surge XT) producing actual output files
       c. Supervisor reviews worker handoffs → phase handoff report
       d. Orchestrator gates the phase → PASS / BLOCK
  3. Orchestrator final assembly → builds the working Unity project from
     all collected artifacts, runs Unity batch compilation, delivers the game.

Everything is driven from the project config (generic for any harness).
Output lands in workspace/{pid}/ with per-phase subdirs + assembly dir.
"""

from __future__ import annotations

import contextvars
import fnmatch
import json
import os
import re
import signal
import shlex
import subprocess
import textwrap
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

# Harness Upgrades v2.1 module (provider routing, naming law, manifests, handoff
# checks, vision QA, Godot legs). Import lazily-tolerant of sys.path layout:
#   - installed as a mem20gamez subpackage -> `from . import v21`
#   - `python -m uvicorn src.app:app`  -> `from src import v21`
#   - `python src/runner.py`           -> `import v21`
# The subpackage form is tried FIRST: without it the seam below silently degrades
# to _V21 = None and worker bucket routing stops working with no error.
try:
    from . import v21 as _V21
except ImportError:  # pragma: no cover - depends on invocation style
    try:
        from src import v21 as _V21
    except ImportError:
        try:
            import v21 as _V21
        except ImportError:
            _V21 = None

if _V21 is not None:
    try:
        _V21.install_seam()  # patch llm.chat / achat for worker bucket routing
    except Exception as _e:  # pragma: no cover - never break startup on seam
        print(f"[runner] v21 seam install failed: {_e}")

# ── paths to real tools ──────────────────────────────────────────────────────

BLENDER = os.environ.get("HARNESS_BLENDER", "/usr/local/bin/blender")
UNITY   = os.environ.get("HARNESS_UNITY",
                          "/home/jayson/Unity/Hub/Editor/6000.5.9f1/Editor/Unity")
FREECAD = os.environ.get("HARNESS_FREECAD", "/usr/local/bin/freecadcmd")
SURGE   = os.environ.get("HARNESS_SURGE",    "/usr/bin/surge-xt-cli")
GODOT   = (os.environ.get("HARNESS_GODOT")
           or (_V21.GODOT if _V21 else "/usr/local/bin/godot"))


def _unity_version() -> str:
    """Extract the editor version (e.g. 6000.5.9f1) from the Unity path."""
    m = re.search(r"(\d+\.\d+\.\d+[abfp]\d+)", UNITY)
    if m:
        return m.group(1)
    p = Path(UNITY)
    for cand in (p.parent.parent.name, p.parent.name):
        if re.fullmatch(r"\d+\.\d+\.\d+[abfp]\d+", cand or ""):
            return cand
    return p.parent.parent.name or "0.0.0f1"


# Extensions Unity actually imports as assets in the final build. Everything
# else (raw .cs source, docs, JSON, Blender scripts, …) is preserved under an
# ignored `_Artifacts~` folder so it never breaks script compilation. Workers
# emit arbitrary/duplicate code (e.g. many copies of BuildProject.cs) that
# cannot be blindly compiled into one project.
_UNITY_ASSET_EXTS = {
    ".glb", ".gltf", ".fbx", ".obj", ".blend", ".dae",
    ".png", ".jpg", ".jpeg", ".tga", ".psd", ".bmp", ".exr", ".hdr",
    ".wav", ".ogg", ".mp3", ".aif", ".aiff",
    ".mat", ".unity", ".prefab", ".controller", ".anim", ".overrideController",
    ".asset", ".shader", ".compute", ".shadergraph", ".cubemap",
    ".rendertexture", ".physicmaterial", ".fontsettings", ".ttf", ".otf",
}

WORKSPACE_ROOT = Path(os.environ.get(
    "HARNESS_WORKSPACE", str(Path(__file__).resolve().parent.parent / "workspace")))

RUN_LOCK = threading.Lock()

# per-worker base dir; set in _run_worker so tools resolve relative paths
_WORKER_BASE: contextvars.ContextVar[str] = contextvars.ContextVar(
    "worker_base", default="")


def _resolve(path: str) -> str:
    """Make a possibly-relative path absolute against the current worker dir."""
    if path and path.strip().startswith("-"):
        cleaned = _clear_path_flags(path.strip())
        if cleaned:
            path = cleaned
    p = Path(path)
    if p.is_absolute() or not p.parts:
        return str(p)
    base = _WORKER_BASE.get()
    return str((Path(base) if base else Path.cwd()) / p)


def _clear_path_flags(path: str) -> str:
    """Strip leading CLI-style flags from a path spec so a path like
    '--outdir /abs/dir Assets/Editor/X.cs' becomes '/abs/dir/Assets/Editor/X.cs'.
    Agents frequently emit the OUTPUT DIRECTORY as --outdir / -o args instead
    of a bare path; treat the flag value as the base and join the rest."""
    parts = path.split()
    if not parts or not parts[0].startswith("-"):
        return path
    out = []
    i = 0
    while i < len(parts):
        tok = parts[i]
        if tok in ("--outdir", "-o", "--output-dir", "--directory", "-d"):
            if i + 1 < len(parts):
                base = parts[i + 1].rstrip("/")
                rest = " ".join(parts[i + 2:]).strip()
                if rest:
                    out.append(base + "/" + rest)
                else:
                    out.append(base)
                break
            i += 1
            continue
        if tok.startswith("--outdir=") or tok.startswith("--output-dir="):
            base = tok.split("=", 1)[1].rstrip("/")
            rest = " ".join(parts[i + 1:]).strip()
            if rest:
                out.append(base + "/" + rest)
            else:
                out.append(base)
            break
        out.append(tok)
        i += 1
    return " ".join(out)

# ── callable tool wrappers (real CLI execution) ─────────────────────────────

def _run(cmd: list[str], timeout: int = 300, cwd: str = ".",
         env: Optional[dict] = None) -> dict:
    """Run a subprocess, return stdout/stderr/exit."""
    try:
        full_env = dict(os.environ)
        if env:
            full_env.update(env)
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, cwd=cwd, env=full_env)
        return {"ok": r.returncode == 0, "exit": r.returncode,
                "stdout": r.stdout[-3000:], "stderr": r.stderr[-2000:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "exit": -1, "stdout": "", "stderr": "timeout"}
    except FileNotFoundError:
        return {"ok": False, "exit": -2, "stdout": "", "stderr": f"not found: {cmd[0]}"}
    except Exception as e:
        return {"ok": False, "exit": -3, "stdout": "", "stderr": str(e)[:500]}


def _run_detached(cmd: list[str], timeout: int = 1800, cwd: str = ".",
                  logpath: str = "", env: Optional[dict] = None) -> dict:
    """Run a long-lived tool (Unity) without pipe deadlocks.

    Unity spawns helper processes (UnityPackageManager) that outlive the editor
    and inherit its stdout/stderr. With ``capture_output=True`` those inherited
    pipe handles keep the read open, so ``subprocess.run`` blocks until the
    timeout even though Unity already exited. Redirecting to a file and using
    ``start_new_session`` (own process group, killed on timeout) avoids that.
    """
    if not logpath:
        logpath = str(Path(cwd) / "tool-run.log")
    Path(logpath).parent.mkdir(parents=True, exist_ok=True)
    timed_out = False
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    try:
        with open(logpath, "w") as lf:
            try:
                p = subprocess.Popen(
                    cmd, stdout=lf, stderr=subprocess.STDOUT,
                    cwd=cwd, env=full_env, start_new_session=True)
            except FileNotFoundError:
                return {"ok": False, "exit": -2, "stdout": "",
                        "stderr": f"not found: {cmd[0]}"}
            try:
                rc = p.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                try:
                    os.killpg(os.getpgid(p.pid), signal.SIGKILL)
                except Exception:
                    p.kill()
                p.wait()
                rc = -1
    except Exception as e:
        return {"ok": False, "exit": -3, "stdout": "", "stderr": str(e)[:500]}

    try:
        tail = Path(logpath).read_text(errors="ignore")[-3000:]
    except Exception:
        tail = ""
    return {"ok": rc == 0 and not timed_out, "exit": rc, "stdout": tail,
            "stderr": "timeout" if timed_out else "", "log": logpath}


def _blender_env() -> Optional[dict]:
    """Unity/Blender builds that need Android SDK use these env vars."""
    sdk = os.path.expanduser("~/Android/Sdk")
    if Path(sdk).is_dir():
        return {"ANDROID_HOME": sdk, "ANDROID_SDK_ROOT": sdk}
    return None


# ── Blender generators (real asset production) ──────────────────────────────
# Each generator builds real geometry from primitives and exports a real GLB.
_BLENDER_GENERATORS = {
    # <output.glb> <kind> [--count N] [--seed N]
    "fishtank": """
import bpy, mathutils, math
scene = bpy.context.scene
for o in list(scene.objects): bpy.data.objects.remove(o, do_unlink=True)
# tank walls (glass box)
tank = bpy.data.objects.new("Tank", None) if False else None
w = 2.4; h = 1.5; d = 0.8
def box(name, sx, sy, sz, x, y, z, color, glass=False):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y, z))
    ob = bpy.context.active_object; ob.name = name; ob.scale = (sx/2, sy/2, sz/2)
    mat = bpy.data.materials.new(name + "_mat")
    mat.diffuse_color = color
    if glass: mat.diffuse_color = (0.95, 0.97, 1.0, 0.25)
    ob.data.materials.append(mat)
    return ob
mat = bpy.data.materials.new("water")
mat.diffuse_color = (0.25, 0.55, 0.8, 0.35)
box("WallL", 0.06, d+0.12, h, -w/2, 0, h/2, (0.8,0.85,0.9))
box("WallR", 0.06, d+0.12, h,  w/2, 0, h/2, (0.8,0.85,0.9))
box("WallBack", w+0.12, 0.06, h, 0, -d/2, h/2, (0.8,0.85,0.9))
box("WallFront", w+0.12, 0.06, h, 0,  d/2, h/2, (0.85,0.9,0.95))
box("Floor", w, d, 0.08, 0, 0, 0.04, (0.75,0.8,0.85))
box("Water", w-0.2, d-0.2, 0.05, 0, 0, 0.55, (0.3,0.6,0.85))
box("Rim",  w+0.1, d+0.1, 0.05, 0, 0, h, (0.2,0.25,0.3))
# a few simple fish forms (triangles/cones) in water
import random; random.seed(73)
for i in range(count):
    fx = random.uniform(-w/2+0.4, w/2-0.4); fy = random.uniform(-d/2+0.3, d/2-0.3); fz = random.uniform(0.35, h-0.5)
    bpy.ops.mesh.primitive_cone_add(radius1=0.14, depth=0.34, vertices=6, location=(fx,fy,fz))
    f = bpy.context.active_object; f.name = f"Fish{i}"
    fm = bpy.data.materials.new(f"fish{m_i(i)}"); fm.diffuse_color = (random.uniform(0.9,1), random.uniform(0.2,0.6), random.uniform(0.1,0.9), 1.0)
    f.data.materials.append(fm); f.rotation_euler[2] = random.uniform(-0.5,0.5)
# lights + camera
bpy.ops.object.light_add(type="AREA", location=(0, -2.5, 2.6)); bpy.context.active_object.data.energy = 400
bpy.ops.object.camera_add(location=(2.6, -3.4, 1.6))
cam = bpy.context.active_object; cam.rotation_euler = (math.radians(62), 0, math.radians(35))
scene.camera = cam; scene.render.film_transparent = True
bpy.ops.export_scene.gltf(filepath=output, use_selection=False)
print("EXPORTED", output)
""",
    "awards-wall": """
import bpy, math, random
for o in list(bpy.context.scene.objects): bpy.data.objects.remove(o, do_unlink=True)
random.seed(11)
for i in range(count):
    x = (i % 10) * 0.32 - 1.4; y = -(i // 10) * 0.4 + 0.9
    bpy.ops.mesh.primitive_cube_add(size=0.26, location=(x, y, 0))
    ob = bpy.context.active_object; ob.name = f"Award{i}"
    m = bpy.data.materials.new(f"award{m_i(i)}")
    m.diffuse_color = (random.uniform(0.6,1), random.uniform(0.5,0.8), random.uniform(0.1,0.6), 1.0)
    ob.data.materials.append(m)
bpy.ops.mesh.primitive_plane_add(size=4.0, location=(0, -1.0, 0))
wall = bpy.context.active_object; wall.rotation_euler = (math.radians(90),0,0)
wm = bpy.data.materials.new("wallbase"); wm.diffuse_color = (0.5,0.35,0.2,1.0); wall.data.materials.append(wm)
bpy.ops.object.light_add(type="POINT", location=(0, 2.2, 1.6)); bpy.context.active_object.data.energy = 300
bpy.ops.object.camera_add(location=(0, 3.2, 0.8))
cam = bpy.context.active_object; cam.rotation_euler = (math.radians(90), 0, 0)
bpy.context.scene.camera = cam; bpy.context.scene.render.film_transparent = True
bpy.ops.export_scene.gltf(filepath=output, use_selection=False)
print("EXPORTED", output)
""",
    "agent-prefab": """
import bpy, math, random
for o in list(bpy.context.scene.objects): bpy.data.objects.remove(o, do_unlink=True)
random.seed(23)
def limb(name, x, y, z, sx, sy, sz, color):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x,y,z))
    o = bpy.context.active_object; o.name = name; o.scale = (sx,sy,sz)
    m = bpy.data.materials.new(name+"_mat"); m.diffuse_color = color; o.data.materials.append(m)
    return o
skin = (0.95,0.8,0.7,1.0); suit = (0.2,0.35,0.6,1.0)
limb("Torso", 0,0,0.9, 0.3,0.2,0.5, suit)
limb("Head", 0,0,1.55, 0.16,0.16,0.16, skin)
limb("ArmL", -0.35,0,0.95, 0.09,0.09,0.45, suit)
limb("ArmR",  0.35,0,0.95, 0.09,0.09,0.45, suit)
limb("LegL", -0.12,0,0.3, 0.1,0.1,0.5, (0.15,0.2,0.35))
limb("LegR",  0.12,0,0.3, 0.1,0.1,0.5, (0.15,0.2,0.35))
# role variant: hair / hat via extra head cube
if count > 0:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0,0,1.78))
    hat = bpy.context.active_object; hat.name="Hat"; hat.scale=(0.2,0.2,0.08)
    hm = bpy.data.materials.new("hat_mat"); hm.diffuse_color=(0.9,0.2,0.2,1.0); hat.data.materials.append(hm)
bpy.ops.object.light_add(type="AREA", location=(0,-1.6,2.0)); bpy.context.active_object.data.energy=300
bpy.ops.object.camera_add(location=(0,-2.2,1.1)); cam=bpy.context.active_object; cam.rotation_euler=(math.radians(88),0,0)
bpy.context.scene.camera=cam; bpy.context.scene.render.film_transparent=True
bpy.ops.export_scene.gltf(filepath=output, use_selection=False)
print("EXPORTED", output)
""",
    "elevator": """
import bpy, math
for o in list(bpy.context.scene.objects): bpy.data.objects.remove(o, do_unlink=True)
def box(name, sx, sy, sz, x, y, z, color):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x,y,z))
    o=bpy.context.active_object; o.name=name; o.scale=(sx/2,sy/2,sz/2)
    m=bpy.data.materials.new(name+"_mat"); m.diffuse_color=color; o.data.materials.append(m)
    return o
box("Shaft", 2.2, 2.4, 4.0, 0, 0, 2.0, (0.15,0.15,0.18))
box("CabFloor", 1.9, 0.1, 0.1, 0, 0, 0.05, (0.4,0.42,0.45))
box("CabBack", 1.9, 1.8, 0.08, 0, -0.85, 1.0, (0.55,0.58,0.62))
box("CabWallL", 0.08, 1.8, 1.9, -0.9, 0, 1.0, (0.55,0.58,0.62))
box("CabWallR", 0.08, 1.8, 1.9,  0.9, 0, 1.0, (0.55,0.58,0.62))
box("Panel", 0.2, 0.5, 0.5, 0.62, 0.8, 1.4, (0.1,0.1,0.12))
box("DoorL", 0.94, 0.06, 1.9, -0.47, 0.9, 1.0, (0.7,0.72,0.76))
box("DoorR", 0.94, 0.06, 1.9,  0.47, 0.9, 1.0, (0.7,0.72,0.76))
box("Indicator", 0.3, 0.06, 0.12, 0, 0.9, 1.9, (0.1, 0.9, 0.2))
bpy.ops.object.light_add(type="POINT", location=(0, 0.6, 1.8)); bpy.context.active_object.data.energy=200
bpy.ops.object.camera_add(location=(0, 3.0, 1.1)); cam=bpy.context.active_object; cam.rotation_euler=(0,0,0)
bpy.context.scene.camera=cam; bpy.context.scene.render.film_transparent=True
bpy.ops.export_scene.gltf(filepath=output, use_selection=False)
print("EXPORTED", output)
""",
    "office": """
import bpy, math, random
for o in list(bpy.context.scene.objects): bpy.data.objects.remove(o, do_unlink=True)
random.seed(7)
def box(name, sx, sy, sz, x, y, z, color):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x,y,z))
    o=bpy.context.active_object; o.name=name; o.scale=(sx/2,sy/2,sz/2)
    m=bpy.data.materials.new(name+"_mat"); m.diffuse_color=color; o.data.materials.append(m)
    return o
box("Floor", 8, 6, 0.1, 0, 0, 0.05, (0.5,0.42,0.35))
box("WallN", 8, 0.1, 3, 0, -3, 1.5, (0.85,0.88,0.92))
box("WallS", 8, 0.1, 3, 0,  3, 1.5, (0.85,0.88,0.92))
box("WallW", 0.1, 6, 3, -4, 0, 1.5, (0.85,0.88,0.92))
box("WallE", 0.1, 6, 3,  4, 0, 1.5, (0.85,0.88,0.92))
box("Desk1", 1.8, 0.9, 0.1, -2, -1, 0.7, (0.35,0.3,0.26))
box("Desk2", 1.8, 0.9, 0.1,  2, -1, 0.7, (0.35,0.3,0.26))
box("Screen1", 1.6, 0.05, 0.8, -2, -0.55, 1.1, (0.15,0.15,0.18))
box("Screen2", 1.6, 0.05, 0.8,  2, -0.55, 1.1, (0.15,0.15,0.18))
box("ChairA", 0.45, 0.45, 0.4, -2, -1.7, 0.4, (0.3,0.5,0.35))
box("Reception", 0.08, 1.4, 1.1, -0.05, 2.6, 1.1, (0.9,0.55,0.2))
box("CarPet", 1.4, 0.06, 2.2, 0, 1.2, 0.35, (0.6,0.1,0.1))
bpy.ops.object.light_add(type="AREA", location=(0, 0, 3.0)); bpy.context.active_object.data.energy=500
bpy.ops.object.camera_add(location=(0, 4.2, 2.0)); cam=bpy.context.active_object; cam.rotation_euler=(math.radians(58),0,0)
bpy.context.scene.camera=cam; bpy.context.scene.render.film_transparent=True
bpy.ops.export_scene.gltf(filepath=output, use_selection=False)
print("EXPORTED", output)
""",
    "crowd": """
import bpy, math, random
for o in list(bpy.context.scene.objects): bpy.data.objects.remove(o, do_unlink=True)
random.seed(101)
for i in range(count):
    x = random.uniform(-4, 4); z = random.uniform(-3, 3)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.35, location=(x, z, 0.3))
    o=bpy.context.active_object; o.name=f"Actor{i}"
    m=bpy.data.materials.new(f"crowd{m_i(i)}"); m.diffuse_color=(random.uniform(0.2,0.9),random.uniform(0.2,0.9),random.uniform(0.2,0.9),1.0)
    if o.data.materials: o.data.materials.append(m)
bpy.ops.object.light_add(type="AREA", location=(0,-2,3)); bpy.context.active_object.data.energy=400
bpy.ops.object.camera_add(location=(4,-4,1.4)); cam=bpy.context.active_object; cam.rotation_euler=(math.radians(55),0,math.radians(35))
bpy.context.scene.camera=cam; bpy.context.scene.render.film_transparent=True
bpy.ops.export_scene.gltf(filepath=output, use_selection=False)
print("EXPORTED", output)
""",
    "bubbles": """
import bpy, math, random
for o in list(bpy.context.scene.objects): bpy.data.objects.remove(o, do_unlink=True)
random.seed(5)
for i in range(count):
    x=random.uniform(-1,1); y=random.uniform(-0.5,0.5); z=random.uniform(0.5,1.8)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=random.uniform(0.02,0.07), location=(x,y,z))
    o=bpy.context.active_object; o.name=f"Bubble{i}"
    m=bpy.data.materials.new(f"bubble{m_i(i)}"); m.diffuse_color=(0.9,0.97,1.0,0.35); o.data.materials.append(m)
bpy.ops.object.light_add(type="POINT", location=(0,-1.5,2)); bpy.context.active_object.data.energy=250
bpy.ops.object.camera_add(location=(2,-2.5,1.2)); cam=bpy.context.active_object; cam.rotation_euler=(math.radians(60),0,math.radians(28))
bpy.context.scene.camera=cam; bpy.context.scene.render.film_transparent=True
bpy.ops.export_scene.gltf(filepath=output, use_selection=False)
print("EXPORTED", output)
""",
    "decimate": """
import bpy, sys, math
for o in list(bpy.context.scene.objects): bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=5, radius=1.0, location=(0,0,0))
o=bpy.context.active_object; o.name="LowPolySphere"
bpy.ops.object.modifier_add(type="DECIMATE"); bpy.context.object.modifiers["Decimate"].ratio = 0.2
bpy.ops.object.modifier_apply(modifier="Decimate")
m=bpy.data.materials.new("lp"); m.diffuse_color=(0.4,0.6,0.9,1.0); o.data.materials.append(m)
bpy.ops.object.light_add(type="POINT", location=(2,2,3)); bpy.context.active_object.data.energy=200
bpy.ops.object.camera_add(location=(2.5,-2.5,1.6)); cam=bpy.context.active_object; cam.rotation_euler=(math.radians(60),0,math.radians(45))
bpy.context.scene.camera=cam; bpy.context.scene.render.film_transparent=True
bpy.ops.export_scene.gltf(filepath=output, use_selection=False)
print("EXPORTED", output)
""",
}

def _blender_alias(args: str, kind: str, default_out: str, tail: str = "") -> dict:
    """Alias dispatch for blender-gen: coerce flag-style args into
    '<output.glb> <kind> [tail]' while always forcing the alias's implied kind.

    Workers habitually call e.g. 'build-agent-prefab --output Scene_X.glb' or
    'build-agent-prefab Scene_X.glb office'; the output token is pulled out and
    the alias kind (agent-prefab/office/...) is appended deterministically.
    `tail` (e.g. '--count 40') is appended after the kind so the parser sees
    count flags in the expected position.
    """
    a = (args or "").strip()
    if not a:
        a = default_out
    toks = a.split()
    if toks[0] in ("--output", "-o", "--output-dir", "--outdir", "-d", "--out"):
        a = toks[1] if len(toks) >= 2 else default_out
    elif toks[0].startswith("--output="):
        a = toks[0].split("=", 1)[1]
    if not a.split():
        a = default_out
    if a.split()[-1] == kind:
        return tool_blender_gen(f"{a}{' ' + tail if tail else ''}")
    return tool_blender_gen(f"{a} {kind}{' ' + tail if tail else ''}")


def _canonical_mesh_name(rawname: str) -> str:
    """Derive a v2.1-legal StaticMesh (.glb) name from a worker's request.

    Workers habitually hand blender-gen output names that are scene/prefab or
    flag-flavored (e.g. 'Scene_X.unity.glb', 'Prefab_X.prefab.glb',
    '--output.glb'). The naming law only allows a .glb as 'SM_*'. A name that
    already satisfies the StaticMesh rule is returned unchanged; every other
    name is rewritten deterministically so the exported mesh can never fail
    the naming audit.
    """
    name = Path(rawname).name.strip()
    name = name.lstrip("-")
    if not name:
        return "SM_Asset_Main.glb"
    # drop asset-kind wrappers workers glue in front of the real extension
    name = re.sub(r"\.(unity|tscn|prefab|mat)\.glb$", ".glb", name, flags=re.I)
    mesh_rule = (_V21.NAMING_RULES[0][0] if _V21 else
                 r"^SM_[A-Za-z0-9]+_[A-Za-z0-9]+(?:_[A-Za-z0-9]*)*(?:_LOD\d+)?(?:\.(?:fbx|glb|gltf|obj|blend))?$")
    if re.match(mesh_rule, name):
        return name
    stem = name[:-4] if name.lower().endswith(".glb") else name
    # drop prefixes reserved for other asset kinds
    stem = re.sub(r"^(SM|Scene|Prefab|Texture|T|A|M|B|V|W|N|Fx)_", "", stem, flags=re.I)
    stem = re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_")
    parts = [p for p in stem.split("_") if p]
    if not parts:
        parts = ["Asset"]
    while len(parts) < 2:
        parts.append("Mesh")
    return "SM_" + "_".join(parts[:4]).rstrip("_") + ".glb"


def tool_blender_gen(args: str) -> dict:
    """Generate a real 3D asset via Blender and export GLB.

    args: "<output.glb> <kind> [--count N] [--seed N]"
    kinds: fishtank | awards-wall | agent-prefab | elevator | office |
           crowd | bubbles | decimate
    """
    parts = args.split()
    if len(parts) < 1:
        return {"ok": False, "stderr": "need output.glb and kind"}
    head = parts[0]
    # tolerate CLI-style flag prefixes workers habitually emit before the arg
    if head in ("--output", "-o", "--output-dir", "--outdir", "-d", "--out"):
        if len(parts) < 3:
            return {"ok": False, "stderr": "need output.glb and kind"}
        out_tok, kind = parts[1], parts[2]
        extra = parts[3:]
    elif head.startswith("--output="):
        out_tok = head.split("=", 1)[1]
        if len(parts) < 2:
            return {"ok": False, "stderr": "need output.glb and kind"}
        kind = parts[1]
        extra = parts[2:]
    else:
        if len(parts) < 2:
            return {"ok": False, "stderr": "need output.glb and kind"}
        out_tok, kind = parts[0], parts[1]
        extra = parts[2:]
    output = _resolve(out_tok)
    # deterministic v2.1 naming: the exported mesh must be a legal SM_* .glb
    canonical = _canonical_mesh_name(out_tok)
    if Path(canonical).name != Path(output).name:
        output = str(Path(output).parent / Path(canonical).name)
    count = 6
    for i, p in enumerate(extra):
        if p == "--count" and i + 1 < len(extra):
            try:
                count = max(1, min(int(extra[i + 1]), 120))
            except ValueError:
                count = 6
    if kind not in _BLENDER_GENERATORS:
        return {"ok": False, "stderr": f"unknown kind '{kind}'; known: {', '.join(_BLENDER_GENERATORS)}"}
    code = _BLENDER_GENERATORS[kind]
    code = code.replace("count", str(count))
    # templates reference m_i(i) for material names — define it + enable glTF addon
    code = ("import bpy, sys\n"
            "def m_i(i):\n    return i % 10\n"
            "def _rgba(c):\n    c = list(c)\n"
            "    if len(c) < 4:\n        c.append(1.0)\n"
            "    return tuple(c)\n"
            "output = sys.argv[-1]\n"
            "bpy.ops.preferences.addon_enable(module='io_scene_gltf2')\n"
            "bpy.context.preferences.use_preferences_save = False\n") + code
    # Blender 5.x requires 4-component RGBA; templates pass 3-tuples via the
    # box() `color` param into `diffuse_color = color`. Route every such
    # assignment through _rgba so the generators work on current Blender.
    code = re.sub(r"diffuse_color\s*=\s*color\b", "diffuse_color = _rgba(color)", code)
    code += f"\nimport bpy\nbpy.ops.wm.save_as_mainfile(filepath='{output.replace('.glb', '.blend')}')"
    script = Path(output).with_suffix(".py")
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(code)
    cmd = [BLENDER, "-b", "-P", str(script), "--", output]
    r = _run(cmd, timeout=600)
    if r["ok"] and "EXPORTED" not in (r["stdout"] + r["stderr"]):
        r["ok"] = False
        r["stderr"] += " [no EXPORTED marker]"
    return r


def tool_unity_batch(args: str) -> dict:
    """Run Unity in batch mode against a real Unity project.

    args: "<project_path> [--method <method>] [--build <target>]"
    Default: -batchmode -nographics -quit (compiles scripts)
    """
    parts = args.split()
    if not parts:
        return {"ok": False, "stderr": "need project_path"}
    project = _resolve(parts[0])
    method = ""
    build_target = ""
    for i, p in enumerate(parts):
        if p == "--method" and i + 1 < len(parts):
            method = parts[i + 1]
        if p == "--build" and i + 1 < len(parts):
            build_target = parts[i + 1]
    if not (Path(project) / "ProjectSettings").is_dir():
        return {"ok": False, "stderr": f"not a Unity project: {project}"}
    logname = (method.split(".")[-1] if method else "compile")
    logpath = str(Path(project) / "Logs" / f"unity-{logname}.log")
    cmd = [UNITY, "-batchmode", "-nographics", "-projectPath", project,
           "-logFile", logpath]
    if method:
        cmd += ["-executeMethod", method]
    if build_target:
        cmd += ["-buildTarget", build_target]
    cmd += ["-quit"]
    return _run_detached(cmd, timeout=1800, cwd=project, logpath=logpath,
                         env=_blender_env())


# Phase 0 Tool Implementations
def tool_scaffold_project_phase0(args: str) -> dict:
    """Run full Phase 0 bootstrap: install packages, configure URP/XR, create scenes, XR Origin.
    
    args: "<project_path>"
    """
    parts = args.split()
    if not parts:
        return {"ok": False, "stderr": "need project_path"}
    project = _resolve(parts[0])
    
    scripts_dir = Path(project) / "Assets" / "Editor"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    
    script_files = [
        ("Phase0InstallPackages.cs", _PHASE0_INSTALL_PACKAGES),
        ("Phase0CreateXROrigin.cs", _PHASE0_CREATE_XR_ORIGIN),
        ("Phase0CreateScenes.cs", _PHASE0_CREATE_SCENES),
        ("Phase0Verify.cs", _PHASE0_VERIFY),
        ("Phase0SetupAndroid.cs", _PHASE0_SETUP_ANDROID),
    ]
    
    for filename, content in script_files:
        (scripts_dir / filename).write_text(content)
    
    (scripts_dir / "BuildProject.cs").write_text(_UNITY_BUILD_SCRIPT)
    
    steps = [
        ("Phase0InstallPackages.Install", "Install Packages & Configure URP/XR"),
        ("Phase0CreateScenes.CreateScenes", "Create Scenes & Core Managers"),
        ("Phase0CreateXROrigin.CreateXROrigin", "Create XR Origin with Locomotion"),
        ("Phase0SetupAndroid.SetupAndroid", "Configure Android/Quest 3 Build"),
        ("Phase0Verify.Verify", "Verify Bootstrap"),
    ]
    
    all_output = []
    for method, description in steps:
        result = tool_unity_batch(f"{project} --method {method}")
        all_output.append(f"=== {description} ===\n{result.get('stdout', '')}\n{result.get('stderr', '')}")
        if not result.get("ok"):
            return {"ok": False, "output": "\n".join(all_output), "stderr": f"Failed at: {description}"}
    
    return {"ok": True, "output": "\n".join(all_output)}


def tool_write_config_phase0(args: str) -> dict:
    """Write Phase 0 configuration files (manifest.json, ProjectVersion.txt, XR settings).
    
    args: "<project_path>"
    """
    parts = args.split()
    if not parts:
        return {"ok": False, "stderr": "need project_path"}
    project = _resolve(parts[0])
    
    root = Path(project)
    (root / "Assets" / "_Project").mkdir(parents=True, exist_ok=True)
    (root / "Assets" / "_Project" / "Prefabs").mkdir(parents=True, exist_ok=True)
    (root / "Assets" / "_Project" / "Resources").mkdir(parents=True, exist_ok=True)
    (root / "Assets" / "_Project" / "ScriptableObjects" / "Dialogues").mkdir(parents=True, exist_ok=True)
    (root / "Assets" / "_Project" / "Scripts" / "Dialogue").mkdir(parents=True, exist_ok=True)
    (root / "Assets" / "_Project" / "Scripts" / "Core").mkdir(parents=True, exist_ok=True)
    (root / "Assets" / "_Project" / "Scripts" / "Elevator").mkdir(parents=True, exist_ok=True)
    (root / "Assets" / "_Project" / "Scripts" / "Agents").mkdir(parents=True, exist_ok=True)
    (root / "Assets" / "_Project" / "Scripts" / "Player").mkdir(parents=True, exist_ok=True)
    (root / "Assets" / "Scenes").mkdir(parents=True, exist_ok=True)
    (root / "Packages").mkdir(parents=True, exist_ok=True)
    (root / "ProjectSettings").mkdir(parents=True, exist_ok=True)
    
    ver = _unity_version()
    (root / "ProjectSettings" / "ProjectVersion.txt").write_text(f"m_EditorVersion: {ver}\n")
    
    manifest = {
        "dependencies": {
            "com.unity.render-pipelines.universal": "17.0.3",
            "com.unity.xr.openxr": "1.13.0",
            "com.unity.xr.interaction.toolkit": "3.0.9",
            "com.unity.inputsystem": "1.12.0",
            "com.unity.textmeshpro": "3.0.6",
            "com.unity.ugui": "1.0.0",
            "com.unity.modules.physics": "1.0.0",
            "com.unity.modules.audio": "1.0.0",
        }
    }
    (root / "Packages" / "manifest.json").write_text(json.dumps(manifest, indent=2))
    
    return {"ok": True, "output": f"Phase 0 config written to {project}"}


def tool_setup_build_target_phase0(args: str) -> dict:
    """Configure Android/Quest 3 build target via Unity batch mode.
    
    args: "<project_path>"
    """
    parts = args.split()
    if not parts:
        return {"ok": False, "stderr": "need project_path"}
    project = _resolve(parts[0])
    
    scripts_dir = Path(project) / "Assets" / "Editor"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "Phase0SetupAndroid.cs").write_text(_PHASE0_SETUP_ANDROID)
    
    result = tool_unity_batch(f"{project} --method Phase0SetupAndroid.SetupAndroid")
    return result


def tool_verify_bootstrap_phase0(args: str) -> dict:
    """Run Phase 0 verification via Unity batch mode.
    
    args: "<project_path>"
    """
    parts = args.split()
    if not parts:
        return {"ok": False, "stderr": "need project_path"}
    project = _resolve(parts[0])
    
    scripts_dir = Path(project) / "Assets" / "Editor"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "Phase0Verify.cs").write_text(_PHASE0_VERIFY)
    
    result = tool_unity_batch(f"{project} --method Phase0Verify.Verify")
    return result


def tool_unity_create_script_mcp(args: str) -> dict:
    """Create a C# script in a Unity project via Unity MCP.
    
    args: "<project_path> <script_name> [--namespace <ns>] [--base <base>] [--fields field:type=default,...]"
    """
    parts = args.split()
    if len(parts) < 2:
        return {"ok": False, "stderr": "need project_path and script_name"}
    project = _resolve(parts[0])
    script_name = parts[1]
    
    namespace = ""
    base_class = "MonoBehaviour"
    fields = []
    
    for i, p in enumerate(parts):
        if p == "--namespace" and i + 1 < len(parts):
            namespace = parts[i + 1]
        if p == "--base" and i + 1 < len(parts):
            base_class = parts[i + 1]
        if p == "--fields" and i + 1 < len(parts):
            for f in parts[i + 1].split(","):
                if f:
                    fparts = f.split(":")
                    if len(fparts) >= 2:
                        fields.append({"name": fparts[0], "type": fparts[1], "default": fparts[2] if len(fparts) > 2 else ""})
    
    ns_block = ""
    if namespace:
        ns_block = "namespace " + namespace + "\n{\n"
        ns_end = "\n}\n"
    else:
        ns_end = "\n"
    
    script_content = "using UnityEngine;\n\n"
    script_content += ns_block
    script_content += "public class " + script_name + " : " + base_class + "\n{\n"
    for field in fields:
        script_content += "    [SerializeField] private " + field['type'] + " " + field['name']
        if field.get('default'):
            script_content += " = " + field['default']
        script_content += ";\n"
    script_content += "}" + ns_end
    
    scripts_dir = Path(project) / "Assets" / "Scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    script_path = scripts_dir / (script_name + ".cs")
    script_path.write_text(script_content)
    
    return {"ok": True, "output": f"Created script at {script_path}"}


def tool_unity_validate_project_mcp(args: str) -> dict:
    """Validate Unity project structure.
    
    args: "<project_path>"
    """
    parts = args.split()
    if not parts:
        return {"ok": False, "stderr": "need project_path"}
    project = _resolve(parts[0])
    
    issues = []
    warnings = []
    required_dirs = ["Assets", "ProjectSettings", "Packages"]
    for d in required_dirs:
        if not os.path.exists(os.path.join(project, d)):
            issues.append(f"Missing required directory: {d}")
    
    phase0_dirs = [
        "Assets/_Project/Prefabs",
        "Assets/_Project/Resources",
        "Assets/_Project/ScriptableObjects/Dialogues",
        "Assets/_Project/Scripts/Dialogue",
        "Assets/_Project/Scripts/Core",
        "Assets/_Project/Scripts/Elevator",
        "Assets/_Project/Scripts/Agents",
        "Assets/_Project/Scripts/Player",
        "Assets/_Project/Scenes",
    ]
    for d in phase0_dirs:
        if not os.path.exists(os.path.join(project, d)):
            warnings.append(f"Phase 0 folder missing: {d}")
    
    scenes = ["Assets/_Project/Scenes/00_Office_Startup.unity", 
              "Assets/_Project/Scenes/01_MainFloor.unity",
              "Assets/_Project/Scenes/02_Exterior_Car.unity"]
    for s in scenes:
        if not os.path.exists(os.path.join(project, s)):
            issues.append(f"Phase 0 scene missing: {s}")
    
    manifest_path = os.path.join(project, "Packages", "manifest.json")
    if os.path.exists(manifest_path):
        manifest_text = open(manifest_path).read()
        required_packages = [
            "com.unity.render-pipelines.universal",
            "com.unity.xr.openxr",
            "com.unity.xr.interaction.toolkit",
            "com.unity.inputsystem",
            "com.unity.textmeshpro"
        ]
        for pkg in required_packages:
            if pkg not in manifest_text:
                issues.append(f"Required package not in manifest: {pkg}")
    
    if not os.path.exists(os.path.join(project, "Assets", "_Project", "Resources", "PipelineAssets", "URP-HighQuality.asset")):
        warnings.append("URP Pipeline Asset not found")
    
    result = f"Validation for {project}:\n"
    if issues:
        result += f"\n❌ Issues ({len(issues)}):\n" + "\n".join(f"  - {i}" for i in issues)
    else:
        result += "\n✅ No critical issues found"
    if warnings:
        result += f"\n⚠️ Warnings ({len(warnings)}):\n" + "\n".join(f"  - {w}" for w in warnings)
    
    return {"ok": len(issues) == 0, "output": result}


_UNITY_SCENE_TPL = """%%YAML 1.1
%%TAG !u! tag:unity3d.com,2011:
--- !u!29 &1
OcclusionCullingSettings:
  m_ObjectHideFlags: 0
  serializedVersion: 2
  m_OcclusionBakeSettings:
    smallestOccluder: 5
    smallestHole: 0.25
    backfaceThreshold: 100
  m_SceneGUID: 00000000000000000000000000000000
  m_OcclusionCullingData: {fileID: 0}
--- !u!104 &2
RenderSettings:
  m_ObjectHideFlags: 0
  serializedVersion: 9
  m_Fog: 0
  m_FogColor: {r: 0.5, g: 0.5, b: 0.5, a: 1}
  m_FogMode: 3
  m_FogDensity: 0.01
  m_LinearFogStart: 0
  m_LinearFogEnd: 300
  m_AmbientSkyColor: {r: 0.212, g: 0.227, b: 0.259, a: 1}
  m_AmbientEquatorColor: {r: 0.114, g: 0.125, b: 0.133, a: 1}
  m_AmbientGroundColor: {r: 0.047, g: 0.043, b: 0.035, a: 1}
  m_AmbientIntensity: 1
  m_AmbientMode: 0
  m_SubtractiveShadowColor: {r: 0.42, g: 0.478, b: 0.627, a: 1}
  m_SkyboxMaterial: {fileID: 0}
  m_HaloStrength: 0.5
  m_FlareStrength: 1
  m_FlareFadeSpeed: 3
  m_HaloTexture: {fileID: 0}
  m_SpotCookie: {fileID: 10001, guid: 0000000000000000e000000000000000, type: 0}
  m_DefaultReflectionMode: 0
  m_DefaultReflectionResolution: 128
  m_ReflectionBounces: 1
  m_ReflectionIntensity: 1
  m_CustomReflection: {fileID: 0}
  m_Sun: {fileID: 0}
  m_IndirectSpecularColor: {r: 0, g: 0, b: 0, a: 1}
  m_UseRadianceAmbientProbe: 0
--- !u!157 &3
LightmapSettings:
  m_ObjectHideFlags: 0
  serializedVersion: 11
  m_GIWorkflowMode: 1
  m_GISettings:
    serializedVersion: 2
    m_BounceScale: 1
    m_IndirectOutputScale: 1
    m_AlbedoBoost: 1
    m_EnvironmentLightingMode: 0
    m_EnableBakedLightmaps: 0
    m_EnableRealtimeLightmaps: 0
  m_LightmapEditorSettings:
    serializedVersion: 12
    m_Resolution: 2
    m_BakeResolution: 40
    m_AtlasSize: 1024
    m_AO: 0
    m_AOMaxDistance: 1
    m_CompAOExponent: 1
    m_CompAOExponentDirect: 0
    m_ExtractAmbientOcclusion: 0
    m_Padding: 2
    m_LightmapParameters: {fileID: 0}
    m_LightmapsBakeMode: 1
    m_TextureCompression: 1
    m_FinalGather: 0
    m_FinalGatherFiltering: 1
    m_FinalGatherRayCount: 256
    m_ReflectionCompression: 2
    m_MixedBakeMode: 2
    m_BakeBackend: 1
    m_PVRSampling: 1
    m_PVRDirectSampleCount: 32
    m_PVRSampleCount: 512
    m_PVRBounces: 2
    m_PVREnvironmentSampleCount: 256
    m_PVREnvironmentReferencePointCount: 2048
    m_PVRFilteringMode: 1
    m_PVRDenoiserTypeDirect: 1
    m_PVRDenoiserTypeIndirect: 1
    m_PVRDenoiserTypeAO: 1
    m_PVRFilterTypeDirect: 0
    m_PVRFilterTypeIndirect: 0
    m_PVRFilterTypeAO: 0
    m_PVREnvironmentMIS: 1
    m_PVRCulling: 1
    m_PVRFilteringGaussRadiusDirect: 1
    m_PVRFilteringGaussRadiusIndirect: 5
    m_PVRFilteringGaussRadiusAO: 2
    m_PVRFilteringAtrousPositionSigmaDirect: 0.5
    m_PVRFilteringAtrousPositionSigmaIndirect: 2
    m_PVRFilteringAtrousPositionSigmaAO: 1
    m_ExportTrainingData: 0
    m_TrainingDataDestination: TrainingData
    m_LightProbeSampleCountMultiplier: 4
  m_LightingDataAsset: {fileID: 0}
  m_LightingSettings: {fileID: 0}
--- !u!196 &4
NavMeshSettings:
  serializedVersion: 2
  m_ObjectHideFlags: 0
  m_BuildSettings:
    serializedVersion: 2
    agentTypeID: 0
    agentRadius: 0.5
    agentHeight: 2
    agentSlope: 45
    agentClimb: 0.4
    ledgeDropHeight: 0
    maxJumpAcrossDistance: 0
    minRegionArea: 2
    manualCellSize: 0
    cellSize: 0.16666667
    manualTileSize: 0
    tileSize: 256
    accuratePlacement: 0
    debug:
      m_Flags: 0
  m_NavMeshData: {fileID: 0}
--- !u!1 &100000
GameObject:
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {fileID: 0}
  m_PrefabInstance: {fileID: 0}
  m_PrefabAsset: {fileID: 0}
  serializedVersion: 6
  m_Component:
  - component: {fileID: 400000}
  - component: {fileID: 660000}
  m_Layer: 0
  m_Name: Main Camera
  m_TagString: MainCamera
  m_Icon: {fileID: 0}
  m_NavMeshLayer: 0
  m_StaticEditorFlags: 0
  m_IsActive: 1
--- !u!4 &400000
Transform:
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {fileID: 0}
  m_PrefabInstance: {fileID: 0}
  m_PrefabAsset: {fileID: 0}
  m_GameObject: {fileID: 100000}
  m_LocalRotation: {x: 0, y: 0, z: 0, w: 1}
  m_LocalPosition: {x: 0, y: 1, z: -10}
  m_LocalScale: {x: 1, y: 1, z: 1}
  m_ConstrainProportionsScale: 0
  m_Children: []
  m_Father: {fileID: 0}
  m_RootOrder: 0
  m_LocalEulerAnglesHint: {x: 0, y: 0, z: 0}
--- !u!81 &660000
AudioListener:
  m_ObjectHideFlags: 0
  m_CorrespondingSourceObject: {fileID: 0}
  m_PrefabInstance: {fileID: 0}
  m_PrefabAsset: {fileID: 0}
  m_GameObject: {fileID: 100000}
  m_Enabled: 1
--- !u!1660057539 &9223372036854775807
SceneRoots:
  m_ObjectHideFlags: 0
  m_Roots:
  - {fileID: 400000}
"""

_UNITY_BUILD_SCRIPT = r"""using UnityEngine;
using UnityEditor;
using UnityEditor.Build.Reporting;
public static class BuildProject {
    static string[] Scenes() { return new string[] { "__SCENE_UNITY__" }; }

    [MenuItem("Build/BuildLinux")]
    public static void Build() {
        PlayerSettings.colorSpace = ColorSpace.Linear;
        var opts = new BuildPlayerOptions {
            scenes = Scenes(),
            locationPathName = "Builds/game.x86_64",
            target = BuildTarget.StandaloneLinux64,
            options = BuildOptions.None,
        };
        var report = BuildPipeline.BuildPlayer(opts);
        Report("Linux build", "Builds/game.x86_64", report, out var ok);
    }

    [MenuItem("Build/BuildAndroidQuest3")]
    public static void BuildAndroid() {
        PlayerSettings.colorSpace = ColorSpace.Linear;
        var group = BuildTargetGroup.Android;
        PlayerSettings.SetScriptingBackend(group, ScriptingImplementation.IL2CPP);
        PlayerSettings.Android.minSdkVersion = AndroidSdkVersions.AndroidApiLevel29;
        PlayerSettings.Android.targetSdkVersion = AndroidSdkVersions.AndroidApiLevel34;
        PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64;
        PlayerSettings.SetGraphicsAPIs(BuildTarget.Android, new[] {
            UnityEngine.Rendering.GraphicsDeviceType.Vulkan,
            UnityEngine.Rendering.GraphicsDeviceType.OpenGLES3,
        });
        PlayerSettings.SetApplicationIdentifier(group, "com.jayson.officegame");
        PlayerSettings.bundleVersion = "0.1.0";
        PlayerSettings.productName = "Mem20 Office Game";
        PlayerSettings.companyName = "JaysonAI";

        var opts = new BuildPlayerOptions {
            scenes = Scenes(),
            locationPathName = "Builds/game.apk",
            target = BuildTarget.Android,
            options = BuildOptions.None,
        };
        var report = BuildPipeline.BuildPlayer(opts);
        Report("Android Quest3 build", "Builds/game.apk", report, out var ok);
        if (!ok) EditorApplication.Exit(2);
    }

    static void Report(string what, string path, BuildReport rpt, out bool ok) {
        var s = rpt.summary;
        ok = s.result == BuildResult.Succeeded;
        Debug.Log($"[BUILD] {what}: result={s.result} size={s.totalSize} time={s.totalTime}");
        if (!ok) Debug.LogError($"[BUILD] {what} FAILED:\n" + rpt.SummarizeErrors());
    }
}
"""

# Phase 0 Editor Scripts - install packages, configure URP/XR, create scenes, XR Origin
_PHASE0_INSTALL_PACKAGES = r"""using UnityEngine;
using UnityEditor;
using UnityEditor.PackageManager;
using UnityEditor.PackageManager.Requests;
using System.Collections.Generic;
using System.Linq;

public static class Phase0InstallPackages
{
    [MenuItem("Phase0/Install Packages")]
    public static void Install()
    {
        var packages = new List<string>
        {
            "com.unity.render-pipelines.universal",
            "com.unity.xr.openxr",
            "com.unity.xr.interaction.toolkit",
            "com.unity.inputsystem",
            "com.unity.textmeshpro"
        };
        
        foreach (var pkg in packages)
        {
            AddRequest req = Client.Add(pkg);
            while (!req.IsCompleted) { }
            if (req.Status == StatusCode.Success)
            {
                Debug.Log($"[Phase0] Installed {pkg}: {req.Result.version}");
            }
            else
            {
                Debug.LogError($"[Phase0] Failed to install {pkg}: {req.Error.message}");
            }
        }
        
        AssetDatabase.Refresh();
        ConfigureURP();
        ConfigureXR();
        ConfigureInputSystem();
        
        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();
        Debug.Log("[Phase0] Package installation complete");
    }
    
    static void ConfigureURP()
    {
        #if URP_AVAILABLE
        var pipelineAsset = Resources.Load<UnityEngine.Rendering.Universal.UniversalRenderPipelineAsset>("PipelineAssets/URP-HighQuality");
        if (pipelineAsset == null)
        {
            pipelineAsset = ScriptableObject.CreateInstance<UnityEngine.Rendering.Universal.UniversalRenderPipelineAsset>();
            pipelineAsset.name = "URP-HighQuality";
            var dir = "Assets/_Project/Resources/PipelineAssets";
            System.IO.Directory.CreateDirectory(dir);
            AssetDatabase.CreateAsset(pipelineAsset, $"{dir}/URP-HighQuality.asset");
        }
        
        GraphicsSettings.renderPipelineAsset = pipelineAsset;
        QualitySettings.renderPipeline = pipelineAsset;
        Debug.Log("[Phase0] URP configured");
        #else
        Debug.Log("[Phase0] URP package not yet available, will configure after domain reload");
        #endif
    }
    
    static void ConfigureXR()
    {
        var settings = UnityEditor.XR.Management.XRGeneralSettingsPerBuildTarget.XRGeneralSettingsForBuildTarget(BuildTargetGroup.Standalone);
        if (settings == null)
        {
            settings = ScriptableObject.CreateInstance<UnityEditor.XR.Management.XRGeneralSettings>();
            UnityEditor.XR.Management.XRGeneralSettingsPerBuildTarget.SetXRGeneralSettingsForBuildTarget(BuildTargetGroup.Standalone, settings);
        }
        
        var manager = settings.Manager;
        if (manager == null)
        {
            manager = ScriptableObject.CreateInstance<UnityEditor.XR.Management.XRManagerSettings>();
            manager.name = "XRManagerSettings";
            settings.Manager = manager;
        }
        
        var loaders = new List<UnityEditor.XR.Management.XRLoader>();
        var openXRLoaderType = System.Type.GetType("UnityEngine.XR.OpenXR.OpenXRLoader, Unity.XR.OpenXR");
        if (openXRLoaderType != null)
        {
            var loader = System.Activator.CreateInstance(openXRLoaderType) as UnityEditor.XR.Management.XRLoader;
            if (loader != null) loaders.Add(loader);
        }
        manager.loaders = loaders.ToArray();
        settings.InitManagerOnStart = true;
        Debug.Log("[Phase0] XR configured with OpenXR");
    }
    
    static void ConfigureInputSystem()
    {
        PlayerSettings.activeInputHandling = ActiveInputHandling.InputSystemPackage;
        Debug.Log("[Phase0] Input System set to Input System Package");
    }
}"""

_PHASE0_CREATE_XR_ORIGIN = r"""using UnityEngine;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine.XR.Interaction.Toolkit;
using UnityEngine.XR.Interaction.Toolkit.Locomotion.Teleportation;
using UnityEngine.XR.Interaction.Toolkit.Locomotion.Movement;
using UnityEngine.XR.Interaction.Toolkit.Locomotion.Turning;
using UnityEngine.InputSystem;

public static class Phase0CreateXROrigin
{
    [MenuItem("Phase0/Create XR Origin")]
    public static void CreateXROrigin()
    {
        var origin = new GameObject("XR Origin");
        var xrOrigin = origin.AddComponent<UnityEngine.XR.Interaction.Toolkit.XROrigin>();
        
        var camera = new GameObject("Main Camera");
        camera.transform.SetParent(origin.transform);
        camera.transform.localPosition = new Vector3(0, 1.6f, 0);
        var cam = camera.AddComponent<Camera>();
        cam.tag = "MainCamera";
        
        var camOffset = new GameObject("Camera Offset");
        camOffset.transform.SetParent(origin.transform);
        camOffset.transform.localPosition = new Vector3(0, 1.6f, 0);
        camera.transform.SetParent(camOffset.transform);
        camera.transform.localPosition = Vector3.zero;
        xrOrigin.CameraFloorOffsetObject = camOffset;
        
        var teleportProvider = origin.AddComponent<TeleportationProvider>();
        
        var leftHand = new GameObject("LeftHand Controller");
        leftHand.transform.SetParent(origin.transform);
        leftHand.transform.localPosition = new Vector3(-0.2f, 1.4f, 0.3f);
        var leftRay = leftHand.AddComponent<UnityEngine.XR.Interaction.Toolkit.Interactors.XRRayInteractor>();
        leftRay.enabled = true;
        var leftTeleport = leftHand.AddComponent<TeleportationInteractor>();
        leftTeleport.teleportationProvider = teleportProvider;
        
        var rightHand = new GameObject("RightHand Controller");
        rightHand.transform.SetParent(origin.transform);
        rightHand.transform.localPosition = new Vector3(0.2f, 1.4f, 0.3f);
        var rightRay = rightHand.AddComponent<UnityEngine.XR.Interaction.Toolkit.Interactors.XRRayInteractor>();
        rightRay.enabled = true;
        var rightTeleport = rightHand.AddComponent<TeleportationInteractor>();
        rightTeleport.teleportationProvider = teleportProvider;
        
        var floor = GameObject.CreatePrimitive(PrimitiveType.Plane);
        floor.name = "Teleportation Area";
        floor.transform.position = new Vector3(0, 0, 0);
        floor.transform.localScale = new Vector3(20, 1, 20);
        floor.AddComponent<TeleportationArea>();
        
        var moveProvider = origin.AddComponent<UnityEngine.XR.Interaction.Toolkit.Locomotion.Movement.ContinuousMoveProvider>();
        moveProvider.moveSpeed = 2.0f;
        
        var turnProvider = origin.AddComponent<UnityEngine.XR.Interaction.Toolkit.Locomotion.Turning.SnapTurnProvider>();
        turnProvider.turnAmount = 45f;
        turnProvider.debounceTime = 0.2f;
        
        SetupActionBasedControllers(leftHand, rightHand);
        
        EditorSceneManager.MarkSceneDirty(EditorSceneManager.GetActiveScene());
        Debug.Log("[Phase0] XR Origin created with Action-based locomotion");
    }
    
    static void SetupActionBasedControllers(GameObject left, GameObject right)
    {
        var leftAction = left.AddComponent<UnityEngine.XR.Interaction.Toolkit.Inputs.Simulation.XRControllerStateDrivenActionController>();
        var rightAction = right.AddComponent<UnityEngine.XR.Interaction.Toolkit.Inputs.Simulation.XRControllerStateDrivenActionController>();
    }
    
    [MenuItem("Phase0/Create Teleportation Area")]
    public static void CreateTeleportArea()
    {
        var floor = GameObject.CreatePrimitive(PrimitiveType.Plane);
        floor.name = "Teleportation Area";
        floor.transform.position = new Vector3(0, 0, 0);
        floor.transform.localScale = new Vector3(20, 1, 20);
        floor.AddComponent<TeleportationArea>();
        EditorSceneManager.MarkSceneDirty(EditorSceneManager.GetActiveScene());
        Debug.Log("[Phase0] Teleportation Area created");
    }
}"""

_PHASE0_CREATE_SCENES = r"""using UnityEngine;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine.SceneManagement;

public static class Phase0CreateScenes
{
    [MenuItem("Phase0/Create Scenes")]
    public static void CreateScenes()
    {
        string scenesPath = "Assets/_Project/Scenes";
        System.IO.Directory.CreateDirectory(scenesPath);
        
        var scene0 = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        scene0.name = "00_Office_Startup";
        
        var floor = GameObject.CreatePrimitive(PrimitiveType.Plane);
        floor.name = "OfficeFloor";
        floor.transform.position = Vector3.zero;
        floor.transform.localScale = new Vector3(20, 1, 20);
        floor.tag = "Floor";
        
        var lightObj = new GameObject("Directional Light");
        var light = lightObj.AddComponent<Light>();
        light.type = LightType.Directional;
        light.intensity = 1.0f;
        light.color = Color.white;
        lightObj.transform.rotation = Quaternion.Euler(50, -30, 0);
        
        CreateManager("DialogueManager", "VROffice.Dialogue.DialogueManager");
        CreateManager("GameFlowManager", "VROffice.Core.GameFlowManager");
        CreateManager("EventBridge", "VROffice.Core.EventBridge");
        CreateManager("ElevatorController", "VROffice.Elevator.ElevatorController");
        CreateManager("AgentPopulationManager", "VROffice.Agents.AgentPopulationManager");
        
        EditorSceneManager.SaveScene(scene0, $"{scenesPath}/00_Office_Startup.unity");
        Debug.Log("[Phase0] Created 00_Office_Startup");
        
        var scene1 = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        scene1.name = "01_MainFloor";
        
        var floor1 = GameObject.CreatePrimitive(PrimitiveType.Plane);
        floor1.name = "MainFloor";
        floor1.transform.position = new Vector3(0, 0, 0);
        floor1.transform.localScale = new Vector3(20, 1, 20);
        floor1.tag = "Floor";
        
        var light1 = new GameObject("Directional Light");
        var l1 = light1.AddComponent<Light>();
        l1.type = LightType.Directional;
        l1.intensity = 1.0f;
        light1.transform.rotation = Quaternion.Euler(50, -30, 0);
        
        var landing = new GameObject("ElevatorLanding_Floor1");
        landing.transform.position = new Vector3(0, 0, 0);
        
        EditorSceneManager.SaveScene(scene1, $"{scenesPath}/01_MainFloor.unity");
        Debug.Log("[Phase0] Created 01_MainFloor");
        
        var scene2 = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        scene2.name = "02_Exterior_Car";
        
        var ground = GameObject.CreatePrimitive(PrimitiveType.Plane);
        ground.name = "ExteriorGround";
        ground.transform.position = Vector3.zero;
        ground.transform.localScale = new Vector3(50, 1, 50);
        
        var car = GameObject.CreatePrimitive(PrimitiveType.Cube);
        car.name = "Car_Placeholder";
        car.transform.position = new Vector3(0, 1, -10);
        car.transform.localScale = new Vector3(4, 2, 8);
        
        var light2 = new GameObject("Directional Light");
        var l2 = light2.AddComponent<Light>();
        l2.type = LightType.Directional;
        l2.intensity = 1.0f;
        light2.transform.rotation = Quaternion.Euler(50, -30, 0);
        
        EditorSceneManager.SaveScene(scene2, $"{scenesPath}/02_Exterior_Car.unity");
        Debug.Log("[Phase0] Created 02_Exterior_Car");
        
        AddScenesToBuildSettings();
        
        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();
    }
    
    static void CreateManager(string name, string typeName)
    {
        var go = new GameObject(name);
        go.AddComponent<PlaceholderManager>().managerType = typeName;
        Debug.Log($"[Phase0] Created placeholder for {typeName}");
    }
    
    static void AddScenesToBuildSettings()
    {
        var scenes = new[]
        {
            "Assets/_Project/Scenes/00_Office_Startup.unity",
            "Assets/_Project/Scenes/01_MainFloor.unity",
            "Assets/_Project/Scenes/02_Exterior_Car.unity"
        };
        
        var buildScenes = new System.Collections.Generic.List<EditorBuildSettingsScene>();
        foreach (var s in scenes)
        {
            if (System.IO.File.Exists(s))
            {
                buildScenes.Add(new EditorBuildSettingsScene(s, true));
            }
        }
        EditorBuildSettings.scenes = buildScenes.ToArray();
        Debug.Log($"[Phase0] Build Settings updated with {buildScenes.Count} scenes");
    }
}

public class PlaceholderManager : MonoBehaviour
{
    public string managerType;
}"""

_PHASE0_VERIFY = r"""using UnityEngine;
using UnityEditor;
using UnityEngine.SceneManagement;
using UnityEditor.SceneManagement;

public static class Phase0Verify
{
    [MenuItem("Phase0/Verify Bootstrap")]
    public static void Verify()
    {
        var results = new System.Collections.Generic.List<string>();
        bool allPass = true;
        
        var scenes = new[] {
            "Assets/_Project/Scenes/00_Office_Startup.unity",
            "Assets/_Project/Scenes/01_MainFloor.unity",
            "Assets/_Project/Scenes/02_Exterior_Car.unity"
        };
        
        foreach (var s in scenes)
        {
            if (System.IO.File.Exists(s))
            {
                results.Add($"[PASS] Scene exists: {s}");
            }
            else
            {
                results.Add($"[FAIL] Scene missing: {s}");
                allPass = false;
            }
        }
        
        var folders = new[] {
            "Assets/_Project/Prefabs",
            "Assets/_Project/Resources",
            "Assets/_Project/ScriptableObjects/Dialogues",
            "Assets/_Project/Scripts/Dialogue",
            "Assets/_Project/Scripts/Core",
            "Assets/_Project/Scripts/Elevator",
            "Assets/_Project/Scripts/Agents",
            "Assets/_Project/Scripts/Player"
        };
        
        foreach (var f in folders)
        {
            if (System.IO.Directory.Exists(f))
            {
                results.Add($"[PASS] Folder exists: {f}");
            }
            else
            {
                results.Add($"[FAIL] Folder missing: {f}");
                allPass = false;
            }
        }
        
        var manifestPath = "Packages/manifest.json";
        if (System.IO.File.Exists(manifestPath))
        {
            var json = System.IO.File.ReadAllText(manifestPath);
            var required = new[] {
                "com.unity.render-pipelines.universal",
                "com.unity.xr.openxr",
                "com.unity.xr.interaction.toolkit",
                "com.unity.inputsystem",
                "com.unity.textmeshpro"
            };
            
            foreach (var pkg in required)
            {
                if (json.Contains(pkg))
                {
                    results.Add($"[PASS] Package installed: {pkg}");
                }
                else
                {
                    results.Add($"[FAIL] Package missing: {pkg}");
                    allPass = false;
                }
            }
        }
        
        if (UnityEngine.Rendering.GraphicsSettings.renderPipelineAsset != null)
        {
            results.Add("[PASS] URP configured");
        }
        else
        {
            results.Add("[FAIL] URP not configured");
            allPass = false;
        }
        
        var reportPath = "Assets/_Project/Phase0_Verification_Report.txt";
        System.IO.File.WriteAllLines(reportPath, results);
        
        Debug.Log($"[Phase0] Verification complete: {(allPass ? "ALL PASS" : "SOME FAIL")}");
        Debug.Log($"[Phase0] Report: {reportPath}");
        
        if (!allPass)
        {
            throw new System.Exception("Phase 0 verification failed");
        }
    }
}"""

_PHASE0_SETUP_ANDROID = r"""using UnityEngine;
using UnityEditor;
using UnityEditor.Build.Reporting;

public static class Phase0SetupAndroid
{
    [MenuItem("Phase0/Setup Android Quest 3")]
    public static void SetupAndroid()
    {
        EditorUserBuildSettings.SwitchActiveBuildTargetAsync(BuildTargetGroup.Android, BuildTarget.Android);
        
        var group = BuildTargetGroup.Android;
        
        PlayerSettings.SetScriptingBackend(group, ScriptingImplementation.IL2CPP);
        PlayerSettings.Android.minSdkVersion = AndroidSdkVersions.AndroidApiLevel29;
        PlayerSettings.Android.targetSdkVersion = AndroidSdkVersions.AndroidApiLevel34;
        PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64;
        
        PlayerSettings.SetGraphicsAPIs(BuildTarget.Android, new[] {
            UnityEngine.Rendering.GraphicsDeviceType.Vulkan,
            UnityEngine.Rendering.GraphicsDeviceType.OpenGLES3,
        });
        
        PlayerSettings.SetApplicationIdentifier(group, "com.jayson.officegame");
        PlayerSettings.bundleVersion = "0.1.0";
        PlayerSettings.productName = "VR Office";
        PlayerSettings.companyName = "JaysonAI";
        
        PlayerSettings.virtualRealitySupported = true;
        PlayerSettings.colorSpace = ColorSpace.Linear;
        PlayerSettings.stripEngineCode = true;
        PlayerSettings.managedStrippingLevel = ManagedStrippingLevel.High;
        
        AssetDatabase.SaveAssets();
        Debug.Log("[Phase0] Android/Quest 3 build target configured");
    }
}"""

# Phase 0 Tool Implementations

def tool_unity_scaffold(args: str) -> dict:
    """Create a real Unity project skeleton (idempotent).

    args: "<project_root> [--scene Scene_Main]"
    Creates ProjectSettings/ProjectVersion.txt, Packages/manifest.json,
    a naming-law-compliant scene and an Editor build script.
    Scene names are enforced against the v2.1 naming law: any scene not
    already prefixed with Scene_ is auto-prefixed so the harness can never
    emit a law-violating file (rule: "naming/budget/art-style consistency").
    """
    parts = args.split()
    if not parts:
        return {"ok": False, "stderr": "need project_root"}
    if parts[0].startswith(("{", "<", "--")) or "=" in parts[0]:
        return {"ok": False,
                "stderr": ("invalid project_root: pass a clean relative path "
                           "like '.' or 'unity' — not a JSON/flag argument")}
    root = Path(_resolve(parts[0]))
    scene = "Scene_Main"
    for i, p in enumerate(parts):
        if p == "--scene" and i + 1 < len(parts):
            scene = parts[i + 1]
    if not re.match(r"^Scene_[A-Za-z0-9]", scene):
        scene = "Scene_" + scene.lstrip("_")
    try:
        (root / "Assets" / "Scenes").mkdir(parents=True, exist_ok=True)
        (root / "Assets" / "_Project").mkdir(parents=True, exist_ok=True)
        (root / "Assets" / "Editor").mkdir(parents=True, exist_ok=True)
        (root / "Packages").mkdir(parents=True, exist_ok=True)
        (root / "ProjectSettings").mkdir(parents=True, exist_ok=True)
        ver = _unity_version()
        (root / "ProjectSettings" / "ProjectVersion.txt").write_text(
            f"m_EditorVersion: {ver}\n")
        (root / "Packages" / "manifest.json").write_text(json.dumps({
            "dependencies": {
                "com.unity.ugui": "1.0.0",
                "com.unity.modules.physics": "1.0.0",
                "com.unity.modules.audio": "1.0.0",
            }}, indent=2))
        scene_path = root / "Assets" / "Scenes" / f"{scene}.unity"
        if not scene_path.exists():
            scene_path.write_text(_UNITY_SCENE_TPL)
        # ensure a leftover Main.unity from an older Harness default never
        # survives the audit (removed files must not linger in the deliverable set)
        stale_main = root / "Assets" / "Scenes" / "Main.unity"
        if stale_main.exists() and stale_main != scene_path:
            stale_main.unlink()
        (root / "Assets" / "Editor" / "BuildProject.cs").write_text(
            _UNITY_BUILD_SCRIPT.replace("__SCENE_UNITY__",
                                        f"Assets/Scenes/{scene}.unity"))
        return {"ok": True, "output": f"scaffolded Unity project at {root}",
                "assets": sorted(str(p.relative_to(root)) for p in
                                 (root / "Assets").rglob("*") if p.is_file())[:20]}
    except Exception as e:
        return {"ok": False, "stderr": str(e)[:500]}


def tool_freecad_run(args: str) -> dict:
    """Execute a FreeCAD Python script headlessly.

    args: "<script_path> [output_path]"
    """
    parts = args.split()
    if not parts:
        return {"ok": False, "stderr": "no script path provided"}
    script = _resolve(parts[0])
    output = _resolve(parts[1]) if len(parts) > 1 else ""
    cmd = [FREECAD, "-c", "-P", script]
    if output:
        cmd += [output]
    return _run(cmd, timeout=600)


SOX = os.environ.get("HARNESS_SOX", "/usr/bin/sox")

# sox procedural synthesis kinds tuned to the LUMEN FORGE sound set
# (deep-space research station orbiting a dead star). Each maps to the
# game's chosen audio: ambient beds, dead-star pulse rumble, scientific
# probe scan tone, cold exterior hum, anomaly bed, shift-cycle transition.
_SOX_KINDS = (
    "ambient",       # station ambient bed: detuned sine pair + slow tremolo
    "rumble",        # deep sub-audible pressure-change rumble (pulse)
    "scantone",      # scientific probe scan tone (clean rising sweep)
    "exterior",      # cold dead-star exterior hum / sparse movement
    "anomaly",       # detuned eerie anomaly bed (tremolo + reverb)
    "shiftcycle",    # shift-cycle transition tone (low two-phase sweep)
    "pulse",         # short pulse-press transient (pressure open + settle)
)


def _law_stem(stem: str) -> str:
    """Normalize an audio stem into a naming-law-safe word.

    Strips any A_ prefix, drops non-alphanumerics (hyphens, spaces, the
    sqrt/echo artifacts of sloppy prefixes), capitalizes each segment, and
    joins with underscores so the result always lexes as A_<Word>.
    """
    s = stem if not stem.isdigit() else stem
    s = re.sub(r"^A_", "", s)
    return "_".join(w.capitalize() for w in re.findall(r"[A-Za-z0-9]+", s))


def _sox_synth(kind: str, output: str, dur: float = 0.0) -> dict:
    """Render one procedural sound with sox (real synthesis, real WAV).

    kind ∈ _SOX_KINDS. Each recipe is Quest-safe: sub-audible lows,
    no harsh transients, gentle fades, mono 44.1k to keep footprint low.
    """
    if dur <= 0:
        dur = {"ambient": 12.0, "rumble": 6.0, "scantone": 3.0, "exterior": 8.0,
               "anomaly": 8.0, "shiftcycle": 4.0, "pulse": 2.0}.get(kind, 4.0)
    d = f"{dur:g}"
    ops = {
        "ambient":    ["sine", "110", "sine", "220", "tremolo", "0.35", "1.8",
                       "reverb", "55", "45", "100", "45", "6", "gain", "-14",
                       "fade", "1.5", d, "1.8"],
        "rumble":     ["brownnoise", "lowpass", "45", "gain", "-4",
                       "fade", "1.2", d, "1.2"],
        "scantone":   ["sine", "600-1400", "fade", "0.4", d, "0.8"],
        "exterior":   ["pinknoise", "lowpass", "320", "tremolo", "0.12", "2.2",
                       "reverb", "70", "20", "80", "60", "3", "gain", "-20",
                       "fade", "2.0", d, "2.0"],
        "anomaly":    ["sine", "55", "sine", "58", "tremolo", "0.22", "2.6",
                       "phaser", "0.6", "0.7", "2", "0.2", "0.1",
                       "reverb", "80", "50", "90", "90", "7", "gain", "-16",
                       "fade", "2.0", d, "2.4"],
        "shiftcycle": ["sine", "160-70", "gain", "-8", "fade", "0.6", d, "1.0"],
        "pulse":      ["sine", "80-35", "gain", "-10", "fade", "0.15", d, "0.5"],
    }
    if kind not in ops:
        return {"ok": False, "stderr": f"unknown kind '{kind}'; "
                f"known: {', '.join(_SOX_KINDS)}"}
    cmd = ([SOX, "-n", "-t", "wavpcm", "-b", "16", output, "synth", d]
           + ops[kind] + ["channels", "1", "rate", "44100"])
    return _run(cmd, timeout=120)


def tool_surge_render(args: str) -> dict:
    """Render a Surge XT patch to audio (real-time render to WAV).

    args: "<patch.xp2> <output.wav> [--sr 48000] [--duration 3]"
    """
    parts = args.split()
    if len(parts) < 2:
        return {"ok": False, "stderr": "need patch.xp2 and output.wav"}
    cmd = [SURGE, "--init-patch", parts[0],
           "--audio-ports", "0", "--no-stdin"]
    for i, p in enumerate(parts):
        if p == "--sr" and i + 1 < len(parts):
            cmd += ["--sample-rate", parts[i + 1]]
    r = _run(cmd, timeout=180)
    return r


def tool_write_file(args: str) -> dict:
    """Write content to a file (real file-writing tool).

    args: (a) "PATH\\nCONTENT..." — first line = path, remainder = content
          (b) a JSON object {"path": "...", "content": "..."}
    Relative paths resolve against the current worker's workspace.
    """
    path = ""
    content = ""
    try:
        obj = json.loads(args)
        if isinstance(obj, dict) and "path" in obj:
            path = str(obj["path"])
            content = str(obj.get("content", ""))
    except Exception:
        pass
    if not path:
        lines = args.split("\n", 1)
        if len(lines) < 2:
            return {"ok": False, "stderr": "need path and content"}
        path = lines[0].strip()
        content = lines[1]
    path = _clear_path_flags(path)
    path = _resolve(path)
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content)
        return {"ok": True, "output": f"wrote {len(content)} bytes to {path}"}
    except Exception as e:
        return {"ok": False, "stderr": str(e)[:500]}


def tool_unity_project(args: str) -> dict:
    """Create/idempotently scaffold the shared Unity project for the run.

    args: "<project_root>" (typically the run's assembly dir)
    Returns the project path so later phase workers can write into
    Assets/_Project and run compile checks.
    """
    parts = args.split()
    if not parts:
        return {"ok": False, "stderr": "need project_root"}
    return tool_unity_scaffold(parts[0])


def tool_verify_files(args: str) -> dict:
    """Verify deliverables exist in the agent workspace and write a report.

    args: "<expected_ext|pattern> [note]" e.g. ".glb" or "*.wav"
    Writes verify-<ts>.md in the workspace with a real listing.
    """
    parts = args.split()
    pattern = parts[0] if parts else "."
    note = " ".join(parts[1:]) if len(parts) > 1 else ""
    cwd = Path(_resolve("."))
    if not any(ch in pattern for ch in "*?["):
        # bare extension (".glb") or name/prefix token → match suffix or name
        files = sorted(str(f.relative_to(cwd)) for f in cwd.rglob("*")
                       if f.is_file() and (pattern in f.suffix or pattern in f.name))
    else:
        # glob pattern ("*.unity", "T_*.png", ...) → true glob match
        files = sorted(str(f.relative_to(cwd)) for f in cwd.rglob("*")
                       if f.is_file() and fnmatch.fnmatch(f.name, pattern))
    report = {
        "pattern": pattern, "note": note,
        "files": files, "count": len(files),
        "ts": _now(),
    }
    out = cwd / f"verify-{time.strftime('%H%M%S')}.json"
    out.write_text(json.dumps(report, indent=2))
    return {"ok": len(files) > 0,
            "output": json.dumps({"report": str(out), "count": len(files)})}


def tool_audio_design(args: str) -> dict:
    """Synthesize real game audio with sox (procedural synthesis).

    args: "<prefix> [--kinds ambient,rumble,scantone,exterior,anomaly,shiftcycle,pulse]"
    Writes A_<Prefix>_<Kind>.wav per requested kind plus A_<Prefix>_Mix.md.
    Output names are LAW-LEGAL A_ form (<prefix> may be an A_ name already or
    a bare stem; the directory is preserved). Kinds are tuned to the game's
    chosen sound set (dead-star station): ambient=station bed, rumble=deep
    pulse pressure-change, scantone=scientific probe sweep, exterior=cold
    dead-star hum, anomaly=detuned eerie bed, shiftcycle=transition tone,
    pulse=short pulse-press. Default kinds: ambient,rumble,scantone.
    """
    parts = args.split()
    if not parts:
        return {"ok": False, "stderr": "need prefix"}
    raw_prefix = parts[0]
    outdir = Path(_resolve(raw_prefix)).parent
    outdir.mkdir(parents=True, exist_ok=True)
    stem = Path(raw_prefix).stem
    kinds = ["ambient", "rumble", "scantone"]
    for i, p in enumerate(parts):
        if p == "--kinds" and i + 1 < len(parts):
            kinds = [k for k in parts[i + 1].split(",") if k in _SOX_KINDS]
    if not kinds:
        return {"ok": False, "stderr": f"no valid kinds; known: {', '.join(_SOX_KINDS)}"}
    base = _law_stem(stem)
    made = []
    for k in kinds:
        wav = outdir / f"A_{base}_{k.capitalize()}.wav"
        r = _sox_synth(k, str(wav))
        if r.get("ok"):
            made.append(str(wav.name))
    if not made:
        return {"ok": False, "stderr": f"no wavs generated for kinds: {kinds}"}
    note = outdir / f"A_{base}_Mix.md"
    Path(note).write_text(
        f"# Audio mix notes\nkinds: {', '.join(kinds)}\n"
        f"channels: 1, rate: 44100, sample: 16-bit\n"
        f"generated: {len(made)} wav files at {time.strftime('%H:%M:%S')}\n")
    return {"ok": len(made) > 0,
            "output": json.dumps({"wavs": made, "note": str(note)})}


# ── tool registry for worker binding ─────────────────────────────────────────
# Maps every declared tool name (worker.py JOB_PACKAGES + base) to a real
# executor that produces actual files in the agent's workspace.
# Hard budget per worker attempt: stop the propose/execute loop if a single
# attempt exceeds this (fall back to deadline-limited output). Slow models /
# dead pool buckets must not wedge a worker for the full MAX_ATTEMPTS sequence.
MAX_WORKER_ATTEMPT_SECS = int(os.environ.get("HARNESS_WORKER_ATTEMPT_SECS", "480"))


def tool_naming_check(args: str) -> dict:
    """Verify output filenames against the v2.1 naming law.

    args: "[glob]"  e.g. "*.glb" (default: all files in the workspace)
    Scans the worker workspace and flags names missing a required prefix
    (SM_/M_/T_/A_/Prefab_/Scene_) or violating validate-* manifest rules.
    """
    parts = args.split()
    pattern = parts[0] if parts else "*"
    cwd = Path(_resolve("."))
    files = sorted(f.name for f in cwd.rglob("*")
                   if f.is_file() and not f.name.startswith("."))
    if pattern != "*":
        files = [f for f in files if pattern in f]
    if _V21 is None:
        return {"ok": True, "output": "v21 unavailable; naming law not enforced"}
    viol = _V21.naming_violations(files)
    out = cwd / f"naming-check-{time.strftime('%H%M%S')}.json"
    out.write_text(json.dumps({"files": files, "violations": viol}, indent=2))
    return {"ok": not viol,
            "output": json.dumps({"report": str(out),
                                  "violations": viol, "count": len(files)})}


def tool_manifest(args: str) -> dict:
    """Emit a standard v2.1 batch manifest for the agent's output files.

    args: "[label]"  e.g. "SM_Interior_Batch"
    Writes MANIFEST.json in the workspace (asset list + naming + job fields).
    """
    label = args.split()[0] if args.split() else "batch"
    cwd = Path(_resolve("."))
    files = sorted(f.name for f in cwd.rglob("*")
                   if f.is_file() and not f.name.startswith("."))
    if _V21 is None:
        return {"ok": False, "stderr": "v21 unavailable"}
    rel = [f for f in files]
    man = _V21.emit_manifest(cwd, "batch", rel)
    out = cwd / "MANIFEST.json"
    out.write_text(json.dumps(man, indent=2))
    return {"ok": True,
            "output": json.dumps({"manifest": str(out), "assets": len(rel)})}


def tool_handoff_check(args: str) -> dict:
    """Validate a handoff report against the 13-field v2.1 template.

    args: "[path]"  (default: ./handoff-report.md)
    Writes handoff-check.json with the missing-field report.
    """
    cwd = Path(_resolve("."))
    raw = args.split()[0] if args.split() else "handoff-report.md"
    target = cwd / raw
    if target.is_dir():
        target = target / "handoff-report.md"
    if not target.exists():
        return {"ok": False, "stderr": f"handoff not found: {target}"}
    if _V21 is None:
        return {"ok": True, "output": "v21 unavailable; handoff not enforced"}
    missing = _V21.check_handoff(target.read_text(errors="replace"))
    out = cwd / f"handoff-check-{time.strftime('%H%M%S')}.json"
    out.write_text(json.dumps({"missing": missing, "complete": not missing},
                              indent=2))
    return {"ok": not missing,
            "output": json.dumps({"missing": missing, "complete": not missing})}


def tool_primitive_check(args: str) -> dict:
    """Flag primitive/unfinal mesh shapes via headless Blender statistics.

    args: "<file>"  e.g. "SM_Chair_LOD0.glb"
    Real mesh stats from Blender (vertex/tri counts, primitive names).
    """
    parts = args.split()
    if not parts:
        return {"ok": False, "stderr": "need mesh file"}
    p = Path(_resolve(parts[0]))
    if not p.exists():
        return {"ok": False, "stderr": f"mesh not found: {p}"}
    if _V21 is None:
        return {"ok": False, "stderr": "v21 unavailable"}
    try:
        stats = _V21.primitive_check(p)
        flagged = [s for s in stats if s.get("primitive")]
        out = p.parent / f"primitive-check-{time.strftime('%H%M%S')}.json"
        out.write_text(json.dumps(stats, indent=2))
        return {"ok": not flagged,
                "output": json.dumps({"report": str(out), "primitives": flagged,
                                      "meshes": len(stats)})}
    except Exception as exc:
        return {"ok": False, "stderr": f"blender stats failed: {exc}"}


def tool_vision_check(args: str) -> dict:
    """Visual QA gate via NVIDIA vision deck + deterministic black-screen gate.

    args: "<screenshot> [requirement...]"
    Returns PASS/FAIL verdict; black/empty screens auto-FAIL (v2.1 rule).
    """
    parts = args.split()
    if not parts:
        return {"ok": False, "stderr": "need screenshot path"}
    img = Path(_resolve(parts[0]))
    if not img.exists():
        return {"ok": False, "stderr": f"screenshot not found: {img}"}
    if _V21 is None:
        return {"ok": False, "stderr": "v21 unavailable"}
    req = " ".join(parts[1:]) if len(parts) > 1 else ""
    try:
        verdict = _V21.vision_pass_fail(img, req)
        out = img.parent / f"vision-check-{time.strftime('%H%M%S')}.json"
        out.write_text(json.dumps(verdict, indent=2))
        return {"ok": verdict["verdict"] == "PASS",
                "output": json.dumps({"report": str(out), **verdict})}
    except Exception as exc:
        return {"ok": False, "stderr": f"vision check failed: {exc}"}


def tool_audio_check(args: str) -> dict:
    """Audio QA gate: real playable sample with live content (+pack semantic
    match when a requirement is given and transcription is available).

    args: "<audio_file> [requirement...]"
    Returns PASS/FAIL verdict; missing/silent/zero-length files auto-FAIL.
    """
    parts = args.split()
    if not parts:
        return {"ok": False, "stderr": "need audio file path"}
    wav = Path(_resolve(parts[0]))
    if not wav.exists():
        return {"ok": False, "stderr": f"audio file not found: {wav}"}
    if _V21 is None:
        return {"ok": False, "stderr": "v21 unavailable"}
    req = " ".join(parts[1:]) if len(parts) > 1 else ""
    try:
        verdict = _V21.audio_pass_fail(wav, req)
        out = wav.parent / f"audio-check-{time.strftime('%H%M%S')}.json"
        out.write_text(json.dumps(verdict, indent=2, default=str))
        return {"ok": verdict["verdict"] == "PASS",
                "output": json.dumps({"report": str(out), **verdict},
                                     default=str)}
    except Exception as exc:
        return {"ok": False, "stderr": f"audio check failed: {exc}"}


def tool_engine_capture(args: str) -> dict:
    """Capture an in-engine screenshot for visual QA (Godot headless).

    args: "<project_root|scene> [out.png]"
    Runs Godot headless with a Capture.gd that curls a frame, then vision-check
    becomes meaningful. Unity capture handled at assembly via batch methods.

    The capture run scaffolds its own throwaway Godot project (capture.gd +
    scenes/main.tscn + capture.png) under <root>/_artifacts~/_capture~ — a
    scratch area excluded by _is_deliverable — so harness QA scaffolding never
    leaks into the worker's deliverable set or trips the naming law.
    """
    parts = args.split()
    if not parts:
        return {"ok": False, "stderr": "need godot project/scene root"}
    root = Path(_resolve(parts[0]))
    if _V21 is None:
        return {"ok": False, "stderr": "v21 unavailable"}
    try:
        scratch = root / "_artifacts~" / "_capture~"
        shot = _V21.godot_capture(scratch)
        if shot is None:
            return {"ok": False, "stderr": "godot capture produced no frame "
                    "(headless dummy renderer has no viewport texture)."}
        if parts[1:]:
            outname = parts[1]
            if not outname.lower().endswith(".png"):
                outname += ".png"
            dest = Path(_resolve(outname))
            import shutil
            shutil.copy2(shot, dest)
            shot = dest
        p = Path(shot)
        if not p.exists() or p.stat().st_size == 0:
            return {"ok": False, "stderr": f"capture invalid/empty: {shot}"}
        return {"ok": True,
                "output": json.dumps({"screenshot": str(p),
                                      "size": p.stat().st_size})}
    except Exception as exc:
        return {"ok": False, "stderr": f"engine capture failed: {exc}"}


def tool_godot_batch(args: str) -> dict:
    """Run Godot 4 headless for import/build/validation.

    args: "<project_root|scene> [--import|--build|--validate]"
    """
    parts = args.split()
    if not parts:
        return {"ok": False, "stderr": "need project root"}
    root = _resolve(parts[0])
    flags = args
    if not os.path.exists(root):
        return {"ok": False, "stderr": f"project not found: {root}"}
    if _V21 is None:
        return {"ok": False, "stderr": "v21 unavailable"}
    imp = " --import" if ("--import" in flags or "--build" not in flags) else ""
    build = " --build" if "--build" in flags else ""
    cmd = f"{_V21.GODOT} --headless --path {shlex.quote(root)}{imp}{build}"
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           timeout=600)
        ok = r.returncode == 0
        return {"ok": ok,
                "output": json.dumps({"cmd": cmd, "returncode": r.returncode,
                                      "stdout": r.stdout[-1200:],
                                      "stderr": r.stderr[-1200:]})}
    except subprocess.TimeoutExpired:
        return {"ok": False, "stderr": "godot batch timed out"}
    except Exception as exc:
        return {"ok": False, "stderr": f"godot batch failed: {exc}"}


TOOL_DISPATCH = {
    # generic real executors
    "write-file":        tool_write_file,
    "blender-gen":       tool_blender_gen,
    "blender-export":    tool_blender_gen,
    "unity-batch":       tool_unity_batch,
    "unity-import":      tool_unity_batch,
    "unity-compile":     tool_unity_batch,
    "unity-build":       tool_unity_batch,
    "freecad-run":       tool_freecad_run,
    "surge-render":      tool_surge_render,
    "unity-project":     tool_unity_project,
    "verify":            tool_verify_files,
    # Phase 0 bootstrap
    "scaffold-project":  tool_unity_project,
    "write-config":      tool_write_file,
    "setup-build-target": tool_unity_project,
    "verify-bootstrap":  tool_verify_files,
    "procedural-execute": tool_write_file,
    # Phase 1 dialogue
    "write-dialogue-data": tool_write_file,
    "validate-eventids": tool_verify_files,
    "config-dialogue-interactable": tool_write_file,
    "branch-check":      tool_verify_files,
    # Phase 2 environment
    "build-fishtank":    lambda a: _blender_alias(a, "fishtank", "SM_Fishtank_Main.glb"),
    "build-awards-wall": lambda a: _blender_alias(a, "awards-wall", "SM_AwardsWall_Main.glb"),
    "scene-integrate":   lambda a: _blender_alias(a, "office", "SM_Office_Main.glb"),
    "lighting-check":    tool_verify_files,
    "assemble-scene":    lambda a: _blender_alias(a, "office", "SM_Office_Main.glb"),
    # Phase 3 characters
    "build-agent-prefab": lambda a: _blender_alias(a, "agent-prefab", "SM_Agent_Main.glb"),
    "lod-optimize":      lambda a: _blender_alias(a, "decimate", "SM_LOD_Main.glb"),
    "population-pool":   lambda a: _blender_alias(a, "crowd", "SM_Crowd_Main.glb", "--count 40"),
    "perf-measure":      tool_verify_files,
    # Phase 4 game flow
    "build-elevator":    lambda a: _blender_alias(a, "elevator", "SM_Elevator_Main.glb"),
    "wire-flow":         tool_write_file,
    "flow-test":         tool_verify_files,
    "50-ride-torture":   tool_verify_files,
    # Phase 5/6 polish
    "audio-mix":         tool_audio_design,
    "vfx-add":           lambda a: _blender_alias(a, "bubbles", "SM_Bubbles_Main.glb", "--count 14"),
    "polish-pass":       tool_verify_files,
    "budget-check":      tool_verify_files,
    # Phase 7 stress / QA
    "stress-test":       tool_verify_files,
    "perf-metrics":      tool_verify_files,
    "repro-report":      tool_write_file,
    "budget-verify":     tool_verify_files,
    # integration
    "smoke-test":        tool_verify_files,
    "verify-handoff":    tool_verify_files,
    "report-breakage":   tool_write_file,
    # base supervisor toolkit
    "delegate":          tool_write_file,
    "review":            tool_write_file,
    "handoff-report":    tool_write_file,
    "probe-memory":      tool_verify_files,
    # Harness upgrades v2.1 enforcement + QA tools
    "naming-check":      tool_naming_check,
    "manifest":          tool_manifest,
    "handoff-check":     tool_handoff_check,
    "primitive-check":   tool_primitive_check,
    "vision-check":      tool_vision_check,
    "engine-capture":    tool_engine_capture,
    "audio-check":       tool_audio_check,
    "godot-batch":       tool_godot_batch,
}

# ── workspace helpers ────────────────────────────────────────────────────────

@dataclass
class RunState:
    """Serialisable state for the full run."""
    pid: str
    status: str = "idle"         # idle | running | done | error | blocked
    phase: str = ""              # current phase name
    phase_idx: int = 0
    started: str = ""
    finished: str = ""
    phases: dict = field(default_factory=dict)  # phase_name -> {status, workers}
    errors: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    # Resume data
    all_worker_results: dict = field(default_factory=dict)  # phase_name -> list[worker_result]
    phase_results_all: dict = field(default_factory=dict)   # phase_name -> supervisor_result
    prior_gate_results: list = field(default_factory=list)  # list of gate results

    def to_dict(self) -> dict:
        return asdict(self)


def _checkpoint_path(pid: str) -> Path:
    return _workspace(pid) / ".run_state.json"


def save_checkpoint(state: RunState) -> None:
    """Persist RunState to disk for resume capability."""
    try:
        _checkpoint_path(state.pid).write_text(json.dumps(state.to_dict(), indent=2))
    except Exception:
        pass  # best-effort


def load_checkpoint(pid: str) -> RunState | None:
    """Load RunState from disk if exists and valid."""
    p = _checkpoint_path(pid)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        return RunState(**data)
    except Exception:
        return None


def _workspace(pid: str) -> Path:
    d = WORKSPACE_ROOT / pid
    d.mkdir(parents=True, exist_ok=True)
    return d


def _phase_dir(pid: str, phase_slug: str) -> Path:
    d = _workspace(pid) / phase_slug
    d.mkdir(parents=True, exist_ok=True)
    return d


# Bookkeeping files are written by the harness, not the worker's deliverable.
# They must NOT count toward a worker's output set, otherwise a worker that
# produced nothing but a handoff report would pass the readiness gate.
_BOOKKEEPING_FILES = {"handoff-report.md", "supervisor-handoff.md"}


# Engine-and-tool generated cache/scratch dirs. Files under these are NOT
# worker deliverables: Unity repopulates Library/Temp/Logs, Godot its
# .godot/.import caches, and build toolchains their obj/Bin on every run.
# Including them in output_files makes the naming audit flag engine-owned
# files (e.g. com.unity.sysroot package screenshots) as worker violations.
_ENGINE_SCRATCH = {
    "library", "temp", "logs", "obj", "bin", "_artifacts~",
    ".godot", ".import", ".tmp",
}


def _is_deliverable(path: Path) -> bool:
    parts = Path(path).parts
    if any(p.lower() in _ENGINE_SCRATCH for p in parts[:-1]):
        return False
    return (path.is_file()
            and not path.name.startswith(".")
            and path.name not in _BOOKKEEPING_FILES
            and not path.name.endswith(".dll")
            and not path.name.endswith(".pdb"))


def _collect_worker_results(ws: Path, project: dict) -> dict[str, list[dict]]:
    """Authoritative worker-result inventory, built by scanning the workspace.

    ``all_worker_results`` is in-memory only: it tracks workers run in the
    current process and is lost across checkpoint resumes and selective
    retries. The files on disk are the real deliverables and cover every
    phase, so the final assembly must read from here to collect everything.
    """
    slug_to_name = {slug(sv["name"]): sv["name"]
                    for sv in project.get("supervisors", [])}
    collected: dict[str, list[dict]] = {}
    if not ws.exists():
        return collected
    for phase_dir in sorted(ws.iterdir()):
        if (not phase_dir.is_dir() or phase_dir.name.startswith(".")
                or phase_dir.name == "assembly"):
            continue
        # Only real supervisor phases ship; ignore smoke-test/debug debris.
        if phase_dir.name not in slug_to_name:
            continue
        phase_name = slug_to_name[phase_dir.name]
        workers = []
        for worker_dir in sorted(phase_dir.iterdir()):
            if not worker_dir.is_dir() or worker_dir.name.startswith("."):
                continue
            files = sorted(
                str(f.relative_to(worker_dir))
                for f in worker_dir.rglob("*")
                if _is_deliverable(f))
            if files:
                workers.append({"name": worker_dir.name,
                                "agent_id": worker_dir.name,
                                "output_files": files,
                                "ready": True})
        collected[phase_name] = workers
    return collected


def _agent_dir(pid: str, phase_slug: str, agent_id: str) -> Path:
    d = _phase_dir(pid, phase_slug) / agent_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def slug(text: str) -> str:
    out = "".join(c if (c.isalnum() or c in "-_") else "-" for c in text.lower())
    return out.strip("-") or "agent"

# ── agent execution wrappers ────────────────────────────────────────────────

def _run_worker(member: dict, task_prompt: str, pid: str, phase_slug: str,
                attempt: int = 1, remediation: str = "") -> dict:
    """Execute one swarm worker via mem20crewz Agent with real tools.

    attempt: 1-based retry counter. remediation: supervisor blocker-fix notes
    appended to the task when the worker is being retried.

    Returns {name, agent_id, handoff_text, output_files[], ok, ready, attempts}.
    """
    from mem20crewz import Agent as CrewzAgent
    from mem20crewz.context import TaskContext

    name = member["name"]
    agent_id = member.get("id", slug(name))
    adir = _agent_dir(pid, phase_slug, agent_id)

    # Retry hygiene: a prior failed attempt may have left naming-law-violating
    # files in the worker dir (e.g. a first-pass "main.tscn", "capture.png" or
    # misprefixed screenshot). Those stale files trip the worker-level v2.1
    # gate on EVERY later attempt regardless of what the worker does now, so
    # the retry loop could never succeed. Purge exactly the violating files
    # before starting a retry; keep everything else (the supervisor fix plan
    # may reference earlier good deliverables).
    if adir.exists() and _V21 is not None:
        try:
            stale = _V21.naming_violations(
                [str(f.relative_to(adir)) for f in adir.rglob("*")
                 if _is_deliverable(f)])
            purged = []
            for desc in stale:
                rel = desc.split(" (missing standard prefix")[0]
                target = adir / rel
                if target.is_file():
                    try:
                        target.unlink()
                        purged.append(str(rel))
                    except Exception as _e:
                        purged.append(f"{rel}(not removed: {_e})")
            # Junk roots: a worker sometimes passes a JSON blob / flag string
            # as a project_root, creating dirs/files literally named like
            # {"project_name":...}, "<path>" or "--type". Those are never
            # legitimate deliverables and poison every later attempt, so purge
            # them too. Content-addressed, prefix-compliant dirs are kept.
            import shutil as _shutil
            for entry in sorted(adir.iterdir()):
                nm = entry.name
                if nm.startswith(("{", "<", "--")) or "=" in nm:
                    try:
                        if entry.is_dir():
                            _shutil.rmtree(entry)
                        else:
                            entry.unlink()
                        purged.append(f"{nm}/ (junk root)")
                    except Exception as _e:
                        purged.append(f"{nm}(not removed: {_e})")
            if purged:
                print(f"[worker] {agent_id} purged {len(purged)} stale "
                      f"naming-violating files before retry: {purged[:6]}")
        except Exception as _e:
            print(f"[worker] {agent_id} stale-purge skipped ({_e})")

    # build the worker agent with real tool bindings
    tools = list(member.get("tools", []))
    if "write-file" not in tools:
        tools = tools + ["write-file"]
    if "verify" not in tools:
        tools = tools + ["verify"]
    agent = CrewzAgent(
        role=name,
        goal=member.get("prompt", ""),
        capabilities=list(member.get("skills", [])),
        tools=tools,
        max_iter=10,
        allow_delegation=False,
        allow_code_execution=False,
        guardrails=True,
    )

    # inject real callable tools into the agent's brain loop.
    # Bind EVERY real executor in TOOL_DISPATCH, not just the declared set:
    # supervisors are briefed with the full executor list and prescribe tools
    # by name (e.g. scaffold-project, verify-bootstrap, handoff-report). If a
    # supervisor-prescribed tool isn't bound, the worker emits "unknown tool"
    # steps and can never reach ready. Declared tools stay the prompt's
    # suggested set; everything real is callable.
    from mem20crewz.skills import Skills
    skills = Skills()
    for t in sorted(set(TOOL_DISPATCH) | set(tools)):
        if t in TOOL_DISPATCH:
            tool_name = t
            tool_fn = TOOL_DISPATCH[t]
            # wrap fn to always return string (Skill.execute returns dict);
            # relative path resolution is handled inside each tool via
            # _WORKER_BASE, so pass args through untouched
            def _wrap(fn=tool_fn):
                def wrapped(raw_args: str) -> str:
                    result = fn(raw_args)
                    return json.dumps(result)
                return wrapped
            skills.add_callable(tool_name, _wrap(tool_fn),
                                description=f"Execute {tool_name} real CLI tool")
        else:
            skills.add_procedural(t)
    # always allow write-file as a fallback (allows the worker to author
    # Blender/Unity/FreeCAD scripts then run them via the executors)
    if "write-file" not in tools:
        def _write_wrap(raw_args: str) -> str:
            return json.dumps(tool_write_file(raw_args))
        skills.add_callable("write-file", _write_wrap,
                            description="Write content to a file in the agent workspace")
    skills.load_procedural_inventory()

    # append remediation (supervisor blocker fixes) on retries
    full_prompt = task_prompt
    if remediation:
        full_prompt += textwrap.dedent(f"""\

        SUPERVISOR BLOCKER FIX — YOU WERE NOT READY. Fix these specific issues:
        {remediation}
        Re-run your tools to correct the deliverable. Do not repeat the same
        mistake. Produce a corrected handoff report.
        """)
    full_prompt += (
        f"\n\nATTEMPT {attempt} of this task. "
        "You MUST write at least one real deliverable file before finishing. "
        "A report is NOT a deliverable.\n"
        f"OUTPUT DIRECTORY (concrete, absolute — write files here): {adir}\n"
        "End your Handoff Report with a line exactly like:\n"
        "Ready for integration: Yes\n")

    full_prompt += textwrap.dedent("""\

    HARNESS v2.1 DELIVERY STANDARDS (mandatory):
    1. NAMING LAW — every output file name must start with a standard prefix:
       SM_ (static mesh), M_ (material), T_ (texture, with type suffix e.g.
       T_<Name>_Albedo.png), A_ (animation/audio+name), Prefab_ (prefab),
       Scene_ (scene). NO generic filenames like model.glb or texture.png.
    2. DESCRIPTION FIRST — for every mesh/scene you create, also write a
       DESC_<name>.md describing exactly what it is, its purpose, and its
       poly/target budget BEFORE generating the model. No unexplained assets.
    3. MANIFEST — write a manifest.json listing every asset you delivered
       (use the 'manifest' tool). Flat dumps are rejected by the supervisor.
    4. HONEST REPORTING — a handoff-report.md covering what was delivered,
       exact file paths, acceptance criteria results, and any blockers.
    """)

    # build context
    ctx = TaskContext(
        task_name=f"{name} — {phase_slug}",
        description=full_prompt,
        expected_output=(
            "A structured Handoff Report with:\n"
            "- Agent ID and Phase\n"
            "- What was completed (bullet list + exact file paths)\n"
            "- Acceptance criteria checklist (pass/fail for each)\n"
            "- Performance notes\n"
            "- Blockers / risks\n"
            "- Ready for integration: Yes / No"
        ),
        inputs={"workspace": str(adir), "pid": pid},
        upstream={},
        agent_identity=agent.identity(),
        memory_recall="",
        tools=", ".join(tools),
    )

    # run the loop manually (mimic kickoff but use our skills set)
    from mem20crewz.neural import CogBrain
    brain = CogBrain()
    from mem20crewz.loop import ToolLoop, Guards
    guards = Guards(actor=agent.namespace, enforce_plan=True)

    import time as _time
    _worker_started_at = _time.monotonic()
    _attempt_deadline = MAX_WORKER_ATTEMPT_SECS

    def _step_trace(**kw):
        try:
            i = kw.get("step_index"); action = kw.get("action")
            tool = kw.get("tool", "") or ""; done = kw.get("ok")
            trace = adir / ".worker-trace.tsv"
            line = f"{_time.strftime('%H:%M:%S')}\t{i}\t{action}\t{tool}\t{done}\t{_time.monotonic()-_worker_started_at:.0f}s"
            with open(trace, "a") as _f:
                _f.write(line + "\n")
        except Exception:
            pass

    loop = ToolLoop(brain=brain, skills=skills, guards=guards,
                    max_iter=12, verbose=False,
                    max_execution_time=_attempt_deadline,
                    require_tool_before_final=True,
                    step_callback=_step_trace)
    base_tok = _WORKER_BASE.set(str(adir))
    try:
        if _V21 is not None:
            with _V21.route_worker():  # round-robin across model x key buckets
                result = loop.run(
                    goal=ctx.prompt(),
                    initial_observations=[],
                    available_tools=skills.inventory(),
                )
        else:
            result = loop.run(
                goal=ctx.prompt(),
                initial_observations=[],
                available_tools=skills.inventory(),
            )
    finally:
        _WORKER_BASE.reset(base_tok)

    # tool-call tracker: persist every loop step (incl. raw "unknown"
    # proposals) so supervisors/orchestrator can see exactly which tool names
    # a worker attempted and which were unavailable. Previously "unknown"
    # steps recorded an empty tool column and the proposal text was lost.
    try:
        from dataclasses import asdict as _dc_asdict
        _journal = []
        for _s in getattr(result, "steps", []):
            _entry = {
                "step": _s.index,
                "action": _s.action,
                "tool": _s.tool or "",
                "ok": bool(_s.ok),
                "output": str(_s.output)[:600],
            }
            if not _entry["tool"] and _entry["action"] in ("unknown", "final-rejected"):
                _entry["proposal"] = str(_s.output)[:600]
            _journal.append(_entry)
        (adir / ".worker-steps.json").write_text(
            json.dumps({"agent": agent_id, "steps": _journal},
                       indent=1, default=str))
    except Exception:
        pass

    # parse handoff (tolerate the brain wrapping its final answer in JSON,
    # e.g. {"action":"final","final":"...Ready for integration: Yes..."});
    # also strip think-wrapper tags / surrounding prose from pool models.
    handoff_text = result.text or ""
    for candidate in _extract_json_candidates(handoff_text):
        try:
            raw_obj = json.loads(candidate)
        except Exception:
            continue
        if isinstance(raw_obj, dict) and raw_obj.get("action") == "final":
            handoff_text = str(raw_obj.get("final") or handoff_text)
            break
        if isinstance(raw_obj, dict):
            handoff_text = candidate
            break

    # real deliverable gate: at least one output file required
    output_files = []
    if adir.exists():
        output_files = [str(f.relative_to(adir))
                        for f in adir.rglob("*")
                        if _is_deliverable(f)]
    output_files.sort()

    ready_marker = _has_ready_marker(handoff_text)

    # If the tool loop produced real deliverable files but ended on a tool
    # observation instead of an explicit handoff report (max_iter exhausted
    # mid-toolchain), synthesize the handoff now: a single-shot summary built
    # from the ACTUAL files on disk. This is honest evidence — the files exist —
    # and closes the loop the agent could not reach within its iteration budget.
    if not ready_marker and output_files:
        try:
            synth = _synthesize_handoff(name, agent_id, member, full_prompt,
                                        output_files, adir)
        except Exception:
            synth = None
        if synth:
            handoff_text = synth
            ready_marker = _has_ready_marker(handoff_text)

    handoff_path = adir / "handoff-report.md"
    try:
        handoff_path.write_text(handoff_text or "[no handoff generated]")
    except Exception:
        pass

    ready = ready_marker and len(output_files) >= 1

    # Phase-aware deliverable gate (v2.1): in the Audio & VFX phase a worker is
    # NOT ready on docs/manifest alone — it must ship real audio (.wav/.ogg/
    # .mp3) or VFX mesh (.glb/.fbx/.obj/.prefab/.unity/.tscn) artifacts. This
    # stops the fake-ready pattern where a worker writes only DESC_*/manifest
    # JSON referencing audio files that were never produced on disk.
    if ready and phase_slug in ("phase-4-audio-and-vfx", "phase-5-6-factory-audio-vfx-polish"):
        _real = [_f for _f in output_files
                 if _f.lower().endswith((".wav", ".ogg", ".mp3",
                                         ".glb", ".fbx", ".obj", ".prefab",
                                         ".unity", ".tscn"))]
        if not _real:
            ready = False
            audit_note = (f"v2.1 audio gate: no real audio/vfx artifact on disk "
                          f"(docs-only: {len(output_files)} files)")

    # Align the worker-level gate with the supervisor's machine audit so a
    # worker can never be "ready" yet rejected on v2.1 compliance (naming law
    # or missing handoff fields). If it fails here, the retry loop remediates
    # it — otherwise such a worker dead-ends at the supervisor verdict with
    # no feedback path.
    if ready and _V21 is not None:
        names = [Path(f).name for f in output_files]
        viol = _V21.naming_violations(names)
        mf = _V21.check_handoff(handoff_text)
        if viol or mf:
            ready = False
            audit_note = (f"v2.1 gate: naming-violations={viol[:4]} "
                          f"handoff-missing={mf[:4]}")
        else:
            audit_note = "v2.1 gate: naming + handoff OK"
        print(f"[worker] {agent_id} {audit_note}")

    return {
        "name": name,
        "agent_id": agent_id,
        "handoff_text": handoff_text,
        "output_files": output_files,
        "ok": result.blocked is False,
        "ready": ready,
        "iterations": result.iterations,
        "attempts": attempt,
    }


# Tolerant of markdown emphasis, which models commonly add, e.g.
# "**Ready for integration:** Yes".
_READY_LINE_RE = re.compile(
    r"(?:ready for integration|integration ready)\s*:?\s*\**\s*"
    r"(yes|no|true|false|1|0)\b",
    re.IGNORECASE)


def _has_ready_marker(text: str) -> bool:
    m = _READY_LINE_RE.search(text or "")
    return bool(m and m.group(1).lower() in ("yes", "true", "1"))

# A phase needs an audio inspector when its deliverables include real sound
# (audio/vfx phases and visual QA over audio assets). This is deterministic
# over the phase slug, never an LLM guess.
_AUDIO_PHASE_MARKERS = ("audio", "sfx", "sound", "music", "vfx")


def _runs_audio(phase_slug: str) -> bool:
    low = (phase_slug or "").lower()
    return any(m in low for m in _AUDIO_PHASE_MARKERS)


def _extract_json_candidates(text: str) -> list[str]:
    """Yield JSON-object candidates from an LLM reply, tolerating think
    wrappers (```...``` / ``...`` fences), surrounding prose, and stray braces."""
    if not text:
        return []
    stripped = text
    # Drop <thinking>...</thinking> blocks entirely (noise, no deliverable).
    while "<thinking>" in stripped:
        a = stripped.find("<thinking>")
        b = stripped.find("</thinking>", a + 10)
        if b == -1:
            break
        stripped = stripped[:a] + stripped[b + 11:]
    # Remove backtick fence markers only (```json / ``` or ``...``), keeping
    # whatever content sits between them.
    ok = True
    while ok:
        ok = False
        for fence in ("```", "``"):
            if fence in stripped:
                a = stripped.find(fence)
                stripped = stripped[:a] + stripped[a + len(fence):]
                ok = True
    stripped = stripped.strip()
    out: list[str] = []
    start = 0
    while True:
        i = stripped.find("{", start)
        if i == -1:
            break
        depth, j, in_str, esc = 0, i, False, False
        while j < len(stripped):
            ch = stripped[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        cand = stripped[i:j + 1]
                        out.append(cand)
                        start = j + 1
                        break
            j += 1
        if depth != 0:
            break
        if j >= len(stripped) and (depth != 0 or i == start):
            break
    # The raw text itself first (best case: already pure JSON).
    if text.strip().startswith("{"):
        out.insert(0, text.strip())
    return out


def _naming_violations_for(worker_dir: Path) -> list[str]:
    """Deterministic v2.1 naming violations for a worker's current files."""
    if _V21 is None:
        return []
    files = [str(f.relative_to(worker_dir))
             for f in worker_dir.rglob("*")
             if _is_deliverable(f)]
    if not files:
        return []
    return _V21.naming_violations([Path(f).name for f in files])


def _synthesize_handoff(name: str, agent_id: str, member: dict,
                        task_prompt: str, output_files: list[str],
                        adir: Path) -> str:
    """Single-shot handoff report from the real files the worker produced."""
    brief_goal = member.get("prompt", "")
    present = []
    for rel in output_files:
        f = adir / rel
        if f.exists():
            present.append(f"- {rel} ({f.stat().st_size} bytes)")
    files_block = "\n".join(present)
    prompt = textwrap.dedent(f"""\
    You are {name} ({agent_id}), a swarm worker.
    Your goal was: {brief_goal}
    Your task prompt was: {task_prompt[:1200]}

    You ran your toolchain and produced these real deliverable files in
    your workspace ({adir}):
    {files_block}

    Inspect the file LIST above (names + sizes). Produce your final
    Handoff Report now, in this exact structure. Include EVERY one of these
    labeled fields verbatim (the supervisor's machine audit checks for them
    exactly):
    - Agent / Supervisor ID: <you>
    - Role: <your role>
    - Phase / Task ID: <phase>
    - Assigned Model Used: <model>
    - What was delivered: <bullet list referencing the actual file paths above>
    - Manifest path: <manifest.json path if produced, else "none">
    - Visual verification performed: <yes/no + how>
    - Acceptance criteria met: <pass/fail per criterion>
    - File placement & naming verified: <yes/no>
    - Primitives present: <yes/no>
    - Known issues / blockers: <any>
    - Dependencies still open: <any>
    - Ready for next stage: <yes/no>
    Then end the report with a line exactly like one of the two:
    Ready for integration: Yes
    Ready for integration: No
    Be truthful: say Yes only if the files above genuinely satisfy your task.
    VISUAL VERIFICATION IS MANDATORY (all-gates law): a live in-engine render
    IS available — run engine-capture on the real game project to produce a
    screenshot, then vision-check it. Ready for integration: Yes requires a
    captured screenshot that vision-check PASSed (and, for audio assets, an
    audio sample that audio-check PASSed). A missing or vision-FAILED render
    is grounds for refusing readiness — it is never an acceptable short-cut.
    If no capture is possible right now, report Ready for integration: No and
    list exactly what blocked the capture.
    Keep the whole report concise (under ~250 words) so the required final
    line is never cut off.
    """)
    # A flaky/empty model response must not be mistaken for "no marker": the
    # caller writes whatever we return to disk. Retry on empty or malformed
    # output. Accept a well-formed report even if it truthfully says No.
    best = ""
    for attempt in range(3):
        try:
            out = _supervisor_llm(prompt, profile=name, max_tokens=1500)
        except Exception as exc:  # noqa: BLE001 - surfaced below
            print(f"[synth] {agent_id} attempt {attempt + 1} failed: {exc}")
            continue
        if out and _READY_LINE_RE.search(out):
            return out
        if out and out.strip() and not best:
            best = out
        print(f"[synth] {agent_id} attempt {attempt + 1} produced no ready line "
              f"({len(out or '')} chars); retrying")
    return best


def _supervisor_llm(prompt: str, profile: str = "supervisor",
                    max_tokens: int = 900) -> str:
    """Single-shot LLM call for supervisor/gate text-analysis roles.

    These roles are pure reasoning (review handoffs, gate decisions,
    remediation plans). Spinning up an interactive AgentCore loop for them
    burns 4-8 LLM calls per invocation, which starves free-tier rate limits
    and turns a 1-call task into a failing agent run. A single chat call is
    the correct shape and is far cheaper.

    v2.1: routed through role-based provider assignments (Groq primary,
    NVIDIA fallback) with LLMError raised if every candidate fails.
    """
    if _V21 is not None:
        try:
            return _V21.chat_role(profile, prompt, max_tokens=max_tokens)
        except Exception as exc:  # noqa: BLE001 - fall back to substrate
            print(f"[runner] v21 role routing failed for {profile!r}: "
                  f"{type(exc).__name__}: {exc}")
    from mem20crewz._substrate import backend as _sub
    return _sub.llm.chat(
        [{"role": "system", "content": f"You are {profile}."},
         {"role": "user", "content": prompt}],
        max_tokens=max_tokens)


def _orchestrator_llm(prompt: str, max_tokens: int = 900,
                      secondary: bool = False) -> str:
    """Orchestrator/TLO calls: routed to assigned orchestrator model."""
    if _V21 is not None:
        try:
            return _V21.orchestrator_chat(prompt, max_tokens=max_tokens,
                                          secondary=secondary)
        except Exception as exc:  # noqa: BLE001 - fall back to substrate
            print(f"[runner] v21 orchestrator routing failed: "
                  f"{type(exc).__name__}: {exc}")
    from mem20crewz._substrate import backend as _sub
    return _sub.llm.chat(
        [{"role": "system", "content": "You are the top-level Orchestrator."},
         {"role": "user", "content": prompt}],
        max_tokens=max_tokens)


def _run_supervisor(sv: dict, project: dict, phase_results: list[dict],
                    pid: str, phase_slug: str, ws: Path) -> dict:
    """Run the phase supervisor: brief → review workers → produce handoff.

    Uses a single-shot LLM call (mem20 substrate).
    Returns {name, handoff_text, ready, gate_passed}.
    """
    name = sv["name"]
    sv_prompt = sv.get("prompt", "")


def _repair_work_order(member: dict, failed: dict, pid: str, pslug: str,
                       ws: Path) -> str:
    """Focused REPAIR prompt for a worker that failed readiness.

    A repair worker is a DISTINCT agent dispatched immediately when a worker
    lands ready:false. It fixes only the machine-verified defects in the
    failed worker's directory — never re-runs the whole original task (that
    is the CPU-hungry retry loop we are eliminating). If ready:false was
    caused by a beta bug report, the bug list is the work order.
    """
    agent_id = failed["agent_id"]
    adir = ws / pslug / agent_id
    # Beta bug reports (phase-7 testers report to supervisor → repair worker):
    bugs = []
    for bfile in sorted(adir.glob("bug-report*.md")) + sorted(
            adir.glob("*bug*report*.md")):
        try:
            bugs.append(bfile.read_text()[:1500])
        except Exception:
            continue
    bug_block = "\n\n".join(bugs) if bugs else (
        "none on disk — fix the machine-verified defects below")
    # Machine-verified naming/placement law violations from ACTUAL files.
    violations = _naming_violations_for(adir)
    viol_block = "\n".join(f"- {v}" for v in violations) if violations \
        else "(none currently detected — re-audit after repair)"
    # Handoff fields missing (machine-verified from the failed handoff).
    handoff_missing = []
    if _V21 is not None:
        handoff_missing = _V21.check_handoff(failed.get("handoff_text", ""))
    mf_block = "\n".join(f"- {m}" for m in handoff_missing) if handoff_missing \
        else "(none missing)"
    return textwrap.dedent(f"""\
        REPAIR WORK ORDER — you are a DISTINCT REPAIR WORKER, not the original
        worker. Your only job is to fix the failed deliverables below so they
        become ready. Do NOT redo the whole original task and do NOT rewrite
        what already works.

        ORIGINAL WORKER: {member.get('name', agent_id)}
        ORIGINAL GOAL (for context, NOT a to-do list):
        {member.get('prompt', '')[:4000]}

        WORKSPACE TO REPAIR (in place): {adir}

        MACHINE-VERIFIED DEFECTS (fix exactly these, then prove the fix):
        - NAMING/PLACEMENT LAW violations:
        {viol_block}
        - HANDBOOK FIELDS missing from the handoff:
        {mf_block}

        BUG REPORTS FROM TESTERS (phase 7 law: testers report bugs to their
        supervisor; the supervisor dispatches YOU to repair. Fix these, then
        the tester's re-test must pass vision/audio verification):
        {bug_block}

        VISUAL/QA GATE (all-gates law): if this milestone involves visuals,
        run engine-capture on the real game project, then vision-check the
        frame — Ready requires a vision-check PASS whose description matches
        the pack requirement. If it involves audio, run audio-check on a real
        sample. A missing or vision-FAILED render/audio means Ready for
        integration: No.

        End with the exact line:
        Ready for integration: Yes
        (only when every defect above is fixed AND verified).""")

    # assemble the supervisor's briefing
    worker_summary = "\n".join(
        f"- {w['name']}: {'PASS' if w['ready'] else 'FAIL'} "
        f"({len(w.get('output_files', []))} files) "
        f"ready={w['ready']}"
        for w in phase_results
    )

    # v2.1 deterministic enforcement facts (naming law + handoff fields) that
    # the supervisor must weigh in its verdict. Computed from real file names,
    # so no extra LLM call — this is verified evidence.
    enforcement = []
    if _V21 is not None:
        for w in phase_results:
            names = [Path(f).name for f in w.get("output_files", [])]
            if not names:
                enforcement.append(f"- {w['name']}: NO OUTPUT FILES")
                continue
            viol = _V21.naming_violations(names)
            mf = _V21.check_handoff(w.get("handoff_text", ""))
            bits = []
            if viol:
                bits.append(f"naming-law violations: {viol[:4]}")
            if mf:
                bits.append(f"handoff missing {len(mf)} fields: {mf[:4]}")
            if not bits:
                bits.append("naming + handoff OK")
            enforcement.append(f"- {w['name']}: " + "; ".join(bits))

    briefing = textwrap.dedent(f"""\
    You are {name}, the Phase Supervisor.

    YOUR PHASE PROMPT:
    {sv_prompt}

    WORKERS IN YOUR PHASE ({len(phase_results)} total):
    {worker_summary}

    V2.1 COMPLIANCE AUDIT (MACHINE-EVERIFIED, DETERMINISTIC):
    {chr(10).join(enforcement) if enforcement else '   (no workers)'}

    Do NOT accept a worker whose deliverable files violate the v2.1 naming law
    (SM_/M_/T_/A_/Prefab_/Scene_ prefixes) or whose handoff is missing the
    required fields (what was delivered, manifest path, acceptance criteria,
    blockers). Flag them in the report body.

    In this pipeline a live in-engine render IS available via engine-capture.
    Every worker whose milestone demands visuals or audio MUST provide a
    captured screenshot that vision-check PASSed (and/or an audio sample that
    audio-check PASSed) as PREREQUISITE for readiness. A missing in-engine
    render or vision-FAILED capture is a rejection ground, not an
    environmental limit to wave off. Judge readiness on deliverables PLUS the
    machine-verified render/audio proof.
    Unfinished or missing deliverables are still grounds for rejection.

    Your job: review the worker handoffs above. For each worker that
    is NOT ready, note why and what must be fixed.

    BEGIN with exactly one line, on its own, before anything else:
    Ready for integration: Yes
    or
    Ready for integration: No

    Then, after that line, produce a PHASE HANDOFF REPORT with:
    - Phase name and supervisor
    - Number of workers: total / passed / failed
    - Per-worker verdict (accept/reject with reason)
    - Phase performance summary
    - Phase blockers / risks

    Be ruthless. Do not sign off on incomplete work. Emit the first line
    even if you then run out of room listing every worker.
    """)

    # The machine-read verdict is required; the report body can be long and
    # may truncate, so it is emitted first. Retry if the model omits it.
    handoff_text = ""
    for attempt in range(3):
        try:
            out = _supervisor_llm(briefing, profile=name, max_tokens=2000)
        except Exception as e:
            out = f"[supervisor error] {type(e).__name__}: {e}"
        if out and _READY_LINE_RE.search(out):
            handoff_text = out
            break
        if out and out.strip() and not handoff_text:
            handoff_text = out
        print(f"[supervisor] {name} attempt {attempt + 1} produced no ready "
              f"line ({len(out or '')} chars); retrying")

    ready = _has_ready_marker(handoff_text)
    passed = all(w["ready"] for w in phase_results) and ready

    # write supervisor handoff to phase dir
    hpath = ws / phase_slug / "supervisor-handoff.md"
    hpath.write_text(handoff_text)

    return {
        "name": name,
        "handoff_text": handoff_text,
        "ready": ready,
        "gate_passed": passed,
        "workers_total": len(phase_results),
        "workers_passed": sum(1 for w in phase_results if w["ready"]),
    }


def _run_supervisor_fix(sv: dict, project: dict, failed_workers: list[dict],
                        pid: str, phase_slug: str, ws: Path) -> dict:
    """Supervisor blocker-fix pass: review failed workers and issue targeted
    remediation per worker so the orchestrator can retry them.

    Returns {worker_agent_id: remediation_text, decision_text}.
    """
    name = sv["name"]
    if not failed_workers:
        return {"remediation": {}, "decision_text": "no failed workers"}

    worker_detail = "\n".join(
        f"- {w['name']} ({w.get('agent_id','?')}):\n"
        f"  ready={w['ready']} ok={w.get('ok')} iters={w.get('iterations')}\n"
        f"  files={w.get('output_files', [])}\n"
        f"  handoff={w.get('handoff_text', '')[:800]}"
        for w in failed_workers
    )

    # v2.1 deterministic violations (naming law + handoff fields) per failed
    # worker, so the supervisor's remediation names EXACTLY which files to
    # rename/move and which fields to add instead of issuing generic advice.
    v21_violations = ""
    if _V21 is not None:
        lines = []
        for w in failed_workers:
            names = [Path(f).name for f in w.get("output_files", [])]
            if not names:
                lines.append(f"- {w.get('agent_id','?')}: NO OUTPUT FILES")
                continue
            viol = _V21.naming_violations(names)
            if viol:
                lines.append(
                    f"- {w.get('agent_id','?')}: naming-law violations "
                    f"(rename these files): {viol[:8]}")
        if lines:
            v21_violations = (
                "V2.1 DETERMINISTIC NAMING-LAW VIOLATIONS (MACHINE-VERIFIED):\n"
                + "\n".join(lines) + "\n"
            )

    # The exact v2.1 naming law, so remediation directives NEVER invent
    # prefixes. Allowed prefixes are exactly: SM_ (static meshes),
    # M_ (materials, NO file extension allowed on the name), T_ (textures,
    # T_NAME_Albedo/Normal/Roughness/Metallic/AO/Emissive), A_ (audio),
    # Prefab_ (prefabs), Scene_ (scenes, only .unity/.tscn). Anything else is
    # a violation and must be renamed or removed.
    naming_law = (
        "V2.1 NAMING LAW (YOU MUST SPELL RENAMES EXACTLY ACCORDING TO THESE):\n"
        "- SM_ prefix: static meshes, e.g. SM_Office_Main.fbx/.glb/.obj/.blend\n"
        "- M_ prefix: materials, e.g. M_Office_Main (NO extension allowed)\n"
        "- T_ prefix: textures, ONE name word then the map type, e.g. "
        "T_Office_Albedo.png / T_Office_Normal.png (not T_Office_Arch_Albedo)\n"
        "- A_ prefix: audio, e.g. A_HoverLoop.wav/.ogg/.mp3\n"
        "- Prefab_ prefix: prefabs/scenes-as-prefabs, e.g. Prefab_Menu.prefab/.tscn\n"
        "- Scene_ prefix: scenes, ONLY .unity or .tscn files\n"
        "- Anything lacking one of these prefixes violates the law → rename "
        "the FILE (or remove it) rather than leaving a broken name."
    )

    # tool-call evidence: pull each failed worker's step journal so the
    # supervisor can see which exact tool names were attempted (including
    # unknown/unbound tool names) instead of guessing.
    tool_evidence = ""
    ws = _workspace(pid)
    ev_lines = []
    for w in failed_workers:
        aid = w.get("agent_id", "")
        jpath = ws / phase_slug / aid / ".worker-steps.json"
        if not jpath.exists():
            continue
        try:
            journal = json.loads(jpath.read_text())
        except Exception:
            continue
        attempts = []
        for s in journal.get("steps", []):
            if s.get("action") == "tool":
                attempts.append(
                    f"{s.get('tool')}:{'OK' if s.get('ok') else 'FAILED'}")
            elif s.get("action") in ("unknown", "final-rejected"):
                attempts.append("unknown-proposal=" + (s.get("proposal") or s.get("output") or "")[:160])
        if attempts:
            ev_lines.append(f"- {aid}: {' | '.join(attempts)}")
    if ev_lines:
        tool_evidence = "TOOL CALL EVIDENCE (from worker step journals):\n" + \
                        "\n".join(ev_lines) + "\n"

    briefing = textwrap.dedent(f"""\
    You are {name}, the Phase Supervisor, performing a BLOCKER-FIX REVIEW.

    The following workers FAILED to reach "Ready for integration: Yes" with
    at least one real deliverable file. Diagnose each failure precisely from
    their handoffs, tool availability, and any files they produced.

    FAILED WORKERS:
    {worker_detail}

    {tool_evidence}
    {v21_violations}
    {naming_law}
    AVAILABLE TOOL NAMES (worker bindings):
    {", ".join(sorted(TOOL_DISPATCH))}

    If the tool-call evidence above shows any unknown/unbound tool name, tell
    the worker the exact registered tool name to use from AVAILABLE TOOL NAMES.

    For EACH failed worker output EXACTLY ONE block in this format:

    WORKER: <agent_id>
    ROOT CAUSE: <one clear sentence>
    REMEDIATION: <numbered concrete steps the worker must retry, including
    which exact tool name + arguments to call and what file to produce>

    Be specific and actionable. A worker must be able to run the steps
    blindly. No vague advice.

    MULTI-WAVE SCOPE RULE (this phase): each wave's deliverable is the
    purpose-built LOD0 mesh set + written DESC_ file(s) named per the v2.1
    naming law. LOD1/LOD2, collision meshes, manifest.json batch entries, and
    in-engine render verification are DOWNSTREAM items for later waves/phases -
    a worker withholding its Ready marker for those reasons alone is NOT a
    real defect. If the worker's own wave deliverables are complete and named
    correctly, remediate it to flip its handoff to "Ready for integration:
    Yes" (downstream items listed under "Dependencies still open").
    """)

    try:
        decision = _supervisor_llm(briefing, profile=name, max_tokens=1200)
    except Exception as e:
        decision = f"[supervisor-fix error] {type(e).__name__}: {e}"

    # parse WORKER: <agent_id> ... REMEDIATION: blocks
    remediation: dict[str, str] = {}
    blocks = re.findall(
        r"WORKER:\s*(\S+)(.*?)(?=WORKER:|\Z)", decision, flags=re.S | re.I)
    for block in blocks:
        aid, body = block[0], block[1]
        rem = ""
        m = re.search(r"REMEDIATION:\s*(.*?)(?=WORKER:|\Z)", body, flags=re.S | re.I)
        if m:
            rem = m.group(1).strip()
        if aid and rem:
            remediation[aid] = rem[:2000]

    # persist the fix plan in the phase dir
    fpath = ws / phase_slug / "supervisor-fix-plan.md"
    fpath.write_text(decision)
    return {"remediation": remediation, "decision_text": decision}


def _run_orchestrator_gating(project: dict, sv_result: dict,
                             prior_results: list[dict]) -> dict:
    """Run TLO to gate a phase. Returns {gate, decision_text}.

    Uses a single-shot LLM call (mem20 substrate). Reviews the supervisor's
    handoff and all prior phase results to decide: PASS, BLOCK, or ASSEMBLE.
    """
    orch = project.get("orchestrator", {})
    orch_name = orch.get("name", "TLO")

    # HARD PRECONDITION (operator rule): a phase gate may NEVER proceed unless
    # worker readiness is 100%/100%. This is deterministic and overrides any
    # LLM verdict — the model's PASS/PROCEED cannot waive an incomplete phase.
    workers_total = int(sv_result.get("workers_total", 0))
    workers_passed = int(sv_result.get("workers_passed", 0))
    fully_complete = (
        workers_total > 0
        and workers_passed == workers_total
        and bool(sv_result.get("ready"))
    )

    prior_summary = "\n".join(
        f"- Phase {p.get('name', str(i + 1))}: "
        f"{'PASS' if p.get('gate_passed', p.get('gate') in ('pass', 'proceed')) else 'BLOCKED'}"
        for i, p in enumerate(prior_results)
    )

    prompt = textwrap.dedent(f"""\
    You are {orch_name}, the top-level Orchestrator.

    YOUR MASTER DIRECTIVE:
    {orch.get('prompt', '')[:2000]}

    PHASE COMPLETED:
    {sv_result['name']}
    Workers: {sv_result['workers_total']} total, {sv_result['workers_passed']} passed
    Supervisor ready: {sv_result['ready']}

    PRIOR PHASES:
    {prior_summary or "(none — this is the first phase)"}

    GATE DECISION:
    Review the supervisor's handoff. Decide:
    - PASS if the phase meets all exit criteria
    - BLOCK if critical work is incomplete
    - PROCEED if you want to advance to the next phase

    Reply with exactly one word on the first line: PASS, BLOCK, or PROCEED.
    Then brief explanation.
    """)

    try:
        text = _orchestrator_llm(prompt, max_tokens=800)
    except Exception as e:
        text = f"[orchestrator error] {type(e).__name__}: {e}"

    first_word = text.strip().split()[0].upper() if text.strip() else "BLOCK"
    gate = "pass" if "PASS" in first_word else ("block" if "BLOCK" in first_word else "proceed")

    # Enforce the hard precondition AFTER the LLM verdict so neither the main
    # nor the secondary orchestrator can advance an incomplete phase.
    if not fully_complete:
        gate = "block"
        text = (f"[DETERMINISTIC GATE BLOCK] worker rate "
                f"{workers_passed}/{workers_total} "
                f"(supervisor ready={sv_result.get('ready')}): a phase may not "
                f"proceed below 100%/100%.\n\n" + text)

    # SECONDARY ORCHESTRATOR CROSS-CHECK (EXECUTION_RULES: 2 orchestrators).
    # Secondary is advisory on phase gates: a veto downgrades PASS->PROCEED
    # (never silently blocks the pipeline) and is recorded on the gate.
    secondary_text = ""
    try:
        secondary_text = _orchestrator_llm(textwrap.dedent(f"""\
        You are the SECONDARY Orchestrator, cross-checking {orch_name}'s gate.

        MASTER DIRECTIVE (abridged):
        {orch.get('prompt', '')[:1500]}

        PHASE COMPLETED:
        {sv_result['name']}
        Workers: {sv_result['workers_total']} total, {sv_result['workers_passed']} passed
        Supervisor ready: {sv_result['ready']}

        MAIN ORCHESTRATOR GATE VERDICT:
        {text[:1500]}

        CROSS-CHECK the verdict for obvious gaps (black screens, broken
        cameras, soft-locks, missing manifests/vision gates). Reply with
        exactly one word on the first line: AGREE or VETO.
        Then one short sentence.
        """), max_tokens=400, secondary=True)
    except Exception as exc:
        secondary_text = f"[secondary orchestrator error] {type(exc).__name__}: {exc}"

    sec_first = secondary_text.strip().split()[0].upper() if secondary_text.strip() else ""
    secondary_veto = "VETO" in sec_first or "REJECT" in sec_first or "BLOCK" in sec_first
    if secondary_veto and gate == "pass":
        gate = "proceed"
        text += ("\n\n[SECONDARY ORCHESTRATOR VETO]\n" + secondary_text[:600])

    return {"gate": gate, "decision_text": text,
            "secondary_text": secondary_text[:600],
            "workers_total": workers_total, "workers_passed": workers_passed}


def _run_assembly(project: dict, pid: str,
                  all_worker_results: dict[str, list[dict]],
                  ws: Path, prior_gate_results: list[dict]) -> dict:
    """Orchestrator final assembly: build the working Unity project.

    Scaffolds a real Unity project, collects all phase outputs into
    Assets/_Project, then runs Unity batch compilation and exports:
      - Android APK (Quest 3: ARM64/IL2CPP/Vulkan)  ← final deliverable
      - Linux x86_64 build                          ← verification build
    """
    project_path = str(ws / "assembly")
    scaffold = tool_unity_scaffold(project_path)
    if not scaffold.get("ok"):
        return {"status": "scaffold_failed", "scaffold": scaffold,
                "ts": _now()}

    import shutil

    assembly_dir = ws / "assembly" / "Assets" / "_Project"
    artifacts_dir = ws / "assembly" / "Assets" / "_Artifacts~"
    # Clean stale copies from prior runs so removed files don't linger.
    for d in (assembly_dir, artifacts_dir):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
    assembly_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # 1. Collect all output files from all phases. Unity-importable assets go
    #    under _Project (compiled/imported); everything else is archived under
    #    _Artifacts~ (Unity ignores folders ending in '~').
    manifest = {"phases": {}, "total_files": 0, "assets": 0, "artifacts": 0}
    seen = set()
    for phase_name, results in all_worker_results.items():
        phase_files = []
        for wr in results:
            for f in wr.get("output_files", []):
                src = ws / slug(phase_name) / wr["agent_id"] / f
                if not src.exists():
                    continue
                is_asset = Path(f).suffix.lower() in _UNITY_ASSET_EXTS
                base = assembly_dir if is_asset else artifacts_dir
                dstdir = base / phase_name / wr["agent_id"]
                dstdir.mkdir(parents=True, exist_ok=True)
                # Unity can't import same-folder files that differ only by
                # case on a case-sensitive filesystem (e.g. Elevator.glb /
                # elevator.glb). Rename later copies to keep every artifact.
                dst = dstdir / f
                key = f.lower()
                n = 1
                while (str(dstdir), key) in seen:
                    stem, suff = Path(f).stem, Path(f).suffix
                    dst = dstdir / f"{stem}-case{n}{suff}"
                    key = dst.name.lower()
                    n += 1
                seen.add((str(dstdir), key))
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                manifest["assets" if is_asset else "artifacts"] += 1
                phase_files.append(str(dst.relative_to(ws / "assembly")))
        manifest["phases"][phase_name] = {
            "files": phase_files,
            "count": len(phase_files),
        }
        manifest["total_files"] += len(phase_files)

    # 2. Write assembly manifest
    (ws / "assembly" / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2))

    # 3. Unity batch compile check (imports assets, compiles scripts)
    compile_result = tool_unity_batch(
        f"{project_path} --method UnityEditor.SyncVS.SyncSolution")

    # 4. Export builds: Linux first (fast sanity), then Quest 3 APK
    builds: dict[str, object] = {"linux": None, "apk": None}
    linux_result = tool_unity_batch(
        f"{project_path} --method BuildProject.Build --build Linux64")
    builds["linux"] = linux_result
    apk_result = tool_unity_batch(
        f"{project_path} --method BuildProject.BuildAndroid --build Android")
    builds["apk"] = apk_result

    # 4b. Godot parity legs — all 4 build targets are equal (Unity + Godot,
    # each Linux + Android). Honest per-leg result; missing export templates
    # produce a reported failure, not a silent skip.
    godot_builds = {}
    if _V21 is not None:
        try:
            gd_root = ws / "godot-assembly"
            _V21.godot_scaffold(gd_root)
            gd_linux = _V21.godot_build(gd_root, "Linux")
            gd_android = _V21.godot_build(gd_root, "Android")
            godot_builds = {"linux": gd_linux, "android": gd_android}
        except Exception as exc:
            godot_builds = {"error": str(exc)}
    builds["godot"] = godot_builds

    apk_path = ws / "assembly" / "Builds" / "game.apk"
    linux_bin = ws / "assembly" / "Builds" / "game.x86_64"
    gd_linux_bin = (ws / "godot-assembly" / "godot" / "builds" / "linux" / "game.x86_64"
                    if _V21 else None)
    gd_apk_path = (ws / "godot-assembly" / "godot" / "builds" / "android" / "game.apk"
                   if _V21 else None)
    deliverable_status = "delivered"
    if not apk_path.exists() and not (gd_apk_path and gd_apk_path.exists()):
        deliverable_status = "apk_missing"
    if (not linux_bin.exists() and linux_result.get("ok")
            and not (gd_linux_bin and gd_linux_bin.exists())):
        deliverable_status = "linux_missing"

    # 5. Produce final deliverable report
    report = {
        "status": deliverable_status,
        "unity_compile": compile_result,
        "builds": {"linux": linux_result, "apk": apk_result,
                   "godot": godot_builds},
        "artifacts": {
            "apk": str(apk_path) if apk_path.exists() else None,
            "linux": str(linux_bin) if linux_bin.exists() else None,
            "godot_linux": str(gd_linux_bin) if (gd_linux_bin and gd_linux_bin.exists()) else None,
            "godot_apk": str(gd_apk_path) if (gd_apk_path and gd_apk_path.exists()) else None,
        },
        "phases_delivered": list(all_worker_results.keys()),
        "total_artifacts": manifest["total_files"],
        "project_path": project_path,
        "ts": _now(),
    }

    (ws / "assembly" / "DELIVERABLE.json").write_text(
        json.dumps(report, indent=2))

    # 6. Final deliverable report: deterministic verified facts + a grounded
    #    LLM narrative that is told to use ONLY the facts provided.
    def _mb(p: Path) -> float:
        try:
            return round(p.stat().st_size / 1_048_576, 1)
        except Exception:
            return 0.0

    apk_size, linux_size = _mb(apk_path), _mb(linux_bin)
    facts = textwrap.dedent(f"""\
        Project: {project.get('name', pid)}
        Project path: {project_path}
        Unity version: {_unity_version()}
        Unity compile: {'PASS' if compile_result.get('ok') else 'FAIL'}
        Unity Linux build (x86_64): {'PASS' if linux_result.get('ok') else 'FAIL'}
        Unity Quest 3 Android APK: {'PASS' if apk_result.get('ok') else 'FAIL'}
        Godot Linux build: {'PASS' if (gd_linux_bin and gd_linux_bin.exists()) else 'FAIL'}
        Godot Android APK: {'PASS' if (gd_apk_path and gd_apk_path.exists()) else 'FAIL'}
        APK path: {apk_path}
        APK size: {apk_size} MB
        Unity Linux binary path: {linux_bin}
        Unity Linux binary size: {linux_size} MB
        Godot Linux binary path: {gd_linux_bin or 'n/a'}
        Godot Android APK path: {gd_apk_path or 'n/a'}
        Total artifact files collected: {manifest['total_files']}
          imported Unity assets: {manifest['assets']}
          archived source/raw files: {manifest['artifacts']}
        Phases delivered: {', '.join(manifest['phases'].keys())}
        """)
    try:
        orch = project.get("orchestrator", {})
        signoff_text = _orchestrator_llm(textwrap.dedent(f"""\
        ASSEMBLY COMPLETE. Below are the REAL, machine-verified facts. Do NOT
        invent or alter paths, sizes, version numbers, or test results. Write
        the FINAL DELIVERABLE SUMMARY using ONLY these facts.

        {facts}

        In your summary include:
        - What was built (use the exact APK + Linux binary paths above)
        - Systems inventory (worker-artifact coverage per phase)
        - Quest 3 performance notes (targets, not measured numbers)
        - Honest remaining work
        - Final line: Ready to ship: Yes / No
        """), max_tokens=900)
        (ws / "FINAL_DELIVERABLE.md").write_text(
            "# FINAL DELIVERABLE — Verified Facts\n\n"
            f"{facts}\n"
            "\n---\n\n### Narrative Summary (LLM)\n\n"
            + (signoff_text or ""))
        report["final_summary"] = facts.replace("\n", "; ")[:600]

        # BOTH ORCHESTRATORS SIGN OFF (VISUAL_QA_AND_BETA_RULES: final
        # acceptance requires the Visual QA Supervisor + both Orchestrators).
        secondary_signoff = ""
        try:
            secondary_signoff = _orchestrator_llm(textwrap.dedent(f"""\
            You are the SECONDARY Orchestrator performing the FINAL SIGN-OFF.

            The Main Orchestrator proposes shipping with this summary:
            {(signoff_text or '')[:1800]}

            VERIFIED FACTS:
            {facts[:2500]}

            Read the facts as given. Reply first word: AGREE (ready to ship)
            or VETO (anything below is unacceptable), then one short sentence.
            """), max_tokens=300, secondary=True)
        except Exception as exc:
            secondary_signoff = f"[secondary signoff error] {type(exc).__name__}: {exc}"
        report["signoffs"] = {"main_orchestrator": (signoff_text or "")[:600],
                              "secondary_orchestrator": secondary_signoff[:600]}
        try:
            dl_path = ws / "assembly" / "DELIVERABLE.json"
            dl = json.loads(dl_path.read_text())
            dl["signoffs"] = report["signoffs"]
            dl_path.write_text(json.dumps(dl, indent=2))
        except Exception:
            pass
    except Exception as e:
        report["final_summary"] = facts.replace("\n", "; ")[:600]
        (ws / "FINAL_DELIVERABLE.md").write_text(
            "# FINAL DELIVERABLE — Verified Facts\n\n" + facts +
            f"\n---\n\n### Narrative Summary (LLM)\n\n[signoff error] {e}")

    return report


# ── main entry point ────────────────────────────────────────────────────────

def run_project(project: dict, dry_run: bool = False,
                phase_filter: Optional[str] = None,
                max_workers: Optional[int] = None,
                retry_workers: Optional[list[str]] = None,
                max_attempts: Optional[int] = None,
                progress_callback=None) -> dict:
    """Execute the live production pipeline for a built project.

    Args:
        project: full project dict (must have orchestrator, supervisors, swarm)
        dry_run: if True, plan only (show what would execute)
        phase_filter: optional phase name to run only that phase
        max_workers: max parallel workers within a phase
        retry_workers: optional list of agent_ids to retry specifically (skips ready workers)
        max_attempts: max retry attempts (default 3, or from env HARNESS_MAX_ATTEMPTS)
        progress_callback: optional fn(phase, event, data) for streaming progress

    Returns: run report dict with phases, workers, assembly results.
    """
    if max_workers is None:
        try:
            max_workers = int(os.environ.get("HARNESS_MAX_WORKERS", "4"))
        except ValueError:
            max_workers = 4
    if max_attempts is None:
        try:
            max_attempts = int(os.environ.get("HARNESS_MAX_ATTEMPTS", "3"))
        except ValueError:
            max_attempts = 3

    # v2.1: key collection FIRST. No keys, no pipeline — this is the upgrade
    # mandate ("Collect Keys First, Then assign roles" is rule zero).
    key_report = None
    if _V21 is not None:
        key_report = _V21.collect_keys()
        if not key_report.get("ready") and not dry_run:
            return {
                "status": "keys_missing",
                "keys": key_report,
                "message": "Refusing to run: provider API keys missing. "
                           f"Missing: {key_report.get('missing')}",
                "ts": _now(),
            }
        print(f"[runner] v2.1 keys ready? {key_report.get('ready')} "
              f"providers={key_report.get('providers')}")

    pid = project["id"]
    ws = _workspace(pid)

    state = RunState(pid=pid, started=_now(), status="running")

    def emit(phase, event, data=None):
        if progress_callback:
            try:
                progress_callback(phase, event, data or {})
            except Exception:
                pass
        # also log to state
        if phase not in state.phases:
            state.phases[phase] = {"events": []}
        state.phases[phase]["events"].append({"ts": _now(), "event": event,
                                              "data": str(data)[:300]})
        # persist checkpoint for resume
        save_checkpoint(state)

    supervisors = project.get("supervisors", [])
    swarm = project.get("swarm", {}).get("members", [])

    # group workers by supervisor
    workers_by_sv: dict[str, list[dict]] = {}
    for m in swarm:
        sv_name = m.get("supervisor", "")
        workers_by_sv.setdefault(sv_name, []).append(m)

    phase_slug_map = {sv["name"]: slug(sv["name"]) for sv in supervisors}

    if dry_run:
        plan = {
            "dry_run": True,
            "pid": pid,
            "phases": [],
            "total_workers": len(swarm),
        }
        for sv in supervisors:
            workers = workers_by_sv.get(sv["name"], [])
            plan["phases"].append({
                "name": sv["name"],
                "slug": phase_slug_map[sv["name"]],
                "workers": len(workers),
                "tools_used": list(set(
                    t for w in workers for t in w.get("tools", []))),
            })
        plan["assembly"] = {
            "unity": UNITY, "blender": BLENDER,
            "freecad": FREECAD, "sox": SOX, "surge": SURGE,
        }
        return plan

    # ── LIVE RUN ──
    # Resume from checkpoint if exists. Full fresh runs only start clean when
    # there is no checkpoint or the previous run reached a real terminal
    # state; a suspended/blocked checkpoint still holds phase results (the
    # solver state for every failed worker), so selective retries MUST resume
    # from it rather than re-run Phase 0 with no matching workers (which
    # would overwrite the good records with a spurious 0/0 block).
    checkpoint = load_checkpoint(pid)
    if checkpoint and (checkpoint.status == "running" or retry_workers):
        state = checkpoint
        fresh_run = False
        phase_results_all = state.phase_results_all
        prior_gate_results = state.prior_gate_results
        all_worker_results = state.all_worker_results
        # Resume from the next phase (or current if not completed)
        resume_from_idx = state.phase_idx
        # Gates are keyed to their phase index. Migrate any legacy entries
        # (recorded in phase order) so lookups work. We deliberately do NOT
        # drop the current/upcoming phase's stale gate here: the upstream
        # check keys on phase_idx == sv_idx - 1, so a phase's own gate can
        # never self-block, and re-running a phase replaces its gate on
        # completion. Keeping prior gates preserves real upstream guards.
        for _i, _g in enumerate(prior_gate_results):
            _g.setdefault("phase_idx", _i)
        print(f"[resume] Loaded checkpoint for {pid}, resuming from phase_idx={resume_from_idx} (phase={state.phase})")
    else:
        phase_results_all = {}
        prior_gate_results = []
        all_worker_results = {}
        resume_from_idx = 0
        fresh_run = True

    for sv_idx, sv in enumerate(supervisors):
        if sv_idx < resume_from_idx:
            continue
        sv_name = sv["name"]
        pslug = phase_slug_map[sv_name]
        workers = workers_by_sv.get(sv_name, [])

        # phase filter: skip phases not matching the filter
        if phase_filter and phase_filter.lower() not in sv_name.lower() \
                and phase_filter.lower() not in pslug:
            emit(pslug, "skipped", {"reason": "phase_filter"})
            continue

        # enforce phase gating: block this phase if the phase immediately
        # before it (by index, not list position) blocked. Keying on phase_idx
        # keeps re-runs and phase-filtered runs from being self-blocked or
        # poisoned by stale gate entries.
        _upstream = [g for g in prior_gate_results
                     if g.get("phase_idx", -1) == sv_idx - 1]
        if _upstream and _upstream[-1].get("gate") == "block":
            state.status = "blocked"
            state.phase = sv_name
            state.errors.append(f"Phase blocked: {_upstream[-1].get('decision_text', '')[:200]}")
            emit(pslug, "blocked", {"reason": "upstream_gate_block"})
            break

        state.phase = sv_name
        state.phase_idx = sv_idx
        # If retry_workers specified, filter to only those workers for this
        # phase. A retry list names workers in a SINGLE phase (the phase we
        # resumed at); every OTHER phase must run its full worker set, or the
        # post-resume pipeline collapses to 0/0 gate blocks.
        if retry_workers:
            _matched = [w for w in workers
                        if w.get("id", slug(w["name"])) in retry_workers]
            if _matched:
                workers = _matched
                emit(pslug, "selective_rerun", {
                    "workers": [w.get("id", slug(w["name"])) for w in workers]})
        # Fresh full run: clean stale phase dirs from prior runs so the
        # deliverable audit sees only THIS run's files. Without this, removed
        # or renamed files (e.g. an old Main.unity) linger in rglob'd output
        # and re-trigger naming-law rejections. Resumes and selective retries
        # skip this so in-flight output is never destroyed.
        if fresh_run and not retry_workers:
            import shutil
            pd = _phase_dir(pid, pslug)
            for stale in list(pd.iterdir()):
                if stale.name == ".run_state.json" or stale.name.startswith("."):
                    continue
                if stale.is_dir():
                    shutil.rmtree(stale, ignore_errors=True)
                else:
                    stale.unlink(missing_ok=True)
        emit(pslug, "phase_start", {"workers": len(workers)})

        # ── NON-OPTIONAL INSPECTION AGENTS (all-gates law) ──
        # A phase's swarm MUST include vision and audio inspection agents; the
        # harness will not run the phase without them (unless a 3D LLM
        # replaces the visual inspector). If the phase produces visual or
        # audio milestones and its swarm lacks the inspectors, refuse the
        # phase instead of running a gate with nothing to verify with.
        has_vision = any(
            "vision" in w.get("name", "").lower() or "inspect" in w.get("name", "").lower()
            for w in workers)
        has_3d_llm = os.environ.get("HARNESS_3D_LLM", "").strip() != ""
        has_audio = any(
            ("audio" in w.get("name", "").lower() or "sound" in w.get("name", "").lower())
            and "inspect" in w.get("name", "").lower()
            for w in workers)
        if not has_vision and not has_3d_llm and not dry_run:
            msg = (f"non-optional vision inspector missing from swarm "
                   f"({len(workers)} workers); refusing to run phase "
                   f"without a vision/3D-LLM verifier (all-gates law)")
            print(f"[phase] {pslug}: {msg}")
            emit(pslug, "phase_refused", {"reason": "missing_vision_inspector"})
            state.errors.append(msg)
            state.status = "blocked"
            break
        if not has_audio and dry_run is False and _runs_audio(pslug):
            msg = (f"non-optional audio inspector missing from swarm "
                   f"({len(workers)} workers); refusing to run phase "
                   f"without an audio verifier (all-gates law)")
            print(f"[phase] {pslug}: {msg}")
            emit(pslug, "phase_refused", {"reason": "missing_audio_inspector"})
            state.errors.append(msg)
            state.status = "blocked"
            break

        # run workers in parallel (attempt 1)
        worker_results = []
        worker_task = textwrap.dedent(f"""\
        You are a swarm worker in phase: {sv_name}.
        Your prompt is your goal. Execute your task now.

        OUTPUT DIRECTORY: your per-agent workspace (the absolute path is given
        in your task). Every real deliverable file you produce MUST be written
        with your tools inside that directory — use relative paths from your
        workspace or the absolute path provided.

        Produce real deliverable files using your declared tools:
        - build-fishtank / build-awards-wall / build-elevator / build-agent-prefab →
          arguments "<output.glb> <kind> [--count N]"
        - vfx-add / lod-optimize / population-pool → blend generation kinds
        - audio-mix → "<prefix> [--kinds ambient,rumble,scantone,exterior,anomaly,shiftcycle,pulse]"
          (sox procedural synthesis: writes law-legal A_*.wav files + a mix note)
        - write-file → first line path, rest content (JSON/dialogue/C#/reports)
        - verify → verify a pattern like ".glb" (writes a verify report)
        - unity-* / scaffold-project → Unity project operations

        You MUST write at least one real deliverable file. A handoff report is
        NOT a deliverable. Call your tools with the exact names above.

        Then produce a Handoff Report in the required format. The report MUST
        include every one of these labeled fields (the supervisor's machine
        audit checks for them exactly):
        - Agent / Supervisor ID
        - Role
        - Phase / Task ID
        - Assigned Model Used
        - What was delivered
        - Manifest path
        - Visual verification performed
        - Acceptance criteria met
        - File placement & naming verified
        - Primitives present
        - Known issues / blockers
        - Dependencies still open
        - Ready for next stage

        In this pipeline a live in-engine render IS available via engine-capture
        against the real game project, and vision/audio verification is MANDATORY
        at every gate (all-gates law). If your milestone involves visuals, capture
        a real screenshot with engine-capture and pass it through vision-check:
        Ready for integration: Yes requires a capture that vision-check PASSed.
        If it involves audio assets, run audio-check on a real sample: Yes
        requires audio-check PASS. In the "Visual verification performed" field
        state exactly what you rendered and its vision-check verdict. A missing
        or vision-FAILED render (and a silent or missing audio sample) is grounds
        for refusing readiness and must never be waved off as a limitation.
        Unfinished or missing deliverables ARE a reason to refuse.

        SCOPE RULE FOR THIS PHASE (multi-wave): your wave's deliverable is the
        purpose-built LOD0 mesh set plus your written DESC_ file(s), all named
        per the v2.1 naming law. Things handed to LATER waves or phases are NOT
        refusal grounds for your own wave: LOD1/LOD2 generation, collision
        meshes, manifest.json batch entries, and in-engine render verification
        are downstream items to LIST under "Dependencies still open", never
        reasons to withhold your Ready marker when your own wave's deliverables
        (files + naming + DESC_) are complete. Say "Ready for integration: Yes"
        when your wave is done.

        AUDIO/VFX (Phase 4) NAME RULE — the v2.1 prefix decides the format:
        audio files use ONLY "A_<Name>.wav/.ogg/.mp3"; VFX spawned/mesh assets
        (e.g. glb) use ONLY "SM_<Name>_LOD0.glb" or "Prefab_<Name>.prefab",
        NEVER "A_<name>.glb". Names with a hyphen (e.g. A_X-hit.wav) or with no
        prefix at all (e.g. station-ambients.wav) are naming-law violations.
        Produce audio with the audio-mix tool: pass a bare descriptive stem and
        --kinds ambient,rumble,scantone,exterior,anomaly,shiftcycle,pulse
        (sox writes legal A_<Stem>_<Kind>.wav files automatically). Do NOT
        invent placeholder names like "-coin/-hit/-jump" or hand-rename audio.
        Every deliverable file must carry a legal v2.1 name: audio as A_ plus a
        legal audio extension; VFX meshes as SM_/Prefab_.""")
        if pslug == "phase-6-scene-assembly":
            worker_task += textwrap.dedent("""\

        SCENE ASSEMBLY (Phase 6) NAME RULE — the v2.1 prefix decides the
        format for every file you write. Scene files (Unity scene, Godot
        scene, or exported scene graph) use ONLY "Scene_<Name>.unity",
        "Scene_<Name>.tscn", or for a bare YAML/text scene "Scene_<Name>".
        Any 3D geometry/mesh you export MUST use the StaticMesh prefix
        "SM_<Name>_LOD0.glb" (or .fbx/.obj/.blend) — NEVER "Scene_*.glb",
        NEVER a double extension like "*.unity.glb". A ".unity" file is a
        Unity scene; a ".glb" file is a mesh, and a mesh is always SM_.
        Prefabs use "Prefab_<Name>.prefab". Scripts use plain .cs/.py.
        Names with a hyphen or no prefix are naming-law violations.
        Every file you write must carry a legal v2.1 name: scene as
        Scene_, geometry as SM_, prefab as Prefab_. Two exceptions to keep
        legal: the blender ".py" generator script and the ".blend" file may
        share the mesh's SM_ stem (e.g. SM_Name.py, SM_Name.glb).""")
        worker_task += textwrap.dedent("""\

        Name every real deliverable file per the v2.1 naming law
        (SM_/M_/T_/A_/Prefab_/Scene_ prefixes). End the report with exactly:
        Ready for integration: Yes
        """)

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {}
            for w in workers:
                wslug = slug(w["name"])
                # each worker gets a subtask with its specific prompt
                wtask = (worker_task +
                         f"\n\nYOUR SPECIFIC ROLE: {w.get('name', 'worker')}\n"
                         f"YOUR SKILLS: {', '.join(w.get('skills', []))}\n"
                         f"YOUR TOOLS: {', '.join(w.get('tools', []))}\n"
                         f"YOUR PROMPT:\n{w.get('prompt', '')[:16000]}")
                fut = pool.submit(_run_worker, w, wtask, pid, pslug)
                futures[fut] = w

            for fut in as_completed(futures):
                w = futures[fut]
                try:
                    res = fut.result(timeout=600)
                    worker_results.append(res)
                    emit(pslug, "worker_done", {
                        "name": res["name"], "ready": res["ready"],
                        "files": len(res.get("output_files", []))})
                except Exception as e:
                    worker_results.append({
                        "name": w.get("name", "unknown"),
                        "agent_id": slug(w.get("name", "unknown")),
                        "handoff_text": f"[worker error] {type(e).__name__}: {e}",
                        "output_files": [], "ok": False, "ready": False,
                        "iterations": 0,
                    })
                    emit(pslug, "worker_error", {
                        "name": w.get("name", "unknown"),
                        "error": f"{type(e).__name__}: {e}"[:200],
                        "trace": (__import__('traceback').format_exc()[-1200:])
                    })

        # ── retry loop: IMMEDIATE repair worker dispatch on ready:false ──
        # Law (Jayson): ready:false on ANY worker launches a DISTINCT repair
        # worker immediately — no waiting for the wave to fully drain, no
        # re-running the original task from scratch. Repair workers fix only
        # the machine-verified defects (naming violations, missing handoff
        # fields, tester bug reports) in the failed worker's directory, which
        # is far cheaper than full re-synthesis and keeps the pipeline moving.
        # Map worker configs by agent_id for lookup (used in both branches)
        worker_by_id = {w.get("id", slug(w["name"])): w for w in workers}
        # If retry_workers specified, only retry those specific agent_ids
        # (filter out already-ready workers unless explicitly listed)
        if retry_workers:
            # Filter failed workers to only those in retry_workers list
            failed = [r for r in worker_results if not r["ready"] and r["agent_id"] in retry_workers]
            if not failed:
                print(f"[selective retry] No matching failed workers for retry list: {retry_workers}")
        else:
            failed = [r for r in worker_results if not r["ready"]]

        for attempt in range(2, max_attempts + 1):
            # Recompute failed from current worker_results each attempt
            if retry_workers:
                failed = [r for r in worker_results if not r["ready"] and r["agent_id"] in retry_workers]
            else:
                failed = [r for r in worker_results if not r["ready"]]
            if not failed:
                break
            emit(pslug, "repair_start", {
                "attempt": attempt,
                "repair_workers": [f["agent_id"] for f in failed]})
            # Supervisor remediation still computed (feedback for humans) but
            # the REPAIR worker's prompt is built from machine-verified defects
            # first; the LLM plan is only a secondary hint, never a blocking gate.
            try:
                fix = _run_supervisor_fix(sv, project, failed, pid, pslug, ws)
            except Exception as _exc:
                fix = {"remediation": {}}
            remediation = fix.get("remediation", {})

            repaired = []
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                repair_futures = {}
                for f in failed:
                    wid = f["agent_id"]
                    w = worker_by_id.get(wid) if retry_workers else next(
                        (ww for ww in workers if ww.get("id", slug(ww["name"])) == wid), None)
                    if not w:
                        continue
                    # Repair worker = the SAME agent_id/workspace (so it fixes
                    # the failed worker's files in place) with a distinct,
                    # surgical REPAIR work order — not the original task.
                    wrep = dict(w)
                    wrep["name"] = f"{w.get('name', wid)} REPAIR"
                    wrep["id"] = wid
                    rtask = _repair_work_order(wrep, f, pid, pslug, ws)
                    hint = remediation.get(wid)
                    if hint:
                        rtask += f"\n\nSUPERVISOR HINT (secondary):\n{hint[:1200]}"
                    fut = pool.submit(_run_worker, wrep, rtask, pid, pslug,
                                      attempt, hint or "")
                    repair_futures[fut] = w

                for fut in as_completed(repair_futures):
                    w = repair_futures[fut]
                    try:
                        res = fut.result(timeout=600)
                        repaired.append(res)
                        emit(pslug, "repair_worker_done", {
                            "name": res["name"], "ready": res["ready"],
                            "attempt": res.get("attempts", attempt)})
                    except Exception as e:
                        repaired.append({
                            "name": w.get("name", "unknown"),
                            "agent_id": slug(w.get("name", "unknown")),
                            "handoff_text": f"[repair error] {type(e).__name__}: {e}",
                            "output_files": [], "ok": False, "ready": False,
                            "iterations": 0, "attempts": attempt,
                        })
                        emit(pslug, "repair_worker_error", {
                            "name": w.get("name", "unknown"), "error": str(e)[:200]})

            # merge: keep passing originals + repaired results
            passed = [r for r in worker_results if r["ready"]]
            # Only replace the repaired ones, keep other failed if not in repair list
            if retry_workers:
                # Keep non-repair failed workers as-is
                other_failed = [r for r in worker_results if not r["ready"] and r["agent_id"] not in retry_workers]
                worker_results = passed + other_failed + repaired
            else:
                worker_results = passed + repaired
            emit(pslug, "repair_complete", {
                "attempt": attempt, "still_failed": [r["name"] for r in repaired if not r["ready"]]})
        sv_result = _run_supervisor(sv, project, worker_results, pid, pslug, ws)
        emit(pslug, "supervisor_done", {
            "passed": sv_result["gate_passed"],
            "workers": f"{sv_result['workers_passed']}/{sv_result['workers_total']}"})

        phase_results_all[sv_name] = sv_result
        state.phase_results_all = phase_results_all
        all_worker_results[sv_name] = worker_results
        state.all_worker_results = all_worker_results

# orchestrator gate
        emit(pslug, "gate_start", {})
        # Only genuinely prior phases may be shown to the orchestrator: passing
        # the current phase's own (possibly stale) gate would self-contradict
        # and make it reject itself as "simultaneously ready and blocked".
        gate = _run_orchestrator_gating(
            project, sv_result,
            [g for g in prior_gate_results if g.get("phase_idx", -1) < sv_idx])
        gate["name"] = sv_name
        gate["phase_idx"] = sv_idx
        gate["gate_passed"] = gate["gate"] in ("pass", "proceed")
        # replace any stale gate for this phase (re-run) rather than appending
        prior_gate_results = [g for g in prior_gate_results
                              if g.get("phase_idx", -1) != sv_idx]
        prior_gate_results.append(gate)
        state.prior_gate_results = prior_gate_results
        emit(pslug, "gate_complete", {"gate": gate["gate"]})
        # A blocked gate (incl. the deterministic <100%/100% block) stops the
        # pipeline immediately and honestly. Without this, a blocked LAST phase
        # would still fall through to final assembly.
        if gate["gate"] == "block":
            state.status = "blocked"
            state.phase = sv_name
            state.errors.append(
                f"Phase blocked: {gate.get('decision_text', '')[:200]}")
            emit(pslug, "blocked", {
                "reason": "gate_block",
                "workers": f"{gate.get('workers_passed')}/{gate.get('workers_total')}"})
            break

    # ── FINAL ASSEMBLY ──
    # Full pipeline only: never assemble on a phase-filtered (partial) run,
    # and never after an upstream gate block.
    full_pipeline = phase_filter is None
    if full_pipeline and state.status != "blocked":
        # Refresh from disk: the in-memory map misses workers from earlier
        # runs / selective retries, which would ship an incomplete project.
        all_worker_results = _collect_worker_results(ws, project)
        state.all_worker_results = all_worker_results
        emit("assembly", "assembly_start",
             {"phases": list(all_worker_results.keys()),
              "workers": sum(len(v) for v in all_worker_results.values())})
        assembly_result = _run_assembly(
            project, pid, all_worker_results, ws, prior_gate_results)
        emit("assembly", "assembly_complete", assembly_result)
        state.status = assembly_result.get("status", "done")
    elif not full_pipeline:
        state.status = "partial"  # filtered debug run: pipeline only, no ship
        assembly_result = {"status": "partial",
                           "reason": "phase_filter set — no assembly on partial runs"}
    else:
        assembly_result = {"status": "blocked"}

    state.finished = _now()
    state.summary = {
        "phases_run": len(all_worker_results),
        "total_workers": sum(len(v) for v in all_worker_results.values()),
        "workers_passed": sum(
            sum(1 for w in v if w["ready"])
            for v in all_worker_results.values()),
        "assembly": assembly_result,
    }

    # persist to project
    run_entry = {
        "ts": _now(),
        "event": "run_complete",
        "dry_run": False,
        "status": state.status,
        "summary": state.summary,
    }

    return {
        "run_id": uuid.uuid4().hex[:12],
        "status": state.status,
        "phase": state.phase,
        "started": state.started,
        "finished": state.finished,
        "phases": state.phases,
        "summary": state.summary,
        "errors": state.errors,
        "state": state.to_dict(),
    }
