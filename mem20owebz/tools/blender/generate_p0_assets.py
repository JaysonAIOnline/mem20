"""
Generate P0 assets for The Unreliable Prophecy using Blender Advanced Pipeline
Run inside Blender background mode.
All assets generated in one scene, then exported individually.
"""

import bpy
import os
from pathlib import Path

# Output directory
OUTPUT_DIR = Path("/home/jayson/Desktop/jayson-openwebui/projects/unreliable_prophecy/art")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def clear_scene():
    """Delete everything and start clean."""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for block in bpy.data.meshes:
        bpy.data.meshes.remove(block)
    for block in bpy.data.materials:
        bpy.data.materials.remove(block)
    for block in bpy.data.collections:
        if block.name != "Scene Collection":
            bpy.data.collections.remove(block)

def setup_base_collections():
    """Create the standard collection hierarchy."""
    main_col = bpy.data.collections.new("UP_Assets")
    bpy.context.scene.collection.children.link(main_col)
    
    cols = {}
    for name in ['characters', 'creatures', 'props', 'weapons', 'environments', 'materials', 'export']:
        cols[name] = bpy.data.collections.new(name.title() if name != 'export' else "COL_UP_Export")
        main_col.children.link(cols[name])
    
    return cols

def create_material(name, color, metallic=0.0, roughness=0.5, emission=0.0):
    """Create a Principled BSDF material."""
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if emission > 0:
        bsdf.inputs["Emission Strength"].default_value = emission
        bsdf.inputs["Emission Color"].default_value = (*color, 1.0)
    return mat

def link_to_collection(obj, collection):
    """Link object to a collection."""
    for col in obj.users_collection:
        col.objects.unlink(obj)
    collection.objects.link(obj)

def create_primitive(primitive_type, name, location, scale, rotation):
    """Create a primitive."""
    if primitive_type == "CUBE":
        bpy.ops.mesh.primitive_cube_add(location=location, scale=scale, rotation=rotation)
    elif primitive_type == "SPHERE":
        bpy.ops.mesh.primitive_uv_sphere_add(location=location, scale=scale, rotation=rotation)
    elif primitive_type == "CYLINDER":
        bpy.ops.mesh.primitive_cylinder_add(location=location, scale=scale, rotation=rotation)
    elif primitive_type == "CONE":
        bpy.ops.mesh.primitive_cone_add(location=location, scale=scale, rotation=rotation)
    elif primitive_type == "PLANE":
        bpy.ops.mesh.primitive_plane_add(location=location, scale=scale, rotation=rotation)
    
    obj = bpy.context.active_object
    obj.name = name
    return obj

def assign_material(obj, material):
    """Assign material to object."""
    if obj.data.materials:
        obj.data.materials[0] = material
    else:
        obj.data.materials.append(material)

def export_glb(name, objects):
    """Export specific objects to GLB."""
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    
    filepath = str(OUTPUT_DIR / f"{name}.glb")
    bpy.ops.export_scene.gltf(
        filepath=filepath,
        use_selection=True,
        export_format='GLB',
        export_apply=True,
        export_texcoords=True,
        export_normals=True,
        export_materials='EXPORT',
        export_yup=True,
    )
    print(f"Exported {filepath}")

# ============================================================
# MAIN GENERATION - ALL IN ONE SCENE
# ============================================================

clear_scene()
cols = setup_base_collections()

