#!/usr/bin/env bash
# Reproducibly copy the local `mcp/` directory (the MCP server, run as a script)
# into `mem20_runtime/mcp/` so it can be shipped as package data and located at
# runtime via importlib.resources WITHOUT turning `mcp/` into an importable
# package (which would shadow the `mcp` SDK). `mcp/` remains the source of truth.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${ROOT}/mcp"
DST="${ROOT}/mem20_runtime/mcp"
rm -rf "${DST}"
mkdir -p "${DST}"
# Copy everything except caches and the (must-not-exist) __init__.py.
find "${SRC}" -type f ! -path '*/__pycache__/*' ! -name '*.pyc' -print0 \
  | while IFS= read -r -d '' f; do
      rel="${f#${SRC}/}"
      dest="${DST}/${rel}"
      mkdir -p "$(dirname "${dest}")"
      cp "${f}" "${dest}"
    done
# Explicitly ensure no __init__.py at the mcp/ boundary (subpackages keep theirs).
rm -f "${DST}/__init__.py"
echo "Synced ${SRC} -> ${DST}"
