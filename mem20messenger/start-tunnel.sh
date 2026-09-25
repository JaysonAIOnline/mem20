#!/usr/bin/env bash
# mem20 messenger Cloudflare quick-tunnel (mem20-native replacement).
# Credentials sourced from /opt/mem20/secrets/.env (mem20 storage).
set -euo pipefail

SECRETS=/opt/mem20/secrets/.env
if [[ -f "$SECRETS" ]]; then
  set -a; source "$SECRETS"; set +a
fi

if command -v cloudflared >/dev/null 2>&1; then
  exec cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8000
fi

echo "[mem20-messenger] cloudflared not found; tunnel disabled" >&2
exit 1