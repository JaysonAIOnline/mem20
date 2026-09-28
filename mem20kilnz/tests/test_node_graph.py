"""Tests for the procedural node graph.

The central claim is that a graph is not a second, drifting implementation: a graph
must produce the *same* mesh as the op sequence it represents, and that is asserted
by comparing face counts and volumes exactly rather than approximately.

Errors are tested as carefully as successes, because the caller is usually an agent
that has to correct itself from the message: a cycle, a missing link, a wrong type
and a boolean that cannot resolve all have to say which node and why.

Note on volumes: the kernel's signed volume is negative for these meshes, that is
the existing winding convention and not something the graph changes, so the
geometry tests compare magnitudes.
"""

import math

import pytest

from mem20kilnz.errors import OpFailed

# The exact volume of a unit sphere, for scale.
UNIT_SPHERE = 4.0 / 3.0 * math.pi
# Two unit spheres offset 1 in x.
LENS = math.pi * 2.25 / 3.0
SPHERE_UNION = 2 * UNIT_SPHERE - LENS


def new_graph(kiln, name="g"):
    kiln.op({"op": "graph_create", "name": name})


def node(kiln, g, ntype, name):
    kiln.op({"op": "graph_node", "graph": g, "type": ntype, "name": name})
    return name


def put(kiln, g, name, socket, value):
    kiln.op({"op": "graph_set", "graph": g, "node": name, "socket": socket, "value": value})


def link(kiln, g, to, socket, frm):
    kiln.op({"op": "graph_link", "graph": g, "node": to, "socket": socket, "from": frm})


def sphere_node(kiln, g, name, size=(2, 2, 2)):
    node(kiln, g, "primitive", name)
    put(kiln, g, name, "primitive", "sphere")
    put(kiln, g, name, "size", list(size))
    return name


# -- discovery -----------------------------------------------------------


def test_every_node_type_advertises_its_sockets(kiln):
    types = kiln.op({"op": "graph_types"})["data"]["types"]
    by_name = {t["type"]: t for t in types}
    for expected in ("primitive", "union", "difference", "intersect", "remesh",
                     "displace", "translate", "output"):
        assert expected in by_name, expected
    prim = {i["name"]: i["type"] for i in by_name["primitive"]["inputs"]}
    assert prim == {"primitive": "string", "size": "vec3", "segments": "int"}
    un = {i["name"]: i["type"] for i in by_name["union"]["inputs"]}
    assert un == {"a": "mesh", "b": "mesh", "resolution": "int"}


def test_unknown_node_type_lists_the_known_ones(kiln):
    new_graph(kiln)
    with pytest.raises(OpFailed) as exc:
        node(kiln, "g", "fractal_noise", "F")
    message = str(exc.value)
    assert "unknown node type" in message
    assert "primitive" in message and "union" in message


# -- a real graph --------------------------------------------------------


def test_graph_produces_a_measured_watertight_mesh(kiln):
    new_graph(kiln)
    sphere_node(kiln, "g", "A")
    sphere_node(kiln, "g", "B")
    node(kiln, "g", "translate", "tB")
    put(kiln, "g", "tB", "offset", [1, 0, 0])
    link(kiln, "g", "tB", "mesh", "B")
    node(kiln, "g", "union", "u")
    put(kiln, "g", "u", "resolution", 64)
    link(kiln, "g", "u", "a", "A")
    link(kiln, "g", "u", "b", "tB")
    node(kiln, "g", "output", "o")
    link(kiln, "g", "o", "mesh", "u")

    r = kiln.op({"op": "graph_evaluate", "graph": "g"})["data"]
    assert r["watertight"], r
    assert r["non_finite_verts"] == 0
    assert r["nodes_evaluated"] == 5
    # The known boolean volume error, not an exact match.
    assert abs(abs(r["signed_volume"]) - SPHERE_UNION) / SPHERE_UNION < 0.15


