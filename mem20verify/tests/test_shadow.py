"""Import-shadow detection tests.

These build throwaway package trees in tmp_path. They do not touch /opt/mem20
and do not depend on the estate's live state, except for one test that asserts
the real estate produces a self-consistent report.
"""

from __future__ import annotations

import os
import sys

import pytest

from mem20verify import cli, shadow

PY = sys.executable


def _make_pkg(root, name, layout="nested-flat", body="__version__ = '0'\n"):
    """Create a minimal importable package under `root`."""
    if layout == "src":
        pkg_dir = os.path.join(root, name, "src", name)
    else:
        pkg_dir = os.path.join(root, name, name)
    os.makedirs(pkg_dir, exist_ok=True)
    with open(os.path.join(pkg_dir, "__init__.py"), "w", encoding="utf-8") as fh:
        fh.write(body)
    with open(os.path.join(root, name, "pyproject.toml"), "w", encoding="utf-8") as fh:
        fh.write(f'[project]\nname = "{name}"\nversion = "0.1.0"\n')
    return pkg_dir


def test_discover_finds_pyproject_dirs(tmp_path):
    _make_pkg(str(tmp_path), "alpha")
    _make_pkg(str(tmp_path), "beta")
    assert shadow.discover(str(tmp_path)) == ["alpha", "beta"]


def test_layout_detection_distinguishes_src_from_nested_flat(tmp_path):
    _make_pkg(str(tmp_path), "srcy", layout="src")
    _make_pkg(str(tmp_path), "flaty", layout="nested-flat")
    assert shadow.detect_layout(str(tmp_path / "srcy"), "srcy") == "src"
    assert shadow.detect_layout(str(tmp_path / "flaty"), "flaty") == "nested-flat"


def test_import_name_read_from_pyproject_not_dirname(tmp_path):
    _make_pkg(str(tmp_path), "dirname-differs")
    name = shadow.import_name_for(str(tmp_path / "dirname-differs"), "dirname-differs")
    assert name == "dirname-differs"


def test_src_layout_package_resolves(tmp_path):
    """src layout is not by itself the protection - reachability is.

    mem20mktz is src-layout and still unimportable from the estate root,
    because it lives only in its own .venv. The test therefore makes the
    package genuinely reachable, and asserts that it then resolves.
    """
    _make_pkg(str(tmp_path), "resolves_ok", layout="src")
    report = shadow.check_package("resolves_ok", root=str(tmp_path), python=PY,
                                  pythonpath=str(tmp_path / "resolves_ok" / "src"))
    assert report.resolution == shadow.RESOLVES
    assert report.shadowed is False
    assert report.problems == []


def test_nested_flat_package_is_reported_shadowed(tmp_path, monkeypatch):
    """Classifier: namespace at the estate root but fine elsewhere.

    Reproducing the real shape (a meta_path-finder registration) needs a venv,
    so the two probe results are supplied directly. The rule under test is that
    a namespace-only result plus a clean control means a sibling shadow.
    """
    _make_pkg(str(tmp_path), "shadowedpkg", layout="nested-flat")
    monkeypatch.setattr(shadow, "probe", lambda *a, **k: {
        "resolution": shadow.RESOLVES if k.get("root") == shadow.CONTROL_ROOT
        else shadow.RAW_NAMESPACE,
        "search_path": [str(tmp_path / "shadowedpkg")],
    })
    report = shadow.check_package("shadowedpkg", root=str(tmp_path), python=PY)
    assert report.resolution == shadow.SHADOWED
    assert report.shadowed is True
    assert report.layout == "nested-flat"
    assert report.control == shadow.RESOLVES
    assert str(tmp_path / "shadowedpkg") in report.search_path


def test_package_unreachable_everywhere_is_distinguished(tmp_path):
    """Not-installed must not be reported as a sibling shadow.

    A src-layout package absent from every path entry fails from the estate
    root and from a neutral directory alike. That is a different defect with a
    different fix, and conflating the two produces wrong advice.
    """
    _make_pkg(str(tmp_path), "own_venv_only", layout="src")
    report = shadow.check_package("own_venv_only", root=str(tmp_path), python=PY)
    assert report.resolution == shadow.UNREACHABLE
    assert report.control != shadow.RESOLVES
    assert "not installed" in report.problems[0]
    assert "layout changes would not help" in report.problems[0]


