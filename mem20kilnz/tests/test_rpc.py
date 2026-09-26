"""The RPC client against a live engine.

These tests exist to prove the client is honest: a bad op must raise, a missing
binary must be named rather than surfacing later as a protocol error, and the
op vocabulary the client reports must match what the engine actually dispatches.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from check_op_sync import advertised_ops, dispatched_ops, live_ops

from mem20kilnz import engine as _engine
from mem20kilnz.errors import EngineMissing, KilnError, OpFailed
from mem20kilnz.rpc import Kiln


def test_session_opens_and_reports_ready(kiln):
    assert kiln.protocol
    assert kiln.op_count > 0
    assert "op" in kiln.methods
    assert "shutdown" in kiln.methods


def test_ping_and_initialize_agree(kiln):
    names, payload = live_ops(kiln.binary_path)
    assert payload["ping_count"] == len(names), (
        "ping reports a count that disagrees with the list initialize returns"
    )


def test_advertised_ops_match_dispatch(engine_dir, binary):
    disp = dispatched_ops(engine_dir / "src/ops/ops.cpp")
    adv = advertised_ops(engine_dir / "src/core/rpc.hpp")
    assert not (disp - adv), f"dispatched but not advertised: {sorted(disp - adv)}"
    assert not (adv - disp), f"advertised but not dispatched: {sorted(adv - disp)}"


def test_op_count_is_stable_across_sessions(binary):
    counts = []
    for _ in range(2):
        with Kiln(binary) as k:
            counts.append(k.op_count)
    assert counts[0] == counts[1]


def test_op_raises_on_failure_not_silent_success(kiln):
    with pytest.raises(OpFailed) as exc:
        kiln.op({"op": "frame", "target": "NoSuchNode"})
    assert "NoSuchNode" in str(exc.value)


def test_try_op_returns_the_failure_instead_of_raising(kiln):
    result = kiln.try_op({"op": "frame", "target": "NoSuchNode"})
    assert isinstance(result, dict)
    assert result.get("ok") is False


def test_unknown_op_is_refused_with_the_valid_list(kiln):
    with pytest.raises((OpFailed, KilnError)) as exc:
        kiln.op({"op": "definitely_not_an_op"})
    assert "definitely_not_an_op" in str(exc.value)


def test_session_survives_a_failed_call(kiln):
    with pytest.raises(OpFailed):
        kiln.op({"op": "frame", "target": "Nope"})
    assert kiln.describe() is not None


def test_error_codes_match_the_engine_header():
    """The restated codes in errors.py must equal the engine's own."""
    header = (_engine.engine_source_dir() / "src/core/rpc.hpp").read_text()
    for name, value in (
        ("ERR_PARSE", -32700),
        ("ERR_INVALID_REQUEST", -32600),
        ("ERR_METHOD_NOT_FOUND", -32601),
        ("ERR_INVALID_PARAMS", -32602),
        ("ERR_INTERNAL", -32603),
        ("ERR_OP_FAILED", -32000),
        ("ERR_NO_SCENE", -32001),
        ("ERR_NOT_FOUND", -32002),
        ("ERR_NO_CAMERA", -32003),
        ("ERR_IO", -32004),
        ("ERR_BAD_SAMPLES", -32005),
        ("ERR_UNSUPPORTED", -32006),
    ):
        assert str(value) in header, f"{name}={value} is not present in the engine header"
        import mem20kilnz.errors as errors

        assert getattr(errors, name) == value


def test_missing_binary_names_the_build_command(tmp_path):
    missing = tmp_path / "not-a-real-binary"
    with pytest.raises(EngineMissing) as exc:
        Kiln(str(missing))
    assert "build-engine" in str(exc.value)


def test_kilnz_binary_override_is_honoured(monkeypatch, binary):
    monkeypatch.setenv("KILNZ_BINARY", binary)
    assert str(_engine.binary_path()) == binary


def test_engine_info_reports_absence_honestly(monkeypatch, tmp_path):
    monkeypatch.setenv("KILNZ_BINARY", str(tmp_path / "nope"))
    info = _engine.engine_info()
    assert info["binary_exists"] is False
    assert "binary_missing_reason" in info


def test_notify_sends_no_reply(kiln):
    kiln.notify("ping")
    assert kiln.ping() is not None


def test_raw_protocol_carries_only_json_on_stdout(binary):
    req = (
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}) + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "shutdown"}) + "\n"
    )
    proc = subprocess.run([binary, "--rpc"], input=req, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0
    for line in proc.stdout.splitlines():
        if line.strip():
            json.loads(line)


def test_relative_paths_resolve_against_the_caller_not_the_engine(tmp_path, monkeypatch):
    """The engine runs with its own CWD, so relative paths must be made absolute.

    Regression: a relative output path used to resolve inside the engine source
    tree, so the CLI reported "cannot write" for a directory the caller had
    already created.
    """
    from mem20kilnz.rpc import _resolve_paths

    monkeypatch.chdir(tmp_path)
    resolved = _resolve_paths({"op": "import", "path": "model.glb"})
    assert resolved["path"] == str(tmp_path / "model.glb")
    assert Path(resolved["path"]).is_absolute()

    # ops with no path field are passed through untouched
    same = {"op": "create", "primitive": "cube"}
    assert _resolve_paths(same) is same


def test_export_from_a_foreign_working_directory(kiln, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "elsewhere.glb"
    kiln.reset()
    kiln.op({"op": "create", "primitive": "cube", "name": "C"})
    kiln.export(str(out))
    assert out.is_file() and out.stat().st_size > 0
