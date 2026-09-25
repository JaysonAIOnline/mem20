#!/usr/bin/env bash
# clawd3d-start — Start all Clawd3D services, auto-resolving port conflicts.
#
# Setup (once):
#   echo 'alias clawd3d="/absolute/path/to/Claw3D/scripts/clawd3d-start.sh"' >> ~/.zshrc
#   source ~/.zshrc
#
# Then just run:  clawd3d

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
CLAWD3D_DIR="$(cd -- "$SCRIPT_DIR/.." >/dev/null 2>&1 && pwd)"
LOG_DIR="/tmp/clawd3d-logs"
mkdir -p "$LOG_DIR"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${GREEN}[clawd3d]${NC} $*"; }
warn() { echo -e "${YELLOW}[clawd3d]${NC} $*"; }
info() { echo -e "${BLUE}[clawd3d]${NC} $*"; }

# ── Helpers ───────────────────────────────────────────────────────────────────

# Returns PIDs *listening* on a port (excludes client connections), or empty.
pids_on_port() { lsof -ti:"$1" -sTCP:LISTEN 2>/dev/null || true; }

# True if the port is free.
port_free() { [ -z "$(pids_on_port "$1")" ]; }

# Find first free port >= $1.
find_free_port() {
  local p=$1
  while ! port_free "$p"; do p=$((p + 1)); done
  echo "$p"
}

# True if every PID on $port matches the grep pattern in its command line.
port_owned_by() {
  local port=$1 pattern=$2
  local pids
  pids=$(pids_on_port "$port")
  [ -z "$pids" ] && return 1
  while IFS= read -r pid; do
    local cmd
    cmd=$(ps -p "$pid" -o command= 2>/dev/null || true)
    if ! echo "$cmd" | grep -qE "$pattern"; then
      return 1
    fi
  done <<< "$pids"
  return 0
}

# ── 1. Mem20 gateway (API, default 8642) ────────────────────────────────────
MEM20_PORT=8642
if ! port_free $MEM20_PORT; then
  if port_owned_by $MEM20_PORT "mem20"; then
    warn "Mem20 gateway already running on :$MEM20_PORT — reusing."
  else
    MEM20_PORT=$(find_free_port $((MEM20_PORT + 1)))
    warn "Port 8642 taken by another process → using :$MEM20_PORT for Mem20."
    log "Starting Mem20 gateway on :$MEM20_PORT..."
    nohup env API_SERVER_PORT="$MEM20_PORT" mem20 gateway run \
      > "$LOG_DIR/mem20-gateway.log" 2>&1 &
    sleep 2
  fi
else
  log "Starting Mem20 gateway on :$MEM20_PORT..."
  nohup mem20 gateway run > "$LOG_DIR/mem20-gateway.log" 2>&1 &
  sleep 2
fi
MEM20_API_URL="http://localhost:$MEM20_PORT"

# ── 2. Mem20 adapter (WebSocket bridge, default 18789) ──────────────────────
ADAPTER_PORT=18789
if ! port_free $ADAPTER_PORT; then
  if port_owned_by $ADAPTER_PORT "node.*mem20-gateway-adapter"; then
    warn "Mem20 adapter already running on :$ADAPTER_PORT — reusing."
  else
    ADAPTER_PORT=$(find_free_port $((ADAPTER_PORT + 1)))
    warn "Port 18789 taken by another process → using :$ADAPTER_PORT for adapter."
    log "Starting Mem20 adapter on :$ADAPTER_PORT..."
    cd "$CLAWD3D_DIR"
    nohup env MEM20_ADAPTER_PORT="$ADAPTER_PORT" MEM20_API_URL="$MEM20_API_URL" \
      npm run mem20-adapter > "$LOG_DIR/mem20-adapter.log" 2>&1 &
    sleep 1
  fi
else
  log "Starting Mem20 adapter on :$ADAPTER_PORT..."
  cd "$CLAWD3D_DIR"
  nohup env MEM20_ADAPTER_PORT="$ADAPTER_PORT" MEM20_API_URL="$MEM20_API_URL" \
    npm run mem20-adapter > "$LOG_DIR/mem20-adapter.log" 2>&1 &
  sleep 1
fi
GATEWAY_WS_URL="ws://localhost:$ADAPTER_PORT"

# ── 3. Next.js dev server (default 3000) ─────────────────────────────────────
APP_PORT=3000
if ! port_free $APP_PORT; then
  if port_owned_by $APP_PORT "node.*next|next-server|server/index\.js"; then
    warn "Clawd3D dev server already running on :$APP_PORT — reusing."
  else
    APP_PORT=$(find_free_port $((APP_PORT + 1)))
    warn "Port 3000 taken by another process → using :$APP_PORT for Clawd3D."
    log "Starting Clawd3D dev server on :$APP_PORT..."
    cd "$CLAWD3D_DIR"
    nohup env PORT="$APP_PORT" NEXT_PUBLIC_GATEWAY_URL="$GATEWAY_WS_URL" \
      npm run dev > "$LOG_DIR/clawd3d-dev.log" 2>&1 &
  fi
else
  log "Starting Clawd3D dev server on :$APP_PORT..."
  cd "$CLAWD3D_DIR"
  nohup env PORT="$APP_PORT" NEXT_PUBLIC_GATEWAY_URL="$GATEWAY_WS_URL" \
    npm run dev > "$LOG_DIR/clawd3d-dev.log" 2>&1 &
fi

# ── 4. Wait until the app responds ───────────────────────────────────────────
log "Waiting for Clawd3D to be ready at :$APP_PORT..."
ready=0
for i in $(seq 1 90); do
  if curl -sf "http://localhost:$APP_PORT" > /dev/null 2>&1; then
    ready=1; break
  fi
  sleep 1
done
if [ "$ready" -eq 0 ]; then
  warn "Timed out waiting for :$APP_PORT — check $LOG_DIR/clawd3d-dev.log"
fi

# ── 5. Open browser ───────────────────────────────────────────────────────────
open "http://localhost:$APP_PORT"

echo ""
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log " Clawd3D      →  http://localhost:$APP_PORT"
info " Gateway WS   →  $GATEWAY_WS_URL"
info " Mem20 API   →  $MEM20_API_URL"
info " Logs         →  $LOG_DIR/"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