def test_probe_never_executes_module_code(tmp_path):
    """find_spec must resolve the module without running it."""
    _make_pkg(str(tmp_path), "explodes", layout="src",
              body="raise SystemExit('module body executed')\n")
    result = shadow.probe("explodes", root=str(tmp_path), python=PY,
                          pythonpath=str(tmp_path / "explodes" / "src"))
    assert result["resolution"] == shadow.RESOLVES


def test_probe_reports_namespace_only_when_package_unreachable(tmp_path):
    """The probe must see the same-named directory as a namespace portion.

    The package here is deliberately not on any path entry, so the only thing
    matching its name is the sibling directory - a PEP 420 namespace portion.
    """
    _make_pkg(str(tmp_path), "namespaceonly", layout="nested-flat")
    result = shadow.probe("namespaceonly", root=str(tmp_path), python=PY)
    assert result["resolution"] == shadow.RAW_NAMESPACE
    assert str(tmp_path / "namespaceonly") in result["search_path"]


def test_path_entry_regular_package_beats_sibling_namespace(tmp_path):
    """Documents why some packages resolve and others do not.

    A regular package found on any path entry outranks a namespace portion
    found earlier (PEP 420). So a package registered with a plain .pth path
    entry is immune, while one registered through an appended meta_path finder
    is not - the finder is consulted only after PathFinder has already
    returned the namespace. Layout alone decides nothing.
    """
    _make_pkg(str(tmp_path), "viapath", layout="nested-flat")
    without = shadow.probe("viapath", root=str(tmp_path), python=PY)
    assert without["resolution"] == shadow.RAW_NAMESPACE

    with_entry = shadow.probe("viapath", root=str(tmp_path), python=PY,
                              pythonpath=str(tmp_path / "viapath"))
    assert with_entry["resolution"] == shadow.RESOLVES, (
        "a regular package on a path entry must outrank the namespace")


def test_probe_uses_cwd_not_script_dir(tmp_path):
    """Regression guard for the bug that made a whole sweep report clean.

    Running `python <script>` puts the script's directory on sys.path[0]; only
    `python -c` puts the working directory there. The probe must use the latter,
    otherwise the shadow condition is never reproduced.
    """
    _make_pkg(str(tmp_path), "cwdprobe", layout="nested-flat")
    result = shadow.probe("cwdprobe", root=str(tmp_path), python=PY)
    assert result["resolution"] == shadow.RAW_NAMESPACE, (
        "probe did not reproduce the namespace condition; it is measuring the "
        "wrong sys.path")
    neutral = shadow.probe("cwdprobe", root=shadow.CONTROL_ROOT, python=PY)
    assert neutral["resolution"] == shadow.NOT_FOUND


def test_probe_reports_missing_package(tmp_path):
    result = shadow.probe("definitely_absent_pkg_xyz", root=str(tmp_path), python=PY)
    assert result["resolution"] == shadow.NOT_FOUND


def test_probe_reports_error_for_bad_interpreter(tmp_path):
    result = shadow.probe("anything", root=str(tmp_path),
                          python="/nonexistent/python")
    assert result["resolution"] == shadow.ERROR
    assert "error" in result


def test_check_package_flags_not_installed(tmp_path):
    _make_pkg(str(tmp_path), "uninstalled_pkg", layout="src")
    # rename the import name so it cannot resolve
    os.rename(str(tmp_path / "uninstalled_pkg" / "src" / "uninstalled_pkg"),
              str(tmp_path / "uninstalled_pkg" / "src" / "other_name"))
    report = shadow.check_package("uninstalled_pkg", root=str(tmp_path), python=PY)
    assert report.resolution == shadow.UNREACHABLE
    assert report.problems


def test_sweep_raises_on_missing_root():
    with pytest.raises(RuntimeError):
        shadow.sweep(root="/nonexistent/root/xyz")


def test_sweep_raises_when_nothing_discovered(tmp_path):
    with pytest.raises(RuntimeError):
        shadow.sweep(root=str(tmp_path))


