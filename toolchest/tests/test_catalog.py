"""Runtime-checks the real toolchest discovery. Requires /opt/mem20 on disk."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
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
    # mem20crewz is NOT installed anywhere → degraded/missing install check
    crewz = subs["mem20crewz"]
    assert not crewz["meta"]["installed"]
    assert crewz["meta"]["version"]  # declared version still present


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