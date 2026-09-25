"""Behavioural tests for mem20-orchestration.

These assert against the real captured catalog, not a fixture, so a corrupted
or truncated catalog fails here rather than silently validating bad plans.
"""

from __future__ import annotations

import json

import pytest

from mem20_orchestration import Catalog, CatalogError, load, validate
from mem20_orchestration.cli import main
from mem20_orchestration.planner import load_plan, save_plan


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return load()


class TestCatalogIntegrity:
    def test_catalog_loads(self, catalog):
        assert catalog.count > 2000

    def test_version_recorded(self, catalog):
        assert catalog.blender_version

    def test_module_count_matches(self, catalog):
        assert len(catalog.modules) == len(catalog.modules)

    def test_every_op_is_namespaced(self, catalog):
        bad = [n for n in catalog.names() if not n.startswith("bpy.ops.")]
        assert bad == []

    def test_module_counts_sum_to_total(self, catalog):
        assert sum(catalog.modules.values()) == catalog.count

    def test_missing_data_file_raises(self, tmp_path):
        with pytest.raises(CatalogError):
            load(str(tmp_path / "absent.json"))


class TestCatalogQueries:
    def test_known_op_exists(self, catalog):
        assert catalog.exists("bpy.ops.mesh.primitive_cube_add")

    def test_bogus_op_does_not_exist(self, catalog):
        assert not catalog.exists("bpy.ops.mesh.not_a_real_op")

    def test_get_parses_module_and_function(self, catalog):
        op = catalog.get("bpy.ops.mesh.primitive_cube_add")
        assert op is not None
        assert op.module == "mesh"
        assert op.function == "primitive_cube_add"

    def test_get_returns_none_for_unknown(self, catalog):
        assert catalog.get("bpy.ops.nope.nope") is None

    def test_require_raises_for_unknown(self, catalog):
        with pytest.raises(CatalogError):
            catalog.require("bpy.ops.nope.nope")

    def test_in_module_returns_real_ops(self, catalog):
        names = catalog.in_module("mesh")
        assert names
        assert all(n.startswith("bpy.ops.mesh.") for n in names)
        assert "bpy.ops.mesh.primitive_cube_add" in names

    def test_in_module_empty_for_unknown(self, catalog):
        assert catalog.in_module("definitely_not_a_module") == []

    def test_search_is_case_insensitive(self, catalog):
        assert catalog.search("CUBE_ADD")
        assert catalog.search("cube_add")

    def test_search_empty_term_returns_nothing(self, catalog):
        assert catalog.search("   ") == []

    def test_search_respects_limit(self, catalog):
        assert len(catalog.search("add", limit=5)) <= 5

    def test_stats_shape(self, catalog):
        stats = catalog.stats()
        assert stats["operators"] == catalog.count
        assert stats["blender_version"] == catalog.blender_version


class TestValidateValid:
    def test_real_sequence_is_valid(self, catalog):
        steps = [
            "bpy.ops.mesh.primitive_cube_add",
            "bpy.ops.mesh.primitive_uv_sphere_add",
            "bpy.ops.object.select_all",
        ]
        report = validate(steps, catalog=catalog)
        assert report.ok
        assert report.valid_steps == 3
        assert report.modules_used == ["mesh", "object"]

    def test_dict_steps_accepted(self, catalog):
        report = validate(
            [{"op": "bpy.ops.mesh.primitive_cube_add"}], catalog=catalog)
        assert report.ok

    def test_name_key_accepted(self, catalog):
        report = validate(
            [{"name": "bpy.ops.mesh.primitive_cube_add"}], catalog=catalog)
        assert report.ok

    def test_empty_plan_is_valid(self, catalog):
        report = validate([], catalog=catalog)
        assert report.ok
        assert report.total_steps == 0


