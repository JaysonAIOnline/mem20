"""
Export helper for glTF (game engines).
Select the root empty or the export collection objects before running.
"""

import bpy
import os

def export_thruster_gltf(output_path="//exports/THR_Thruster_Assembly_LOD0.glb"):
    # Ensure absolute path relative to blend file
    blend_dir = bpy.path.abspath("//")
    full_path = os.path.join(blend_dir, "exports")
    os.makedirs(full_path, exist_ok=True)
    
    filepath = os.path.join(full_path, "THR_Thruster_Assembly_LOD0.glb")

    # Select only objects in COL_THR_Export or selected
    bpy.ops.object.select_all(action='DESELECT')
    
    export_col = bpy.data.collections.get("COL_THR_Export")
    if export_col:
        for obj in export_col.objects:
            obj.select_set(True)
    else:
        # fallback to selected
        pass

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
    print(f"Exported to {filepath}")


if __name__ == "__main__":
    export_thruster_gltf()