# ---- MATERIALS ----
print("Creating materials...")
mat_parchment = create_material("MAT_Parchment", (0.92, 0.88, 0.78), metallic=0.0, roughness=0.9)
mat_wood = create_material("MAT_Wood", (0.45, 0.30, 0.18), metallic=0.0, roughness=0.7)
mat_metal_stamp = create_material("MAT_MetalStamp", (0.55, 0.55, 0.58), metallic=0.9, roughness=0.3)
mat_ink = create_material("MAT_Ink", (0.05, 0.03, 0.08), metallic=0.0, roughness=0.3, emission=0.1)
mat_skin = create_material("MAT_Skin", (0.95, 0.78, 0.65), metallic=0.0, roughness=0.6)
mat_robe = create_material("MAT_Robe", (0.25, 0.20, 0.35), metallic=0.0, roughness=0.8)
mat_robe_cynical = create_material("MAT_Robe_Cynical", (0.15, 0.12, 0.25), metallic=0.0, roughness=0.85)
mat_bureaucrat = create_material("MAT_Bureaucrat", (0.40, 0.35, 0.30), metallic=0.1, roughness=0.6)
mat_bone = create_material("MAT_Bone", (0.85, 0.80, 0.70), metallic=0.0, roughness=0.5)
mat_ink_creature = create_material("MAT_InkCreature", (0.02, 0.01, 0.05), metallic=0.0, roughness=0.2, emission=0.15)

# Save materials library
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_DIR / "materials" / "UP_Materials.blend"))

# ============================================================
# CHARACTER: CH_PC1 (Player)
# ============================================================
print("Generating CH_PC1...")
body = create_primitive("CYLINDER", "CH_PC1_Body", (0, 0, 1.0), (0.4, 0.4, 1.8), (0, 0, 0))
assign_material(body, mat_skin)
link_to_collection(body, cols['characters'])

head = create_primitive("SPHERE", "CH_PC1_Head", (0, 0, 2.3), (0.35, 0.35, 0.35), (0, 0, 0))
assign_material(head, mat_skin)
link_to_collection(head, cols['characters'])
head.parent = body

export_glb("CH_PC1", [body, head])

# ============================================================
# CHARACTER: CH_Wizard (Old Wizard)
# ============================================================
print("Generating CH_Wizard...")
body = create_primitive("CYLINDER", "CH_Wizard_Body", (5, 0, 1.0), (0.35, 0.35, 1.6), (0, 0, 0))
assign_material(body, mat_robe_cynical)
link_to_collection(body, cols['characters'])

head = create_primitive("SPHERE", "CH_Wizard_Head", (5, 0, 2.1), (0.3, 0.3, 0.3), (0, 0, 0))
assign_material(head, mat_skin)
link_to_collection(head, cols['characters'])
head.parent = body

staff = create_primitive("CYLINDER", "CH_Wizard_Staff", (4.5, 0, 1.5), (0.05, 0.05, 2.0), (0, 0, 0))
assign_material(staff, mat_wood)
link_to_collection(staff, cols['props'])

export_glb("CH_Wizard", [body, head, staff])

# ============================================================
# CHARACTER: CH_Companion2 (Placeholder)
# ============================================================
print("Generating CH_Companion2...")
body = create_primitive("CYLINDER", "CH_Companion2_Body", (10, 0, 1.0), (0.4, 0.4, 1.7), (0, 0, 0))
assign_material(body, mat_robe)
link_to_collection(body, cols['characters'])

head = create_primitive("SPHERE", "CH_Companion2_Head", (10, 0, 2.2), (0.33, 0.33, 0.33), (0, 0, 0))
assign_material(head, mat_skin)
link_to_collection(head, cols['characters'])
head.parent = body

export_glb("CH_Companion2", [body, head])

# ============================================================
# CHARACTER: CH_Bureaucrat
# ============================================================
print("Generating CH_Bureaucrat...")
body = create_primitive("CYLINDER", "CH_Bureaucrat_Body", (15, 0, 1.0), (0.35, 0.35, 1.7), (0, 0, 0))
assign_material(body, mat_bureaucrat)
link_to_collection(body, cols['characters'])

head = create_primitive("SPHERE", "CH_Bureaucrat_Head", (15, 0, 2.2), (0.3, 0.3, 0.3), (0, 0, 0))
assign_material(head, mat_skin)
link_to_collection(head, cols['characters'])
head.parent = body

export_glb("CH_Bureaucrat", [body, head])

# ============================================================
# CREATURE: CR_MisfiledSkeleton
# ============================================================
print("Generating CR_MisfiledSkeleton...")
torso = create_primitive("CUBE", "CR_MisfiledSkeleton_Torso", (0, 5, 1.2), (0.4, 0.25, 0.6), (0, 0, 0))
assign_material(torso, mat_bone)
link_to_collection(torso, cols['creatures'])

