"""Behavioural tests for mem20verify.

These assert the checks actually detect the defects they exist for, and that
they never manufacture a pass. Tests that exercise the host (systemd, the real
bridge) skip cleanly when unavailable rather than faking success.
"""

from __future__ import annotations

import ast
import shutil

import pytest

from mem20verify import dataintegrity, linters, outage, systemd, testrun


def _tree(src: str) -> ast.AST:
    return ast.parse(src)


# --------------------------------------------------------------- linters
class TestIdenticalBranches:
    def test_detects_identical_arms(self):
        src = (
            "def f(cond, log):\n"
            "    if cond:\n"
            "        log('x')\n"
            "    else:\n"
            "        log('x')\n"
        )
        issues = linters.identical_branches("m.py", _tree(src))
        assert len(issues) == 1
        assert issues[0].check == "identical-branches"

    def test_ignores_genuinely_different_arms(self):
        src = (
            "def f(cond, log):\n"
            "    if cond:\n"
            "        log('x')\n"
            "    else:\n"
            "        log('y')\n"
        )
        assert linters.identical_branches("m.py", _tree(src)) == []

    def test_ignores_multi_statement_arms(self):
        src = (
            "def f(c):\n"
            "    if c:\n"
            "        a = 1\n"
            "        return a\n"
            "    else:\n"
            "        b = 2\n"
            "        return b\n"
        )
        assert linters.identical_branches("m.py", _tree(src)) == []

    def test_detects_flag_plus_shared_work(self):
        """The real breaker shape: the if only sets a flag, both arms log."""
        src = (
            "def handler(self, cond, log):\n"
            "    if cond:\n"
            "        self._tripped = True\n"
            "        log('err')\n"
            "    else:\n"
            "        log('err')\n"
        )
        issues = linters.identical_branches("m.py", _tree(src))
        assert issues and issues[0].check == "identical-branches"
        assert "_tripped" in issues[0].message

    def test_does_not_flag_genuinely_different_extra_work(self):
        src = (
            "def f(c, log):\n"
            "    if c:\n"
            "        log('a')\n"
            "        log('b')\n"
            "    else:\n"
            "        log('a')\n"
        )
        assert linters.identical_branches("m.py", _tree(src)) == []


class TestMisplacedLookbehind:
    def test_detects_lookbehind_after_prefix(self):
        src = 'PATTERN = r"sk-" + r"(?<![A-Za-z0-9])" + r"[A-Za-z0-9]{32,64}"\n'
        issues = linters.misplaced_lookbehind("m.py", _tree(src))
        assert issues and issues[0].check == "misplaced-lookbehind"

    def test_ignores_lookbehind_before_prefix(self):
        src = 'PATTERN = r"(?<![A-Za-z0-9])sk-" + r"[A-Za-z0-9]{32,64}"\n'
        assert linters.misplaced_lookbehind("m.py", _tree(src)) == []

    def test_ignores_plain_concatenation(self):
        src = 'PATTERN = r"ghp_" + r"[A-Za-z0-9]{36}"\n'
        assert linters.misplaced_lookbehind("m.py", _tree(src)) == []


class TestUnboundedTests:
    def test_flags_while_true_in_test(self):
        src = (
            "def test_runs():\n"
            "    while True:\n"
            "        pass\n"
        )
        issues = linters.unbounded_tests("m.py", _tree(src))
        assert any(i.check == "unbounded-loop" for i in issues)

    def test_flags_fail_for_none(self):
        src = "def test_x():\n    helper(fail_for=None)\n"
        issues = linters.unbounded_tests("m.py", _tree(src))
        assert any(i.check == "unbounded-parameter" for i in issues)

    def test_flags_long_sleep(self):
        src = "def test_x():\n    time.sleep(600)\n"
        issues = linters.unbounded_tests("m.py", _tree(src))
        assert any(i.check == "long-sleep" for i in issues)

    def test_ignores_short_sleep(self):
        src = "def test_x():\n    time.sleep(0.01)\n"
        assert linters.unbounded_tests("m.py", _tree(src)) == []

    def test_ignores_while_true_outside_test(self):
        src = "def helper():\n    while True:\n        pass\n"
        assert linters.unbounded_tests("m.py", _tree(src)) == []


