import json

from mem20ops import fleet


def test_inventory_lists_fleet_clis():
    rows = fleet.inventory()
    assert rows, "expected fleet CLIs in the venv"
    names = {r["subsystem"] for r in rows}
    assert "ops" in names
    assert "corez" in names


def test_inventory_prefers_fs_prefixed_binaries():
    for row in fleet.inventory():
        fs_bins = [b for b in row["binaries"] if b.startswith("fs-")]
        if fs_bins:
            assert row["preferred"].startswith("fs-"), row


def test_every_row_has_an_executable_path():
    import os

    for row in fleet.inventory():
        assert row["path"]
        assert os.path.exists(row["path"]), row


def test_resolve_by_subsystem_name():
    assert fleet.resolve("corez") is not None


def test_resolve_by_full_binary_name():
    row = fleet.resolve("fs-ops")
    assert row is not None
    assert row["preferred"] == "fs-ops"


def test_resolve_is_case_insensitive():
    assert fleet.resolve("COREZ") is not None


def test_resolve_mem20_prefixed_name():
    assert fleet.resolve("mem20corez") is not None


def test_resolve_unknown_returns_none():
    assert fleet.resolve("definitely-not-a-subsystem") is None


def test_list_with_no_args_renders(capsys):
    assert fleet.main([]) == 0
    out = capsys.readouterr().out
    assert "fleet CLI" in out
    assert "run a subsystem" in out


def test_list_json_is_valid(capsys):
    assert fleet.main(["list", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] >= 1
    assert all("subsystem" in r and "preferred" in r for r in payload["subsystems"])


def test_unknown_subsystem_exits_nonzero(capsys):
    assert fleet.main(["not-a-real-subsystem"]) == 1
    assert "unknown subsystem" in capsys.readouterr().err


def test_help_returns_zero(capsys):
    assert fleet.main(["--help"]) == 0


def test_dispatch_runs_real_child_and_propagates_exit(capfd):
    code = fleet.main(["ops", "cli-coverage", "--help"])
    assert code == 0
    assert "cli-coverage" in capfd.readouterr().out


def test_dispatch_propagates_child_failure(capsys):
    assert fleet.main(["ops", "pages-delete", "some-project"]) == 1


def test_dispatch_rejects_leading_option(capsys):
    code = fleet.main(["--nope"])
    assert code != 0
    assert "unknown option" in capsys.readouterr().err
