"""The registry's honesty contract: nothing reports ok that was not verified."""

import pytest

from mem20controlz import registry as registry_mod

VALID_STATUSES = {"ok", "degraded", "unreachable", "unknown"}
VALID_KINDS = {"core", "manager", "subsystem"}
PANEL_KEYS = {"id", "name", "kind", "description", "status", "status_reason"}

UNREACHABLE = {
    "reachable": False,
    "status": None,
    "error": "ConnectionRefusedError",
}
HTTP_500 = {"reachable": True, "status": 500, "body": "", "http_error": True}
HTTP_404 = {"reachable": True, "status": 404, "body": ""}
HTTP_200 = {"reachable": True, "status": 200, "body": '{"ok":true}'}

CLI_FAIL = {"ok": False, "exit_code": 3, "stdout": "", "stderr": "boom"}
CLI_NO_EXIT = {"ok": False}
CLI_TIMEOUT = {"ok": False, "timed_out": True, "detail": "exceeded 0.01s"}
CLI_OK = {"ok": True, "exit_code": 0, "stdout": "{}", "stderr": ""}


def run_registry(
    monkeypatch,
    binaries,
    fleet_rows=(),
    http_by_port=None,
    cli_by_binary=None,
    http_timeout=0.01,
    cli_timeout=0.01,
):
    calls = []

    def fake_http(port, path, timeout):
        calls.append(("http", port, path, timeout))
        result = dict((http_by_port or {}).get(port, UNREACHABLE))
        result.setdefault("url", f"http://127.0.0.1:{port}{path}")
        return result

    def fake_cli(binary, timeout):
        calls.append(("cli", binary, timeout))
        return dict((cli_by_binary or {}).get(binary, CLI_FAIL))

    monkeypatch.setattr(
        registry_mod.clicheck,
        "installed_binaries",
        lambda: {name: {"path": f"/root/.venv/bin/{name}"} for name in binaries},
    )
    monkeypatch.setattr(registry_mod, "fleet_inventory", lambda: list(fleet_rows))
    monkeypatch.setattr(registry_mod, "_http_probe", fake_http)
    monkeypatch.setattr(registry_mod, "_cli_probe", fake_cli)
    return registry_mod.registry(cli_timeout=cli_timeout, http_timeout=http_timeout), calls


def by_name(result, name):
    return next(p for p in result["panels"] if p.get("name") == name)


def test_top_level_contract_keys(monkeypatch):
    result, _ = run_registry(monkeypatch, binaries=[])
    assert set(result) == {
        "panels",
        "counts",
        "total",
        "probe_timeouts",
        "contract",
    }
    assert set(result["contract"]) == {"discovery", "precedence", "honesty"}
    assert "never ok" in result["contract"]["honesty"]


def test_probe_timeouts_are_echoed_back(monkeypatch):
    result, _calls = run_registry(
        monkeypatch, binaries=[], http_timeout=0.25, cli_timeout=0.5
    )
    assert result["probe_timeouts"] == {"http_s": 0.25, "cli_s": 0.5}


def test_core_and_manager_panels_lead_the_registry(monkeypatch):
    result, _ = run_registry(monkeypatch, binaries=[])
    head = result["panels"][:2]
    assert [p["id"] for p in head] == ["core", "websites"]
    assert [p["kind"] for p in head] == ["core", "manager"]
    assert all(p["status"] == "ok" for p in head)
    assert all(p["status_reason"] for p in head)


def test_every_panel_has_the_documented_shape(monkeypatch):
    result, _ = run_registry(
        monkeypatch, binaries=["fs-mcp", "mem20cviz", "fs-ops"]
    )
    for panel in result["panels"]:
        assert PANEL_KEYS <= set(panel), panel
        assert panel["kind"] in VALID_KINDS, panel
        assert panel["status"] in VALID_STATUSES, panel
        assert panel["status_reason"], panel


def test_subsystem_panels_carry_probe_evidence(monkeypatch):
    result, _ = run_registry(
        monkeypatch,
        binaries=["fs-mcp", "fs-ops"],
        fleet_rows=[{"subsystem": "mcp", "binaries": ["fs-mcp"], "description": "d"}],
    )
    mcp = by_name(result, "fs-mcp")
    assert mcp["kind"] == "subsystem"
    assert mcp["binary"] == "fs-mcp"
    assert mcp["naming"] in {"fs-standard", "mem20-native", "other"}
    assert mcp["description"] == "d"
    assert mcp["rest"]["reachable"] is False
    assert mcp["cli"]["ok"] is False

    ops = by_name(result, "fs-ops")
    assert ops["rest"] is None
    assert ops["http_surface"] is None
    assert ops["description"] == ""