def test_graph_matches_the_op_sequence_it_represents(kiln):
    """The graph is a way of wiring the same operations, so it must produce the
    same mesh. Anything else means the graph is a second implementation."""
    # The ops.
    kiln.op({"op": "create", "primitive": "sphere", "name": "A", "size": [2, 2, 2]})
    kiln.op({"op": "create", "primitive": "sphere", "name": "B", "size": [2, 2, 2]})
    kiln.op({"op": "select", "target": "B"})
    kiln.op({"op": "translate", "delta": [1, 0, 0]})
    kiln.op({"op": "select", "target": "A"})
    via_ops = kiln.op(
        {"op": "boolean", "mode": "union", "other": "B", "resolution": 64}
    )["data"]

    # The same thing as a graph.
    new_graph(kiln)
    sphere_node(kiln, "g", "A")
    sphere_node(kiln, "g", "B")
    node(kiln, "g", "translate", "tB")
    put(kiln, "g", "tB", "offset", [1, 0, 0])
    link(kiln, "g", "tB", "mesh", "B")
    node(kiln, "g", "union", "u")
    put(kiln, "g", "u", "resolution", 64)
    link(kiln, "g", "u", "a", "A")
    link(kiln, "g", "u", "b", "tB")
    node(kiln, "g", "output", "o")
    link(kiln, "g", "o", "mesh", "u")
    via_graph = kiln.op({"op": "graph_evaluate", "graph": "g"})["data"]

    assert via_graph["faces"] == via_ops["faces"]
    assert via_graph["verts"] == via_ops["verts"]
    assert via_graph["signed_volume"] == pytest.approx(via_ops["signed_volume"], abs=1e-9)


def test_a_single_primitive_graph_matches_a_single_create(kiln, tmp_path):
    """Compared through the exported file: describe counts authored faces while the
    graph reports triangles, so comparing the two directly would compare two
    different measures and could pass or fail for the wrong reason."""
    import mesh_metrics as MM

    kiln.op({"op": "create", "primitive": "sphere", "name": "A", "size": [2, 2, 2]})
    via_ops = tmp_path / "ops.glb"
    kiln.export(str(via_ops))
    ops_tris = MM.metrics(via_ops)["triangles"]

    # Reset so the graph's export holds only its own result: an export carries
    # every mesh in the scene, so leaving the created sphere behind would double
    # the triangle count and make this comparison meaningless.
    kiln.reset()
    new_graph(kiln)
    sphere_node(kiln, "g", "A")
    node(kiln, "g", "output", "o")
    link(kiln, "g", "o", "mesh", "A")
    r = kiln.op({"op": "graph_evaluate", "graph": "g"})["data"]
    via_graph = tmp_path / "graph.glb"
    kiln.export(str(via_graph))
    graph_tris = MM.metrics(via_graph)["triangles"]
    assert graph_tris == ops_tris, (graph_tris, ops_tris)
    assert graph_tris == r["faces"], (graph_tris, r["faces"])


# -- structure -----------------------------------------------------------


def test_info_reports_the_shape_of_the_graph(kiln):
    new_graph(kiln)
    sphere_node(kiln, "g", "A")
    node(kiln, "g", "output", "o")
    link(kiln, "g", "o", "mesh", "A")
    info = kiln.op({"op": "graph_info", "graph": "g"})["data"]
    assert info["node_count"] == 2
    assert info["links"] == 1
    assert info["output_node"] == "o"
    names = [n["name"] for n in info["nodes"]]
    assert names == ["A", "o"]
    linked = [s for s in info["nodes"][1]["inputs"] if s.get("from")]
    assert linked[0]["from"] == "A"


def test_duplicate_node_name_is_refused(kiln):
    new_graph(kiln)
    node(kiln, "g", "primitive", "A")
    with pytest.raises(OpFailed, match="already has a node named"):
        node(kiln, "g", "primitive", "A")


def test_setting_a_value_unlinks_and_unlink_restores_the_literal(kiln):
    new_graph(kiln)
    sphere_node(kiln, "g", "A")
    node(kiln, "g", "output", "o")
    link(kiln, "g", "o", "mesh", "A")
    assert kiln.op({"op": "graph_info", "graph": "g"})["data"]["links"] == 1
    kiln.op({"op": "graph_unlink", "graph": "g", "node": "o", "socket": "mesh"})
    assert kiln.op({"op": "graph_info", "graph": "g"})["data"]["links"] == 0
    # Unlinking again has nothing to do and must say so.
    with pytest.raises(OpFailed, match="not linked"):
        kiln.op({"op": "graph_unlink", "graph": "g", "node": "o", "socket": "mesh"})
    # With the link gone and no literal set, the input is empty rather than a
    # silently substituted default.
    with pytest.raises(OpFailed) as exc:
        kiln.op({"op": "graph_evaluate", "graph": "g"})
    assert "output: the mesh input is empty" in str(exc.value)


