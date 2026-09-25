"""
Helper: Quickly turn a selected Bezier Curve into a Screw-based mesh setup.
Run with a curve selected.
"""

import bpy


def setup_screw_from_curve():
    obj = bpy.context.active_object
    if not obj or obj.type != 'CURVE':
        print("Select a Curve object first")
        return

    # Ensure good curve settings
    obj.data.dimensions = '2D'  # change to 3D if needed
    obj.data.resolution_u = 12
    obj.data.render_resolution_u = 12

    # Add Screw modifier
    mod = obj.modifiers.new(name="Screw", type='SCREW')
    mod.axis = 'Z'
    mod.steps = 32
    mod.render_steps = 64
    mod.screw_offset = 0.0
    mod.use_normal_flip = False
    mod.use_smooth_shade = True

    # Add Subdivision for preview
    sub = obj.modifiers.new(name="Subdivision", type='SUBSURF')
    sub.levels = 1
    sub.render_levels = 2

    print(f"Screw setup applied to {obj.name}. Adjust profile in Edit Mode.")


if __name__ == "__main__":
    setup_screw_from_curve()
