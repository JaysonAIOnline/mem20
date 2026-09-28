import os

from mem20ops import clicheck


def test_classify_naming():
    assert clicheck.classify_naming("fs-cv") == "fs-standard"
    assert clicheck.classify_naming("fs-ops") == "fs-standard"
    assert clicheck.classify_naming("mem20corez") == "mem20-native"
    assert clicheck.classify_naming("mem20-orchestration") == "mem20-native"
    assert clicheck.classify_naming("mem20_mcp") == "mem20-native"
    assert clicheck.classify_naming("mem20-metrics") == "mem20-native"
    assert clicheck.classify_naming("mem20") == "mem20-native"
    assert clicheck.classify_naming("toolchest") == "other"
    assert clicheck.classify_naming("random-binary") == "other"


def test_declared_scripts_reads_real_pyprojects():
    rows = clicheck.declared_scripts()
    assert rows, "expected console scripts on disk"
    names = {r["name"] for r in rows}
    assert "fs-ops" in names
    for row in rows:
        assert row["package"]
        assert row["target"]


def test_installed_binaries_detects_fs_ops():
    binaries = clicheck.installed_binaries()
    assert "fs-ops" in binaries
    assert os.path.exists(binaries["fs-ops"]["path"])


def test_probe_help_on_known_good_binary():
    result = clicheck.probe_help("fs-ops", "/root/.venv/bin/fs-ops", timeout=30)
    assert result["help_ok"] is True
    assert result["has_json"] is True
    assert "dns-audit" in result["verbs"]


def test_probe_help_respects_timeout():
    result = clicheck.probe_help("mem20-metrics", "/root/.venv/bin/mem20-metrics", timeout=1)
    assert result["timed_out"] is True
    assert result["help_ok"] is False


def test_probe_help_on_missing_binary():
    result = clicheck.probe_help("nope", "/nonexistent/fs-nope", timeout=5)
    assert result["help_ok"] is False
    assert result["timed_out"] is False


def test_audit_shape_and_totals():
    report = clicheck.audit(timeout=20)
    totals = report["totals"]
    assert totals["audited_clis"] == len(report["results"])
    assert totals["skipped"] == len(report["skipped_non_cli"])
    assert totals["fully_compliant"] <= totals["installed_binaries"]
    assert totals["with_json"] <= totals["installed_binaries"]
    names = [r["name"] for r in report["results"]]
    assert len(names) == len(set(names)), "duplicate binary names in report"
    for row in report["results"]:
        assert "gaps" in row
        assert row["naming"] in {"fs-standard", "mem20-native", "other"}
        assert "naming-not-fs" not in row["gaps"], row


def test_install_counter_is_not_audited():
    report = clicheck.audit(timeout=20)
    assert "mem20-metrics" in report["skipped_non_cli"]
    assert "mem20-metrics" not in {r["name"] for r in report["results"]}


def test_naming_is_not_reported_as_a_gap():
    report = clicheck.audit(timeout=20)
    assert report["naming_is_a_gap"] is False
    mem20_native = [r for r in report["results"] if r["naming"] == "mem20-native"]
    assert mem20_native, "expected mem20*-named CLIs in the fleet"
    for row in mem20_native:
        assert "naming-not-fs" not in row["gaps"], row


def test_audit_is_json_serialisable():
    import json

    json.dumps(clicheck.audit(timeout=20))


def test_audit_probes_concurrently(monkeypatch):
    """The audit must overlap its help probes, not run them one after another.

    Serial probing made a full sweep take ~24s, which is slow enough to time
    out when the control plane calls it through a tunnel.
    """
    import threading
    import time

    barrier_count = 4
    barrier = threading.Barrier(barrier_count, timeout=5)
    live = 0
    peak = 0
    lock = threading.Lock()

    def slow_probe(name, path, timeout=25):
        nonlocal live, peak
        with lock:
            live += 1
            peak = max(peak, live)
        try:
            # A serial implementation can never get four probes past this point.
            barrier.wait()
        except threading.BrokenBarrierError:
            pass
        time.sleep(0.01)
        with lock:
            live -= 1
        return {
            "help_exit": 0,
            "help_ok": True,
            "timed_out": False,
            "has_json": True,
            "verbs": ["health"],
            "detail": "",
        }

    monkeypatch.setattr(clicheck, "probe_help", slow_probe)
    monkeypatch.setattr(clicheck, "declared_scripts", list)
    monkeypatch.setattr(
        clicheck,
        "installed_binaries",
        lambda: {f"fs-probe{i}": {"path": "/bin/true", "is_symlink": False} for i in range(8)},
    )
    monkeypatch.setattr(clicheck, "NON_CLI_BINARIES", ())

    report = clicheck.audit(timeout=20)

    assert peak > 1, "probes ran one at a time"
    assert len(report["results"]) == 8


def test_audit_preserves_sorted_order_under_concurrency(monkeypatch):
    """Concurrency must not make the report order depend on probe timing."""
    import random
    import time

    def jittery_probe(name, path, timeout=25):
        time.sleep(random.uniform(0, 0.02))
        return {
            "help_exit": 0,
            "help_ok": True,
            "timed_out": False,
            "has_json": True,
            "verbs": [],
            "detail": "",
        }

    monkeypatch.setattr(clicheck, "probe_help", jittery_probe)
    monkeypatch.setattr(clicheck, "declared_scripts", list)
    monkeypatch.setattr(
        clicheck,
        "installed_binaries",
        lambda: {f"fs-j{i}": {"path": "/bin/true", "is_symlink": False} for i in range(12)},
    )
    monkeypatch.setattr(clicheck, "NON_CLI_BINARIES", ())

    names = [r["name"] for r in clicheck.audit(timeout=20)["results"]]
    assert names == sorted(names)
