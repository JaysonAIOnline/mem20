"""End-to-end CLI tests via subprocess `python -m toolchest`."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def run_cli(args, inventory=None, timeout=180):
    cmd = [sys.executable, "-m", "toolchest", "--inventory", str(inventory or JL),
           *args]
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True,
                          timeout=timeout)


@pytest.fixture(scope="module")
def inv_file(tmp_path_factory):
    out = tmp_path_factory.mktemp("inv") / "inventory.json"
    from toolchest import catalog
    inv = catalog.build_inventory(help_sampling=False)
    catalog.write_inventory(inv, out)
    return out


@pytest.fixture(scope="module")
def inv_file_path(inv_file):
    return inv_file


JL = Path("/opt/mem20/toolchest/inventory.json")


def test_stats_command(inv_file_path):
    r = run_cli(["stats"], inv_file_path)
    assert r.returncode == 0, r.stderr
    assert "counts" in r.stdout
    assert "mcp=" in r.stdout


def test_list_command_agent_platform(inv_file_path):
    r = run_cli(["list", "--category", "agent-platform"], inv_file_path)
    assert r.returncode == 0, r.stderr
    assert "mem20agentz" in r.stdout
    assert "subsystem" in r.stdout


def test_list_json_valid(inv_file_path):
    r = run_cli(["list", "--kind", "mcp", "--limit", "5", "--json"], inv_file_path)
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert len(data) == 5
    assert all(e["kind"] == "mcp" for e in data)


def test_search_command(inv_file_path):
    r = run_cli(["search", "braid"], inv_file_path)
    assert r.returncode == 0, r.stderr
    assert "braid_write" in r.stdout


def test_show_command_checks_path(inv_file_path):
    r = run_cli(["show", "memory_store", "--check-path"], inv_file_path)
    assert r.returncode == 0, r.stderr
    body = json.loads(r.stdout.split("\npath exists on disk:")[0])
    assert body["name"] == "memory_store"
    assert "path exists on disk: True" in r.stdout


def test_show_unknown_returns_1(inv_file_path):
    r = run_cli(["show", "definitely_not_a_tool"], inv_file_path)
    assert r.returncode == 1


def test_query_without_inventory_returns_2(tmp_path):
    r = run_cli(["list"], tmp_path / "nope.json")
    assert r.returncode == 2
    assert "not found" in r.stderr


def test_refresh_writes_file(tmp_path):
    out = tmp_path / "gen.json"
    r = run_cli(["refresh", "--no-help-samples", "--output", str(out)])
    assert r.returncode == 0, r.stderr
    inv = json.loads(out.read_text())
    assert inv["counts"]["mcp"] >= 200
    assert inv["counts"]["subsystem"] >= 20


def test_default_inventory_file_exists():
    assert JL.exists(), "run `python -m toolchest refresh` to generate inventory.json"