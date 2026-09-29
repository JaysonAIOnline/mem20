"""Tests for indexing roots that live outside the monorepo.

The motivating case is /sb: a real tool that deliberately does not live under
/opt/mem20. These tests use a throwaway directory so they never depend on /sb
being present.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mem20sitemapz import cli, report, search  # noqa: E402
from mem20sitemapz.index import scan, scan_extra  # noqa: E402


@pytest.fixture
def outside_root(tmp_path: Path) -> Path:
    """A project shaped like /sb: pyproject one level down, no root pyproject."""
    root = tmp_path / "outside"
    backend = root / "backend" / "widgetz"
    backend.mkdir(parents=True)
    (backend / "cli.py").write_text("def main():\n    return 0\n", encoding="utf-8")
    (backend / "store.py").write_text("X = 1\n", encoding="utf-8")
    (backend / "pyproject.toml").write_text(
        '[project]\nname = "widgetz"\nversion = "0.2.0"\n'
        'description = "A widget tool that lives elsewhere."\n'
        'keywords = ["widgets", "tool"]\n'
        '[project.scripts]\nwidgetz = "widgetz.cli:main"\n',
        encoding="utf-8",
    )
    (root / "frontend").mkdir()
    (root / "frontend" / "index.html").write_text("<html></html>\n", encoding="utf-8")
    (root / "README.md").write_text("# widgetz\n\nThe outside tool.\n", encoding="utf-8")
    return root


class TestScanExtra:
    def test_an_outside_root_is_one_entry_not_a_directory_listing(self, outside_root: Path):
        entries = scan_extra(outside_root)
        assert len(entries) == 1
        # Not "backend", "frontend", "data" - one entry for the whole project.
        assert entries[0]["name"] == "widgetz"

    def test_the_entry_carries_the_real_path(self, outside_root: Path):
        entry = scan_extra(outside_root)[0]
        assert entry["dir"] == str(outside_root.resolve())
        assert entry["external_root"] == str(outside_root.resolve())

    def test_the_entry_is_flagged_external(self, outside_root: Path):
        assert scan_extra(outside_root)[0]["external"] is True

    def test_metadata_is_found_even_though_pyproject_is_nested(self, outside_root: Path):
        entry = scan_extra(outside_root)[0]
        assert entry["packaged"] is True
        assert entry["version"] == "0.2.0"
        assert entry["keywords"] == ["widgets", "tool"]
        assert entry["entry_points"] == {"widgetz": "widgetz.cli:main"}

    def test_readme_is_picked_up_from_the_root(self, outside_root: Path):
        entry = scan_extra(outside_root)[0]
        assert entry["readme_summary"] == "widgetz"
        assert "outside tool" in entry["readme_text"]

    def test_source_files_are_counted_across_the_whole_tree(self, outside_root: Path):
        entry = scan_extra(outside_root)[0]
        assert entry["languages"]["python"] == 2
        assert entry["languages"]["html"] == 1

    def test_a_missing_root_yields_nothing_rather_than_raising(self, tmp_path: Path):
        assert scan_extra(tmp_path / "does-not-exist") == []

    def test_an_empty_root_yields_nothing(self, tmp_path: Path):
        empty = tmp_path / "empty"
        empty.mkdir()
        assert scan_extra(empty) == []

    def test_a_root_with_no_pyproject_still_gets_an_entry(self, tmp_path: Path):
        root = tmp_path / "plain"
        (root / "a").mkdir(parents=True)
        (root / "a" / "x.py").write_text("y = 1\n", encoding="utf-8")
        entries = scan_extra(root)
        assert len(entries) == 1
        assert entries[0]["name"] == "plain"
        assert entries[0]["packaged"] is False

    def test_databases_and_caches_are_not_counted_as_source(self, outside_root: Path):
        before = scan_extra(outside_root)[0]["file_count"]
        (outside_root / "data").mkdir()
        (outside_root / "data" / "board.db").write_bytes(b"sqlite")
        (outside_root / "backend" / "widgetz" / "__pycache__").mkdir()
        (outside_root / "backend" / "widgetz" / "__pycache__" / "x.pyc").write_bytes(b"\x00")
        after = scan_extra(outside_root)[0]
        # The database and the bytecode are excluded, so adding them must not
        # move the count. If either started counting, this would fail.
        assert after["file_count"] == before
        assert "__pycache__" not in after["subdirs"]
        # A directory holding only skipped files is not part of the project.
        assert "data" not in after["subdirs"]


class TestBuildMerges:
    def _args(
        self,
        monorepo: Path,
        index_dir: Path,
        extra: list[Path],
        no_extra_roots: bool = False,
    ) -> argparse.Namespace:
        return argparse.Namespace(
            root=str(monorepo),
            index_dir=str(index_dir),
            depth=14,
            extra_root=[str(e) for e in extra],
            no_extra_roots=no_extra_roots,
            verbose=False,
        )

    @pytest.fixture
    def monorepo(self, tmp_path: Path) -> Path:
        root = tmp_path / "mono"
        pkg = root / "mem20fanz"
        pkg.mkdir(parents=True)
        (pkg / "cli.py").write_text("def main():\n    return 0\n", encoding="utf-8")
        (pkg / "pyproject.toml").write_text(
            '[project]\nname = "mem20fanz"\nversion = "0.1.0"\ndescription = "Inside."\n',
            encoding="utf-8",
        )
        return root

    def test_build_includes_both_roots(self, monorepo, outside_root, tmp_path):
        args = self._args(monorepo, tmp_path / "idx", [outside_root])
        assert cli.cmd_build(args) == 0
        index = json.loads((tmp_path / "idx" / "sitemap.json").read_text(encoding="utf-8"))
        names = {s["name"] for s in index["subsystems"]}
        assert {"mem20fanz", "widgetz"} <= names

    def test_build_records_every_root(self, monorepo, outside_root, tmp_path):
        args = self._args(monorepo, tmp_path / "idx", [outside_root])
        cli.cmd_build(args)
        index = json.loads((tmp_path / "idx" / "sitemap.json").read_text(encoding="utf-8"))
        assert index["roots"] == [str(monorepo), str(outside_root.resolve())]

    def test_totals_include_the_outside_root(self, monorepo, outside_root, tmp_path):
        args = self._args(monorepo, tmp_path / "idx", [outside_root])
        cli.cmd_build(args)
        index = json.loads((tmp_path / "idx" / "sitemap.json").read_text(encoding="utf-8"))
        totals = index["totals"]
        assert totals["subsystems"] == len(index["subsystems"])
        assert totals["files"] == sum(s["file_count"] for s in index["subsystems"])
        assert totals["code_lines"] == sum(s["code_lines"] for s in index["subsystems"])

    def test_no_extra_roots_flag_scans_the_monorepo_only(self, monorepo, outside_root, tmp_path):
        args = self._args(monorepo, tmp_path / "idx", [outside_root], no_extra_roots=True)
        cli.cmd_build(args)
        index = json.loads((tmp_path / "idx" / "sitemap.json").read_text(encoding="utf-8"))
        assert {s["name"] for s in index["subsystems"]} == {"mem20fanz"}

    def test_a_missing_extra_root_does_not_fail_the_build(self, monorepo, tmp_path):
        args = self._args(monorepo, tmp_path / "idx", [tmp_path / "nope"])
        assert cli.cmd_build(args) == 0
        index = json.loads((tmp_path / "idx" / "sitemap.json").read_text(encoding="utf-8"))
        assert {s["name"] for s in index["subsystems"]} == {"mem20fanz"}

    def test_the_outside_tool_is_findable_by_search(self, monorepo, outside_root, tmp_path):
        args = self._args(monorepo, tmp_path / "idx", [outside_root])
        cli.cmd_build(args)
        index = json.loads((tmp_path / "idx" / "sitemap.json").read_text(encoding="utf-8"))
        hits = search.search(index, "widgetz")
        assert hits and hits[0]["entry"]["name"] == "widgetz"
        found = search.find(index, "widgetz")
        assert found is not None
        assert found["dir"] == str(outside_root.resolve())


class TestReport:
    def _index(self, outside_root: Path) -> dict:
        root_scan = {
            "schema": "x",
            "generated_at": "now",
            "root": "/opt/mem20",
            "roots": ["/opt/mem20", str(outside_root.resolve())],
            "scan_seconds": 1.0,
            "totals": {"subsystems": 2, "files": 5, "lines": 50, "code_lines": 40,
                       "languages": {"python": 4}, "categories": {"organ": 2}},
            "root_files": [],
            "root_languages": {},
            "subsystems": [
                {"name": "mem20fanz", "dir": "mem20fanz", "category": "organ",
                 "code_lines": 20, "test_files": 1, "entry_points": {}, "description": "Inside."},
                *scan_extra(outside_root),
            ],
        }
        return root_scan

    def test_outside_tools_get_their_own_section(self, outside_root: Path):
        text = report.render_markdown(self._index(outside_root))
        assert "## Outside the monorepo" in text

    def test_the_outside_section_shows_the_real_path(self, outside_root: Path):
        text = report.render_markdown(self._index(outside_root))
        assert str(outside_root.resolve()) in text

    def test_an_outside_entry_is_not_listed_as_a_mem20_subsystem(self, outside_root: Path):
        text = report.render_markdown(self._index(outside_root))
        organ_section = text.split("## Native subsystem")[1].split("## Outside")[0]
        assert "widgetz" not in organ_section

    def test_ordinary_projects_get_no_outside_section(self, outside_root: Path):
        index = self._index(outside_root)
        index["subsystems"] = index["subsystems"][:1]
        text = report.render_markdown(index)
        assert "## Outside the monorepo" not in text

    def test_scan_of_a_plain_tree_is_unchanged(self, tmp_path: Path):
        root = tmp_path / "mono"
        (root / "pkg").mkdir(parents=True)
        (root / "pkg" / "a.py").write_text("x = 1\n", encoding="utf-8")
        index = scan(root)
        assert index["roots"] == [str(root.resolve())]
        assert all(not s.get("external") for s in index["subsystems"])
