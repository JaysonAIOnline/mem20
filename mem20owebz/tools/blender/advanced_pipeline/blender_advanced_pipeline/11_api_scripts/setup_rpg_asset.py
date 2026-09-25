"""
One-click setup for a new RPG asset.
Creates collections, root empty, and basic custom properties.
"""

import bpy

def setup_rpg_asset(prefix="NEW", asset_name="Prop"):
    # Collections
    root_name = f"COL_{prefix}_Root"
    children = [f"COL_{prefix}_{s}" for s in ["High", "Low", "Cutters", "GN_Details", "Cages", "Export"]]

    if root_name not in bpy.data.collections:
        root = bpy.data.collections.new(root_name)
        bpy.context.scene.collection.children.link(root)
    else:
        root = bpy.data.collections[root_name]

    for name in children:
        if name not in bpy.data.collections:
            col = bpy.data.collections.new(name)
            root.children.link(col)

    # Root Empty
    empty_name = f"{prefix}_{asset_name}_Root"
    if empty_name in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects[empty_name], do_unlink=True)

    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0))
    empty = bpy.context.active_object
    empty.name = empty_name
    empty.empty_display_size = 0.3

    empty["prop_scale"] = 1.0
    empty["prop_detail_density"] = 1.0
    empty["prop_wear_amount"] = 0.3
    empty["prop_version"] = "v001"
    empty["prop_type"] = "RPG"

    # Link empty to root collection
    for col in list(empty.users_collection):
        col.objects.unlink(empty)
    root.objects.link(empty)

    print(f"RPG asset setup complete: {empty_name}")


if __name__ == "__main__":
    setup_rpg_asset(prefix="BOW", asset_name="Longbow")
