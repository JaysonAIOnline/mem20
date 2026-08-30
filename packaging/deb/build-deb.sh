#!/usr/bin/env bash
# Build a Debian (.deb) package for mem20.
#
# What it produces:
#   - /opt/mem20/venv  : an isolated Python venv with the mem20 wheel installed
#   - /usr/bin/mem20-mcp   : console script (the MCP stdio + :8080 health server)
#   - /usr/bin/mem20-health: health probe (curl /health)
#   - /lib/systemd/system/mem20.service : rendered from systemd/mem20.service.template
#
# Usage:
#   packaging/deb/build-deb.sh [--skip-install]
#
#   --skip-install : skip the (heavy) pip install of the wheel. Useful to validate
#                    the packaging mechanics locally without downloading torch etc.
#                    The resulting .deb will be structurally correct but the venv
#                    will be empty until you install the wheel manually.
#
# Requires: dpkg-deb, python3. Network is needed for the real pip install.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEB_DIR="${ROOT}/packaging/deb"
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

SKIP_INSTALL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --skip-install) SKIP_INSTALL=1; shift;;
    *) echo "unknown arg: $1" >&2; exit 1;;
  esac
done

# --- read version from pyproject.toml (PEP 621) ---
VERSION_RAW="$(python3 - <<PY
import tomllib
with open("${ROOT}/pyproject.toml","rb") as f:
    print(tomllib.load(f)["project"]["version"])
PY
)"
# Debian pre-release convention: 2.1.0rc2 -> 2.1.0~rc2
VERSION="${VERSION_RAW//rc/~rc}"
ARCH="$(dpkg --print-architecture 2>/dev/null || echo amd64)"
PKG="mem20_${VERSION}_${ARCH}.deb"

echo "==> Building ${PKG} (version ${VERSION_RAW} -> ${VERSION})"

STAGE="${WORK}/mem20"
mkdir -p "${STAGE}/opt/mem20" "${STAGE}/usr/bin" "${STAGE}/lib/systemd/system" "${STAGE}/DEBIAN"

# --- install the wheel into an isolated venv under /opt/mem20/venv ---
VENV="${STAGE}/opt/mem20/venv"
if [ "${SKIP_INSTALL}" -eq 1 ]; then
  echo "==> (--skip-install) creating empty venv placeholder"
  python3 -m venv "${VENV}"
else
  echo "==> Building wheel"
  WHEEL_DIR="$(mktemp -d)"
  python3 -m pip wheel --no-cache-dir -w "${WHEEL_DIR}" "${ROOT}" >/dev/null
  echo "==> Creating venv at ${VENV}"
  python3 -m venv "${VENV}"
  "${VENV}/bin/python" -m pip install --quiet --upgrade pip wheel
  # Install the built wheel plus its dependencies.
  "${VENV}/bin/python" -m pip install --quiet "${WHEEL_DIR}"/*.whl
  rm -rf "${WHEEL_DIR}"
fi

# --- console wrapper ---
cat > "${STAGE}/usr/bin/mem20-mcp" <<'EOF'
#!/usr/bin/env bash
exec /opt/mem20/venv/bin/mem20-mcp "$@"
EOF
chmod 0755 "${STAGE}/usr/bin/mem20-mcp"

# --- health probe ---
cat > "${STAGE}/usr/bin/mem20-health" <<'EOF'
#!/usr/bin/env bash
# Probe the running mem20 MCP server's /health endpoint.
PORT="${MEM20_HEALTH_PORT:-8080}"
curl -fsS "http://localhost:${PORT}/health" || exit 1
EOF
chmod 0755 "${STAGE}/usr/bin/mem20-health"

# --- systemd unit (rendered from the template) ---
STORE_PATH="${MEM20_STORE_PATH:-/var/lib/mem20/store}"
sed -e "s#__MEM20_USER__#mem20#g" \
    -e "s#__MEM20_WORKDIR__#/opt/mem20#g" \
    -e "s#__MEM20_VENV_PYTHON__#/opt/mem20/venv/bin/python#g" \
    -e "s#__MEM20_STORE_PATH__#${STORE_PATH}#g" \
    "${ROOT}/systemd/mem20.service.template" > "${STAGE}/lib/systemd/system/mem20.service"
# Let the template's ExecStart point at the installed console script instead.
sed -i "s#^ExecStart=.*#ExecStart=/opt/mem20/venv/bin/mem20-mcp#" "${STAGE}/lib/systemd/system/mem20.service"

# --- DEBIAN control ---
cat > "${STAGE}/DEBIAN/control" <<EOF
Package: mem20
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Depends: python3 (>=3.10), systemd, curl
Maintainer: JaysonAI <noreply@jayson.ai>
Description: mem20 — trusted, auditable memory + world-model MCP server
 mem20 is a persistent memory + cognition substrate for AI agents, exposed
 over the Model Context Protocol (MCP) as a JSON-RPC service on stdio, with
 an HTTP health endpoint on :8080 (/health, /ready, /metrics).
 .
 This package installs an isolated venv and a systemd unit.
EOF

# --- maintainer scripts ---
cat > "${STAGE}/DEBIAN/postinst" <<'EOF'
#!/usr/bin/env bash
set -e
if [ "$1" = "configure" ] && command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload
  systemctl enable --now mem20.service || true
fi
# --- install telemetry (opt-out: MEM20_NO_TELEMETRY=1) ---
VENVPY=/opt/mem20/venv/bin/python
"$VENVPY" - <<'PY' || true
import importlib.util, os
try:
    import mem20_runtime
    p = os.path.join(os.path.dirname(mem20_runtime.__file__), "mcp", "install_tracker.py")
    spec = importlib.util.spec_from_file_location("install_tracker", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.report("deb", event="install")
except Exception:
    pass
PY
exit 0
EOF

cat > "${STAGE}/DEBIAN/prerm" <<'EOF'
#!/usr/bin/env bash
set -e
if command -v systemctl >/dev/null 2>&1; then
  systemctl disable --now mem20.service || true
fi
exit 0
EOF

cat > "${STAGE}/DEBIAN/postrm" <<'EOF'
#!/usr/bin/env bash
set -e
if [ "$1" = "purge" ] && command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload || true
fi
exit 0
EOF
chmod 0755 "${STAGE}/DEBIAN/postinst" "${STAGE}/DEBIAN/prerm" "${STAGE}/DEBIAN/postrm"

# --- build ---
mkdir -p "${DEB_DIR}"
dpkg-deb --build --root-owner-group "${STAGE}" "${DEB_DIR}/${PKG}"
echo "==> Wrote ${DEB_DIR}/${PKG}"
