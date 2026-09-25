"""
CAD Integration Layer for Blender Advanced Pipeline
Uses OpenCASCADE (OCP), SolveSpace, OpenSCAD, VMTK via Python bindings
Generates exact mechanical GLBs for bureaucratic aesthetic
"""

import subprocess
import tempfile
import os
import json
from pathlib import Path
from typing import Optional, Dict, Any

# Output directory
OUTPUT_DIR = Path("/home/jayson/Desktop/jayson-openwebui/projects/unreliable_prophecy/art")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def run_cmd(cmd: list, cwd: Optional[str] = None, timeout: int = 60) -> dict:
    """Run command and return result."""
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "timeout"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================
# OPENCASCADE (OCP) - Exact B-rep mechanical parts
# ============================================================

def occt_available() -> bool:
    """Check if OCP is available."""
    try:
        import OCP
        return True
    except ImportError:
        return False


def create_occt_filing_cabinet(output_path: str, params: Dict = None) -> dict:
    """Create exact filing cabinet with drawer slides, lips, handle recesses."""
    if not occt_available():
        return {"success": False, "error": "OCP not available"}
    
    params = params or {}
    width = params.get("width", 0.45)
    depth = params.get("depth", 0.55)
    height = params.get("height", 0.7)
    drawer_count = params.get("drawers", 4)
    wall_thickness = params.get("wall_thickness", 0.02)
    fillet_radius = params.get("fillet_radius", 0.005)
    
    script = """import sys
sys.path.insert(0, "/usr/lib/python3/dist-packages")

from OCP.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Ax1, gp_Ax2, gp_Pln
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse, BRepAlgoAPI_Cut
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeThickSolid
from OCP.TopoDS import TopoDS_Shape, TopoDS_Face
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone
from OCP.StlAPI import StlAPI_Writer
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.gp import gp_Trsf
import math

# Parameters
W, D, H = {width}, {depth}, {height}
DRAWERS = {drawer_count}
WT = {wall_thickness}
FILLET = {fillet_radius}

# Create outer cabinet box
outer = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), W, D, H).Shape()

# Create inner void (hollow out)
inner = BRepPrimAPI_MakeBox(
    gp_Pnt(WT, WT, WT), 
    W - 2*WT, D - 2*WT, H - WT
).Shape()

# Cabinet shell = outer - inner
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
shell = BRepAlgoAPI_Cut(outer, inner).Shape()

# Fillet vertical edges
fillet = BRepFilletAPI_MakeFillet(shell)
exp = TopExp_Explorer(shell, TopAbs_EDGE)
while exp.More():
    edge = exp.Current()
    # Convert to Edge
    from OCP.TopoDS import TopoDS
    edge = TopoDS.Edge(edge)
    fillet.Add(FILLET, edge)
    exp.Next()
shell = fillet.Shape()

# Drawer cutouts
drawer_h = (H - WT) / DRAWERS
for i in range(DRAWERS):
    z = WT + i * drawer_h + 0.002  # Small gap
    drawer_void = BRepPrimAPI_MakeBox(
        gp_Pnt(WT + 0.01, WT, z),
        W - 2*WT - 0.02, D - WT - 0.01, drawer_h - 0.004
    ).Shape()
    shell = BRepAlgoAPI_Cut(shell, drawer_void).Shape()

# Drawer fronts (separate pieces)
drawers = []
for i in range(DRAWERS):
    z = WT + i * drawer_h + 0.002
    front = BRepPrimAPI_MakeBox(
        gp_Pnt(WT - 0.005, D - WT - 0.01, z),
        W - 2*WT + 0.01, WT + 0.01, drawer_h - 0.004
    ).Shape()
    # Fillet front edges
    f = BRepFilletAPI_MakeFillet(front)
    exp2 = TopExp_Explorer(front, TopAbs_EDGE)
    while exp2.More():
        edge = exp2.Current()
        from OCP.TopoDS import TopoDS
        edge = TopoDS.Edge(edge)
        f.Add(FILLET * 2, edge)
        exp2.Next()
    drawers.append(f.Shape())

# Handle cutouts on drawer fronts
for i, drawer in enumerate(drawers):
    z = WT + i * drawer_h + 0.002 + (drawer_h - 0.004) / 2
    handle = BRepPrimAPI_MakeBox(
        gp_Pnt(W/2 - 0.04, D - WT - 0.015, z - 0.015),
        0.08, WT + 0.02, 0.03
    ).Shape()
    drawer = BRepAlgoAPI_Cut(drawer, handle).Shape()
    drawers[i] = drawer

# Base feet
feet = []
for x, y in [(0.05, 0.05), (W-0.05, 0.05), (0.05, D-0.05), (W-0.05, D-0.05)]:
    foot = BRepPrimAPI_MakeBox(gp_Pnt(x-0.02, y-0.02, -0.01), 0.04, 0.04, 0.015).Shape()
    feet.append(foot)

# Fuse everything
from functools import reduce
all_parts = [shell] + drawers + feet
result = reduce(lambda a, b: BRepAlgoAPI_Fuse(a, b).Shape(), all_parts)

# Export STL
mesh = BRepMesh_IncrementalMesh(result, 0.001)
stl_writer = StlAPI_Writer()
stl_writer.Write(result, "{output_path}")
print("OK: OCCT filing cabinet generated")
""".format(
        width=width, depth=depth, height=height,
        drawer_count=drawer_count, wall_thickness=wall_thickness, fillet_radius=fillet_radius,
        output_path=output_path
    )
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(script)
        script_path = f.name
    
    try:
        result = run_cmd(["/usr/bin/python3", script_path], timeout=120)
        os.unlink(script_path)
        return result
    except Exception as e:
        if os.path.exists(script_path):
            os.unlink(script_path)
        return {"success": False, "error": str(e)}


