"""
Batch rename selected objects with a prefix and optional numbering.
"""

import bpy

def batch_rename(prefix="OBJ_", start_number=1, padding=2):
    selected = bpy.context.selected_objects
    if not selected:
        print("Nothing selected")
        return

    for i, obj in enumerate(sorted(selected, key=lambda o: o.name), start=start_number):
        new_name = f"{prefix}{str(i).zfill(padding)}"
        print(f"{obj.name} → {new_name}")
        obj.name = new_name
        if obj.data:
            obj.data.name = new_name


if __name__ == "__main__":
    batch_rename(prefix="SWD_Part_", start_number=1)
