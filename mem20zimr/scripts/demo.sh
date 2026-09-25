#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT/src"
export FREESTACK_SIGNING_SECRET="dev-secret"
python -m mem20zimr.cli build "$ROOT/examples/hello_py" "$ROOT/release/hello_py.fsmicro" --app-id demo.hello --entrypoint main.py --modes local,hybrid,cloud
python -m mem20zimr.cli inspect "$ROOT/release/hello_py.fsmicro"
python -m mem20zimr.cli launch "$ROOT/release/hello_py.fsmicro" --payload '{"name":"RM-002"}'