def create_occt_stamp_mechanism(output_path: str, params: Dict = None) -> dict:
    """Create stamp with spring cavity, die holder, ink pad recess."""
    if not occt_available():
        return {"success": False, "error": "OCP not available"}
    
    params = params or {}
    body_dia = params.get("body_dia", 0.04)
    body_h = params.get("body_h", 0.08)
    die_dia = params.get("die_dia", 0.03)
    die_h = params.get("die_h", 0.01)
    spring_cavity = params.get("spring_cavity", True)
    
    script = """import sys
sys.path.insert(0, "/usr/lib/python3/dist-packages")

from OCP.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Ax2
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse, BRepAlgoAPI_Cut
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.TopoDS import TopoDS_Shape
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_EDGE
from OCP.StlAPI import StlAPI_Writer
from OCP.BRepMesh import BRepMesh_IncrementalMesh

BD, BH = {body_dia}, {body_h}
DD, DH = {die_dia}, {die_h}
R = BD / 2

# Main body cylinder
body = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), R, BH).Shape()

# Die cavity at bottom
die_cut = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), DD/2, DH).Shape()
body = BRepAlgoAPI_Cut(body, die_cut).Shape()

# Spring cavity
if {spring_cavity}:
    spring = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, DH), gp_Dir(0, 0, 1)), R*0.6, BH - DH - 0.005).Shape()
    body = BRepAlgoAPI_Cut(body, spring).Shape()

# Top cap (removable)
cap = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, BH), gp_Dir(0, 0, 1)), R, 0.005).Shape()
body = BRepAlgoAPI_Fuse(body, cap).Shape()

# Fillet top and bottom edges
fillet = BRepFilletAPI_MakeFillet(body)
exp = TopExp_Explorer(body, TopAbs_EDGE)
while exp.More():
    edge = exp.Current()
    from OCP.TopoDS import TopoDS
    edge = TopoDS.Edge(edge)
    fillet.Add(0.002, edge)
    exp.Next()
body = fillet.Shape()

# Export
mesh = BRepMesh_IncrementalMesh(body, 0.0005)
stl_writer = StlAPI_Writer()
stl_writer.Write(body, "{output_path}")
print("OK: OCCT stamp mechanism generated")
""".format(
        body_dia=body_dia, body_h=body_h, die_dia=die_dia, die_h=die_h,
        spring_cavity=spring_cavity, output_path=output_path
    )
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(script)
        script_path = f.name
    
    try:
        result = run_cmd(["/usr/bin/python3", script_path], timeout=60)
        os.unlink(script_path)
        return result
    except Exception as e:
        if os.path.exists(script_path):
            os.unlink(script_path)
        return {"success": False, "error": str(e)}


