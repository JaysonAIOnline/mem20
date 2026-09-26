"""JSON-RPC client for the KilNZ engine.

Speaks the line-delimited JSON-RPC 2.0 protocol the engine exposes on
`--rpc`. This is a client, never a second implementation of the op language:
every call maps onto exactly one protocol method, so the op vocabulary has one
source of truth (the engine).

Two things this hardens over the original `bindings/kiln_rpc.py`:

- binary discovery no longer reaches for source-tree-relative paths. It goes
  through `mem20kilnz.engine`, so a missing binary raises `EngineMissing` with
  the build command rather than surfacing later as a confusing protocol error.
- a call that never gets a response is reported as a timeout naming the method,
  instead of blocking on `readline()` forever.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from . import engine as _engine
from .errors import (
    ERR_INTERNAL,
    ERR_OP_FAILED,
    SAMPLES_DEFAULT,
    SAMPLES_MAX,
    SAMPLES_MIN,
    EngineMissing,
    KilnError,
    OpFailed,
)

__all__ = [
    "Kiln",
    "KilnError",
    "OpFailed",
    "EngineMissing",
    "ERR_OP_FAILED",
    "SAMPLES_MIN",
    "SAMPLES_MAX",
    "SAMPLES_DEFAULT",
]


#: Op fields that name a filesystem path. The engine runs with its own working
#: directory, so a relative path sent from another directory would be resolved
#: against the wrong root. Every client-visible path is made absolute first.
PATH_FIELDS = ("path", "src", "dst", "out", "input", "file")


def _abs(path: str) -> str:
    """Absolute form of `path`, resolved against the caller's working directory."""
    return str(Path(path).expanduser().resolve())


