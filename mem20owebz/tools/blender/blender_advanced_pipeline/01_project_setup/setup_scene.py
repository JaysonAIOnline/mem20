"""
Advanced Blender Pipeline - Scene Setup Script
Run inside Blender (Scripting workspace → Run Script)
Creates correct units, collections, root empty, and custom properties.
"""

import bpy

def clear_scene():
    """Optional: remove default objects"""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)


def set_units():
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = 'METERS'
    # Clip
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.clip_start = 0.01
                    space.clip_end = 1000.0


def create_collections():
    root_name = "COL_THR_Root"
    children = [
        "COL_THR_High",
        "COL_THR_Low",
        "COL_THR_Cutters",
        "COL_THR_GN_Details",
        "COL_THR_Cages",
        "COL_THR_References",
        "COL_THR_Export",
    ]

    # Create root
    if root_name not in bpy.data.collections:
        root = bpy.data.collections.new(root_name)
        bpy.context.scene.collection.children.link(root)
    else:
        root = bpy.data.collections[root_name]

    for name in children:
        if name not in bpy.data.collections:
            col = bpy.data.collections.new(name)
            root.children.link(col)
        else:
            col = bpy.data.collections[name]
            if col.name not in [c.name for c in root.children]:
                root.children.link(col)


def create_root_empty():
    # Remove existing if present
    if "THR_Thruster_Root" in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects["THR_Thruster_Root"], do_unlink=True)

    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0))
    empty = bpy.context.active_object
    empty.name = "THR_Thruster_Root"
    empty.empty_display_size = 0.5

    # Custom properties
    empty["prop_scale"] = 1.0
    empty["prop_detail_density"] = 1.0
    empty["prop_wear_amount"] = 0.35
    empty["prop_version"] = "v001"
    empty["prop_artist"] = "YourName"

    # Move to root collection
    for col in empty.users_collection:
        col.objects.unlink(empty)
    bpy.data.collections["COL_THR_Root"].objects.link(empty)


def main():
    print("=== Advanced Thruster Pipeline Setup ===")
    # clear_scene()  # uncomment if you want a completely clean file
    set_units()
    create_collections()
    create_root_empty()
    print("Setup complete. Collections and root empty created.")
    print("Remember to save as THR_Thruster_Assembly_v001.blend")


if __name__ == "__main__":
    main()
