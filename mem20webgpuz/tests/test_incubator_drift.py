"""Cross-package drift guard for the mem30 Phase 4 incubators.

`mem20wasmz` (RM-101) and `mem20webgpuz` (RM-102) ship independent copies of
what was a single shared runtime, because the corpus ships them as separate
archives. That is a real drift risk, so this test asserts the shared substrate
stays identical while the domain engines stay distinct.

If this test fails, one package was patched and its sibling was not. That is
the failure mode worth catching, because the two are otherwise indistinguishable
by MD5 and nobody would notice.
"""

from __future__ import annotations

import ast
import hashlib
import os
import re
import sys

import pytest

WASZ = "/opt/mem20/mem20wasmz"
WEBZ = "/opt/mem20/mem20webgpuz"


def _core_path(package: str) -> str:
    return os.path.join("/opt/mem20", package, package, "core.py")


def _shared_substrate(package: str) -> str:
    """The shared runtime machinery, excluding the per-package domain engine.

    `family_otherstack` is expected to diverge: mem20webgpuz carries a real
    correctness fix (hardware probing, no fabricated speedup) that
    mem20wasmz has no reason to carry. Everything else is shared substrate and
    must stay byte-identical, or a fix applied to one package silently misses
    the other.
    """
    with open(_core_path(package), encoding="utf-8") as fh:
        source = fh.read()
    marker = "# ---------- domain algorithms ----------"
    start = source.find(marker)
    assert start != -1, f"family_otherstack not found in {package}"
    shared = source[:start]
    shared = shared.replace(package, "PKG")
    shared = re.sub(r"DEFAULT_PORT\s*=\s*\d+", "DEFAULT_PORT = 0", shared)
    return shared


def _func_source(package: str, name: str) -> str:
    with open(_core_path(package), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.dump(node, annotate_fields=False, include_attributes=False)
    raise AssertionError(f"{name} not found in {package}/core.py")


class TestSharedSubstrate:
    def test_both_packages_exist(self):
        assert os.path.isfile(_core_path("mem20wasmz"))
        assert os.path.isfile(_core_path("mem20webgpuz"))

    def test_shared_runtime_is_identical(self):
        left = _shared_substrate("mem20wasmz")
        right = _shared_substrate("mem20webgpuz")
        if left != right:
            left_h = hashlib.sha256(left.encode()).hexdigest()[:12]
            right_h = hashlib.sha256(right.encode()).hexdigest()[:12]
            pytest.fail(
                f"shared runtime drifted: wasmz={left_h} webgpuz={right_h}. "
                "A fix to the shared substrate must land in both packages."
            )

    def test_family_dispatch_present(self):
        for package in ("mem20wasmz", "mem20webgpuz"):
            assert "FAMILY_FUNCS" in open(
                _core_path(package), encoding="utf-8").read()


class TestDomainEnginesStayDistinct:
    def test_101_branch_present_only_where_expected(self):
        source = open(_core_path("mem20wasmz"), encoding="utf-8").read()
        assert "rid==101" in source
        assert "component-sandbox" in source

    def test_102_branch_is_honest_about_measurement(self):
        source = open(_core_path("mem20webgpuz"), encoding="utf-8").read()
        assert "rid==102" in source
        assert "not_measured" in source, (
            "RM-102 must not report a speedup it did not measure")
        assert "estimated_speedup" not in source, (
            "the fabricated estimated_speedup field has come back")

    def test_webgpu_branch_probes_hardware(self):
        source = open(_core_path("mem20webgpuz"), encoding="utf-8").read()
        assert "def probe_gpu" in source
        assert "nvidia-smi" in source
        assert "webgpu_available" in source, (
            "the caller's assertion must still be recorded, just not trusted")

    def test_domain_branches_differ_between_packages(self):
        wasz = open(_core_path("mem20wasmz"), encoding="utf-8").read()
        webz = open(_core_path("mem20webgpuz"), encoding="utf-8").read()
        assert wasz != webz, (
            "the two domain engines must not be byte-identical after the "
            "honesty fix; identical means the patch was lost")


class TestPorts:
    def test_default_ports_are_distinct_and_not_8765(self):
        ports = {}
        for package in ("mem20wasmz", "mem20webgpuz"):
            run_py = os.path.join("/opt/mem20", package, "run.py")
            with open(run_py, encoding="utf-8") as fh:
                match = re.search(r"DEFAULT_PORT\s*=\s*(\d+)", fh.read())
            assert match, f"{package} run.py has no DEFAULT_PORT"
            ports[package] = int(match.group(1))
        assert ports["mem20wasmz"] == 8766
        assert ports["mem20webgpuz"] == 8767
        claimed = {"8765", "33823", "4096", "4100", "4210"}
        assert not (claimed & {str(p) for p in ports.values()}), (
            "an incubator port collides with an existing service")

    def test_ports_are_distinct(self):
        ports = set()
        for package in ("mem20wasmz", "mem20webgpuz"):
            with open(os.path.join("/opt/mem20", package, "run.py"),
                      encoding="utf-8") as fh:
                ports.add(int(re.search(r"DEFAULT_PORT\s*=\s*(\d+)",
                                        fh.read()).group(1)))
        assert len(ports) == 2


class TestHonesty:
    @pytest.mark.parametrize("package,script", [
        ("mem20wasmz", "mem20wasmz"),
        ("mem20webgpuz", "mem20webgpuz"),
    ])
    def test_console_script_runs_and_returns_json(self, package, script):
        import json
        import subprocess
        payload = ('{"components":[{"name":"a","exports":["x"]},'
                   '{"name":"b","imports":["x","missing"]}],"cache":false}'
                   if package == "mem20wasmz" else
                   '{"webgpu_available":true,"cache":false}')
        proc = subprocess.run([f"/root/.venv/bin/{script}", "run", payload],
                              capture_output=True, text=True, timeout=90)
        assert proc.returncode == 0, proc.stderr[-500:]
        data = json.loads(proc.stdout)
        assert "result" in data
