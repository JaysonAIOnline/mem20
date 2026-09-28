import json
import sys

import pytest

from mem20cliz import (
    JSON_FLAG,
    add_json_flag,
    build_envelope,
    json_main,
    main,
    split_json_flag,
)


@json_main
def demo_main(argv=None) -> int:
    print("human line one")
    print("human line two")
    return 0


@json_main
def failing_main(argv=None) -> int:
    print("partial output")
    return 3


@json_main
def stderr_main(argv=None) -> int:
    import sys

    print("to stderr", file=sys.stderr)
    return 1


@json_main
def raising_main(argv=None) -> int:
    raise RuntimeError("boom")


@json_main
def exiting_main(argv=None) -> int:
    raise SystemExit(4)


@json_main
def uses_argv(argv=None) -> int:
    print(f"argv={argv}")
    return 0


def test_split_json_flag_removes_and_reports():
    assert split_json_flag(["sweep", "--json"]) == (True, ["sweep"])
    assert split_json_flag(["--json", "sweep"]) == (True, ["sweep"])
    assert split_json_flag(["sweep"]) == (False, ["sweep"])


def test_split_json_flag_removes_every_occurrence():
    requested, remaining = split_json_flag(["a", "--json", "b", "--json"])
    assert requested is True
    assert remaining == ["a", "b"]


def test_human_path_is_untouched(capsys):
    assert demo_main(["sweep"]) == 0
    out = capsys.readouterr().out
    assert out == "human line one\nhuman line two\n"


def test_human_path_takes_no_argv(capsys):
    assert demo_main() == 0
    assert "human line one" in capsys.readouterr().out


def test_json_mode_emits_valid_envelope(capsys):
    assert demo_main(["sweep", JSON_FLAG]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "mem20.cli/1"
    assert payload["ok"] is True
    assert payload["exit_code"] == 0
    assert payload["argv"] == ["sweep"]
    assert "human line one" in payload["stdout"]
    assert payload["stderr"] == ""


def test_json_mode_works_before_subcommand(capsys):
    assert demo_main([JSON_FLAG, "sweep"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["argv"] == ["sweep"]


def test_json_mode_does_not_leak_human_text(capsys):
    demo_main(["x", JSON_FLAG])
    raw = capsys.readouterr().out
    assert not raw.startswith("human line one")
    assert raw.lstrip().startswith("{")


def test_nonzero_exit_is_preserved(capsys):
    assert failing_main([JSON_FLAG]) == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["exit_code"] == 3
    assert payload["ok"] is False
    assert "partial output" in payload["stdout"]


def test_stderr_is_captured_into_envelope(capsys):
    assert stderr_main([JSON_FLAG]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert "to stderr" in payload["stderr"]
    assert payload["stderr"] != ""


def test_exception_becomes_exit_one(capsys):
    assert raising_main([JSON_FLAG]) == 1
    err = capsys.readouterr().err
    assert "RuntimeError: boom" in err


def test_system_exit_code_is_respected(capsys):
    assert exiting_main([JSON_FLAG]) == 4
    payload = json.loads(capsys.readouterr().out)
    assert payload["exit_code"] == 4


def test_wrapped_function_receives_argv_without_flag(capsys):
    assert uses_argv(["keep", JSON_FLAG, "this"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "argv=['keep', 'this']" in payload["stdout"]


def test_build_envelope_extra_fields():
    payload = build_envelope("c", ["a"], 0, "out", "", extra={"installed": True})
    assert payload["installed"] is True
    assert payload["schema"] == "mem20.cli/1"


def test_add_json_flag_registers_option():
    import argparse

    parser = argparse.ArgumentParser()
    add_json_flag(parser)
    assert parser.parse_args([JSON_FLAG]).json is True
    assert parser.parse_args([]).json is False


def test_module_main_json_mode(capsys):
    assert main([JSON_FLAG]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "mem20.cli/1"
    assert payload["installed"] is True


def test_module_main_human(capsys):
    assert main([]) == 0
    assert "mem20cliz" in capsys.readouterr().out


def test_envelope_is_json_serialisable_for_odd_output():
    class Odd:
        def __repr__(self):
            return "<odd>"

    payload = build_envelope("c", [], 0, str(Odd()), "")
    assert json.loads(json.dumps(payload))["stdout"] == "<odd>"


@json_main
def zero_arg_main() -> int:
    print("zero arg ran")
    return 0


@json_main
def keyword_argv_main(*, argv=None) -> int:
    print(f"kw argv={argv}")
    return 0


def test_zero_arg_main_is_not_passed_argv(capsys):
    assert zero_arg_main() == 0
    assert "zero arg ran" in capsys.readouterr().out


def test_zero_arg_main_json_mode(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["zero_arg_main", JSON_FLAG, "sub"])
    assert zero_arg_main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["argv"] == ["sub"]
    assert "zero arg ran" in payload["stdout"]


def test_keyword_only_argv_is_supported(capsys):
    assert keyword_argv_main(argv=["a", JSON_FLAG]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["argv"] == ["a"]


def test_envelope_built_when_command_needs_args(capsys):
    """A command that fails argument parsing still yields a valid envelope."""

    @json_main
    def needs_argv(argv=None) -> int:
        import argparse

        parser = argparse.ArgumentParser(prog="needs")
        parser.add_argument("required")
        args = parser.parse_args(argv)
        print(f"got {args.required}")
        return 0

    code = needs_argv([JSON_FLAG])
    payload = json.loads(capsys.readouterr().out)
    assert payload["exit_code"] == code
    assert payload["ok"] is (code == 0)
    assert "required" in payload["stderr"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