def create_occt_parametric_rivet(output_path: str, params: Dict = None) -> dict:
    """Parametric rivet: shank, head (round/flat/countersunk), fillets."""
    if not occt_available():
        return {"success": False, "error": "OCP not available"}
    
    params = params or {}
    shank_dia = params.get("shank_dia", 0.006)
    shank_len = params.get("shank_len", 0.012)
    head_dia = params.get("head_dia", 0.01)
    head_h = params.get("head_h", 0.003)
    head_type = params.get("head_type", "round")
    
    script = """import sys
sys.path.insert(0, "/usr/lib/python3/dist-packages")

from OCP.gp import gp_Pnt, gp_Vec, gp_Ax2
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.TopoDS import TopoDS_Shape
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_EDGE
from OCP.StlAPI import StlAPI_Writer
from OCP.BRepMesh import BRepMesh_IncrementalMesh

SD, SL = {shank_dia}, {shank_len}
HD, HH = {head_dia}, {head_h}
HT = "{head_type}"

# Shank
shank = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 0), gp_Vec(0, 0, 1)), SD/2, SL).Shape()

# Head
if HT == "round":
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeSphere
    head = BRepPrimAPI_MakeSphere(gp_Ax2(gp_Pnt(0, 0, SL), gp_Vec(0, 0, 1)), HD/2).Shape()
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    cut_box = BRepPrimAPI_MakeBox(gp_Pnt(-HD, -HD, SL), HD*2, HD*2, HD).Shape()
    head = BRepAlgoAPI_Cut(head, cut_box).Shape()
elif HT == "flat":
    head = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, SL), gp_Vec(0, 0, 1)), HD/2, HH).Shape()
else:
    pass

# Fuse
body = BRepAlgoAPI_Fuse(shank, head).Shape()

# Fillet shank-to-head junction
fillet = BRepFilletAPI_MakeFillet(body)
exp = TopExp_Explorer(body, TopAbs_EDGE)
while exp.More():
    fillet.Add(0.0005, exp.Current())
    exp.Next()
body = fillet.Shape()

# Export
mesh = BRepMesh_IncrementalMesh(body, 0.0002)
stl_writer = StlAPI_Writer()
stl_writer.Write(body, "{output_path}")
print("OK: OCCT rivet generated")
""".format(
        shank_dia=shank_dia, shank_len=shank_len,
        head_dia=head_dia, head_h=head_h, head_type=head_type,
        output_path=output_path
    )
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(script)
        script_path = f.name
    
    try:
        result = run_cmd(["/usr/bin/python3", script_path], timeout=60)
        os.unlink(script_path)
        return result
    except Exception as e:
        if os.path.exists(script_path):
            os.unlink(script_path)
        return {"success": False, "error": str(e)}


# ============================================================
# SOLVESPACE - Constraint-driven parametric parts
# ============================================================

def solvespace_available() -> bool:
    return run_cmd(["solvespace-cli", "--version"]).get("success", False)


def createspace_filing_cabinet(output_path: str, params: Dict = None) -> dict:
    if not solvespace_available():
        return {"success": False, "error": "solvespace-cli not found"}
    
    params = params or {}
    slvs_content = generate_slvs_filing_cabinet(params)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.slvs', delete=False) as f:
        f.write(slvs_content)
        slvs_path = f.name
    
    try:
        result = run_cmd(["solvespace-cli", "--export-stl", output_path.replace('.glb', '.stl'), slvs_path])
        os.unlink(slvs_path)
        if result.get("success"):
            return convert_stl_to_glb(output_path.replace('.glb', '.stl'), output_path)
        return result
    except Exception as e:
        if os.path.exists(slvs_path):
            os.unlink(slvs_path)
        return {"success": False, "error": str(e)}


def generate_slvs_filing_cabinet(params: Dict) -> str:
    return """(solvespace
  (version 2)
  (units mm)
  (group
    (type sketch)
    (plane 0 0 1 0)
    (entity line 0 0 {} 0)
    (entity line {} 0 {} {})
    (entity line {} {} 0 {})
    (entity line 0 {} 0 0)
    (constraint equal-length 0 1)
    (constraint equal-length 1 2)
    (constraint perpendicular 0 1)
  )
  (group
    (type extrude)
    (length {})
  )
)""".format(
        params.get('width', 450), params.get('width', 450), params.get('depth', 550),
        params.get('width', 450), params.get('depth', 550), params.get('depth', 550),
        params.get('height', 700)
    )


# ============================================================
# OPENSCAD - Script-based CSG
# ============================================================

def openscad_available() -> bool:
    return run_cmd(["openscad", "--version"]).get("success", False)


