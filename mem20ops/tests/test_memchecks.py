import json

import pytest

from mem20ops import memchecks


def test_identity_check_isolated_store_has_no_content(tmp_path, monkeypatch):
    monkeypatch.setenv("MEM20_STORE_PATH", str(tmp_path / "store"))
    result = memchecks.identity_check()
    assert result["pinned_block_count"] == 0
    assert result["namespace_count"] == 0
    assert result["life_voice_blocks"] == []


def test_identity_check_parses_legacy_namespace_metadata(tmp_path, monkeypatch):
    store = tmp_path / "store"
    monkeypatch.setenv("MEM20_STORE_PATH", str(store))
    memchecks._load_engine(str(store))
    from memory import remember

    remember(
        topic="namespace_meta",
        content="Namespace: legacy-ns, Owner: legacy-owner, ACL: {'reader': 'read'}",
        tags=["namespace", "metadata", "legacy-ns"],
    )
    result = memchecks.identity_check()
    names = {ns["namespace"]: ns for ns in result["namespaces"]}
    assert "legacy-ns" in names
    assert names["legacy-ns"]["owner"] == "legacy-owner"
    assert names["legacy-ns"]["structured"] is False


def test_identity_check_parses_structured_namespace_metadata(tmp_path, monkeypatch):
    store = tmp_path / "store"
    monkeypatch.setenv("MEM20_STORE_PATH", str(store))
    memchecks._load_engine(str(store))
    from memory import remember

    payload = json.dumps(
        {"namespace": "new-ns", "owner": "owner-a", "acl": {"reader": "read"}},
        sort_keys=True,
    )
    remember(
        topic="namespace_meta",
        content="NSMETA2 " + payload,
        tags=["namespace", "metadata", "new-ns"],
    )
    result = memchecks.identity_check()
    names = {ns["namespace"]: ns for ns in result["namespaces"]}
    assert names["new-ns"]["owner"] == "owner-a"
    assert names["new-ns"]["structured"] is True
    assert names["new-ns"]["acl"] == {"reader": "read"}


def test_acl_probe_reports_per_actor(tmp_path, monkeypatch):
    store = tmp_path / "store"
    monkeypatch.setenv("MEM20_STORE_PATH", str(store))
    memchecks._load_engine(str(store))
    from memory import remember

    remember(topic="namespace_probe", content="life model secret", tags=["shared"])
    result = memchecks.acl_probe("probe", actors=["alice", "bob"], probe_query="life model")
    assert result["namespace"] == "probe"
    assert [row["actor"] for row in result["actors"]] == ["alice", "bob"]
    assert "ACL" in result["note"]


def test_acl_probe_does_not_cross_namespace_prefixes(tmp_path, monkeypatch):
    store = tmp_path / "store"
    monkeypatch.setenv("MEM20_STORE_PATH", str(store))
    memchecks._load_engine(str(store))
    from memory import remember

    remember(topic="namespace_ceo-10", content="life model ceo ten", tags=["shared"])
    result = memchecks.acl_probe("ceo-1", actors=["alice"])
    assert result["actors"][0]["matching_rows"] == 0


def test_lint_delta_detects_new_findings_in_temp_repo(tmp_path):
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    target = repo / "sample.py"
    target.write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "sample.py"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=repo,
        check=True,
    )
    target.write_text("import os\nimport sys\n", encoding="utf-8")
    result = memchecks.lint_delta("sample.py", repo=str(repo))
    assert "error" not in result, result
    assert result["after_total"] >= result["before_total"]


def test_lint_delta_reports_error_for_missing_revision(tmp_path):
    result = memchecks.lint_delta("does/not/exist.py", revision="nope-ref", repo=str(tmp_path))
    assert "error" in result
    assert "staged-but-uncommitted" in result["hint"]


def test_identity_check_reads_nested_blocks_file(tmp_path, monkeypatch):
    """pinned_blocks.json nests the real blocks under a 'blocks' key."""
    store = tmp_path / "store"
    store.mkdir()
    monkeypatch.setenv("MEM20_STORE_PATH", str(store))
    payload = {
        "blocks": {
            "pickle-life": {"content": "x", "ts": "1"},
            "pickle-voice": {"content": "y", "ts": "2"},
            "space-bunny-life": {"content": "z", "ts": "3"},
            "unrelated": {"content": "w", "ts": "4"},
        },
        "order": ["a", "b"],
    }
    (store / "pinned_blocks.json").write_text(json.dumps(payload), encoding="utf-8")
    result = memchecks.identity_check()
    assert result["pinned_block_count"] == 4, result["pinned_blocks"]
    assert result["pinned_blocks"] == [
        "pickle-life",
        "pickle-voice",
        "space-bunny-life",
        "unrelated",
    ]
    assert result["life_voice_blocks"] == [
        "pickle-life",
        "pickle-voice",
        "space-bunny-life",
    ]


def test_identity_check_reads_flat_blocks_file(tmp_path, monkeypatch):
    store = tmp_path / "store"
    store.mkdir()
    monkeypatch.setenv("MEM20_STORE_PATH", str(store))
    (store / "pinned_blocks.json").write_text(
        json.dumps({"pickle-life": {"content": "x"}}), encoding="utf-8"
    )
    result = memchecks.identity_check()
    assert result["pinned_block_count"] == 1
    assert result["pinned_blocks"] == ["pickle-life"]


def test_lint_delta_supports_index_revision(tmp_path):
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    target = repo / "sample.py"
    target.write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "sample.py"], cwd=repo, check=True)
    target.write_text("import os\n", encoding="utf-8")
    result = memchecks.lint_delta("sample.py", revision=":", repo=str(repo))
    assert "error" not in result, result
    assert result["after_total"] >= 1


def test_acl_probe_declares_raw_ledger_scope(tmp_path, monkeypatch):
    store = tmp_path / "store"
    monkeypatch.setenv("MEM20_STORE_PATH", str(store))
    memchecks._load_engine(str(store))
    result = memchecks.acl_probe("ns", actors=["stranger"])
    assert "no ACL layer" in result["scope"]
    assert "EXPECTED" in result["note"]


def test_isolated_store_creates_directory():
    path = memchecks.isolated_store("mem20ops_test_")
    assert path
    import os

    assert os.path.isdir(path)


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
