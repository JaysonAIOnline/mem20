import os
import subprocess
import sys
import time

import pytest

from mem20ops import runtime


def _spawn_sleeper(marker: str) -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)", marker],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(50):
        rows = runtime._ps_fields()
        if any(str(proc.pid) == r["pid"] for r in rows):
            break
        time.sleep(0.1)
    return proc


def test_find_stale_processes_detects_older_process(tmp_path):
    source = tmp_path / "mod.py"
    source.write_text("x = 1\n", encoding="utf-8")
    old = time.time() - 10_000
    os.utime(source, (old, old))
    proc = _spawn_sleeper(str(source))
    try:
        time.sleep(1.2)
        now = time.time()
        os.utime(source, (now, now))
        result = runtime.find_stale_processes([str(source)], match=str(source))
        stale = [r for r in result["processes"] if r["pid"] == proc.pid]
        assert stale, result
        assert stale[0]["verdict"] == "STALE", stale[0]
        assert stale[0]["started_before_source"] is True
        assert result["stale_count"] >= 1
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_find_stale_processes_reports_current(tmp_path):
    source = tmp_path / "mod.py"
    source.write_text("x = 1\n", encoding="utf-8")
    old = time.time() - 10_000
    os.utime(source, (old, old))
    proc = _spawn_sleeper(str(source))
    try:
        result = runtime.find_stale_processes([str(source)], match=str(source))
        mine = [r for r in result["processes"] if r["pid"] == proc.pid]
        assert mine, result
        assert mine[0]["verdict"] == "current", mine[0]
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_recent_process_is_not_flagged_stale_for_older_source(tmp_path):
    """A process started after the source was last edited is 'current'.

    Guards the arithmetic that computes process start time: elapsed seconds are
    relative to now, so start = now - elapsed. Deriving it from the source mtime
    instead falsely reports every process as STALE.
    """
    source = tmp_path / "mod.py"
    source.write_text("x = 1\n", encoding="utf-8")
    old = time.time() - 86_400
    os.utime(source, (old, old))
    proc = _spawn_sleeper(str(source))
    try:
        result = runtime.find_stale_processes([str(source)], match=str(source))
        mine = [r for r in result["processes"] if r["pid"] == proc.pid]
        assert mine, result
        started = time.time() - mine[0]["elapsed_s"]
        assert started > old, "start time arithmetic is wrong"
        assert mine[0]["verdict"] == "current", mine[0]
        assert result["stale_count"] == 0, result
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_related_files_contribute_mtime_without_cmdline_match(tmp_path):
    entry = tmp_path / "server.py"
    entry.write_text("x = 1\n", encoding="utf-8")
    module = tmp_path / "module.py"
    module.write_text("y = 2\n", encoding="utf-8")
    old = time.time() - 86_400
    os.utime(entry, (old, old))
    proc = _spawn_sleeper(str(entry))
    try:
        time.sleep(1.2)
        now = time.time()
        os.utime(module, (now, now))
        result = runtime.find_stale_processes([str(entry)], related=[str(module)])
        mine = [r for r in result["processes"] if r["pid"] == proc.pid]
        assert mine, result
        assert mine[0]["verdict"] == "STALE", mine[0]
        assert str(module) in mine[0]["watched_related"]
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_find_stale_processes_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        runtime.find_stale_processes([str(tmp_path / "nope.py")])


def test_verify_suite_runs_tests_and_reports_counts(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "tests").mkdir()
    (repo / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    result = runtime.verify_suite(repo=str(repo), run_lint=False)
    assert result["steps"][0]["name"] == "pytest"
    assert result["steps"][0]["exit_code"] == 0
    assert result["steps"][0]["counts"].get("passed") == 1
    assert result["ok"] is True


def test_verify_suite_fails_on_failing_test(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "tests").mkdir()
    (repo / "tests" / "test_bad.py").write_text("def test_bad():\n    assert False\n", encoding="utf-8")
    result = runtime.verify_suite(repo=str(repo), run_lint=False)
    assert result["steps"][0]["exit_code"] != 0
    assert result["ok"] is False
    assert result["failed_steps"] == ["pytest"]


def test_verify_suite_timeout_is_bounded(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "tests").mkdir()
    (repo / "tests" / "test_slow.py").write_text(
        "import time\n\ndef test_slow():\n    time.sleep(5)\n", encoding="utf-8"
    )
    result = runtime.verify_suite(repo=str(repo), run_lint=False, timeout=1)
    assert result["steps"][0]["exit_code"] == 124
    assert result["steps"][0]["timed_out"] is True


def test_verify_suite_lint_step(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "tests").mkdir()
    lint_target = repo / "bad.py"
    lint_target.write_text("import os\n", encoding="utf-8")
    result = runtime.verify_suite(
        repo=str(repo), run_tests=False, lint_paths=[str(lint_target)]
    )
    assert result["steps"][0]["name"] == "ruff"
    assert "finding_lines" in result["steps"][0]


def test_service_status_reports_fields():
    result = runtime.service_status("definitely-not-a-unit-xyz")
    assert result["unit"] == "definitely-not-a-unit-xyz"
    assert result["active_state"] is None or isinstance(result["active_state"], str)


def test_service_status_on_real_unit():
    result = runtime.service_status("mcp-server.service")
    assert "main_pid" in result
    assert "active_enter" in result
