"""Runtime-checks the real toolchest discovery. Requires /opt/mem20 on disk."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from toolchest import catalog  # noqa: E402

MEM20_ROOT = Path("/opt/mem20")
MCP_DIR = MEM20_ROOT / "mcp"


@pytest.fixture(scope="module")
def inventory():
    inv = catalog.build_inventory(help_sampling=False)
    return inv


def test_format_and_counts(inventory):
    assert inventory["format"] == "mem20-toolchest-inventory"
    assert inventory["format_version"] == 1
    c = inventory["counts"]
    assert c["total"] == c["mcp"] + c["cli"] + c["subsystem"]
    assert c["mcp"] >= 200
    assert c["cli"] >= 200
    assert c["subsystem"] >= 20


def test_entry_required_fields(inventory):
    missing = 0
    for e in inventory["entries"]:
        for f in catalog.REQUIRED_FIELDS:
            if f not in e:
                missing += 1
    assert missing == 0, f"{missing} entries missing required fields"


def test_unique_ids(inventory):
    ids = [e["id"] for e in inventory["entries"]]
    assert len(ids) == len(set(ids))


def test_mcp_runtime_matches_server(inventory):
    mcp_entries = [e for e in inventory["entries"] if e["kind"] == "mcp"]
    names = {e["name"] for e in mcp_entries}
    # spot-check well-known tools that must exist in the real registry
    assert "memory_store" in names
    assert "memory_recall" in names
    assert "braid_write" in names
    for e in mcp_entries:
        assert e["runtime_status"] == "ok"
        assert e["description"].strip()


def test_mcp_registration_map_covers_known_specials(inventory):
    mcp_entries = [e for e in inventory["entries"] if e["kind"] == "mcp"]
    names = {e["name"] for e in mcp_entries}
    assert "world_model_status" in names  # registered behind a variable name
    by_name = {e["name"]: e for e in mcp_entries}
    wm = by_name["world_model_status"]
    assert wm["subcategory"] == "world-model"


def test_cli_sources_exist(inventory):
    broken = [e["source"] for e in inventory["entries"]
              if e["kind"] == "cli"
              and e["runtime_status"] != "broken"
              and not Path(e["source"]).exists()]
    assert broken == [], f"{len(broken)} cli sources missing on disk"
    # broken entries are honest: status 'broken' and path really absent
    broke = [e for e in inventory["entries"] if e["kind"] == "cli"
             and e["runtime_status"] == "broken"]
    if broke:
        assert all(not Path(e["source"]).exists() for e in broke)


def test_subsystem_sources_exist(inventory):
    broken = [e["source"] for e in inventory["entries"]
              if e["kind"] == "subsystem" and not Path(e["source"]).exists()]
    assert broken == [], f"{len(broken)} subsystem sources missing on disk"


def test_subsystem_categories_match_agend_md_table(inventory):
    subs = {e["name"]: e for e in inventory["entries"]
            if e["kind"] == "subsystem"}
    assert subs["mem20agentz"]["category"] == "agent-platform"
    assert subs["mem20crewz"]["category"] == "agent-platform"
    assert subs["mem20yetiz"]["category"] == "games-3d"
    assert subs["mem20gamez"]["category"] == "games-3d"
    assert subs["mem20corez"]["category"] == "infra-model-ui"
    assert subs["mem20oreo"]["category"] == "infra-model-ui"


def test_subsystem_runtime_truthfulness(inventory):
    subs = {e["name"]: e for e in inventory["entries"]
            if e["kind"] == "subsystem"}
    # mem20corez is installed in the root venv → ok
    assert subs["mem20corez"]["runtime_status"] == "ok"
    # An installed subsystem must be reported as installed. This used to assert
    # the opposite for mem20crewz, which was written when crewz was not
    # installed; it now is, so asserting "not installed" would enshrine a lie
    # about the host. Cross-check the real environment rather than a snapshot.
    from importlib.metadata import PackageNotFoundError, version

    crewz = subs["mem20crewz"]
    try:
        installed_version = version("mem20crewz")
    except PackageNotFoundError:
        installed_version = None
    assert bool(crewz["meta"]["installed"]) is (installed_version is not None)
    if installed_version is not None:
        assert crewz["meta"]["installed"]["version"] == installed_version
    assert crewz["meta"]["version"]  # declared version still present


def test_import_probe_is_not_shadowed_by_source_directories(inventory):
    """Installed subsystems must not read as un-importable.

    The import probe used to run from /opt/mem20, where each subsystem's source
    directory shadows the installed package as a namespace package with a None
    origin - which made every one of them look un-importable.
    """
    subs = {e["name"]: e for e in inventory["entries"]
            if e["kind"] == "subsystem"}
    for name in ("mem20ops", "mem20controlz"):
        entry = subs.get(name)
        if entry is None:
            continue
        if entry["meta"].get("installed"):
            assert entry["runtime_status"] == "ok", (
                f"{name} is installed but reported {entry['runtime_status']}: "
                f"{entry.get('runtime_detail')}"
            )
            assert "importable=True" in entry.get("runtime_detail", "")


def test_write_load_roundtrip(tmp_path):
    inv = catalog.build_inventory(help_sampling=False)
    out = tmp_path / "inventory.json"
    catalog.write_inventory(inv, out)
    loaded = catalog.load_inventory(out)
    assert loaded["counts"]["total"] == inv["counts"]["total"]
    assert len(loaded["entries"]) == len(inv["entries"])


def test_mcp_dump_script_is_runnable():
    """The same subprocess the catalog uses must succeed standalone."""
    py = catalog.ROOT_VENV / "bin" / "python"
    r = subprocess.run(
        [str(py), "-c", catalog._MCP_SCRIPT, str(MEM20_ROOT), str(MCP_DIR)],
        capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    tools = json.loads(r.stdout)
    assert len(tools) >= 200
    for t in tools:
        assert t["name"] and t["description"]
        assert "input_schema_props" in t

class TestImportCandidates:
    """`[tool.setuptools.packages.find]` must not yield a module called `find`."""

    def test_finder_form_uses_include_globs(self):
        from toolchest.catalog import _import_candidates

        data = {"tool": {"setuptools": {"packages": {"find": {
            "where": ["."], "include": ["mem20kilnz*"]}}}}}
        assert _import_candidates("mem20kilnz", data) == ["mem20kilnz"]

    def test_explicit_list_form_still_works(self):
        from toolchest.catalog import _import_candidates

        data = {"tool": {"setuptools": {"packages": ["mem20crewz"]}}}
        assert _import_candidates("mem20crewz", data) == ["mem20crewz"]

    def test_falls_back_to_normalised_distribution_name(self):
        from toolchest.catalog import _import_candidates

        assert _import_candidates("mem20-orchestration", {}) == ["mem20_orchestration"]

    def test_py_modules_are_included(self):
        from toolchest.catalog import _import_candidates

        data = {"tool": {"setuptools": {"packages": {"find": {"include": ["pkg*"]}},
                                        "py-modules": ["loose_mod"]}}}
        assert _import_candidates("whatever", data) == ["pkg", "loose_mod"]

    def test_never_reports_the_literal_name_find(self):
        from toolchest.catalog import _import_candidates

        data = {"tool": {"setuptools": {"packages": {"find": {
            "where": ["src"], "include": ["realpkg*"]}}}}}
        assert "find" not in _import_candidates("somepkg", data)

    def test_subpackage_shorthand_glob_yields_one_clean_name(self):
        """`include = ["pkg", "pkg.*"]` must not produce a module named `pkg.`"""
        from toolchest.catalog import _import_candidates

        data = {"tool": {"setuptools": {"packages": {"find": {
            "include": ["mem20agentz", "mem20agentz.*"]}}}}}
        assert _import_candidates("mem20agentz", data) == ["mem20agentz"]