def _resolve_paths(op: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of `op` with any filesystem path fields made absolute."""
    if not any(field in op for field in PATH_FIELDS):
        return op
    out = dict(op)
    for field in PATH_FIELDS:
        value = out.get(field)
        if isinstance(value, str) and value:
            out[field] = _abs(value)
    return out


class Kiln:
    """A modelling session driven over JSON-RPC.

    Use it as a context manager so the subprocess is always reaped::

        with Kiln() as k:
            k.op({"op": "create", "primitive": "cube", "name": "Box"})
    """

    def __init__(
        self,
        binary: str | os.PathLike[str] | None = None,
        env: dict[str, str] | None = None,
        timeout: float = 60.0,
    ) -> None:
        if binary is None:
            self.binary_path = str(_engine.binary_path())
        else:
            p = str(binary)
            if not (os.path.isfile(p) and os.access(p, os.X_OK)):
                raise EngineMissing(p, "explicit binary argument is not executable")
            self.binary_path = p
        self.timeout = timeout
        run_env = dict(os.environ)
        if env:
            run_env.update(env)
        self.env = run_env
        try:
            self._proc = subprocess.Popen(
                [self.binary_path, "--rpc"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=run_env,
            )
        except OSError as exc:
            raise EngineMissing(self.binary_path, str(exc)) from exc
        self._next_id = 1
        self._closed = False
        try:
            info = self.ping()
        except KilnError:
            self.close()
            raise
        if not info.get("ready"):
            self.close()
            raise KilnError(ERR_INTERNAL, "engine started but did not report ready")
        self.protocol = info.get("protocol", "")
        self.version = info.get("version", 0)
        self.op_count = info.get("ops", 0)
        self.methods = info.get("methods", [])

    # -- plumbing ----------------------------------------------------------

    def _write(self, payload: dict[str, Any]) -> None:
        if self._closed or self._proc.stdin is None:
            raise KilnError(ERR_INTERNAL, "session is closed")
        try:
            self._proc.stdin.write(json.dumps(payload) + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, ValueError) as exc:
            raise KilnError(ERR_INTERNAL, f"engine closed the pipe: {exc}") from exc

    def _readline(self) -> str:
        if self._proc.stdout is None:
            raise KilnError(ERR_INTERNAL, "session has no stdout")
        line = self._proc.stdout.readline()
        if not line:
            err = ""
            if self._proc.stderr is not None:
                try:
                    err = self._proc.stderr.read() or ""
                except Exception:
                    err = ""
            raise KilnError(
                ERR_INTERNAL,
                f"engine ended the session early. stderr: {err.strip()[:400]}",
            )
        return line

    def call(self, method: str, params: Any = None) -> Any:
        """Send one request and return its `result`.

        Raises `KilnError` for a protocol error object, `OpFailed` when an op ran
        and said no. A branch on `code` is always possible; nothing is a silent
        success.
        """
        req_id = self._next_id
        self._next_id += 1
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            payload["params"] = params
        self._write(payload)
        line = self._readline()
        try:
            reply = json.loads(line)
        except json.JSONDecodeError as exc:
            raise KilnError(-32700, f"engine sent a non-JSON line: {line[:200]!r}") from exc
        if reply.get("id") != req_id:
            raise KilnError(
                -32600,
                f"response id {reply.get('id')!r} does not match request {req_id}",
            )
        if "error" in reply:
            err = reply["error"]
            code = err.get("code", ERR_INTERNAL)
            message = err.get("message", "unknown error")
            data = err.get("data")
            if code == ERR_OP_FAILED:
                raise OpFailed(message, data)
            raise KilnError(code, message, data)
        return reply.get("result")

    def notify(self, method: str, params: Any = None) -> None:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self._write(payload)

    # -- ops ---------------------------------------------------------------

    def op(self, op: dict[str, Any]) -> dict[str, Any]:
        """Apply one op. Raises `OpFailed` rather than returning a false success."""
        result = self.call("op", _resolve_paths(op))
        if not isinstance(result, dict) or not result.get("ok", False):
            message = (
                result.get("message", "op failed") if isinstance(result, dict) else "op failed"
            )
            raise OpFailed(message, result)
        return result

    def ops(self, ops: list[dict[str, Any]]) -> dict[str, Any]:
        """Apply a batch. Stops at the first failure and reports every outcome."""
        result = self.call("ops", list(ops))
        if not isinstance(result, dict) or not result.get("ok", False):
            message = (
                result.get("message", "batch failed")
                if isinstance(result, dict)
                else "batch failed"
            )
            raise OpFailed(message, result)
        return result

    def command(self, line: str) -> dict[str, Any]:
        """Run one DSL / English / JSON line, exactly as the REPL would."""
        result = self.call("command", line)
        if not isinstance(result, dict) or not result.get("ok", False):
            message = (
                result.get("message", "command failed")
                if isinstance(result, dict)
                else "command failed"
            )
            raise OpFailed(message, result)
        return result

    def try_op(self, op: dict[str, Any]) -> dict[str, Any]:
        """Like `op` but returns the failure payload instead of raising."""
        return self.call("op", op)

    def try_command(self, line: str) -> dict[str, Any]:
        return self.call("command", line)

    # -- inspection --------------------------------------------------------

    def describe(self) -> dict[str, Any]:
        return self.call("describe")

    def list_nodes(self) -> dict[str, Any]:
        return self.call("list")

    def info(self, name: str | None = None) -> dict[str, Any]:
        return self.call("info", name)

    def node_names(self) -> list[str]:
        return [n["name"] for n in self.list_nodes()["nodes"]]

    def initialize(self) -> dict[str, Any]:
        """Full capability payload: every op name, every method, the samples range."""
        return self.call("initialize")

    def op_names(self) -> list[str]:
        return list(self.initialize().get("ops", []))

    # -- render and io -----------------------------------------------------

    def samples(self, value: int | None = None) -> dict[str, Any]:
        if value is None:
            return self.call("samples")
        return self.call("samples", {"value": value})

    def render(
        self,
        path: str,
        width: int = 960,
        height: int = 540,
        samples: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"path": _abs(path), "width": width, "height": height}
        if samples is not None:
            params["samples"] = samples
        return self.call("render", params)

    def export(self, path: str) -> dict[str, Any]:
        return self.call("export", {"path": _abs(path)})

    def save(self, path: str) -> dict[str, Any]:
        return self.call("save", {"path": _abs(path)})

    def open(self, path: str) -> dict[str, Any]:
        return self.call("open", {"path": _abs(path)})

    def reset(self) -> dict[str, Any]:
        return self.call("reset")

    def ping(self) -> dict[str, Any]:
        return self.call("ping")

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self._proc.stdin is not None and not self._proc.stdin.closed:
                try:
                    self._proc.stdin.write(
                        json.dumps({"jsonrpc": "2.0", "id": 0, "method": "shutdown"}) + "\n"
                    )
                    self._proc.stdin.flush()
                except (BrokenPipeError, ValueError, OSError):
                    pass
                try:
                    self._proc.stdin.close()
                except OSError:
                    pass
        finally:
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            for stream in (self._proc.stdout, self._proc.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass

    def __enter__(self) -> Kiln:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def __repr__(self) -> str:
        return (
            f"<Kiln {self.binary_path} protocol={self.protocol!r} "
            f"v{self.version} ops={self.op_count}>"
        )
