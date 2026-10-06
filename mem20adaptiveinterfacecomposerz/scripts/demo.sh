#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$ROOT/src"
DB="${TMPDIR:-/tmp}/rm003-demo-$$.sqlite"
python -m freestack_interface_composer.cli --db "$DB" register "$ROOT/examples/search_capability.json"
python -m freestack_interface_composer.cli --db "$DB" compose "search deployment notes"
