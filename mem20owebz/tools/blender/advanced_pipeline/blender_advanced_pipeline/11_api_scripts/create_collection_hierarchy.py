"""
Create a standard pipeline collection hierarchy for any asset prefix.
Example: run with prefix "SWD" to create COL_SWD_Root and children.
"""

import bpy

def create_hierarchy(prefix="ASSET"):
    root_name = f"COL_{prefix}_Root"
    children = [
        f"COL_{prefix}_High",
        f"COL_{prefix}_Low",
        f"COL_{prefix}_Cutters",
        f"COL_{prefix}_GN_Details",
        f"COL_{prefix}_Cages",
        f"COL_{prefix}_References",
        f"COL_{prefix}_Export",
    ]

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

    print(f"Hierarchy created for prefix: {prefix}")


if __name__ == "__main__":
    # Change this prefix as needed
    create_hierarchy("SWD")
