#!/usr/bin/env bash
# mem20 portable installer.
# Usage: sudo ./install.sh [--user <user>] [--dir <mem20_dir>] [--venv <venv_path>]
#
# What it does:
#   1. Creates a Python venv and installs requirements.txt (core deps).
#   2. Installs requirements-optional.txt notes (no-op; documents external apps).
#   3. Generates a systemd unit from systemd/mem20.service.template.
#   4. Enables + starts the service (skipped with --no-systemd).
#
# Blender/Unity are OPTIONAL external apps (see requirements-optional.txt); the
# server runs without them and tells you when a tool needs one.
set -euo pipefail

USER_ARG="${SUDO_USER:-${USER:-mem20}}"
DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${DIR}/.venv"
NO_SYSTEMD=0
while [ $# -gt 0 ]; do
  case "$1" in
    --user) USER_ARG="$2"; shift 2;;
    --dir)  DIR="$2"; shift 2;;
    --venv) VENV="$2"; shift 2;;
    --no-systemd) NO_SYSTEMD=1; shift;;
    *) echo "unknown arg $1"; exit 1;;
  esac
done

echo "==> Creating venv at ${VENV}"
python3 -m venv "${VENV}"
"${VENV}/bin/python" -m pip install --quiet --upgrade pip
"${VENV}/bin/python" -m pip install --quiet -r "${DIR}/requirements.txt"

STORE_PATH="${MEM20_STORE_PATH:-${DIR}/store}"
mkdir -p "${STORE_PATH}"

if [ "${NO_SYSTEMD}" -eq 0 ] && command -v systemctl >/dev/null 2>&1; then
  UNIT="/etc/systemd/system/mem20.service"
  echo "==> Generating ${UNIT}"
  sed -e "s#__MEM20_USER__#${USER_ARG}#g" \
      -e "s#__MEM20_WORKDIR__#${DIR}#g" \
      -e "s#__MEM20_VENV_PYTHON__#${VENV}/bin/python#g" \
      -e "s#__MEM20_STORE_PATH__#${STORE_PATH}#g" \
      "${DIR}/systemd/mem20.service.template" > "${UNIT}"
  systemctl daemon-reload
  systemctl enable --now mem20.service
  echo "==> mem20.service enabled + started"
else
  echo "==> Skipping systemd (--no-systemd or no systemctl). Run manually:"
  echo "    MEM20_STORE_PATH=${STORE_PATH} ${VENV}/bin/python ${DIR}/mcp/mcp_server.py"
fi

# --- optional install telemetry (opt-out: MEM20_NO_TELEMETRY=1) ---
MEM20_INSTALL_DIR="${DIR}" "${VENV}/bin/python" - <<'PY' || true
import sys, os
sys.path.insert(0, os.path.join(os.environ.get("MEM20_INSTALL_DIR", "."), "mcp"))
try:
    import install_tracker
    install_tracker.report("git-install.sh", event="install")
except Exception:
    pass
PY

echo "==> Done. Health: curl http://localhost:8080/health"
echo "==> Note: anonymous install metrics are recorded locally"
echo "         (opt out with MEM20_NO_TELEMETRY=1; send to a collector via MEM20_INSTALL_WEBHOOK)."
