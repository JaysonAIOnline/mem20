# mem20cliz

The shared machine contract for mem20 fleet CLIs.

One decorator gives any mem20 CLI a `--json` mode **without changing what it
prints for humans** and without touching its command internals:

```python
from mem20cliz import json_main

@json_main
def main(argv: list[str] | None = None) -> int:
    ...  # existing body, unchanged
```

```
mytool sweep --json
```

emits a stable envelope on stdout:

```json
{
  "schema": "mem20.cli/1",
  "ok": true,
  "command": "mytool",
  "argv": ["sweep"],
  "exit_code": 0,
  "stdout": "...",
  "stderr": ""
}
```

## Guarantees

- The human path is byte-for-byte identical; the wrapper only engages on `--json`.
- The command's real exit code is returned and recorded in `exit_code`.
- One schema across every fleet CLI, so scripts depend on a single shape.
- `--json` is accepted at any argument position, including before the subcommand.
- An unhandled exception in the command becomes exit 1 with the error on stderr
  rather than a traceback through the envelope.

## Install

```
cd /opt/mem20/mem20cliz
/root/.venv/bin/pip install -e .
```

Verify the contract from the command line:

```
mem20-cli --json
python -m mem20cliz
```

## Adopting it in a subsystem CLI

Two lines per CLI, no other changes:

1. `from mem20cliz import json_main`
2. put `@json_main` directly above the existing `def main(...)`

Subcommands that already emit their own domain-specific JSON keep it; this is for
the CLIs that have no machine output yet.

## Tests

```
/root/.venv/bin/python -m pytest /opt/mem20/mem20cliz -q
```

The suite asserts the property that matters most: the human path is unchanged,
and JSON mode never leaks human text to stdout.
