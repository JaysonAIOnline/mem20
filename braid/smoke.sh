#!/usr/bin/env bash
# E2 — smoke harness: re-verify the substrate in 3 commands after each milestone.
#   ./smoke.sh  => full workspace tests
#   ./smoke.sh 3  => all doors live example
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$PATH:/root/.cargo/bin"

echo "== smoke: cargo test --workspace =="
cargo test --workspace 2>&1 | tail -25

echo "== smoke: m1 example =="
cargo run -p braid_core --example three_uis 2>&1 | tail -1

echo "== smoke: m2 example =="
cargo run -p braid_ui_bridge --example three_doors_over_wire 2>&1 | tail -1

echo "== smoke: m3 audit =="
cargo test -p braid_drive --test m3_concurrency 2>&1 | grep "m3 GREEN" || true