def test_counts_match_panel_statuses_and_total_matches_len(monkeypatch):
    result, _ = run_registry(
        monkeypatch,
        binaries=["fs-mcp", "mem20cviz", "fs-ops"],
        http_by_port={8080: HTTP_200, 8783: UNREACHABLE},
        cli_by_binary={"fs-ops": CLI_OK, "mem20cviz": CLI_TIMEOUT},
    )
    tally = {}
    for panel in result["panels"]:
        tally[panel["status"]] = tally.get(panel["status"], 0) + 1
    assert result["counts"] == tally
    assert sum(result["counts"].values()) == result["total"] == len(result["panels"])


def test_non_cli_binaries_are_excluded(monkeypatch):
    skipped = set(registry_mod.clicheck.NON_CLI_BINARIES)
    result, _ = run_registry(monkeypatch, binaries=sorted(skipped) or ["mem20-metrics"])
    assert "mem20-metrics" in skipped
    assert [p for p in result["panels"] if p.get("binary") == "mem20-metrics"] == []


def test_panel_id_comes_from_the_fleet_row_that_owns_the_binary(monkeypatch):
    result, _ = run_registry(
        monkeypatch,
        binaries=["mem20mcp", "fs-mcp"],
        fleet_rows=[
            {
                "subsystem": "mcp",
                "binaries": ["mem20mcp", "fs-mcp"],
                "description": "shared",
            }
        ],
    )
    ids = [p["id"] for p in result["panels"] if p.get("kind") == "subsystem"]
    assert ids == ["mcp", "mcp"]


def test_rest_success_short_circuits_the_cli_probe(monkeypatch):
    result, calls = run_registry(
        monkeypatch,
        binaries=["fs-mcp"],
        http_by_port={8080: HTTP_200},
    )
    panel = by_name(result, "fs-mcp")
    assert panel["status"] == "ok"
    assert panel["status_reason"] == "REST http://127.0.0.1:8080/health -> 200"
    assert panel["cli"] is None
    assert [c for c in calls if c[0] == "cli"] == []


def test_rest_404_counts_as_reachable(monkeypatch):
    result, _ = run_registry(
        monkeypatch, binaries=["fs-mcp"], http_by_port={8080: HTTP_404}
    )
    panel = by_name(result, "fs-mcp")
    assert panel["status"] == "ok"
    assert "-> 404" in panel["status_reason"]


def test_rest_500_is_reachable_but_not_ok(monkeypatch):
    result, calls = run_registry(
        monkeypatch, binaries=["fs-mcp"], http_by_port={8080: HTTP_500}
    )
    panel = by_name(result, "fs-mcp")
    assert panel["rest"]["reachable"] is True
    assert panel["status"] != "ok"
    assert "not reachable" in panel["status_reason"] or "CLI" in panel["status_reason"]
    assert [c for c in calls if c[0] == "cli"] == [("cli", "fs-mcp", 0.01)]


def test_both_probes_failing_reports_degraded_with_a_reason(monkeypatch):
    result, _ = run_registry(
        monkeypatch, binaries=["fs-mcp"], http_by_port={8080: UNREACHABLE}
    )
    panel = by_name(result, "fs-mcp")
    assert panel["status"] == "degraded"
    assert panel["status"] != "ok"
    assert panel["status_reason"]
    assert "fs-mcp" in panel["status_reason"]
    assert panel["rest"]["reachable"] is False
    assert panel["cli"]["ok"] is False


def test_both_probes_failing_is_never_ok_for_any_binary(monkeypatch):
    for binary in ("fs-mcp", "mem20cviz", "fs-ops", "mem20corez", "mem20forge"):
        result, _ = run_registry(
            monkeypatch, binaries=[binary], http_by_port={}
        )
        panel = by_name(result, binary)
        assert panel["status"] in {"degraded", "unreachable"}, (binary, panel)
        assert panel["status_reason"], (binary, panel)
        assert panel["cli"]["ok"] is False, (binary, panel)


def test_cli_fallback_alone_can_report_ok(monkeypatch):
    result, calls = run_registry(
        monkeypatch,
        binaries=["fs-mcp"],
        http_by_port={8080: UNREACHABLE},
        cli_by_binary={"fs-mcp": CLI_OK},
    )
    panel = by_name(result, "fs-mcp")
    assert panel["status"] == "ok"
    assert panel["status_reason"] == "CLI fs-mcp --json health exit 0"
    assert [c for c in calls if c[0] == "cli"] == [("cli", "fs-mcp", 0.01)]


def test_cli_timeout_reports_unreachable(monkeypatch):
    result, _ = run_registry(
        monkeypatch,
        binaries=["fs-mcp"],
        http_by_port={8080: UNREACHABLE},
        cli_by_binary={"fs-mcp": CLI_TIMEOUT},
    )
    panel = by_name(result, "fs-mcp")
    assert panel["status"] == "unreachable"
    assert "0.01" in panel["status_reason"]