def openscad_filing_cabinet(output_path: str, params: Dict = None) -> dict:
    if not openscad_available():
        return {"success": False, "error": "openscad not found"}
    
    params = params or {}
    scad_script = """// Filing Cabinet - Parametric
width = {width};
depth = {depth};
height = {height};
wall = {wall_thickness};
drawers = {drawers};
fillet_r = {fillet_radius};

module cabinet_body() {{
    difference() {{
        cube([width, depth, height]);
        translate([wall, wall, wall])
            cube([width - 2*wall, depth - 2*wall, height - wall]);
    }}
}}

module drawer_fronts() {{
    dh = (height - wall) / drawers;
    for (i = [0:drawers-1]) {{
        translate([wall - 5, depth - wall - 1, wall + i*dh + 2]) {{
            difference() {{
                cube([width - 2*wall + 10, wall + 1, dh - 4]);
                translate([width/2 - 40, -1, (dh - 30)/2])
                    cube([80, wall + 3, 30]);
            }}
        }}
    }}
}}

module feet() {{
    for (x = [50, width - 50], y = [50, depth - 50]) {{
        translate([x - 20, y - 20, -10])
            cube([40, 40, 15]);
    }}
}}

module label_holders() {{
    dh = (height - wall) / drawers;
    for (i = [0:drawers-1]) {{
        translate([width/2 - 50, wall + 5, wall + i*dh + 10])
            cube([100, 10, 15]);
    }}
}}

cabinet_body();
drawer_fronts();
feet();
label_holders();
""".format(
        width=params.get("width", 450), depth=params.get("depth", 550),
        height=params.get("height", 700), wall_thickness=params.get("wall_thickness", 20),
        drawers=params.get("drawers", 4), fillet_radius=params.get("fillet_radius", 5)
    )
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.scad', delete=False) as f:
        f.write(scad_script)
        scad_path = f.name
    
    stl_path = output_path.replace('.glb', '.stl')
    try:
        result = run_cmd(["openscad", "-o", stl_path, scad_path], timeout=60)
        os.unlink(scad_path)
        if result.get("success"):
            return convert_stl_to_glb(stl_path, output_path)
        return result
    except Exception as e:
        if os.path.exists(scad_path):
            os.unlink(scad_path)
        return {"success": False, "error": str(e)}


def openscad_stamp_mechanism(output_path: str, params: Dict = None) -> dict:
    if not openscad_available():
        return {"success": False, "error": "openscad not found"}
    
    params = params or {}
    scad_script = """// Bureaucrat Stamp Mechanism
body_dia = {body_dia};
body_h = {body_h};
die_dia = {die_dia};
die_h = {die_h};
wall = 3;

module stamp_body() {{
    difference() {{
        cylinder(d=body_dia, h=body_h, $fn=64);
        translate([0, 0, die_h])
            cylinder(d=body_dia - 2*wall, h=body_h - die_h - wall, $fn=64);
        cylinder(d=die_dia, h=die_h + 1, $fn=64);
        translate([0, 0, die_h + 5])
            cylinder(d=body_dia*0.6, h=body_h - die_h - 15, $fn=64);
    }}
}}

module top_cap() {{
    translate([0, 0, body_h])
        cylinder(d=body_dia, h=5, $fn=64);
}}

stamp_body();
top_cap();
""".format(
        body_dia=params.get("body_dia", 40),
        body_h=params.get("body_h", 80),
        die_dia=params.get("die_dia", 30),
        die_h=params.get("die_h", 10)
    )
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.scad', delete=False) as f:
        f.write(scad_script)
        scad_path = f.name
    
    stl_path = output_path.replace('.glb', '.stl')
    try:
        result = run_cmd(["openscad", "-o", stl_path, scad_path], timeout=60)
        os.unlink(scad_path)
        if result.get("success"):
            return convert_stl_to_glb(stl_path, output_path)
        return result
    except Exception as e:
        if os.path.exists(scad_path):
            os.unlink(scad_path)
        return {"success": False, "error": str(e)}


# ============================================================
# VMTK - Cable/hose routing
# ============================================================

def vmtk_available() -> bool:
    try:
        import vmtk
        return True
    except ImportError:
        return False


def vmtk_cable_routing(output_path: str, params: Dict = None) -> dict:
    if not vmtk_available():
        return {"success": False, "error": "VMTK not available"}
    return create_spline_cables(output_path, params)


def create_spline_cables(output_path: str, params: Dict = None) -> dict:
    params = params or {}
    start = params.get("start", (0, 0, 0))
    end = params.get("end", (1, 0, 0))
    control_points = params.get("control_points", [])
    radius = params.get("radius", 0.01)
    
    script = """import bpy
from mathutils import Vector

# Clear
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Create curve
curve_data = bpy.data.curves.new('Cable', 'CURVE')
curve_data.dimensions = '3D'
curve_data.resolution_u = 12
curve_data.fill_mode = 'FULL'
curve_data.bevel_depth = {radius}
curve_data.bevel_resolution = 8

spline = curve_data.splines.new('BEZIER')
points = {points}
spline.bezier_points.add(len(points) - 1)

for i, pt in enumerate(points):
    bp = spline.bezier_points[i]
    bp.co = Vector(pt)
    bp.handle_left_type = 'AUTO'
    bp.handle_right_type = 'AUTO'

obj = bpy.data.objects.new('Cable', curve_data)
bpy.context.collection.objects.link(obj)

# Export
bpy.ops.export_scene.gltf(
    filepath=r"{output_path}",
    export_format='GLB',
    export_apply=True
)
print("OK: Cable generated")
""".format(
        radius=params.get("radius", 0.01),
        points=str([start] + params.get("control_points", []) + [end]),
        output_path=output_path
    )
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(script)
        script_path = f.name
    
    try:
        result = run_cmd(["blender", "--background", "--python", script_path], timeout=60)
        os.unlink(script_path)
        return result
    except Exception as e:
        if os.path.exists(script_path):
            os.unlink(script_path)
        return {"success": False, "error": str(e)}