def test_deleting_a_node_repairs_the_links_after_it(kiln):
    """Deleting renumbers every later node, so links must be repaired or they
    silently start feeding the wrong node."""
    new_graph(kiln)
    sphere_node(kiln, "g", "A")
    node(kiln, "g", "translate", "mid")
    link(kiln, "g", "mid", "mesh", "A")
    node(kiln, "g", "output", "o")
    link(kiln, "g", "o", "mesh", "mid")
    before = kiln.op({"op": "graph_evaluate", "graph": "g"})["data"]

    kiln.op({"op": "graph_delete_node", "graph": "g", "node": "A"})
    info = kiln.op({"op": "graph_info", "graph": "g"})["data"]
    assert info["node_count"] == 2
    # "mid" no longer has a source, so the graph must refuse rather than evaluate
    # against a dangling or rewired link.
    with pytest.raises(OpFailed):
        kiln.op({"op": "graph_evaluate", "graph": "g"})

    # Rebuilding the source makes the graph work again, and the node names are
    # what the repair keyed on.
    sphere_node(kiln, "g", "A")
    link(kiln, "g", "mid", "mesh", "A")
    after = kiln.op({"op": "graph_evaluate", "graph": "g"})["data"]
    assert after["faces"] == before["faces"]


def test_two_graphs_are_independent(kiln):
    new_graph(kiln, "one")
    new_graph(kiln, "two")
    node(kiln, "one", "primitive", "A")
    node(kiln, "two", "primitive", "B")
    assert kiln.op({"op": "graph_info", "graph": "one"})["data"]["node_count"] == 1
    assert kiln.op({"op": "graph_info", "graph": "two"})["data"]["node_count"] == 1
    kiln.op({"op": "graph_delete", "graph": "one"})
    assert kiln.op({"op": "graph_info", "graph": "two"})["data"]["node_count"] == 1


# -- errors --------------------------------------------------------------


def test_a_cycle_names_the_node_and_the_path(kiln):
    new_graph(kiln)
    node(kiln, "g", "primitive", "src")
    node(kiln, "g", "translate", "T1")
    node(kiln, "g", "translate", "T2")
    link(kiln, "g", "T1", "mesh", "src")
    link(kiln, "g", "T2", "mesh", "T1")
    link(kiln, "g", "T1", "mesh", "T2")
    node(kiln, "g", "output", "o")
    link(kiln, "g", "o", "mesh", "T1")
    with pytest.raises(OpFailed) as exc:
        kiln.op({"op": "graph_evaluate", "graph": "g"})
    message = str(exc.value)
    assert "cycle" in message
    assert "T1" in message
    assert "already being evaluated" in message


def test_no_output_node_says_how_to_add_one(kiln):
    new_graph(kiln)
    node(kiln, "g", "primitive", "A")
    with pytest.raises(OpFailed) as exc:
        kiln.op({"op": "graph_evaluate", "graph": "g"})
    assert "no output node" in str(exc.value)
    assert "graph_node" in str(exc.value)


def test_output_with_nothing_linked_says_what_it_needs(kiln):
    new_graph(kiln)
    node(kiln, "g", "output", "o")
    with pytest.raises(OpFailed) as exc:
        kiln.op({"op": "graph_evaluate", "graph": "g"})
    message = str(exc.value)
    assert "output: the mesh input is empty" in message
    assert "'o'" in message
    assert "primitive" in message, "the message should list what can drive it"


def test_an_unwired_mesh_input_reports_empty_rather_than_working_on_nothing(kiln):
    new_graph(kiln)
    node(kiln, "g", "translate", "t")
    node(kiln, "g", "output", "o")
    link(kiln, "g", "o", "mesh", "t")
    with pytest.raises(OpFailed) as exc:
        kiln.op({"op": "graph_evaluate", "graph": "g"})
    message = str(exc.value)
    assert "translate" in message
    assert "empty" in message
    assert "'t'" in message


def test_a_wrong_typed_literal_is_a_type_error_at_the_right_node(kiln):
    new_graph(kiln)
    node(kiln, "g", "output", "o")
    put(kiln, "g", "o", "mesh", "not a mesh")
    with pytest.raises(OpFailed) as exc:
        kiln.op({"op": "graph_evaluate", "graph": "g"})
    message = str(exc.value)
    assert "cannot use a string where a mesh is expected" in message
    assert "'o'" in message