head = create_primitive("SPHERE", "CR_MisfiledSkeleton_Head", (0, 5, 1.8), (0.25, 0.25, 0.25), (0, 0, 0))
assign_material(head, mat_bone)
link_to_collection(head, cols['creatures'])
head.parent = torso

arm_l = create_primitive("CYLINDER", "CR_MisfiledSkeleton_Arm_L", (-0.5, 5, 1.3), (0.08, 0.08, 0.6), (0, 1.57, 0))
assign_material(arm_l, mat_bone)
link_to_collection(arm_l, cols['creatures'])
arm_l.parent = torso

arm_r = create_primitive("CYLINDER", "CR_MisfiledSkeleton_Arm_R", (0.5, 5, 1.3), (0.08, 0.08, 0.6), (0, 1.57, 0))
assign_material(arm_r, mat_bone)
link_to_collection(arm_r, cols['creatures'])
arm_r.parent = torso

leg_l = create_primitive("CYLINDER", "CR_MisfiledSkeleton_Leg_L", (-0.15, 5, 0.4), (0.1, 0.1, 0.8), (0, 0, 0))
assign_material(leg_l, mat_bone)
link_to_collection(leg_l, cols['creatures'])
leg_l.parent = torso

leg_r = create_primitive("CYLINDER", "CR_MisfiledSkeleton_Leg_R", (0.15, 5, 0.4), (0.1, 0.1, 0.8), (0, 0, 0))
assign_material(leg_r, mat_bone)
link_to_collection(leg_r, cols['creatures'])
leg_r.parent = torso

export_glb("CR_MisfiledSkeleton", [torso, head, arm_l, arm_r, leg_l, leg_r])

# ============================================================
# CREATURE: CR_InkBlot
# ============================================================
print("Generating CR_InkBlot...")
blob = create_primitive("SPHERE", "CR_InkBlot_Main", (5, 5, 0.5), (0.6, 0.6, 0.4), (0, 0, 0))
assign_material(blob, mat_ink_creature)
link_to_collection(blob, cols['creatures'])

blob2 = create_primitive("SPHERE", "CR_InkBlot_Sub1", (5.5, 5.3, 0.3), (0.3, 0.3, 0.25), (0, 0, 0))
assign_material(blob2, mat_ink_creature)
link_to_collection(blob2, cols['creatures'])
blob2.parent = blob

blob3 = create_primitive("SPHERE", "CR_InkBlot_Sub2", (4.6, 4.7, 0.2), (0.25, 0.25, 0.2), (0, 0, 0))
assign_material(blob3, mat_ink_creature)
link_to_collection(blob3, cols['creatures'])
blob3.parent = blob

export_glb("CR_InkBlot", [blob, blob2, blob3])

# ============================================================
# PROP: PR_Binder
# ============================================================
print("Generating PR_Binder...")
cover = create_primitive("CUBE", "PR_Binder_Cover", (10, 5, 0.05), (0.25, 0.18, 0.03), (0, 0, 0))
assign_material(cover, mat_parchment)
link_to_collection(cover, cols['props'])

pages = create_primitive("CUBE", "PR_Binder_Pages", (10, 5, 0.01), (0.23, 0.16, 0.02), (0, 0, 0))
assign_material(pages, mat_parchment)
link_to_collection(pages, cols['props'])
pages.parent = cover

stamp = create_primitive("CYLINDER", "PR_Binder_Stamp", (10.1, 5, 0.04), (0.04, 0.04, 0.02), (0, 0, 0))
assign_material(stamp, mat_metal_stamp)
link_to_collection(stamp, cols['props'])
stamp.parent = cover

export_glb("PR_Binder", [cover, pages, stamp])

# ============================================================
# PROP: PR_FilingCabinet
# ============================================================
print("Generating PR_FilingCabinet...")
body = create_primitive("CUBE", "PR_FilingCabinet_Body", (15, 5, 0.7), (0.35, 0.45, 0.7), (0, 0, 0))
assign_material(body, mat_metal_stamp)
link_to_collection(body, cols['props'])

