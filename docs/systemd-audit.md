# Systemd / Services Audit — Phase 21 `21_systemz` (FINAL)

Every persistent interface and frontend defined by `hypo-map-1` now runs as
an enabled systemd unit. Audit performed 2026-09-10; rule applied
throughout: keys come only from `/opt/mem20/secrets/.env`, and anything that
must survive reboot is systemd-managed.

## Change log for this phase

| Action | What |
| --- | --- |
| Added | `mem20-gateway.service` (mem20 native model gateway :4000) |
| Added | `mem20-chat.service` (mem20 chat web UI :3000) |
| Added | `mem20-agentz-web.service` (:18778 webgateway/dashboard/OREO editor routes) |
| Added | `mem20-agentz-desktop.service` (:18785 unified office/3D frontend) |
| Added | `mem20-agentz-gateway.service` (messaging gateway daemon: loopback + telegram bridges) |
| Rewritten | `mcp-server.service` — platform mem20 MCP + health/ready/metrics on :8080 (stdio guardian; was disabled/stale) |
| Removed | `mem20-gateway-*.service` (24 profile + base user units) + unit files + all :9900–:9923 listeners — messaging absorbed by `mem20-agentz-gateway` |
| Removed | mem20-managed MCP layer (:8080 watchdog child) — replaced by native `mcp-server.service` |
| Removed | `tt3d-studio.service` + `/root/tt3d-nim-ui` + process (Jayson-confirmed) |
| Removed (earlier) | `jayson.service`, `claw3d.service` dead units + relic processes |
| Removed | `yacy.service` — stuck `activating`/auto-restart fork-loop against a missing `/opt/search/yacy` tree; unit disabled + deleted |

## Enabled systemd units (multi-user.target)

| Unit | Port | Purpose | Exec | Health | Restart |
| --- | --- | --- | --- | --- | --- |
| `mem20-gateway.service` | 4000 | mem20 native model gateway (OpenAI-compat /v1; 53 routes / 44 keyed; failover fast/balanced/strong) | `/root/.venv/bin/python -m mem20owebz serve --port 4000` (WD `/opt/mem20/mem20owebz`) | `/health` 200, `/v1/models` 200, chat-completions round-trip | always 5s |
| `mem20-chat.service` | 3000 | mem20 chat web UI over gateway | `/root/.venv/bin/python -m mem20owebz chat --port 3000` (WD `/opt/mem20/mem20owebz`) | GET `/` 200 | always 5s |
| `mem20-agentz-web.service` | 18778 | opencode web gateway + status dashboard + OREO `/ln` editor routes | `/root/.venv/bin/python -m mem20agentz webgateway serve --port 18778 --host 0.0.0.0` (WD `/opt/mem20/mem20agentz`) | GET `/` 200, `webgateway status` JSON | always 5s |
| `mem20-agentz-desktop.service` | 18785 | unified office/3D web frontend (serves `/office` bundle + ledger; shared `web:` session prefix) | `/root/.venv/bin/python -m mem20agentz desktop serve --port 18785 --host 0.0.0.0` (WD `/opt/mem20/mem20agentz`) | GET `/office` 200 | always 5s |
| `mem20-agentz-gateway.service` | — | messaging gateway daemon (loopback + telegram BOTH live) | `/root/.venv/bin/python -m mem20agentz gateway serve --bridges loopback,telegram` (WD `/opt/mem20/mem20agentz`) | `gateway status`; loopback deliver→agent reply→recv verified; established TLS to Telegram api range (IPv6 2001:67c:4e8::; bot `mem20_lddbs2vpenjf44qa_bot`, getMe ok, token from canonical) | always 5s |
| `mcp-server.service` | 8080 | mem20 platform MCP server (stdio transport; guardian keeps instance alive) — `/health /ready /metrics` | `/root/.venv/bin/python /opt/mem20/mcp/stdio_guardian.py` (WD `/opt/mem20/mcp`) | `/health`, `/ready`, `/metrics` all 200 | always 5s |
| `mem20-messenger.service` | 8000 | mem20 Messenger backend (18 bots, `messenger.db`) | `/root/mem20-messenger/backend/start.sh` → uvicorn `server:app` | GET `/` 200 | always 5s |
| `mem20-dashboard.service` | 9119 | mem20 Agent dashboard (loopback) | `/root/.local/bin/mem20 dashboard` | GET `/` 200 | on-failure 5s |
| `interstice.service` | 4200 | INTERSTICE visual guide (static) | `python3 -m http.server 4200 -d /root/interstice` | GET `/` 200 | on-failure 3s |
| `ollama.service` | 11434 | Local Ollama models | ollama serve | `ollama list` / port | always 3s |
| `docker.service` / socket | — | container runtime (no mem20 containers) | docker | `docker ps` | systemd |

All mem20 units set `SECRETS_ENV=/opt/mem20/secrets/.env` (plus `HOME=/root`,
`WorkingDirectory` at the repo dir that owns the package so `-m` resolves the
real package, not a namespace dir). MCP unit additionally sets
`MEM20_STORE_PATH=/root/.mem20/store` and `MEM20_HEALTH_PORT=8080`.

