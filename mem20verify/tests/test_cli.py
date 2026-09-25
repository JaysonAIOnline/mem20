"""CLI surface tests.

The CLI must never manufacture a pass: a check that cannot run has to exit
non-zero with a real error, not return 0.
"""

from __future__ import annotations

import json

import pytest

from mem20verify import cli


def test_parser_exposes_every_check():
    parser = cli.build_parser()
    for command in ("systemd", "tests", "baseline", "outage",
                    "dataintegrity", "lint", "all"):
        args = parser.parse_args([command] if command not in
                                 ("baseline", "lint") else
                                 ([command, "pkg"] if command == "baseline"
                                  else [command, "."]))
        assert args.command == command


def test_missing_command_is_an_error():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([])


def test_baseline_without_ids_errors(capsys):
    code = cli.main(["baseline", "somepkg"])
    assert code == cli.EXIT_ERROR
    assert "error" in capsys.readouterr().err


def test_lint_on_clean_file_passes(tmp_path, capsys):
    clean = tmp_path / "clean.py"
    clean.write_text("def f(x):\n    return x + 1\n", encoding="utf-8")
    assert cli.main(["lint", str(clean)]) == cli.EXIT_OK
    assert "0 issue" in capsys.readouterr().out


def test_lint_detects_and_exits_nonzero(tmp_path, capsys):
    bad = tmp_path / "bad.py"
    bad.write_text(
        "def f(cond, log):\n"
        "    if cond:\n"
        "        log('x')\n"
        "    else:\n"
        "        log('x')\n",
        encoding="utf-8",
    )
    assert cli.main(["lint", str(bad)]) == cli.EXIT_FINDINGS
    assert "identical-branches" in capsys.readouterr().out


def test_lint_json_is_parseable(tmp_path, capsys):
    bad = tmp_path / "bad.py"
    bad.write_text("def f():\n    pass\n", encoding="utf-8")
    cli.main(["--json", "lint", str(bad)])
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["scanned"] == 1
    assert payload["issues"]


def test_unknown_command_exits_error():
    with pytest.raises(SystemExit):
        cli.main(["not-a-command"])