def test_cli_failure_without_exit_code_still_degrades(monkeypatch):
    result, _ = run_registry(
        monkeypatch,
        binaries=["fs-mcp"],
        http_by_port={8080: UNREACHABLE},
        cli_by_binary={"fs-mcp": CLI_NO_EXIT},
    )
    panel = by_name(result, "fs-mcp")
    assert panel["status"] == "degraded"
    assert "None" in panel["status_reason"]


def test_binary_without_a_surface_still_probes_the_cli(monkeypatch):
    result, calls = run_registry(monkeypatch, binaries=["fs-ops"])
    panel = by_name(result, "fs-ops")
    assert [c for c in calls if c[0] == "http"] == []
    assert panel["status"] == "degraded"
    assert "no verified surface" in panel["status_reason"]


def test_configured_timeouts_reach_both_probes(monkeypatch):
    _, calls = run_registry(
        monkeypatch,
        binaries=["fs-mcp"],
        http_by_port={8080: UNREACHABLE},
        http_timeout=0.125,
        cli_timeout=0.25,
    )
    assert ("http", 8080, "/health", 0.125) in calls
    assert ("cli", "fs-mcp", 0.25) in calls


@pytest.mark.parametrize(
    "rest,rest_ok",
    [
        (UNREACHABLE, False),
        (HTTP_500, False),
        (HTTP_404, True),
        (HTTP_200, True),
    ],
)
@pytest.mark.parametrize(
    "cli,cli_ok,cli_timeouted",
    [
        (CLI_FAIL, False, False),
        (CLI_NO_EXIT, False, False),
        (CLI_TIMEOUT, False, True),
        (CLI_OK, True, False),
    ],
)
def test_status_never_exceeds_the_probe_evidence(
    monkeypatch, rest, rest_ok, cli, cli_ok, cli_timeouted
):
    result, calls = run_registry(
        monkeypatch=monkeypatch,
        binaries=["fs-mcp"],
        http_by_port={8080: rest},
        cli_by_binary={"fs-mcp": cli},
    )
    panel = by_name(result, "fs-mcp")
    verified = rest_ok or cli_ok

    assert (panel["status"] == "ok") is verified, panel
    if not verified:
        assert panel["status"] in {"degraded", "unreachable"}, panel
        assert panel["status_reason"], panel
    if cli_timeouted and not rest_ok:
        assert panel["status"] == "unreachable", panel
    if rest_ok:
        assert panel["cli"] is None, panel
        assert [c for c in calls if c[0] == "cli"] == []


def test_raising_probe_is_contained_and_scored_unknown(monkeypatch):
    """A probe that raises must not take the whole registry down.

    Previously the exception propagated and killed the request. It is now
    captured, the panel reports ``unknown`` with the error as its reason, and
    the rest of the registry still renders.
    """

    def exploding_http(port, path, timeout):
        raise RuntimeError("probe exploded")

    monkeypatch.setattr(
        registry_mod.clicheck,
        "installed_binaries",
        lambda: {"fs-mcp": {}, "mem20cviz": {}},
    )
    monkeypatch.setattr(registry_mod, "fleet_inventory", list)
    monkeypatch.setattr(registry_mod, "_http_probe", exploding_http)
    monkeypatch.setattr(registry_mod, "_cli_probe", lambda b, t: dict(CLI_FAIL))

    result = registry_mod.registry(cli_timeout=0.01, http_timeout=0.01)

    assert result["total"] == len(result["panels"])
    for panel in result["panels"]:
        if panel.get("kind") != "subsystem":
            continue
        assert panel["status"] != "ok", panel
        assert panel["status_reason"], panel


def test_raising_cli_probe_yields_unknown(monkeypatch):
    def exploding_cli(binary, timeout):
        raise RuntimeError("cli probe exploded")

    monkeypatch.setattr(
        registry_mod.clicheck,
        "installed_binaries",
        lambda: {"mem20cviz": {}},
    )
    monkeypatch.setattr(registry_mod, "fleet_inventory", list)
    monkeypatch.setattr(registry_mod, "_http_probe", lambda p, path, t: {"reachable": False, "status": None, "url": "u"})
    monkeypatch.setattr(registry_mod, "_cli_probe", exploding_cli)

    result = registry_mod.registry(cli_timeout=0.01, http_timeout=0.01)
    panel = by_name(result, "mem20cviz")
    assert panel["status"] == "unknown", panel
    assert "cli probe exploded" in panel["status_reason"], panel


def test_classify_maps_binaries_to_known_surfaces():
    assert registry_mod._classify("fs-mcp") == "mcp"
    assert registry_mod._classify("mem20cviz") == "cviz"
    assert registry_mod._classify("fs-ops") == ""
    assert registry_mod._classify("mem20-metrics") == ""


def test_http_surfaces_are_well_formed():
    for key, surface in registry_mod.HTTP_SURFACES.items():
        assert isinstance(surface["port"], int), key
        assert surface["port"] > 0, key
        assert surface["health"].startswith("/"), key