## Disabled / optional / on-demand (documented)

- `cloudflared-messenger.service` — disabled.
- `searxng.service` + docker `searxng` container — disabled/exited (THESTACK).
- `hostapd.service` — masked (by design).
- OREO per-graph web apps — spawned on demand by `mem20agentz oreo build
  <nl>` (unit-per-graph would be wrong; the editor surface is the
  `mem20-agentz-web` route). On-demand, documented.
- `mem20agentz webhooks serve` / `acp serve` / `egress serve` /
  `auth proxyserve` — on-demand foreground servers (no persistent consumer);
  run under a unit when used.
- `mem20officez` standalone server — superseded by `mem20-agentz-desktop`
  (same `/office` surface over the shared `web:` session prefix); not run
  separately to avoid port/session divergence.

## Ephemeral / session-scoped (NOT services)

- `:8081` `mcp_server.py` — the mem20 MCP instance for *this* opencode
  session (parent: opencode; separate per-client instance from the platform
  one on :8080). Dies with the session.
- `systemd-modules-load.service` failed — benign, pre-existing.
- `kdeconnectd` :1716, `containerd` — desktop/runtime, not services.

## Removed this phase (absorbed / dead)

- mem20 messaging gateways (24 profile units + `mem20-gateway.service`,
  files under `/root/.config/systemd/user`) — absorbed by
  `mem20-agentz-gateway`.
- mem20-managed mem20 MCP (:8080 under gateway `github` watchdog) —
  replaced by native `mcp-server.service`.
- `tt3d-studio.service` (+ `/root/tt3d-nim-ui`) — removed, Jayson-confirmed.
- `jayson.service`, `claw3d.service` — dead target dirs, disabled+deleted.
- `yacy.service` — fork-looping against a missing `/opt/search/yacy` (data dir
  already gone, unit never cleared); disabled + unit file deleted.

## Full listener map (final)

| Port | Owner |
| --- | --- |
| 22 | sshd |
| 3000 | mem20 chat (systemd) |
| 4000 | mem20 gateway (systemd) |
| 4200 | interstice (systemd) |
| 8000 | mem20 messenger (systemd) |
| 8080 | mem20 platform MCP health (systemd) |
| 8081 | *session* mem20 MCP (opencode, ephemeral) |
| 9119 | mem20 dashboard (systemd, loopback) |
| 11434 | ollama (systemd) |
| 18778 | mem20 webgateway/dashboard (systemd) |
| 18785 | mem20 office/3D frontend (systemd) |

## Cron survivors (root crontab + /etc/cron.d)

- `03:14` `/opt/thestack/scripts/thestack-persist.sh` (THESTACK)
- `*/30` `/opt/thestack/scripts/agent-sync.sh` (THESTACK)
- `*/5` `/usr/local/bin/cloudflare-ddns.sh` → `/var/log/cloudflare-ddns.log`
- `*/5` ddns-notifier.sh × 5 (owner, cfo, cco, user, jnet1)
- System timers: e2scrub, geoipupdate, john, sysstat, logrotate, fstrim,
  man-db, plocate, apt.

## Open items

- `mem20crewz` present at `/opt/mem20/mem20crewz` but NOT editable-installed
  in the shared venv (pre-existing `ModuleNotFoundError`; unrelated to this
  phase). Fix when a phase needs it.
- THESTACK cron survivors (`*/30 agent-sync.sh`, `03:14 thestack-persist.sh`)
  remain active — out of scope for this phase unless directed.
- Session mem20 MCP (:8081) is ephemeral per-client by design; the platform
  MCP is the `mcp-server.service` unit (:8080).

## Resolved this session (previously open)

- Duplicate/alias `_2`/`_3` keys removed from canonical
  `/opt/mem20/secrets/.env` (98→90 keys). A live-system grep found ZERO
  consumers for `CLOUDFLARE_API_KEY_2`, `CLOUDFLARE_API_TOKEN_2`,
  `HF_TOKEN_2`, `HF_TOKEN_3`, `MISTRAL_API_KEY_2`, `GROQ_API_KEY_2`,
  `R2_ACCESS_KEY_ID_2`, `R2_SECRET_ACCESS_KEY_2`. Their value-identical
  copies are archived in `/opt/mem20/secrets/.env.fallback`. All mem20
  services verified active and the messaging gateway kept its live Telegram
  TLS after the edit.

- YaCy removed entirely: `yacy.service` was enabled but stuck
  `activating`/auto-restarting (Restart=on-failure, NRestarts 9550+) against a
  **missing** `/opt/search/yacy` tree (data dir already absent; unit was
  fork-looping against nothing). Unit disabled + unit file deleted;
  `/opt/search` was empty and retained. No cron/other references existed.
- Telegram bridge now LIVE: `TELEGRAM_BOT_TOKEN` present in canonical
  `/opt/mem20/secrets/.env` (bot `mem20_lddbs2vpenjf44qa_bot`, `getMe` ok).
  `mem20-agentz-gateway` holds established TLS to Telegram API (IPv6
  `2001:67c:4e8::` :443) alongside the running loopback bridge; unit 0
  restarts.