for i in range(4):
    y = -0.38 + i * 0.25
    drawer = create_primitive("CUBE", f"PR_FilingCabinet_Drawer_{i}", (15, 5 + y, -0.5 + i * 0.35), (0.33, 0.05, 0.3), (0, 0, 0))
    assign_material(drawer, mat_metal_stamp)
    link_to_collection(drawer, cols['props'])
    drawer.parent = body
    
    handle = create_primitive("CYLINDER", f"PR_FilingCabinet_Handle_{i}", (15.2, 5 + y, -0.5 + i * 0.35), (0.02, 0.02, 0.1), (1.57, 0, 0))
    assign_material(handle, mat_metal_stamp)
    link_to_collection(handle, cols['props'])
    handle.parent = drawer

export_glb("PR_FilingCabinet", [body] + [bpy.data.objects[f"PR_FilingCabinet_Drawer_{i}"] for i in range(4)] + [bpy.data.objects[f"PR_FilingCabinet_Handle_{i}"] for i in range(4)])

# ============================================================
# PROP: PR_Desk
# ============================================================
print("Generating PR_Desk...")
top = create_primitive("CUBE", "PR_Desk_Top", (20, 5, 0.75), (0.8, 0.5, 0.05), (0, 0, 0))
assign_material(top, mat_wood)
link_to_collection(top, cols['props'])

legs = []
for x in (-0.7, 0.7):
    for y in (-0.4, 0.4):
        leg = create_primitive("CYLINDER", f"PR_Desk_Leg_{x}_{y}", (20 + x, 5 + y, 0.35), (0.05, 0.05, 0.7), (0, 0, 0))
        assign_material(leg, mat_wood)
        link_to_collection(leg, cols['props'])
        leg.parent = top
        legs.append(leg)

export_glb("PR_Desk", [top] + legs)

# ============================================================
# PROP: PR_Forms (stack)
# ============================================================
print("Generating PR_Forms...")
forms = []
for i in range(5):
    form = create_primitive("CUBE", f"PR_Forms_Form_{i}", (25, 5, 0.01 + i * 0.005), (0.21, 0.15, 0.003), (0, 0, 0))
    assign_material(form, mat_parchment)
    link_to_collection(form, cols['props'])
    if i > 0:
        form.parent = bpy.data.objects["PR_Forms_Form_0"]
    forms.append(form)

export_glb("PR_Forms", forms)

# ============================================================
# WEAPON: WP_BasicMelee
# ============================================================
print("Generating WP_BasicMelee...")
blade = create_primitive("CUBE", "WP_BasicMelee_Blade", (0, 10, 0.5), (0.04, 0.08, 0.6), (0, 0, 0))
assign_material(blade, mat_metal_stamp)
link_to_collection(blade, cols['weapons'])

hilt = create_primitive("CYLINDER", "WP_BasicMelee_Hilt", (0, 10, -0.1), (0.05, 0.05, 0.15), (0, 0, 0))
assign_material(hilt, mat_wood)
link_to_collection(hilt, cols['weapons'])
hilt.parent = blade

guard = create_primitive("CUBE", "WP_BasicMelee_Guard", (0, 10, 0.2), (0.15, 0.03, 0.03), (0, 0, 0))
assign_material(guard, mat_metal_stamp)
link_to_collection(guard, cols['weapons'])
guard.parent = blade

export_glb("WP_BasicMelee", [blade, hilt, guard])

# ============================================================
# ENVIRONMENT: ENV_Quietvale (modular pieces)
# ============================================================
print("Generating ENV_Quietvale...")
quietvale_parts = []

ground = create_primitive("PLANE", "ENV_Quietvale_Ground", (0, 10, 0), (10, 10, 1), (0, 0, 0))
assign_material(ground, mat_wood)
link_to_collection(ground, cols['environments'])
quietvale_parts.append(ground)