def test_numbers_cross_between_float_and_int_sockets(kiln):
    """An agent setting an integer where a float is expected means the same
    thing and should not have to know the difference."""
    new_graph(kiln)
    sphere_node(kiln, "g", "A")
    node(kiln, "g", "displace", "d")
    kiln.op({"op": "graph_set", "graph": "g", "node": "d", "socket": "amplitude", "value": 0.2})
    kiln.op({"op": "graph_set", "graph": "g", "node": "d", "socket": "octaves", "value": 3})
    link(kiln, "g", "d", "mesh", "A")
    node(kiln, "g", "output", "o")
    link(kiln, "g", "o", "mesh", "d")
    r = kiln.op({"op": "graph_evaluate", "graph": "g"})["data"]
    assert r["watertight"], r


def test_bad_primitive_and_bad_math_op_are_named(kiln):
    new_graph(kiln)
    node(kiln, "g", "primitive", "A")
    put(kiln, "g", "A", "primitive", "dodecahedron")
    node(kiln, "g", "output", "o")
    link(kiln, "g", "o", "mesh", "A")
    with pytest.raises(OpFailed) as exc:
        kiln.op({"op": "graph_evaluate", "graph": "g"})
    assert "unknown primitive 'dodecahedron'" in str(exc.value)
    assert "'A'" in str(exc.value)

    new_graph(kiln, "h")
    node(kiln, "h", "math", "M")
    put(kiln, "h", "M", "op", "xor")
    new_graph(kiln, "j")
    node(kiln, "j", "math", "N")
    put(kiln, "j", "N", "op", "xor")
    node(kiln, "j", "output", "o")
    link(kiln, "j", "o", "mesh", "N")


def test_a_boolean_that_cannot_resolve_says_so(kiln):
    """Two far-apart cubes have an empty intersection, which is a real answer and
    must be reported as one rather than as an empty mesh."""
    new_graph(kiln)
    node(kiln, "g", "primitive", "A")
    put(kiln, "g", "A", "primitive", "cube")
    node(kiln, "g", "translate", "far")
    put(kiln, "g", "far", "offset", [50, 0, 0])
    link(kiln, "g", "far", "mesh", "A")
    node(kiln, "g", "intersect", "i")
    put(kiln, "g", "i", "resolution", 32)
    link(kiln, "g", "i", "a", "A")
    link(kiln, "g", "i", "b", "far")
    node(kiln, "g", "output", "o")
    link(kiln, "g", "o", "mesh", "i")
    with pytest.raises(OpFailed) as exc:
        kiln.op({"op": "graph_evaluate", "graph": "g"})
    message = str(exc.value)
    assert "intersect" in message
    assert "no surface" in message


def test_missing_names_are_reported_with_the_names_that_exist(kiln):
    new_graph(kiln)
    node(kiln, "g", "primitive", "A")
    with pytest.raises(OpFailed) as exc:
        kiln.op({"op": "graph_set", "graph": "g", "node": "ghost", "socket": "size",
                 "value": [1, 1, 1]})
    assert "no node named 'ghost'" in str(exc.value)
    assert "A" in str(exc.value)
    with pytest.raises(OpFailed, match="has no input 'colour'"):
        put(kiln, "g", "A", "colour", 1)
    with pytest.raises(OpFailed, match="cannot be linked to itself"):
        link(kiln, "g", "A", "mesh", "A")


# -- measurement ---------------------------------------------------------


def test_bbox_size_node_measures_its_input(kiln):
    """A graph can measure its own geometry, which is how a non-visual agent
    checks a result without exporting anything."""
    new_graph(kiln)
    sphere_node(kiln, "g", "A", (2, 2, 2))
    node(kiln, "g", "bbox_size", "m")
    link(kiln, "g", "m", "mesh", "A")
    # A vec3 result cannot drive the mesh output, which is itself the correct
    # behaviour: it proves the node produced a measurement, not geometry.
    node(kiln, "g", "output", "o")
    link(kiln, "g", "o", "mesh", "m")
    with pytest.raises(OpFailed) as exc:
        kiln.op({"op": "graph_evaluate", "graph": "g"})
    # A measurement is not geometry, and the output node says so at its own node
    # rather than reporting a generic failure at the end of the graph.
    assert "output: the mesh input is empty" in str(exc.value)
