"""
Creates a basic layered hard-surface metal material with edge wear support.
Run in Blender. The material expects an Attribute named 'ATTR_WearMask' or uses pointiness.
"""

import bpy


def create_layered_metal(name="M_THR_Metal_Primary"):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # Clear default
    nodes.clear()

    # Output
    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (600, 0)

    # Principled
    principled = nodes.new("ShaderNodeBsdfPrincipled")
    principled.location = (300, 0)
    principled.inputs["Base Color"].default_value = (0.15, 0.16, 0.18, 1)
    principled.inputs["Metallic"].default_value = 1.0
    principled.inputs["Roughness"].default_value = 0.35

    # Color Ramp for wear
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.location = (-100, -150)
    ramp.color_ramp.elements[0].position = 0.4
    ramp.color_ramp.elements[1].position = 0.6

    # Geometry - Pointiness as fallback wear
    geom = nodes.new("ShaderNodeNewGeometry")
    geom.location = (-400, -150)

    # Mix for wear color (darker metal)
    mix = nodes.new("ShaderNodeMix")
    mix.data_type = 'RGBA'
    mix.location = (50, 100)
    mix.inputs["A"].default_value = (0.15, 0.16, 0.18, 1)  # base
    mix.inputs["B"].default_value = (0.05, 0.05, 0.05, 1)   # worn

    # Links
    links.new(geom.outputs["Pointiness"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], mix.inputs["Factor"])
    links.new(mix.outputs["Result"], principled.inputs["Base Color"])
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])

    print(f"Created material: {name}")
    print("Replace Pointiness with Attribute node reading 'ATTR_WearMask' for production.")
    return mat


if __name__ == "__main__":
    create_layered_metal()
