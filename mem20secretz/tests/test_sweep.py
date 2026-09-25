"""Behavioural tests for mem20secretz.

Every test asserts the property that matters: a value is detected where it
leaked, values never appear in output, and nothing on disk is modified.
"""

from __future__ import annotations

import os

import pytest

from mem20secretz.sweep import (
    SECRET_CRIT,
    SECRET_INFO,
    SweepResult,
    classify,
    load_store,
    sweep,
)

FAKE_KEY = "sk-live-AAAABBBBCCCCDDDDEEEEFFFFGGGGHHHH"
FAKE_URL = "https://api.example.invalid/v1/endpoint/path"


@pytest.fixture()
def estate(tmp_path):
    """A miniature estate: one store, a leaking file, a clean file."""
    store = tmp_path / "secrets"
    store.mkdir()
    (store / ".env").write_text(
        f"OPENAI_API_KEY={FAKE_KEY}\n"
        f"SERVICE_BASE_URL={FAKE_URL}\n",
        encoding="utf-8",
    )
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "leak.py").write_text(
        f'KEY = "{FAKE_KEY}"\n', encoding="utf-8"
    )
    (root / "pkg" / "config.py").write_text(
        f'URL = "{FAKE_URL}"\n', encoding="utf-8"
    )
    (root / "pkg" / "clean.py").write_text(
        "value = 42\n", encoding="utf-8"
    )
    return root, store


class TestClassification:
    def test_credential_name_is_critical(self):
        sev, kind = classify("OPENAI_API_KEY", FAKE_KEY)
        assert sev == SECRET_CRIT
        assert kind == "credential"

    def test_url_value_is_info(self):
        sev, kind = classify("SERVICE_BASE_URL", FAKE_URL)
        assert sev == SECRET_INFO
        assert kind == "config"

    def test_bare_url_value_is_info_regardless_of_name(self):
        sev, _ = classify("SOMETHING_WEIRD", "https://x.invalid/deep/path/here")
        assert sev == SECRET_INFO

    def test_password_is_critical(self):
        assert classify("DB_PASSWORD", "hunter2hunter2")[0] == SECRET_CRIT

    def test_token_is_critical(self):
        assert classify("GH_TOKEN", "ghp_" + "a" * 36)[0] == SECRET_CRIT


class TestStoreLoading:
    def test_loads_env_pairs(self, estate):
        _, store = estate
        values = load_store(str(store))
        assert values["OPENAI_API_KEY"] == FAKE_KEY

    def test_strips_quotes(self, tmp_path):
        store = tmp_path / "secrets"
        store.mkdir()
        (store / ".env").write_text('K="quoted-value-1234"\n', encoding="utf-8")
        assert load_store(str(store))["K"] == "quoted-value-1234"

    def test_skips_short_values(self, tmp_path):
        store = tmp_path / "secrets"
        store.mkdir()
        (store / ".env").write_text("SHORT=abc\n", encoding="utf-8")
        assert "SHORT" not in load_store(str(store))

    def test_missing_store_is_empty(self, tmp_path):
        assert load_store(str(tmp_path / "nope")) == {}


class TestSweep:
    def test_finds_credential_leak(self, estate):
        root, store = estate
        result = sweep(root=str(root), store_dir=str(store), git_aware=False)
        leaked = [f for f in result.findings if f.variable == "OPENAI_API_KEY"]
        assert len(leaked) == 1
        assert leaked[0].severity == SECRET_CRIT
        assert leaked[0].path == "pkg/leak.py"

    def test_config_url_is_info_not_critical(self, estate):
        root, store = estate
        result = sweep(root=str(root), store_dir=str(store), git_aware=False)
        url_hits = [f for f in result.findings if f.variable == "SERVICE_BASE_URL"]
        assert url_hits and all(f.severity == SECRET_INFO for f in url_hits)
        assert not any(f.variable == "SERVICE_BASE_URL" for f in result.critical)

    def test_critical_only_hides_info(self, estate):
        root, store = estate
        result = sweep(root=str(root), store_dir=str(store),
                       include_info=False, git_aware=False)
        assert all(f.severity != SECRET_INFO for f in result.findings)
        assert result.info == []

    def test_clean_file_produces_nothing(self, estate):
        root, store = estate
        result = sweep(root=str(root), store_dir=str(store), git_aware=False)
        assert not any(f.path == "pkg/clean.py" for f in result.findings)

    def test_store_directory_itself_is_excluded(self, estate):
        root, store = estate
        result = sweep(root=str(root.parent), store_dir=str(store),
                       git_aware=False)
        assert not any(f.path.startswith("secrets/") for f in result.findings)

    def test_counts_are_populated(self, estate):
        root, store = estate
        result = sweep(root=str(root), store_dir=str(store), git_aware=False)
        assert result.values_hunted == 2
        assert result.files_scanned >= 3


class TestNoValueLeakage:
    def test_value_never_appears_in_repr(self, estate):
        root, store = estate
        result = sweep(root=str(root), store_dir=str(store), git_aware=False)
        blob = repr(result.as_dict())
        assert FAKE_KEY not in blob

    def test_value_never_appears_in_json(self, estate):
        import json
        root, store = estate
        result = sweep(root=str(root), store_dir=str(store), git_aware=False)
        assert FAKE_KEY not in json.dumps(result.as_dict())

    def test_preview_is_masked(self, estate):
        root, store = estate
        result = sweep(root=str(root), store_dir=str(store), git_aware=False)
        for finding in result.findings:
            assert FAKE_KEY not in finding.preview
            assert "..." in finding.preview


class TestNonDestructive:
    def test_sweep_does_not_modify_any_file(self, estate):
        root, store = estate
        before = {}
        for dirpath, _, filenames in os.walk(root):
            for fn in filenames:
                p = os.path.join(dirpath, fn)
                before[p] = (os.path.getsize(p), open(p, "rb").read())
        store_before = open(store / ".env", "rb").read()

        sweep(root=str(root), store_dir=str(store), git_aware=False)

        for p, (size, data) in before.items():
            assert os.path.getsize(p) == size
            assert open(p, "rb").read() == data
        assert open(store / ".env", "rb").read() == store_before

    def test_sweep_does_not_modify_store_files(self, estate):
        root, store = estate
        before = sorted(os.listdir(store))
        sweep(root=str(root), store_dir=str(store), git_aware=False)
        assert sorted(os.listdir(store)) == before


class TestResultShape:
    def test_as_dict_has_counts(self, estate):
        root, store = estate
        data = sweep(root=str(root), store_dir=str(store),
                     git_aware=False).as_dict()
        assert set(data["counts"]) == {
            "critical", "high", "info", "would_commit"}
        assert data["counts"]["critical"] >= 1

    def test_empty_store_yields_no_findings(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        result = sweep(root=str(tmp_path), store_dir=str(empty), git_aware=False)
        assert isinstance(result, SweepResult)
        assert result.findings == []
        assert result.values_hunted == 0
