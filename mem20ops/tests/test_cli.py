import json

import pytest

from mem20ops import cli


def test_parser_requires_subcommand():
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args([])
    assert exc.value.code == 2


def test_parser_rejects_unknown_subcommand():
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(["not-a-command"])
    assert exc.value.code == 2


def test_pages_delete_without_confirm_fails_without_network():
    code = cli.main(["pages-delete", "some-project"])
    assert code == cli.EXIT_FAIL


def test_identity_check_json_output(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MEM20_STORE_PATH", str(tmp_path / "store"))
    code = cli.main(["--json", "identity-check"])
    captured = capsys.readouterr()
    assert code == cli.EXIT_OK
    payload = json.loads(captured.out)
    assert "pinned_block_count" in payload
    assert "namespaces" in payload


def test_acl_probe_json_output(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MEM20_STORE_PATH", str(tmp_path / "store"))
    code = cli.main(["--json", "acl-probe", "some-ns", "--actor", "alice", "--actor", "bob"])
    captured = capsys.readouterr()
    assert code == cli.EXIT_OK
    payload = json.loads(captured.out)
    assert [row["actor"] for row in payload["actors"]] == ["alice", "bob"]


def test_lint_delta_bad_revision_returns_fail(tmp_path, capsys):
    code = cli.main(["lint-delta", "nope/missing.py", "--revision", "bogus-ref"])
    assert code == cli.EXIT_FAIL


def test_stale_code_missing_path_returns_fail(tmp_path):
    code = cli.main(["stale-code", str(tmp_path / "absent.py")])
    assert code == cli.EXIT_FAIL


def test_verify_with_no_tests_and_no_lint(tmp_path, capsys):
    code = cli.main(["--json", "verify", "--repo", str(tmp_path), "--no-tests", "--no-lint"])
    captured = capsys.readouterr()
    assert code == cli.EXIT_OK
    assert json.loads(captured.out)["ok"] is True


def test_exit_codes_are_distinct():
    codes = [cli.EXIT_OK, cli.EXIT_FAIL, cli.EXIT_FINDINGS, cli.EXIT_NO_CREDENTIALS]
    assert len(set(codes)) == len(codes)


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