class TestNoopBodies:
    def test_flags_pass_body(self):
        src = "def f():\n    pass\n"
        issues = linters.noop_bodies("m.py", _tree(src))
        assert issues and issues[0].check == "noop-body"

    def test_exempts_abstractmethod(self):
        src = (
            "import abc\n"
            "class C(abc.ABC):\n"
            "    @abc.abstractmethod\n"
            "    def f(self):\n"
            "        pass\n"
        )
        assert linters.noop_bodies("m.py", _tree(src)) == []


# --------------------------------------------------------------- testrun
class TestParseCounts:
    def test_parses_passed(self):
        assert testrun.parse_counts("5 passed in 0.1s")["passed"] == 5

    def test_parses_mixed(self):
        counts = testrun.parse_counts("10 passed, 2 failed, 1 skipped in 1s")
        assert counts == {"passed": 10, "failed": 2, "skipped": 1, "errors": 0}

    def test_parses_errors(self):
        assert testrun.parse_counts("3 errors in 0.2s")["errors"] == 3

    def test_empty_output_is_zero(self):
        assert testrun.parse_counts("") == {
            "passed": 0, "failed": 0, "skipped": 0, "errors": 0}


class TestInterpreterSelection:
    def test_prefers_local_venv(self, tmp_path):
        local = tmp_path / ".venv" / "bin"
        local.mkdir(parents=True)
        (local / "python").write_text("", encoding="utf-8")
        assert testrun.interpreter_for(str(tmp_path)) == str(local / "python")

    def test_falls_back_to_shared(self, tmp_path):
        assert testrun.interpreter_for(str(tmp_path)) == testrun.DEFAULT_PYTHON


class TestRunPackage:
    def test_missing_interpreter_is_error_not_pass(self, tmp_path):
        result = testrun.run_package("nope", root=str(tmp_path),
                                     python=str(tmp_path / "no_python"))
        assert result.returncode == 127
        assert not result.ok
        assert result.error_text

    def test_timeout_is_reported(self, tmp_path):
        pkg = tmp_path / "slowpkg"
        pkg.mkdir()
        (pkg / "test_slow.py").write_text(
            "import time\ndef test_a():\n    time.sleep(30)\n",
            encoding="utf-8",
        )
        result = testrun.run_package(
            "slowpkg", root=str(tmp_path), python="/root/.venv/bin/python",
            timeout=3)
        assert result.timed_out
        assert result.returncode == 124
        assert not result.ok

    def test_real_passing_package(self, tmp_path):
        pkg = tmp_path / "goodpkg"
        pkg.mkdir()
        (pkg / "test_ok.py").write_text(
            "def test_a():\n    assert 1 + 1 == 2\n", encoding="utf-8")
        result = testrun.run_package(
            "goodpkg", root=str(tmp_path), python="/root/.venv/bin/python")
        assert result.ok
        assert result.passed == 1

    def test_real_failing_package_reports_id(self, tmp_path):
        pkg = tmp_path / "badpkg"
        pkg.mkdir()
        (pkg / "test_bad.py").write_text(
            "def test_broken():\n    assert 0\n", encoding="utf-8")
        result = testrun.run_package(
            "badpkg", root=str(tmp_path), python="/root/.venv/bin/python")
        assert not result.ok
        assert result.failed == 1
        assert any("test_broken" in x for x in result.failed_ids)


