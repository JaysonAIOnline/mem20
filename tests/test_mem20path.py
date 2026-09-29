"""Tests for mem20path, which exposes mem20 CLIs on the default PATH."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mem20path import EXCLUDED, discover_scripts, plan, run  # noqa: E402


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
