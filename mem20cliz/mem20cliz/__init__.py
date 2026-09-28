"""mem20cliz — the shared machine contract for mem20 fleet CLIs.

Gives any mem20 CLI a ``--json`` mode with a single decorator, without
changing what it prints for humans and without touching its command internals::

    from mem20cliz import json_main

    @json_main
    def main(argv: list[str] | None = None) -> int:
        ...

With ``--json`` anywhere in the arguments, the flag is removed, the command runs
exactly as it always would with its output captured, and a stable JSON envelope is
printed to stdout::

    {
      "ok": true,
      "command": "mem20secretz",
      "argv": ["sweep"],
      "exit_code": 0,
      "stdout": "...",
      "stderr": ""
    }

Guarantees:

* the human path is untouched — the wrapper only activates on ``--json``
* the child's real exit code is preserved in ``exit_code`` and returned
* the envelope schema is identical across every fleet CLI, so scripts can rely
  on one shape
* ``--json`` is accepted at any position, including before the subcommand
"""

from __future__ import annotations

import contextlib
import functools
import inspect
import io
import json
import os
import sys
from collections.abc import Callable
from typing import Any

SCHEMA_VERSION = 1
JSON_FLAG = "--json"


def add_json_flag(parser) -> None:
    """Register ``--json`` on an existing argparse parser (for explicit wiring)."""
    parser.add_argument(
        JSON_FLAG,
        action="store_true",
        help="emit a machine-readable JSON envelope instead of human output",
    )


def split_json_flag(argv: list[str]) -> tuple[bool, list[str]]:
    """Separate the ``--json`` flag from the argument list.

    Returns ``(json_requested, remaining_argv)``.
    """
    remaining = [a for a in argv if a != JSON_FLAG]
    return len(remaining) != len(argv), remaining


def build_envelope(
    command: str,
    argv: list[str],
    exit_code: int,
    stdout: str,
    stderr: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the stable JSON envelope every fleet CLI emits."""
    payload: dict[str, Any] = {
        "schema": f"mem20.cli/{SCHEMA_VERSION}",
        "ok": exit_code == 0,
        "command": command,
        "argv": list(argv),
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
    }
    if extra:
        payload.update(extra)
    return payload


def _program_name() -> str:
    return os.path.basename(sys.argv[0]) if sys.argv and sys.argv[0] else "unknown"


def _accepts_arg(func: Callable[..., int]) -> bool:
    """True when the wrapped main can accept an argv argument.

    Some subsystem CLIs expose a zero-argument ``main()`` and read sys.argv
    themselves; passing argv positionally to those raises TypeError.
    """
    try:
        params = inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False

    positional = inspect.Parameter
    for name, param in params.items():
        if param.kind in (positional.VAR_POSITIONAL, positional.VAR_KEYWORD):
            return True
        if param.kind is positional.POSITIONAL_ONLY:
            return True
        if name == "argv" and param.kind in (
            positional.POSITIONAL_OR_KEYWORD,
            positional.KEYWORD_ONLY,
        ):
            return True
    return False


def json_main(func: Callable[..., int]) -> Callable[..., int]:
    """Decorate a CLI ``main`` to support ``--json`` without altering human output.

    The wrapped function is called with the original signature. When ``--json``
    is absent, behaviour is byte-for-byte identical to the undecorated function.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        takes_argv = _accepts_arg(func)
        argv = kwargs.get("argv")
        if argv is None and args and takes_argv:
            argv = args[0]
        argv = list(argv) if argv is not None else sys.argv[1:]

        requested, remaining = split_json_flag(argv)
        if not requested:
            return func(*args, **kwargs)

        if takes_argv:
            call_args, call_kwargs = args, dict(kwargs)
            if call_kwargs.get("argv") is not None:
                call_kwargs["argv"] = remaining
            elif args:
                call_args = (remaining, *args[1:])
            else:
                call_args = (remaining,)
            out, err = io.StringIO(), io.StringIO()
            try:
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = func(*call_args, **call_kwargs)
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 1
            except Exception as exc:  # noqa: BLE001 - reported, never swallowed silently
                sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
                return 1
        else:
            # A zero-argument main reads sys.argv itself, so the flag has to be
            # removed from the process arguments for the call to succeed.
            saved_argv = list(sys.argv)
            sys.argv = [saved_argv[0], *remaining]
            out, err = io.StringIO(), io.StringIO()
            try:
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = func()
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 1
            except Exception as exc:  # noqa: BLE001 - reported, never swallowed silently
                sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
                return 1
            finally:
                sys.argv = saved_argv

        envelope = build_envelope(
            command=_program_name(),
            argv=remaining,
            exit_code=int(code or 0),
            stdout=out.getvalue(),
            stderr=err.getvalue(),
        )
        json.dump(envelope, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return int(code or 0)

    return wrapper


def main(argv: list[str] | None = None) -> int:
    """``python -m mem20cliz`` — report the contract and this installation."""
    args = list(sys.argv[1:] if argv is None else argv)
    if "--json" in args:
        json.dump(
            build_envelope(
                command="mem20cliz",
                argv=[a for a in args if a != JSON_FLAG],
                exit_code=0,
                stdout=f"mem20cli envelope schema mem20.cli/{SCHEMA_VERSION}",
                stderr="",
                extra={"installed": True, "package": "mem20cliz"},
            ),
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
        return 0

    print("mem20cliz - shared machine contract for mem20 fleet CLIs")
    print(f"envelope schema : mem20.cli/{SCHEMA_VERSION}")
    print("usage           : add '@json_main' above a CLI main(), and import from mem20cliz")
    print(f"flag            : {JSON_FLAG} (accepted at any argument position)")
    print(f"install path    : {os.path.dirname(os.path.abspath(__file__))}")
    return 0
