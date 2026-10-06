"""Tests for mem20path, which exposes mem20 CLIs on the default PATH."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mem20path import (  # noqa: E402
    DEFAULT_TARGET,
    EXCLUDED,
    SYSTEMD_DEFAULT_PATH,
    discover_scripts,
    plan,
    run,
)


def _dist(site: Path, name: str, scripts: dict[str, str]) -> None:
    """Write a fake installed distribution with console scripts."""
    safe = name.replace("-", "_")
    info = site / f"{safe}-1.0.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: 1.0\n", encoding="utf-8"
    )
    body = "[console_scripts]\n" + "".join(f"{k} = {v}\n" for k, v in scripts.items())
    (info / "entry_points.txt").write_text(body, encoding="utf-8")


@pytest.fixture
def site(tmp_path: Path) -> Path:
    sp = tmp_path / "site-packages"
    sp.mkdir()
    return sp


@pytest.fixture
def venv(tmp_path: Path) -> Path:
    vb = tmp_path / "venv" / "bin"
    vb.mkdir(parents=True)
    return vb


def _script(venv: Path, name: str) -> None:
    path = venv / name
    path.write_text(f"#!/bin/sh\necho {name}\n", encoding="utf-8")
    os.chmod(path, 0o755)


class TestDiscovery:
    def test_finds_mem20_owned_scripts(self, site):
        _dist(site, "mem20ops", {"fs-ops": "mem20ops.fleet:main"})
        assert discover_scripts(site) == {"fs-ops": "mem20ops"}

    def test_ignores_third_party_scripts(self, site):
        _dist(site, "chromadb", {"chroma": "chromadb.cli:app"})
        assert discover_scripts(site) == {}

    def test_ignores_a_distribution_with_no_console_scripts(self, site):
        _dist(site, "mem20corez", {})
        assert discover_scripts(site) == {}

    def test_ownership_survives_an_underscore_spelling(self, site):
        _dist(site, "mem20agentz_sdk", {"mem20agentz_sdk": "x:main"})
        assert "mem20agentz_sdk" in discover_scripts(site)

    def test_a_blocking_server_is_excluded(self, site):
        _dist(site, "mem20", {"mem20-mcp": "x:main", "mem20-metrics": "y:main"})
        found = discover_scripts(site)
        assert "mem20-mcp" in found
        assert "mem20-metrics" not in found
        assert "serve_forever" in EXCLUDED["mem20-metrics"]

    def test_a_missing_site_packages_is_not_fatal(self, tmp_path):
        assert discover_scripts(tmp_path / "nope") == {}

    def test_malformed_metadata_does_not_stop_the_sweep(self, site):
        bad = site / "broken-1.0.dist-info"
        bad.mkdir()
        (bad / "METADATA").write_bytes(b"\xff\xfe not metadata at all \x00")
        (bad / "entry_points.txt").write_text("[console_scripts]\nbroken = x:main\n", encoding="utf-8")
        _dist(site, "mem20ops", {"fs-ops": "mem20ops.fleet:main"})
        # The broken one is skipped; the good one is still found.
        assert "fs-ops" in discover_scripts(site)


class TestPlan:
    def test_a_fresh_tool_is_marked_for_linking(self, site, venv, tmp_path):
        _dist(site, "mem20ops", {"fs-ops": "x:main"})
        _script(venv, "fs-ops")
        findings = plan(venv, site, tmp_path / "bin")
        assert [f.status for f in findings if f.script == "fs-ops"] == ["link"]

    def test_an_already_correct_link_is_current(self, site, venv, tmp_path):
        _dist(site, "mem20ops", {"fs-ops": "x:main"})
        _script(venv, "fs-ops")
        target_dir = tmp_path / "bin"
        target_dir.mkdir()
        (target_dir / "fs-ops").symlink_to(venv / "fs-ops")
        findings = plan(venv, site, target_dir)
        assert [f.status for f in findings if f.script == "fs-ops"] == ["current"]

    def test_a_real_file_is_never_clobbered(self, site, venv, tmp_path):
        _dist(site, "mem20ops", {"fs-ops": "x:main"})
        _script(venv, "fs-ops")
        target_dir = tmp_path / "bin"
        target_dir.mkdir()
        precious = target_dir / "fs-ops"
        precious.write_text("someone else's file\n", encoding="utf-8")
        findings = plan(venv, site, target_dir)
        conflict = [f for f in findings if f.script == "fs-ops"][0]
        assert conflict.status == "conflict"
        assert precious.read_text(encoding="utf-8") == "someone else's file\n"

    def test_a_stale_link_is_relinked(self, site, venv, tmp_path):
        _dist(site, "mem20ops", {"fs-ops": "x:main"})
        _script(venv, "fs-ops")
        target_dir = tmp_path / "bin"
        target_dir.mkdir()
        elsewhere = tmp_path / "old"
        elsewhere.mkdir()
        _script(elsewhere, "fs-ops")
        (target_dir / "fs-ops").symlink_to(elsewhere / "fs-ops")
        findings = plan(venv, site, target_dir)
        assert [f.status for f in findings if f.script == "fs-ops"] == ["link"]

    def test_a_missing_source_script_is_reported(self, site, venv, tmp_path):
        _dist(site, "mem20ops", {"fs-ops": "x:main"})
        findings = plan(venv, site, tmp_path / "bin")
        assert [f.status for f in findings if f.script == "fs-ops"] == ["missing"]

    def test_exclusions_are_visible_in_the_plan(self, site, venv, tmp_path):
        _dist(site, "mem20", {"mem20-metrics": "y:main"})
        findings = plan(venv, site, tmp_path / "bin")
        excluded = [f for f in findings if f.status == "excluded"]
        assert [f.script for f in excluded] == ["mem20-metrics"]


class TestRun:
    def _args(self, site, venv, tmp_path, *extra):
        return [
            "--target", str(tmp_path / "bin"),
            "--site", str(site),
            "--venv", str(venv),
            *extra,
        ]

    def test_dry_run_changes_nothing(self, site, venv, tmp_path, monkeypatch, capsys):
        import mem20path

        _dist(site, "mem20ops", {"fs-ops": "x:main"})
        _script(venv, "fs-ops")
        monkeypatch.setattr(mem20path, "SITE_PACKAGES", site)
        monkeypatch.setattr(mem20path, "VENV_BIN", venv)
        assert run(self._args(site, venv, tmp_path)) == 0
        assert not (tmp_path / "bin" / "fs-ops").exists()
        assert "dry run" in capsys.readouterr().out

    def test_apply_creates_the_link_and_it_works(self, site, venv, tmp_path, monkeypatch):
        import mem20path

        _dist(site, "mem20ops", {"fs-ops": "x:main"})
        _script(venv, "fs-ops")
        monkeypatch.setattr(mem20path, "SITE_PACKAGES", site)
        monkeypatch.setattr(mem20path, "VENV_BIN", venv)
        assert run(self._args(site, venv, tmp_path, "--apply")) == 0
        link = tmp_path / "bin" / "fs-ops"
        assert link.is_symlink()
        assert os.access(link, os.X_OK)

    def test_apply_is_idempotent(self, site, venv, tmp_path, monkeypatch, capsys):
        import mem20path

        _dist(site, "mem20ops", {"fs-ops": "x:main"})
        _script(venv, "fs-ops")
        monkeypatch.setattr(mem20path, "SITE_PACKAGES", site)
        monkeypatch.setattr(mem20path, "VENV_BIN", venv)
        run(self._args(site, venv, tmp_path, "--apply"))
        first = (tmp_path / "bin" / "fs-ops").resolve()
        run(self._args(site, venv, tmp_path, "--apply"))
        assert (tmp_path / "bin" / "fs-ops").resolve() == first

    def test_apply_repairs_a_stale_link(self, site, venv, tmp_path, monkeypatch):
        import mem20path

        _dist(site, "mem20ops", {"fs-ops": "x:main"})
        _script(venv, "fs-ops")
        target_dir = tmp_path / "bin"
        target_dir.mkdir()
        old = tmp_path / "old"
        old.mkdir()
        _script(old, "fs-ops")
        (target_dir / "fs-ops").symlink_to(old / "fs-ops")
        monkeypatch.setattr(mem20path, "SITE_PACKAGES", site)
        monkeypatch.setattr(mem20path, "VENV_BIN", venv)
        run(self._args(site, venv, tmp_path, "--apply"))
        assert (target_dir / "fs-ops").resolve() == (venv / "fs-ops").resolve()


class TestDefaultTargetIsOnTheSystemdPath:
    """The bug this file exists to prevent: linking into a directory systemd
    cannot see, while the tool's own verify() said everything was fine.

    ``/root/.local/bin`` looked right -- an interactive shell has it -- but
    systemd's compiled-in default PATH does not, so 19 units could not resolve a
    single mem20 CLI. Nothing tested the default, so nothing caught it.
    """

    def test_default_target_is_on_the_systemd_default_path(self):
        assert str(DEFAULT_TARGET) in SYSTEMD_DEFAULT_PATH.split(":")

    def test_systemd_default_path_excludes_the_shell_only_bin(self):
        # /root/.local/bin arrives from root's rc files, not from systemd.
        # If this ever passes, the old wrong premise has crept back in.
        assert "/root/.local/bin" not in SYSTEMD_DEFAULT_PATH.split(":")

    def test_verify_flags_a_link_that_systemd_cannot_see(
        self, site, venv, tmp_path, monkeypatch
    ):
        import mem20path

        # Stand in for systemd's PATH so the test is hermetic and still proves
        # the point: verify() measures against SYSTEMD_DEFAULT_PATH, and a link
        # outside that list is MISSING no matter that it exists and is valid.
        name = "mem20ghostz"
        _dist(site, "mem20ghostz", {name: "x:main"})
        _script(venv, name)
        visible = tmp_path / "usr-local-bin"
        visible.mkdir()
        invisible = tmp_path / "root-local-bin"
        invisible.mkdir()
        # The link exists and is a perfectly valid symlink. It is simply in a
        # directory systemd's PATH does not contain -- exactly the shipped bug.
        (invisible / name).symlink_to(venv / name)
        monkeypatch.setattr(
            mem20path, "SYSTEMD_DEFAULT_PATH", str(visible), raising=True
        )

        assert shutil.which(name, path=str(invisible)), "precondition: the link is valid"
        missing = mem20path.verify(site_packages=site, target_dir=invisible)
        assert name in missing, (
            "a link systemd cannot see must read as MISSING; this is the "
            "false negative that shipped"
        )
