"""
LOD Generation Helper
Creates simple Decimate-based LODs from the active object.
For hero assets, prefer manual retopology for LOD0/LOD1.
"""

import bpy


def create_lods(obj=None, ratios=(0.5, 0.25, 0.1)):
    if obj is None:
        obj = bpy.context.active_object
    if not obj or obj.type != 'MESH':
        print("Select a mesh object first")
        return

    base_name = obj.name
    collection = obj.users_collection[0] if obj.users_collection else bpy.context.scene.collection

    for i, ratio in enumerate(ratios, start=1):
        # Duplicate
        new_obj = obj.copy()
        new_obj.data = obj.data.copy()
        new_obj.name = f"{base_name}_LOD{i}"
        collection.objects.link(new_obj)

        # Add Decimate
        mod = new_obj.modifiers.new(name=f"Decimate_LOD{i}", type='DECIMATE')
        mod.ratio = ratio
        mod.use_collapse_triangulate = True

        # Optionally apply immediately (comment out to keep non-destructive)
        # bpy.context.view_layer.objects.active = new_obj
        # bpy.ops.object.modifier_apply(modifier=mod.name)

        print(f"Created {new_obj.name} with ratio {ratio}")


if __name__ == "__main__":
    create_lods()