# ----------------------------------------------------------------- CLI layer
def test_cli_shadow_exits_findings_when_shadowed(tmp_path, capsys, monkeypatch):
    _make_pkg(str(tmp_path), "cli_shadow_case", layout="nested-flat")
    monkeypatch.setattr(shadow, "probe", lambda *a, **k: {
        "resolution": shadow.RESOLVES if k.get("root") == shadow.CONTROL_ROOT
        else shadow.RAW_NAMESPACE,
        "search_path": [str(tmp_path / "cli_shadow_case")],
    })
    code = cli.main(["shadow", "--root", str(tmp_path), "--python", PY])
    out = capsys.readouterr().out
    assert code == cli.EXIT_FINDINGS
    assert "SHADOW" in out


def test_cli_shadow_exits_ok_when_all_resolve(tmp_path, capsys):
    _make_pkg(str(tmp_path), "cli_clean_case", layout="src")
    code = cli.main(["shadow", "--root", str(tmp_path), "--python", PY,
                     "--pythonpath", str(tmp_path / "cli_clean_case" / "src")])
    assert code == cli.EXIT_OK
    assert "OK" in capsys.readouterr().out


def test_cli_shadow_json_is_machine_readable(tmp_path, capsys, monkeypatch):
    import json as _json
    _make_pkg(str(tmp_path), "cli_json_case", layout="nested-flat")
    monkeypatch.setattr(shadow, "probe", lambda *a, **k: {
        "resolution": shadow.RESOLVES if k.get("root") == shadow.CONTROL_ROOT
        else shadow.RAW_NAMESPACE,
        "search_path": [str(tmp_path / "cli_json_case")],
    })
    code = cli.main(["--json", "shadow", "--root", str(tmp_path), "--python", PY])
    payload = _json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_FINDINGS
    assert payload["ok"] is False
    assert payload["shadowed"][0]["package"] == "cli_json_case"
    assert payload["shadowed"][0]["control"] == shadow.RESOLVES


def test_cli_shadow_missing_root_is_error_not_pass(capsys):
    code = cli.main(["shadow", "--root", "/nonexistent/root/xyz"])
    assert code == cli.EXIT_ERROR
    assert "error" in capsys.readouterr().err


def test_parser_exposes_shadow():
    assert cli.build_parser().parse_args(["shadow"]).command == "shadow"


def test_cli_shadow_distinguishes_shadowed_from_unreachable(tmp_path, capsys,
                                                            monkeypatch):
    """The two verdicts must never render identically.

    Reporting a not-installed package as a sibling shadow would send someone to
    migrate a layout that was never the problem.
    """
    _make_pkg(str(tmp_path), "mixed_shadow", layout="nested-flat")
    _make_pkg(str(tmp_path), "mixed_unreach", layout="src")

    def fake_probe(import_name, root=shadow.DEFAULT_ROOT, **kwargs):
        if import_name == "mixed_shadow":
            if root == shadow.CONTROL_ROOT:
                return {"resolution": shadow.RESOLVES}
            return {"resolution": shadow.RAW_NAMESPACE,
                    "search_path": [str(tmp_path / "mixed_shadow")]}
        return {"resolution": shadow.NOT_FOUND}

    monkeypatch.setattr(shadow, "probe", fake_probe)
    code = cli.main(["shadow", "--root", str(tmp_path), "--python", PY])
    out = capsys.readouterr().out
    assert code == cli.EXIT_FINDINGS
    assert "SHADOWED  mixed_shadow" in out
    assert "UNREACH   mixed_unreach" in out


def test_live_estate_report_is_self_consistent():
    """Read-only sanity check against the real estate. No writes, no imports."""
    if not os.path.isdir(shadow.DEFAULT_ROOT):
        pytest.skip("estate root not present")
    reports = shadow.sweep(root=shadow.DEFAULT_ROOT, python=shadow.DEFAULT_PYTHON)
    assert reports
    for report in reports:
        assert report.resolution in (shadow.SHADOWED, shadow.UNREACHABLE,
                                     shadow.RESOLVES, shadow.NOT_FOUND,
                                     shadow.ERROR)
        if report.resolution == shadow.SHADOWED:
            # a sibling shadow is only credible if the package *does* import
            # from a neutral cwd, and the shadower must be named
            assert report.control == shadow.RESOLVES, (
                f"{report.package} reported as sibling-shadowed but does not "
                "import from a neutral cwd either")
            assert report.search_path, "a shadowed package must name its shadower"
        if report.resolution == shadow.UNREACHABLE:
            assert report.control != shadow.RESOLVES
