"""
Python script that creates a basic Geometry Nodes group for rivet scattering.
Run inside Blender (Scripting workspace).

This generates a usable starting point. Refine the node tree visually afterward.
"""

import bpy

def create_rivet_scatter_group():
    # Create new node group
    group = bpy.data.node_groups.new("GN_Detail_Rivets_Basic", "GeometryNodeTree")
    
    # Interface
    group.interface.new_socket(name="Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    dens = group.interface.new_socket(name="Density", in_out='INPUT', socket_type='NodeSocketFloat')
    dens.default_value = 10.0
    scale = group.interface.new_socket(name="Rivet Scale", in_out='INPUT', socket_type='NodeSocketFloat')
    scale.default_value = 0.015
    group.interface.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')

    nodes = group.nodes
    links = group.links

    # Nodes
    input_node = nodes.new("NodeGroupInput")
    input_node.location = (-400, 0)

    output_node = nodes.new("NodeGroupOutput")
    output_node.location = (600, 0)

    # Distribute Points on Faces
    distribute = nodes.new("GeometryNodeDistributePointsOnFaces")
    distribute.location = (-150, 100)
    distribute.distribute_method = 'POISSON_DISK'
    # Note: density input linked later

    # Instance on Points
    instance = nodes.new("GeometryNodeInstanceOnPoints")
    instance.location = (150, 0)

    # Ico Sphere as simple rivet (user should replace with real rivet object)
    ico = nodes.new("GeometryNodeMeshIcoSphere")
    ico.location = (-150, -150)
    ico.inputs["Radius"].default_value = 1.0
    ico.inputs["Subdivisions"].default_value = 1

    # Scale Instances
    scale_inst = nodes.new("GeometryNodeScaleInstances")
    scale_inst.location = (350, 0)

    # Join
    join = nodes.new("GeometryNodeJoinGeometry")
    join.location = (500, 50)

    # Links
    links.new(input_node.outputs["Geometry"], distribute.inputs["Mesh"])
    links.new(input_node.outputs["Density"], distribute.inputs["Density"])
    links.new(distribute.outputs["Points"], instance.inputs["Points"])
    links.new(ico.outputs["Mesh"], instance.inputs["Instance"])
    links.new(instance.outputs["Instances"], scale_inst.inputs["Instances"])
    links.new(input_node.outputs["Rivet Scale"], scale_inst.inputs["Scale"])
    links.new(input_node.outputs["Geometry"], join.inputs[0])
    links.new(scale_inst.outputs["Instances"], join.inputs[0])  # will auto-create multi-input
    links.new(join.outputs["Geometry"], output_node.inputs["Geometry"])

    print("Created Geometry Node group: GN_Detail_Rivets_Basic")
    print("Replace the Ico Sphere with a real rivet object via Object Info node for production use.")
    return group


if __name__ == "__main__":
    create_rivet_scatter_group()