class TestIndexBaseline:
    def test_index_version_missing_returns_none(self, tmp_path):
        assert testrun.index_version(str(tmp_path), "nope.py") is None

    def test_head_has_path_false_in_empty_repo(self, tmp_path):
        assert not testrun.head_has_path(str(tmp_path), "nope.py")

    def test_attribute_without_baseline_reports_unknown(self, tmp_path):
        pkg = tmp_path / "p"
        pkg.mkdir()
        (pkg / "test_x.py").write_text("def test_a():\n    pass\n",
                                       encoding="utf-8")
        verdicts = testrun.attribute("p", ["test_a"], root=str(tmp_path))
        assert verdicts and not verdicts[0].baseline_available
        assert not verdicts[0].preexisting


# ------------------------------------------------------------------ outage
class TestOutage:
    def test_bridge_module_importable(self):
        try:
            import mem20agentz.bridge  # noqa: F401
        except ImportError:
            pytest.skip("mem20agentz not installed")
        assert True

    def test_contract_passes_on_real_bridge(self):
        result = outage.check()
        if result.error and "not importable" in result.error:
            pytest.skip(result.error)
        assert result.ok, result.error
        assert result.strikes == 3
        assert result.trip_events == 1
        assert result.ledger_rows == 0
        assert result.reset_after_recovery

    def test_transport_is_bounded(self):
        class _Bridge:
            def __init__(self):
                self.stopped = False

            def stop(self):
                self.stopped = True

        bridge = _Bridge()
        transport = outage._DeadTransport(bridge, fail_for=2)
        with pytest.raises(OSError):
            transport.poll(0)
        with pytest.raises(OSError):
            transport.poll(0)
        assert transport.poll(0) is None, "must stop the loop, never hang"
        assert bridge.stopped is True


# --------------------------------------------------------- dataintegrity
class TestDataIntegrity:
    def test_payloads_cover_the_corrupted_shapes(self):
        for key in ("git_sha", "content_hash", "braid_cid", "uuid"):
            assert key in dataintegrity.PAYLOADS

    def test_roundtrip_on_real_engine(self):
        result = dataintegrity.check()
        if result.error:
            pytest.skip(result.error)
        assert result.ok, result.failures
        assert result.checked == len(dataintegrity.PAYLOADS)
        assert result.roundtrip_ok == result.checked
        assert result.false_positive_detections == []

    def test_sha_helper_is_stable(self):
        assert dataintegrity._sha("abc") == dataintegrity._sha("abc")
        assert dataintegrity._sha("abc") != dataintegrity._sha("abd")


# ----------------------------------------------------------------- systemd
class TestSystemdHelpers:
    def test_unit_file_path(self):
        assert systemd._unit_file("x.service") == "/etc/systemd/system/x.service"

    def test_ppid_of_missing_pid_is_zero(self):
        assert systemd._ppid_of(0) == 0
        assert systemd._ppid_of(999999999) == 0

    def test_ppid_of_real_process(self):
        assert systemd._ppid_of(1) == 0  # init itself

    def test_port_from_execstart(self, tmp_path, monkeypatch):
        unit = tmp_path / "u.service"
        unit.write_text(
            "[Service]\nExecStart=/bin/x --port 8099\n", encoding="utf-8")
        monkeypatch.setattr(systemd, "_unit_file", lambda u: str(unit))
        assert systemd._port_from_execstart("u.service") == 8099

    def test_port_absent_is_zero(self, tmp_path, monkeypatch):
        unit = tmp_path / "u.service"
        unit.write_text("[Service]\nExecStart=/bin/x\n", encoding="utf-8")
        monkeypatch.setattr(systemd, "_unit_file", lambda u: str(unit))
        assert systemd._port_from_execstart("u.service") == 0

    def test_missing_unit_reports_problem(self):
        report = systemd.check_unit("definitely-not-a-unit-xyz.service")
        assert not report.exists
        assert not report.ok
        assert "unit file missing" in report.problems

    @pytest.mark.skipif(not shutil.which("systemctl"), reason="no systemd")
    def test_sweep_returns_one_report_per_unit(self):
        reports = systemd.sweep(("mem20corez-serve.service",))
        assert len(reports) == 1
        assert reports[0].unit == "mem20corez-serve.service"