# ============================================================
# STL -> GLB Conversion (via Blender)
# ============================================================

def convert_stl_to_glb(stl_path: str, glb_path: str) -> dict:
    script = """import bpy
import os

# Enable STL import addon
bpy.ops.preferences.addon_enable(module="io_mesh_stl")

# Clear
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Import STL
bpy.ops.import_mesh.stl(filepath=r"{stl_path}")

obj = bpy.context.active_object
if obj:
    obj.name = os.path.basename("{glb_path}").replace(".glb", "")
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project()
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.shade_smooth()

bpy.ops.export_scene.gltf(
    filepath=r"{glb_path}",
    export_format='GLB',
    export_apply=True,
    export_texcoords=True,
    export_normals=True,
    export_materials='EXPORT',
    export_yup=True
)
print("OK: Converted to GLB")
""".format(stl_path=stl_path, glb_path=glb_path)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(script)
        script_path = f.name
    
    try:
        result = run_cmd(["blender", "--background", "--python", script_path], timeout=60)
        os.unlink(script_path)
        return result
    except Exception as e:
        if os.path.exists(script_path):
            os.unlink(script_path)
        return {"success": False, "error": str(e)}


# ============================================================
# MAIN: cad_to_glb.py CLI
# ============================================================

def cad_to_glb(
    part_type: str,
    output_path: str,
    params: Dict = None,
    engine: str = "auto"
) -> dict:
    """Main entry point: Generate GLB from parametric definition."""
    params = params or {}
    
    if engine == "auto":
        if part_type in ["filing_cabinet", "stamp_mechanism", "rivet", "desk", "binder"]:
            if occt_available():
                engine = "occt"
            elif openscad_available():
                engine = "openscad"
            elif solvespace_available():
                engine = "solvespace"
            else:
                return {"success": False, "error": "No CAD engine available"}
        elif part_type == "cable":
            if vmtk_available():
                engine = "vmtk"
            else:
                engine = "blender_spline"
        else:
            return {"success": False, "error": "Unknown part type: " + part_type}
    
    print("Generating " + part_type + " via " + engine + " -> " + output_path)
    
    generators = {
        ("filing_cabinet", "occt"): create_occt_filing_cabinet,
        ("filing_cabinet", "openscad"): openscad_filing_cabinet,
        ("filing_cabinet", "solvespace"): createspace_filing_cabinet,
        ("stamp_mechanism", "occt"): create_occt_stamp_mechanism,
        ("stamp_mechanism", "openscad"): openscad_stamp_mechanism,
        ("rivet", "occt"): create_occt_parametric_rivet,
        ("cable", "vmtk"): vmtk_cable_routing,
        ("cable", "blender_spline"): create_spline_cables,
    }
    
    gen = generators.get((part_type, engine))
    if not gen:
        return {"success": False, "error": "No generator for " + part_type + " with " + engine}
    
    result = gen(output_path, params)
    
    if result.get("success") and os.path.exists(output_path):
        size = os.path.getsize(output_path)
        result["output_size"] = size
        print("Generated " + output_path + " (" + str(size) + " bytes)")
    elif result.get("success"):
        result["success"] = False
        result["error"] = "Output file not created"
    
    return result


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="CAD -> GLB Generator")
    parser.add_argument("part_type", choices=["filing_cabinet", "stamp_mechanism", "rivet", "cable", "desk", "binder"])
    parser.add_argument("output", help="Output GLB path")
    parser.add_argument("--engine", default="auto", choices=["auto", "occt", "openscad", "solvespace", "vmtk", "blender_spline"])
    parser.add_argument("--params", help="JSON params")
    
    args = parser.parse_args()
    
    params = json.loads(args.params) if args.params else {}
    result = cad_to_glb(args.part_type, args.output, params, args.engine)
    
    print(json.dumps(result, indent=2))
    exit(0 if result.get("success") else 1)