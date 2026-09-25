# Blender Python API (bpy) Scripts & Automation

This folder contains practical production scripts that go beyond the basic helpers.

## Scripts Included
- `batch_rename.py` – Enforce naming conventions across selected objects
- `apply_all_modifiers.py` – Safe apply with backup
- `create_collection_hierarchy.py` – Instant standard pipeline collections for any prefix
- `attribute_to_vertex_group.py` – Convert GN attributes for further use
- `export_selected_lods.py` – Export multiple LODs at once
- `setup_rpg_asset.py` – One-click starter for a new RPG prop (collections + root empty + basic properties)

## How to Use
1. Open Scripting workspace in Blender
2. Open the .py file or paste into Text Editor
3. Run Script
4. Most scripts operate on selected objects or active object

## Extending
These are starting points. You can turn any of them into a proper add-on with a `bl_info` block and register functions.