house = create_primitive("CUBE", "ENV_Quietvale_House", (0, 10, 1.5), (3, 2.5, 1.5), (0, 0, 0))
assign_material(house, mat_wood)
link_to_collection(house, cols['environments'])
quietvale_parts.append(house)

roof = create_primitive("CONE", "ENV_Quietvale_Roof", (0, 10, 3.5), (3.2, 3.2, 2), (0, 0, 0))
assign_material(roof, mat_wood)
link_to_collection(roof, cols['environments'])
roof.parent = house
quietvale_parts.append(roof)

gate_l = create_primitive("CYLINDER", "ENV_Quietvale_Gate_L", (-2, 10, 1.5), (0.3, 0.3, 3), (0, 0, 0))
assign_material(gate_l, mat_metal_stamp)
link_to_collection(gate_l, cols['environments'])
quietvale_parts.append(gate_l)

gate_r = create_primitive("CYLINDER", "ENV_Quietvale_Gate_R", (2, 10, 1.5), (0.3, 0.3, 3), (0, 0, 0))
assign_material(gate_r, mat_metal_stamp)
link_to_collection(gate_r, cols['environments'])
quietvale_parts.append(gate_r)

path = create_primitive("PLANE", "ENV_Quietvale_Path", (0, 5, 0.01), (2, 10, 1), (0, 0, 0))
assign_material(path, mat_parchment)
link_to_collection(path, cols['environments'])
quietvale_parts.append(path)

tree_trunk = create_primitive("CYLINDER", "ENV_Quietvale_Tree_Trunk", (5, 15, 1), (0.4, 0.4, 2), (0, 0, 0))
assign_material(tree_trunk, mat_wood)
link_to_collection(tree_trunk, cols['environments'])
quietvale_parts.append(tree_trunk)

tree_leaves = create_primitive("SPHERE", "ENV_Quietvale_Tree_Leaves", (5, 15, 3.5), (1.5, 1.5, 1.5), (0, 0, 0))
assign_material(tree_leaves, mat_robe)
link_to_collection(tree_leaves, cols['environments'])
tree_leaves.parent = tree_trunk
quietvale_parts.append(tree_leaves)

export_glb("ENV_Quietvale", quietvale_parts)

# ============================================================
# ENVIRONMENT: ENV_Hills (modular pieces)
# ============================================================
print("Generating ENV_Hills...")
hills_parts = []

ground = create_primitive("PLANE", "ENV_Hills_Ground", (0, 20, 0), (10, 10, 1), (0, 0, 0))
assign_material(ground, mat_parchment)
link_to_collection(ground, cols['environments'])
hills_parts.append(ground)

for i in range(3):
    for j in range(2):
        cab = create_primitive("CUBE", f"ENV_Hills_Cabinet_{i}_{j}", (i*2-2, 20 + j*2-1, 0.7), (0.35, 0.45, 0.7), (0, 0, 0))
        assign_material(cab, mat_metal_stamp)
        link_to_collection(cab, cols['environments'])
        hills_parts.append(cab)

for i in range(2):
    desk = create_primitive("CUBE", f"ENV_Hills_Desk_{i}", (i*4-2, 24, 0.75), (0.8, 0.5, 0.05), (0, 0, 0))
    assign_material(desk, mat_wood)
    link_to_collection(desk, cols['environments'])
    hills_parts.append(desk)
    for x in (-0.7, 0.7):
        for y in (-0.4, 0.4):
            leg = create_primitive("CYLINDER", f"ENV_Hills_Desk_{i}_Leg_{x}_{y}", (i*4-2+x, 24+y, 0.35), (0.05, 0.05, 0.7), (0, 0, 0))
            assign_material(leg, mat_wood)
            link_to_collection(leg, cols['environments'])
            leg.parent = desk
            hills_parts.append(leg)

path = create_primitive("PLANE", "ENV_Hills_Path", (0, 15, 0.01), (2, 10, 1), (0, 0, 0))
assign_material(path, mat_parchment)
link_to_collection(path, cols['environments'])
hills_parts.append(path)

export_glb("ENV_Hills", hills_parts)

print("ALL P0 ASSETS GENERATED SUCCESSFULLY")