class TestValidateInvalid:
    def test_unknown_op_is_error(self, catalog):
        report = validate(["bpy.ops.mesh.fake_op"], catalog=catalog)
        assert not report.ok
        assert "unknown operator" in report.errors[0].message

    def test_unknown_module_is_named_in_error(self, catalog):
        report = validate(["bpy.ops.totallyfake.thing"], catalog=catalog)
        assert not report.ok
        assert "does not exist" in report.errors[0].message

    def test_wrong_namespace_is_error(self, catalog):
        report = validate(["mesh.primitive_cube_add"], catalog=catalog)
        assert not report.ok
        assert "must start with" in report.errors[0].message

    def test_step_without_name_is_error(self, catalog):
        report = validate([{"params": {}}], catalog=catalog)
        assert not report.ok
        assert "no op name" in report.errors[0].message

    def test_repeat_is_warning_not_error(self, catalog):
        op = "bpy.ops.mesh.primitive_cube_add"
        report = validate([op, op], catalog=catalog)
        assert report.ok
        assert report.warnings
        assert "already run" in report.warnings[0].message

    def test_error_indices_point_at_the_step(self, catalog):
        report = validate(
            ["bpy.ops.mesh.primitive_cube_add", "bpy.ops.mesh.fake"],
            catalog=catalog)
        assert report.errors[0].index == 1
        assert report.valid_steps == 1


class TestPlanFiles:
    def test_roundtrip(self, tmp_path):
        steps = ["bpy.ops.mesh.primitive_cube_add"]
        target = tmp_path / "plan.json"
        save_plan(str(target), steps, "5.2.0 LTS")
        assert load_plan(str(target)) == steps

    def test_bare_list_accepted(self, tmp_path):
        target = tmp_path / "plan.json"
        target.write_text(json.dumps(["bpy.ops.mesh.primitive_cube_add"]),
                          encoding="utf-8")
        assert load_plan(str(target)) == ["bpy.ops.mesh.primitive_cube_add"]

    def test_bad_shape_rejected(self, tmp_path):
        target = tmp_path / "plan.json"
        target.write_text(json.dumps({"nope": 1}), encoding="utf-8")
        with pytest.raises(ValueError):
            load_plan(str(target))


class TestCLI:
    def test_ops_stats(self, capsys):
        assert main(["ops"]) == 0
        assert "operators" in capsys.readouterr().out

    def test_ops_show(self, capsys):
        assert main(["ops", "--show", "bpy.ops.mesh.primitive_cube_add"]) == 0
        assert "primitive_cube_add" in capsys.readouterr().out

    def test_ops_show_unknown_exits_error(self, capsys):
        assert main(["ops", "--show", "bpy.ops.mesh.nope"]) == 2

    def test_ops_module(self, capsys):
        assert main(["ops", "--module", "mesh"]) == 0
        assert "bpy.ops.mesh." in capsys.readouterr().out

    def test_ops_bad_module_exits_error(self):
        assert main(["ops", "--module", "nope_nope"]) == 2

    def test_modules_listing(self, capsys):
        assert main(["modules"]) == 0
        assert "mesh" in capsys.readouterr().out

    def test_json_output_parses(self, capsys):
        main(["--json", "ops"])
        assert json.loads(capsys.readouterr().out)["operators"] > 2000

    def test_new_plan_then_validate(self, tmp_path, capsys):
        plan = tmp_path / "p.json"
        assert main(["new-plan", "bpy.ops.mesh.primitive_cube_add",
                     "--out", str(plan)]) == 0
        capsys.readouterr()
        assert main(["validate", str(plan)]) == 0
        assert "VALID" in capsys.readouterr().out

    def test_validate_bad_plan_exits_one(self, tmp_path, capsys):
        plan = tmp_path / "bad.json"
        plan.write_text(json.dumps(["bpy.ops.mesh.fake_op"]), encoding="utf-8")
        assert main(["validate", str(plan)]) == 1
        assert "INVALID" in capsys.readouterr().out

    def test_validate_missing_file_exits_error(self):
        assert main(["validate", "/nonexistent/plan.json"]) == 2
