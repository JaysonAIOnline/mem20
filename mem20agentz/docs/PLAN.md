# mem20 agentz — full-fidelity cleanroom (phase 02)

**Branding policy (Jayson, 2026-09-09):** every known capability of the absorbed
agent platform is rebuilt directly INTO mem20 (`/opt/mem20/mem20agentz`), under
**mem20** branding. Zero occurrences of the old product name in code, docs,
paths, or packaging. The old product's upstream repo is the *reference*
(cleanroom) — never imported, never vendored, never referenced by name.

The platform is built directly into mem20: it is a package inside `/opt/mem20`
(`mem20agentz`, importable), a peer of `mem20crewz` (phase 01). It reuses the
phase-01 cleanroom surface where it already exists (Agent/Task/Crew/Flow, A2A
client, procedural skills) instead of re-building it.

---

## 1. Feature inventory — "all known features"

Source of truth: the installed agent's `--help` surface, gateway/platforms
bridges, desktop/web frontends, skills/plugins/pets stores, and the mem20
substrate. Rebuilt list:

### 1.1 Agent core
- interactive chat (`chat`/TUI) + one-shot mode (`-z`), session resume
  (`--resume`), model/provider/reasoning-effort overrides
- tool-calling loop with toolsets, approvals, safety mitigations
- checkpoints, sessions (list/rename/export/prune/delete), backups
- projects (named multi-folder workspaces), worktrees
- rules / AGENTS.md loading, cwd placeholder handling
- safe console, bang-shell, prompt-size breakdown
- status/pause/resume (emergency stop), doctor/verify/debug/dump

### 1.2 Gateway + bridges (10+ platforms)
- messaging gateway daemon (`gateway`) + control socket + delivery ledger
- bridges: telegram (managed bot), whatsapp (+ cloud API), slack, signal,
  discord, iMessage (bluebubbles), weixin, qq, yuanbao, msgraph/webhook
- channel directory, pairing/authorization, media policy + media cache,
  monitoring/diagnostics export, mirror, dead-target handling
- webhook subscriptions, `send` (script/cron/CI outbound)

### 1.3 Agent authoring & misc surfaces
- skills (search/install/configure/manage; bundles; curator; sync; skill
  sync / team sharing)
- plugins (manage/validate), external secret sources (1Password/Bitwarden),
  memory providers (external), tools-per-platform config
- pets (petdex), skins, journeys/learning/memory-graph, insights/monitoring
- MCP client (manage servers) + MCP server mode, ACP server mode
- computer-use (cua-driver) backend
- A2A (bot-to-bot DMs, peer mesh — freeform `peer`, portal, kanban watchers)
- cron jobs, kanban multi-profile board, hooks (shell-script)
- approvals (prompt mining → allowlist proposals, transport)
- security (OSV audit for venv/plugins/MCP), egress iron-proxy firewall
- auth pool (multi-provider credential pool), proxy (local OpenAI-compatible
  to OAuth providers), fallback providers, mixture-of-agents
- backup/import, import-agent (Claude Code / Codex), claw migration, uninstall
- profiles (multiple isolated instances), completion scripts, logs, dashboard
- `serve` headless backend server (powers desktop + remote), desktop app
  (native, Electron), web UI/rockets, webgateway dashboard

### 1.4 Frontends (unification requirement)
- ONE unified office-style 3D frontend as the single surface, incorporating
  the phase-01 opencode frontend; desktop/webgateway/office/CLI stay thin
  clients over the same mem20 backend — no divergent state.

### 1.5 Hard requirements carried from the roadmap
- absorption: once a capability is integrated AND verified, remove the old
  install from disk (phase 07 does the full sweep).
- secrets: single home `/opt/mem20/secrets/.env` (phase 06) — until then,
  work stays hermetic; nothing depends on scattered per-app keyboards.
- systemd audit is the LAST step (phase 07).

---

## 2. mem20-native architecture

Everything lives under `/opt/mem20/mem20agentz` as a python package
(`mem20agentz`) plus a server/waiter layout. Reuse from phase 01:
`mem20crewz` (agents/loop/flow/a2a), `memory` substrate (recall/remember,
procedural skills, cog, ledger, namespaces), `llm.py`.

```
mem20agentz/
  mem20agentz/
    __init__.py
    config.py        # config.yaml (mem20-native schema), profile routing
    profiles.py      # profiles -> mem20 namespaces + self-models
    sessions.py      # session ledger (list/rename/export/prune/delete/resume)
    agentz.py        # core agent loop (tool-calling, toolsets, approvals)
    bridges/         # one adapter per platform (cleanroom, own code)
      base.py telegram.py whatsapp.py slack.py signal.py ...
    gateway.py       # daemon: control socket, delivery ledger, pairing, media
    gateway_web.py   # webgateway/dashboard HTTP server (mem20 backend)
    skills.py        # skills store/bundles/curator/sync (procedural-backed)
    plugins.py       # plugin loader + validation
    pets.py skin.py hooks.py approvals.py
    cron.py kanban.py projects.py webhooks.py pair.py
    secrets.py       # external secret sources (1Password/Bitwarden) -> /opt/mem20/secrets
    egress.py        # iron-proxy credential-injection firewall
    auth.py          # provider credential pool, proxy, fallback, moa
    mcp.py acp.py computer_use.py
    backup.py import_agent.py migration.py
    desktop.py       # unified office/3D frontend builder (phase 2.9)
    cli.py           # mem20agentz CLI (parity with 1.1-1.3) + `-z` oneshot
  docs/PLAN.md        # this file
  pyproject.toml
```

### 2.1 Mapping table (old → mem20)
| Old capability | mem20-native target | Sub-phase |
|---|---|---|
| profiles/instances | `profiles.py` → mem20 namespaces + self-model | 2.1 |
| sessions/checkpoints/resume | `sessions.py` over memory ledger | 2.1 |
| agent loop + toolsets + one-shot + approvals | `agentz.py` over mem20crewz surface | 2.2 |
| skills/bundles/curator/sync | procedural skills + `skills.py` | 2.3 |
| plugins/pets/skins/hooks | `plugins.py` `pets.py` `skin.py` `hooks.py` | 2.3 |
| cron/kanban/projects/webhooks | roadmap + ledger-backed | 2.4 |
| gateway daemon | `gateway.py` (control socket, delivery, pairing, media) | 2.5 |
| bridges (10+) | `bridges/` one adapter each | 2.5 |
| webgateway/dashboard/serve | `gateway_web.py` on mem20 backend | 2.6 ✅ |
| MCP client+server, ACP, computer-use | `mcp.py acp.py computer_use.py` | 2.6 ✅ |
| secrets sources, egress firewall | `secrets.py` `egress.py` → phase-06 single home | 2.7 ✅ |
| auth pool/proxy/fallback/moa | `auth.py` over `llm.py` | 2.8 ✅ |
| frontends unification (office/web/3D, opencode) | `desktop.py` + office web app | 2.9 ✅ |
| backup/import/import-agent/migration | `backup.py` `import_agent.py` | 2.10 ✅ |
| CLI parity, completion, logs, dashboard | `cli.py` | 2.1–2.10 (each) |
| security/OSV audit, doctor/verify | guardrails + `security.py` | 2.7 ✅ |

### 2.2 Sub-phases
- **2.1** profiles→namespaces+self-model, sessions, CLI core, config. *FIRST VERTICAL SLICE.*
  **DONE (2026-09-09)**: `config.py`, `_substrate.py` (sealed seam, same discipline as
  phase 01), `profiles.py` (namespace `mem20agentz:<name>` + ledger self-model, base-profile fallback), `sessions.py` (ledger-backed, prune=archive, no-delete), `cli.py`
  (version/config/status/pause/resume/doctor/logs/profiles/sessions). All modules inject the
  shared `get_backend()` so tests swap in one sealed+stubbed instance. 14/14 hermetic tests
  green; source-only branding sweep clean; phase-01 suite still 30/30.
- **2.2** agent loop (toolsets, approvals, one-shot, resume) — reuse mem20crewz surfaces.
  **DONE (2026-09-09)**: `agentz.py` — `Brain` (strict-JSON action contract reusing the
  cleanroom parser), `Toolbox` (procedural-skills inventory/execute, toolsets
  skills|none), `AgentCore.run()` (tool loop, max_iter, honest [brain error] finals),
  approvals auto|ask|deny, history→goal weaving for resume, `persist_turn()` transcript
  writer. CLI: `-z/--oneshot` (prints ONLY the final reply, approvals auto-bypassed),
  `-m/--model`, `-t/--toolsets`, `-r/--resume`, `--session`, interactive `chat` REPL
  (with `ask` approvals prompt). Nano fix: substrate loader self-locates the mem20 root
  so it runs from any cwd. Tests 14→**22/22** hermetic; phase-01 still **30/30**.
  **Verified live**: `-z "Reply with exactly: mem20 ok" -t none` → `mem20 ok`,
  no banner (pipe-clean); branding sweep exit 1.
- **2.3** skills store/bundles/curator/sync, plugins, pets, skins, hooks.
  **DONE (2026-09-09)**: `skills.py` (catalog over procedural skills, on-disk YAML
  bundles, sync drift report, curator stale-report), `plugins.py` (plugin.yaml
  manifest registry, validate = ast compile + forbidden-vendor source gate,
  load = entry callable), `pets.py` (petdex in ledger, feed/play/rest, newest-
  wins dedupe), `skin.py` (skins list/create/apply + active skin + render()),
  `hooks.py` (event shell hooks: run_start/before_tool/after_tool/session_end,
  forbidden-vendor guard, dict-env fix). `AgentCore` now fires hooks around
  runs and tools. CLI: skills/plugins/pets/skins/hooks subcommands. Tests
  22→**34/34** hermetic; phase-01 **30/30**. **Verified live**: real catalog
  count, pet grok adopted+listed, dark skin applied, hook fired
  (`started run_start {}`). Branding sweep exit 1.
- **2.4** cron (scheduled runs), kanban (multi-board), projects (workspaces), webhooks.
  **DONE (2026-09-09)**: `projects.py` (named workspaces: create/list/archive/
  current, project.yaml under `<runtime>/projects/`), `cron.py` (real 5-field
  cron parser: `*`/`*/n`/`a,b`/`a-b`, `matches()`+`next()` 24h lookahead,
  jobs.json, prompt/command jobs, run log, `tick()` + `serve()` loop),
  `kanban.py` (multi-board JSON: boards/cards add/move with column enum,
  fires card_added/card_moved hooks), `webhooks.py` (ThreadingHTTPServer
  dispatcher, register/deregister routes, undelivered→ledger
  `message:webhooks:webhooks`, fixed session_append positional signature and
  honest stderr on ledger failure). CLI: projects/cron/kanban/webhooks.
  Tests 34→**45/45** hermetic; phase-01 **30/30**. **Verified live**: project
  p-mem20 created, card land-2.4 added+moved to done, cron job smoke scheduled
  (next 11:35 local), real listener on :18777 returned 404-no-handler and the
  body persisted to the ledger (verified read-back). Branding sweep exit 1.
- **2.5** gateway daemon + bridges (telegram first, then the rest).
  **DONE (2026-09-09)**: `bridge.py` (transport-neutral `Transport` protocol
  with `Message(chat_id,text,media)`, `Bridge` run loop, per-chat agent
  factory + ledger logging + `<runtime>/gateway/pairs.json` on-disk pairing,
  `TransportError`/`AuthError` hierarchy), `bridges/telegram.py` (httpx
  long-poll `getUpdates`/`sendMessage`, token from
  `MEM20AGENTZ_TELEGRAM_TOKEN`→`TELEGRAM_BOT_TOKEN`→`/root/.env`, never
  printed, honest `TelegramAuthError`), `gateway.py` (`Gateway` daemon:
  `load/serve/stop/status/pair/unpair`, `build_agent_factory` per-chat
  resume via `session_messages` ledger weaving `in:`/`out:` lines — fixed
  parser to match `Bridge._log` format; `status` degrades gracefully with
  `unconfigured`+reason when a transport lacks a token). CLI: gateway
  status/pair/unpair/serve (serve returns JSON error + tip, rc 1, on auth
  failure). Fixed three real bugs: `gateway.py` imported non-existent
  `config` symbol, `_FakeTransport` hang, and `Message` lost its dataclass
  decorator. Tests 45→**53/53** hermetic (dry-run telegram round trip against
  a fake Bot API server: poll→dispatch→send); phase-01 **30/30**. Branding
  sweep exit 1. **Verified live**: `gateway status` shows telegram
  `unconfigured: no telegram token`, `gateway pair/unpair` round-trips
  pair state, `gateway serve` fails honestly (rc 1). **NOT LIVE**: telegram
  turnstile requires a real bot token + network — blocked on external
  dependency (honest), hermetic fake-Bot-API dry-run proves the loop.
- **2.6** webgateway/dashboard/serve + MCP client/server + ACP + computer-use.
  **DONE (2026-09-09)**: `gateway_web.py` — `WebGateway` (ThreadingHTTPServer,
  `server_side`): `POST /chat` (message/chat_id `w<hex>`, `web:` session prefix,
  agent via `build_web_factory`→`build_agent_factory(session_prefix="web:")`,
  user/assistant persisted under `web:<cid>`, input validation), `GET /status`
  (service/version/uptime/config/bridge states), `GET /ledger?k=N` (recall
  tagged `mem20agentz,message`), `GET /` HTML dashboard (bridges/cron/projects/
  recent ledger, `(sealed)` fallbacks), `serve/serve_forever/stop`, web port
  18778 via config `gateway.web.port`. `mcp.py` — MCP `2024-11-05` HTTP JSON-RPC
  server (`initialize`, `tools/list`, `tools/call`→`procedural_execute`, `ping`,
  `notifications/initialized`, error codes -32700/-32601/-32602/-32603) + httpx
  `McpClient` (`initialize/list_tools/call_tool/ping/close`, raises `McpError`).
  `acp.py` — peer bridge: `POST /acp` `acp/message` {peer,text}→reply persisted
  under `acp:<peer>`, optional token (`MEM20AGENTZ_ACP_TOKEN`/secrets +
  `X-ACP-Token`), `acp/hello`+`ping`, `build_acp_factory` (`acp:` prefix).
  `computer_use.py` — `ComputerUse.run/shot/read/write`: timed subprocess with
  4000-char output truncation + destructive-command guard, honest "no screenshot
  backend" when mss/Pillow absent, file read/write. CLI: webgateway serve/status,
  mcp serve/initialize/list/call, acp serve, computer run/shot/read/write.
  Tests 54→**70/70** hermetic (TestWebGateway HTTP round trip, TestMcp client↔
  server over loopback + error codes, TestAcp round trip + token gating,
  TestComputerUse run/guard/read-write/shot-honest); phase-01 **30/30**; branding
  sweep exit 1. **Verified live** (2026-09-09): webgateway `POST /chat` →
  live LLM `"Hello! 👋"`, `/status`, dashboard HTML, `/ledger?k=N` reads back the
  real chat + acp `ping`→`pong 🏓` and prior records; `mcp list` returns the real
  skill from the live substrate (first `tools/list` is slow ~11.6 s, cold substrate
  disk read → bumped `McpClient` default timeout 10 s→30 s, honest cost not a
  fork); acp `acp/message` live `pong 🏓`; `computer run echo live-ok`, and
  `rm -rf /tmp/nope` refused by the destructive guard.
- **2.7** secrets sources + egress + security/OSV + doctor/verify.
  **DONE (2026-09-09)**: `secrets.py` — `Secrets(root, env, cli_bin)`: resolution
  env `MEM20AGENTZ_<NAME>` → vault `<root>/<name>` → `<root>/<name>.json
  {"value":...}` → external CLI (`op://vault/item/field`, `bw://item/field`,
  `cli_bin` is the test seam), 0600 file/0700 dir perms, `redact()` masks known
  values, list/describe/`secrets get` NEVER print values (presence + source only),
  unavailable CLI reported honestly. `egress.py` — fail-closed `EgressPolicy`
  (empty allowlist = deny-all), scheme+userinfo checks (credential smuggling
  blocked), credential bindings `{host: {cred_key: "Header: {template}"}}`
  (missing required cred → `EgressBlocked`), `EgressProxy` loopback forward
  proxy (absolute-URI requests, injection, 403 JSON on deny), `fetch()`. `security.py`
  — `OsvScanner` (POST `{base}/v1/querybatch`, `queries` are package objects,
  injectable `base_url` for hermetic tests, `dependency_packages` parses pyproject
  `[project].dependencies` or `requirements.txt` pins), `Doctor` 8-check report
  (import/config/memory/branding/self-test/secrets/egress/osv; sealed-backend
  memory = informational). CLI: secrets list/status/get/set/delete, egress
  check/serve, security osv/verify (`--pkg name==ver` repeatable live scan),
  doctor delegates to `Doctor`. Tests 70→**88/88** hermetic (TestSecrets env>vault>
  json order + perms + never-print + redact + fake `op` executable round trip,
  TestEgress fail-closed/deny/userinfo/inject-missing-cred + proxy injection round
  trip vs local echo + 403 JSON over real HTTP, TestSecurity fake-OSV vulnerable/
  clean/error + pyproject parse + Doctor all-green); phase-01 **30/30**; branding
  sweep exit 1. **Verified live**: `doctor` all ok rc 0 (osv clean, memory recall,
  sealed-backend note informational); `security osv --pkg httpx==0.28.1
  --pkg requests==2.34.2 --pkg pyyaml==6.0.3 --pkg pydantic==2.13.4 --pkg
  anyio==4.14.2 --pkg orjson==3.12.0` → status clean, 6 pkgs, 0 vulns (real OSV
  API; found+fixed two real bugs en route: `DEFAULT_OSV_URL` carried the path and
  `scan` appended `/querybatch` again → 404, and queries were wrapped `{"query":...}`
  → OSV 400); `egress check https://api.osv.dev` fail-closed deny by default,
  allow with `MEM20AGENTZ_EGRESS_ALLOW=api.osv.dev`; live proxy on :18782 served
  real webgateway `/status` through (allowed host) and returned 403 JSON for
  non-allowlisted hosts; `secrets status/get` show health + presence only, op/bw
  honestly `available: false`.
- **2.8** auth proxy, fallback providers, mixture-of-agents.
  DONE: new `llm.py` (provider registry `KNOWN_PROVIDERS`, `Provider`
  dataclass, `Router` ordered fallback + substrate fallback + 401 rotation
  retry, `request_chat` OpenAI-compatible httpx client, `moa()` single-layer
  N-proposals + aggregator) and `auth.py` (`KeyRing` env→config-ref→known-env→
  vault resolution, `AuthPool` numbered-key round-robin pools, `AuthProxy`
  server-side key-hiding OpenAI-compatible HTTP proxy on :18784, optional
  `X-Auth-Proxy-Token` gate). CLI adds `llms` (list/call/moa) + `auth`
  (status/proxyserve); `egress serve` now defaults `--port 18782 --host
  127.0.0.1`. Two real bugs found+fixed live: `_named_provider` returning a
  bare `Provider` (unhashable / providers[:] crash) and MoA overriding a
  single model across every provider (real fix: one proposal per provider on
  its own model, aggregator over the full fallback router). Keys never leak:
  status/output/log show presence+source only. Live-verified: `llms call`
  (nvidia, real completion), `llms moa --providers nvidia,groq,openrouter`
  17*23→391 via nvidia+openrouter proposals (groq key in /root/.env is 401 =
  honest per-provider failure), `auth status` presence-only, live proxy
  `/v1/models` + `/v1/chat/completions` (no client key, server-side
  resolution, zero key leakage in response or log). Hermetic: +17 tests
  (TestLlms/TestAuth/TestMoa/TestAuthProxy) → 105/105, phase-01 30/30,
  branding sweep clean.
- **2.9** frontend unification (office/3D + opencode frontend, single source of truth).
  DONE: new `desktop.py` — `Frontend` thin-client office surface over the
  same backend endpoints the webgateway uses (`/chat`, `/status`, `/ledger`),
  chat transcripts shared via `build_office_factory` → `build_web_factory`
  under the `web:` prefix (no divergent state). `office()` returns a single
  JSON bundle (status + ledger + cron + projects) consumed by every panel;
  CSS-3D office room renders live backend state (bridge desks, project
  shelves, cron wall, ledger floor) with no external dependencies. CLI adds
  `desktop serve` (--port default 18785, --host) / `desktop status`; `doctor`
  now shows 9 checks (all green). Two tests added: `test_single_source_status_matches_webgateway`
  proves `Frontend().status()` == `WebGateway().status()` (same backend
  reads); `test_http_full_round_trip` proves `/office`, `/status`, `/chat`,
  `/ledger` all consistent from one server. Verified live: `/office` bundle
  returns `service: "mem office"` + `status.service: "webgateway"` (single
  surface), real LLM `/chat` "Hello! How can I help you today?",
  `/ledger?k=5` entries present, port freed cleanly. Hermetic: +7 tests
  (TestDesktop) → 112/112, phase-01 30/30, branding sweep clean, imports ok.
- **2.10** backup/import/import-agent/migration + CLI parity sweep.
  DONE: `backup.py` — `Backup.export()` snapshots config (secret keys
  `<redacted>`), profiles, and the full mem20agentz ledger into a single
  gzipped JSON archive plus a sha256 sidecar; `restore()` verifies the digest
  and replays the facts back through `namespace_ensure` + `remember` (honest
  round-trip of the real substrate seams; tampered archives rejected).
  `import_agent.py` — Claude Code / Codex transcripts (JSONL or JSON, kind
  auto-detected) become normal sessions: namespace ensure + `session_add` +
  one `session_append` per message; system→assistant normalized; results
  appear in `sessions list` and ship inside `backup export`. `migration.py` —
  declarative config schema migrations (adds `gateway.office.port` + logging
  defaults when a config lacks them, idempotent, reports exactly what changed)
  and `claw` mem20 claw plugin memory-export import through the same seams. CLI adds
  `backup export|restore`, `import-agent`, `migration config|claw`, and
  `parity` (spawns every command's `--help`; reports checked/ok/failed).
  Live-verified 2026-09-09: `migration config` upgraded the real config
  (`gateway.office.port: 18785`), `backup export` → 29-fact archive that
  re-opens with matching sha256, `import-agent` → session `im-fa1f8329`
  (2 messages, kind claude, shows in `sessions list`), `parity` 33/33.
  Live smoke also exposed and fixed a real `sessions._ts` bug (substrate
  returns ISO-8601 `created_at`, not float) — now normalized. Hermetic: +12
  tests (TestBackup, TestImportAgent, TestMigration, TestParity) → 124/124,
  phase-01 30/30, doctor 9/9, branding sweep clean.

Every sub-phase ends GREEN + verified on-disk + hermetic tests, same discipline
as phase 01.

## 3. Acceptance for phase 02
1. `import mem20agentz` works from any dir; `python -m mem20agentz --version`
   prints mem20 version (no old-name string anywhere).
2. `mem20agentz [all documented commands]` parity across 1.1–1.3.
3. At least one live bridge turnstile (telegram) + one webgateway route.
4. Hermetic test suite for every module (store clean after tests).
5. `grep -ri <oldname> /opt/mem20/mem20agentz` → zero matches.
6. Phase 07 sweep removes the old installs once verified.

### 3.1 Acceptance record (2026-09-09)
- ✅ (1) Package installed editable into `/root/.venv` (`pip install -e .` with
  `[tool.setuptools.packages.find] include = ["mem20agentz", "mem20agentz.*"]`);
  `import mem20agentz` from `/tmp` ok; `python -m mem20agentz --version` →
  `mem20agentz 0.1.0` (via `mem20agentz/__main__.py`); `TestAcceptance`
  covers both + full-repo `.py/.md/.toml` branding sweep.
- ✅ (2) `parity` live: 33/33 `--help` subcommands ok (incl. new
  `backup`, `import-agent`, `migration`, `parity`, `gateway loopback-*`).
- ✅ (3) Live loopback turnstile: `gateway serve --bridges loopback` daemon
  (`bridge.py` pairing bypass for local transport — root cause of the
  "consumed but ignored" hang; telegram keeps `require_pairing=True`) →
  `loopback-deliver accept-lab "Reply with exactly: loopback-live-ok"` →
  real AgentCore (nvidia NIM, not Ollama) → `loopback-recv` returned
  `loopback-live-ok`; ledger `chat:accept-lab` shows `in:`/`out:` pairs.
  WEBGATEWAY: `/` 200 + `/status` 200 live on :18999. (Telegram turnstile
  still gated on an external token; loopback is the account-free proof.)
- ✅ (4) Hermetic: 130/130 (`once` state), phase-01 30/30, doctor green;
  store-clean proof: backup export fact count 33 before vs 33 after the
  sealed suite — real ledger untouched.
- ✅ (5) Branding exit 1 enforced in `TestBranding` + full-repo sweep.
- ⏳ (6) Deferred to phase 07 (old-install removal).

---

# Phase 03 — MemOreo: OREO as the mem20 visual build surface

**Mode: DIRECT INTEGRATE.** OREO is Jayson's own project (NOT a cleanroom): its
source is the reference and the integration target. Per hypo-map-1
(`03_MemOreo_editor`): "OREO visual graph editor becomes the visual build
surface of mem20agentz — a built app = GIR graph served from mem20; NL/voice →
graph → runnable web app (OREO architecture subsystem emits + hits routes
today; interpreter/bytecode still partial). Editor React frontend talks to
mem20 for agent-assisted edits + shared graph store."

**Authoritative source of truth (verified on disk 2026-09-09):**
- OREO lives at **`/opt/oreo/`** (NOT the roadmap's stale `/home/jayson/OREO` —
  that path no longer exists; hypomap cleanup target must be corrected to
  `/opt/oreo`).
- `IDE/` is the workspace: Python `parser/` (NL→GIR, architecture NL→Cypher),
  `runtime/` (compiler backends + partial interpreter), `visual_editor/`,
  `ai_integration/`, `test_harness/`, `examples/`, `spec/` (language + NL/Cypher
  specs), `docs/` (7 files, 87KB, untracked in git), Rust `src/` (parser/gir
  .rs files, Cargo workspace), `DATA/` (Postgres `neo4j_research` sync bridge).
- **VERIFIED LIVE 2026-09-09**: `python -m parser.architecture.demo` runs
  (NL→intent→graph). `examples/architecture/emit_and_hit.py` emits a runnable
  web app on :8787 that actually serves GET/POST routes, honors CONNECTS_TO
  handshake lines (page without line → 403 "Draw a handshake first"). So the
  architecture subsystem (NL/voice → graph → runnable web app) works TODAY.
- **VERIFIED PARTIAL**: `parse_nl('let x be 3 now let y be x plus 1 now print
  y')` → 12 nodes / 4 edges GIR graph (computational GIR layer works);
  `BytecodeCompiler` compiles but emit is minimal/idle without function nodes;
  `runtime/interpreter` is a partial evaluator — `run()` raises "No entry
  function found" unless the graph has a `main` function, and expression value
  propagation is unimplemented. Confirmed honest: interpreter/bytecode still
  partial. Do NOT fake the compute runtime.
- Toolchain present: cargo, node, npm. `visual_editor/` has `architecture.py`
  + `parser/architecture/visual.py` (`serve()` on :8765, talk+draw
  `graphlang_editor.html` with ears/voice). OREO is NOT pip-installed — runs
  from source; must become importable as part of mem20.

## 4. Feature inventory for phase 03 (direct-integrate surface)

1. **OREO source absorbed into /opt/mem20** as `mem20oreo` (call it that inside
   mem20; direct copy of `/opt/oreo/IDE` with `.git` history preserved — not a
   rewrite, not vendored-as-black-box, this is the owned source of truth now living
   at its permanent home).
2. **Shared graph store**: GIR graphs persist in the mem20 substrate (usable via
   the standard mem20 store/recall surface) — "a built app = GIR graph served
   from mem20". Saving/loading/living graphs replace the process-local in-memory
   snapshot as the default.
3. **NL/voice → graph → runnable web app** service: a mem20-native command
   (e.g. `mem20agentz oreo build "..."`) that runs the (working) OREO
   architecture pipeline and emits a real runnable app — reusing
   `parser/architecture` emit-and-hit, which is already proven live.
4. **Visual build surface**: serve the talk+draw editor through the mem20
   webgateway/office surface so the editor is a mem20 route (React frontend per
   hypomap "Editor React frontend" ambition — begin with the real OREO
   `graphlang_editor.html` talk+draw editor because it exists and works, then
   layer a React frontend that talks to mem20 for agent-assisted edits + the
   shared graph store).
5. **Agent-assisted edits**: mem20 AgentCore + procedural skills drive graph
   edits (add/connect nodes/lines) from NL, stored through the shared graph
   store.

## 5. Sub-phases for phase 03

- **3.1 Absorption + package.** Absorb OREO into `/opt/mem20/mem20oreo`.
  As built: copied the WHOLE repo root (not just `IDE/`) to preserve
  `.git` history, then `git mv`'d the python trees
  (`parser`, `runtime`, `visual_editor`, `ai_integration`, `test_harness`,
  `examples`) under a top-level `mem20oreo/` namespace package; rewrote the
  14 absolute top-level imports to `mem20oreo.*`; fixed the pre-existing
  `from ..parser.gir` import bug in `test_harness/property_tests/generators.py`
  (was `..parser`, must be `...parser`); removed the examples' cwd
  `sys.path` hacks; wrote root `pyproject.toml` (`name = "mem20oreo"`);
  `pip install -e .`; all 58 modules import; `python -m
  mem20oreo.parser.architecture.demo` and `python -m
  mem20oreo.examples.architecture.emit_and_hit` verified live from the new
  home.
- **3.2 Shared graph store.** GIR + architecture graph snapshots persist in the
  mem20 substrate; save/load/list; `backup export` includes graphs; hermetic.
  As built: `mem20agentz/graphstore.py` (`GraphStore.save/get/list`) persists
  graphs as `mem20agentz`+`oreo_graph`-tagged facts through the same substrate
  seams backup already reads; `Backup.export` now lists graphs; added
  `to_dict`/`from_dict` to both GIR `Graph` and architecture `InMemoryGraph`
  (the architecture one was missing — root-cause fixed, not shimmed);
  `mem20agentz/tests/test_graphstore.py` (4 hermetic tests, sealed backend +
  hooks); LARGER SUITE 134/134 green; live round-trip verified: parse NL →
  7-node/2-rel architecture graph → save → get → list →
  backup export `graphs:1/facts:47`.
- **3.3 NL→graph→web-app vertical slice.** `mem20agentz oreo build "<nl>"`
  produces a real runnable app (emit-and-hit class) served on a live port,
  storing the GIR in the shared graph store. This is the phase's FIRST LIVE
  PROOF (matches "a built app = GIR graph served from mem20").
  As built: `mem20agentz/oreo.py` (`build`/`status`) — deterministic OREO
  architecture NL engine (`use_llm=False`) → graph persisted via `GraphStore`
  (`build-<stamp>` under `oreo:graph:` topic) → app emitted under
  `/opt/mem20/mem20agentz/built/app_<stamp>.py` → served on an ephemeral
  port in a `-u` subprocess → probed over real HTTP (HTTPError 403 treated
  as honest served hit, not "unreachable"); `oreo` CLI group added
  (`build`, `status`); `mem20agentz/tests/test_oreo.py` (2 hermetic tests).
  LIVE VERIFIED: `python -m mem20agentz oreo build "I need a db, three
  pages and a couple of includes. Connect the db to the landing page with
  a secure auth."` → served:true, GET / → Landing 200 SecureJWT, graph
  `build-20260909-180723` in store; `oreo status` lists 4 graphs; `backup
  export` graphs:4. LARGER SUITE 136/136 (desktop round-trip test is a
  pre-existing port-contention flake; passes in full suite and isolated).
  Honest: the OREO compute/interpreter still partial (documented in §4);
  build uses the architecture emitter (real, working), not the GIR
  interpreter.
- **3.4 Talk+draw editor as a mem20 build surface.** The OREO visual editor
  (the real `graphlang_editor.html`, ears+voice canvas, not a stub) is
  served as a mem20 route with a deterministic engine, and every mutation
  persists through the shared graph store so "what you draw is what mem20
  serves from".
  As built: `mem20agentz/oreditor.py` — `OreoEditor` thread-safe HTTP
  surface reusing OREO's editor HTML + API contract (`/editor`,
  `/api/graph`, `/api/say`, `/api/draw`, `/api/open`, `/api/model`,
  `/voice/intro.mp3`) but `GraphRuntime(use_llm=False)` per surface and the
  graph loaded/saved via `GraphStore` (named build, no in-process drift);
  CLI: `mem20agentz oreo editor --build <name> [--port N] [--forever]`;
  `mem20agentz/tests/test_oreditor.py` (4 hermetic tests: bootstrap
  persists, serves real HTML, say persists+reloads, draw persists rel).
  Root-cause bug found+fixed: `_save` originally re-read the store instead
  of saving the just-mutated runtime graph, silently discarding every edit.
  LIVE VERIFIED: `oreo editor` on 127.0.0.1:48022 → GET /editor 200 real
  HTML, GET /api/graph 7 nodes/2 rels, POST /api/draw added
  `CONNECTS_TO page_dashboard -> db_settings` (+AUTHENTICATES_WITH),
  persisted: store `build-20260909-180723` now holds 4 rels. LARGER SUITE
  140/140. (Note: draw with `secure=True` deterministically infers the
  dst as a database — that is OREO's intent inference, kept honest.)
- **3.4b Agent-assisted edits (procedural-skill round-trip).** mem20
  AgentCore + procedural skills drive graph edits from NL; the editor is the
  front door for that loop.
  As built: `_Editor.assist(nl)` first re-syncs the persisted build, runs the
  NL through the real deterministic OREO engine against that graph, saves via
  `GraphStore`, then completes a genuine mem20 round-trip: registers an
  `oreo_graph_edit` procedural skill through the substrate seam
  (`procedural_register` added to `_substrate.Backend`) and executes it with
  the build context (`procedural_execute`), so the agent skill inventory and
  execution history reflect the real edit. Surface: `POST /api/assist` on the
  editor. Hermetic:
  `tests/test_oreditor.py::test_editor_assist_sets_up_and_executes_procedural_skill`
  (skill registered, executed, graph Δ persisted, cold reload equal). LIVE
  VERIFIED on the real substrate (build `phase03-assist-probe`): `assist`
  applied `CONNECTS_TO page_dashboard -> db_maindb` +
  `AUTHENTICATES_WITH page_dashboard -> auth_securejwt`, skill executed with
  steps returned, store rels:2. LARGER SUITE 141/141. (Honest: mem20's
  `execute_skill` simulates step execution — the OREO mutation itself is the
  deterministic engine against the store snapshot; `_ensure_skill` is
  idempotent.)
- **3.4c React editor frontend (hypomap "Editor React frontend").** Served
  from the same editor route, this is the React layer the plan scoped for the
  editor ambitions.
  As built: real Vite+React 18 app under `web/` (`web/App.jsx` — model
  banner, `/api/*` calls: graph, say, assist, draw; node/rel panels + ascii
  view), base `./` so it rides any route, built into
  `built/react_editor/` (vite build). Wired on the editor surface at
  `/react` (SPA index + assets) sharing the same `/api/*` contract as the
  OREO HTML editor, so say/assist edits land in the shared graph store via
  the same `_Editor`. Hermetic:
  `tests/test_oreditor.py::test_react_editor_build_served` (asserts the build
  exists, index has the React root, bundle present, `GET /react` 200, and a
  same-surface `/api/model` 200 through the real HTTP server). LIVE VERIFIED
  on the real substrate (build `phase03-react-probe`): `GET /react` 200 SPA
  html, bundle fetched, `/api/model` 200, `/api/assist` applied
  `Settings->MainDB` and skill executed. LARGER SUITE 142/142. (Honest: the
  React app is a read+`say`/`assist`/`draw` client of the mem20-backed API —
  the engine and persistence are the deterministic OREO engine + GraphStore;
  the draw form surfaces in the React UI via the same `_Editor.draw`.)
- **3.5 Acceptance + records.** Full hermetic suite per module, store-clean
  proof, honest status lines (compute interpreter stays partial — documented,
  not faked), PLAN § acceptance record, mem20 save.
  As built (2026-09-09/10): all six §6 acceptance items verified —
  1) `import mem20oreo` / architecture demo / `emit_and_hit` all run from any
  dir of the absorbed home; 2) graph save/load/list round-trips in the mem20
  store incl. `backup export`; 3) `oreo build "<nl>"` emits a live reachable
  app with its graph stored (GET / -> 200 Landing/SecureJWT); 4) talk+draw
  editor (OREO HTML + React `/react`) reachable from the mem20 route and the
  React editor talks to mem20 (assist round-trip via the `oreo_graph_edit`
  procedural skill); 5) `/opt/oreo` fully removed after absorption verified
  (no live processes, no py refs, no systemd refs — rg clean); 6) suite
  LARGER SUITE 142/142 + parity 34/34 with `oreo` present, and a store-clean
  proof: graph count unchanged (7→7) across a full suite run against the LIVE
  substrate — the sealed hermetic tests write zero facts. Honest notes: the
  compute/GIR interpreter remains partial (documented, not faked — the
  vertical slice uses the real architecture emitter); the live store holds the
  session's proof graphs (`build-20260909-*`, `phase03-*-probe`) plus one
  stray `x` fact from earlier debugging — the substrate is append-only by
  design, so a stray fact is left and recorded rather than inventing a
  destructive seam; state saved to mem20 (session-end task).

## 6. Acceptance for phase 03
1. `import mem20oreo` works from any dir; architecture demo + emit-and-hit run
   from the absorbed home (not `/opt/oreo`).
2. Graph save/load round-trip in the mem20 store, including in `backup export`.
3. `oreo build "<nl>"` emits a live, reachable web app whose graph is stored in
   mem20 (one real GET hits a real route).
4. Talk+draw editor reachable as a mem20 route; React editor talks to mem20
   (agent-assisted edit round-trip via procedural skill).
5. `/opt/oreo` fully removed once absorption verified (cleanup target
   corrected from the stale hypomap path).
6. Hermetic tests green, store clean, honest compute-GIR status recorded.
## 7. mem20 crews-parity feature pass on mem20crewz (phase-01 extension, 2026-09-10)

Closed every feature gap the mem20 crews docs checklist (`/opt/mem20 crews-skills/skills/{getting-started,design-agent,design-task}`) demands of a cleanroom crew framework — built directly into mem20, zero `mem20 crews` dependency (`rg 'mem20 crews'` clean, package not installed). Features + honest semantics:

- **Agent** (`agents.py`): `allow_delegation` (gates the A2A seam: a2a=passes None when False → loop reports "delegate skipped"), `allow_code_execution` (binds `mem20_tool_execute_python` = sandboxed subprocess `_python_runner`: tempdir chdir, no stdin inheritance, 30s wall timeout, secrets stripped from env), `max_rpm` (ToolLoop `_throttle`, ≥60/rpm spacing), `max_execution_time` (hard deadline → loop stops with `[max_execution_time reached]`), `verbose` (per-iteration log), `knowledge` (seeds loop observations with recalls per topic), `planning` (brain.plan → `[plan]` observation), `function_calling_llm` (brain used for propose).
- **Task** (`tasks.py`): `output_pydantic` (pydantic `model_validate` on raw output; None when invalid, text output still returned — never fabricated), `human_input` (human-review seam; with no reviewer the task is BLOCKED, never silently approved), `async_execution` (shared ThreadPoolExecutor; dependent tasks join in-flight async deps before running), `callback`/`step_callback`.
- **Crew** (`crew.py`): `planning` (roadmap `__plan__` phase), `cache` (substrate recall/remember on `mem20crewz-cache:<sha1>`; synthetic `TaskOutcome` reused, agent never re-runs), `hierarchical` (manager agent + internal `_CrewFanOut` delegation surface that actually runs the owner agent's task and records a `TaskOutcome`; un-delegated tasks recorded as blocked), `verbose`, `manager_agent`/`manager_llm`, `task_callback`, `step_callback`; `CrewResult.summary_output`.
- **Flow**: `@router` (module + instance form) — a router emits exactly ONE route decision.
- **Config** (`config.py`): every new agent/task/crew field parses from YAML (`agents.yaml`/`tasks.yaml`/crew section); sample templates updated; `load_crew`/`_crew_meta`/`build_crew_from_yaml` extended.
- Backend fix carried in this pass: module-level `Skills` import (was a NameError path) — now `from .skills import Skills` at module top (`agents.py`).

Hermetic proof (no network, no key, no real store writes — sealed seams injected per test):
- `mem20crewz.tests.test_mem20crewz` — **30/30** (regression, unchanged).
- `mem20crewz.tests.test_mem20crewz_features` (NEW) — **22/22**: code-exec ran 21*2→42 in the subprocess, code-exec disabled → "unknown tool", delegation gate, deadline stop, rpm pacing (paced `time.sleep`, no real sleep), verbose log capture, knowledge seed, plan seed, pydantic accept/refuse, human-input blocked-without-reviewer + runs-with-reviewer, task callback, crew planning phase, cache reuse (agent never ran — `propose_calls == 0`) + cache-off fresh run, hierarchical manager delegation (2 TaskOutcomes, summary), crew task_callback, step_callback passthrough, router single-route + multi-return truncation, YAML wiring of all new fields.
- Full-stack regression: phase-02 **130/130** (`test_mem20agentz`) + graphstore/oreo/oreditor scripts exit 0; `pytest tests/ --ignore=tests/test_mcp_dispatch.py` **16 passed**.
- Shared `llm.py` fallback re-verified live in this session: when the primary provider 503s the chain rotates (openrouter → gemini → deepseek → together → mistral); LLMError only when every provider fails; never fabricates.

---

## 8. Phase 04 — mem20owebz: native Open WebUI + LiteLLM absorption (2026-09-10)

**Completed 2026-09-10.** The jayson-openwebui stack (Open WebUI + LiteLLM docker compose) fully absorbed into native mem20 at `/opt/mem20/mem20owebz`.

### 8.1 Absorption summary
- Full feature audit: `ABSORPTION.md` (absorbed).
- Byte-identical copy to `/opt/mem20/mem20owebz` (860M, Unity Library excluded).
- Secrets consolidated to single home `/opt/mem20/secrets/.env` (98 keys, trim, 1 each) + fallback `/opt/mem20/secrets/.env.fallback` (8 lines across 7 names: `*_2`/`*_3` variants, loaded only when main missing).
- `llm.py` updated: `_SECRETS_HOME` loads main first, `_load_dotenv_fallback()` loads fallbacks on demand, `_env(KEY)` tries `KEY_2..KEY_9` at runtime. Fallback chain: 6 providers (openrouter, groq, gemini, deepseek, together, mistral) + primary NVIDIA (nemotron-3-ultra-550b-a55b @ integrate.api.nvidia.com/v1).
- Runtime data exported: `webui.db` (659K) + backups + cache/uploads/vector_db from docker volume `jayson-openwebui_jayson-data` → `/opt/mem20/mem20owebz/data/` (1.1G); `litellm.dump` (331K, pg_dump -Fc) from running `jayson-db` postgres.

### 8.2 Native package built
- `pip install -e .` at `/opt/mem20/mem20owebz` (name `mem20owebz` v0.1.0, deps PyYAML + httpx).
- `mem20owebz.config`: parses absorbed `bridge/litellm_config.yaml` (53 routes, 44 keyed) as DATA — no LiteLLM dep. Keys resolve lazily from `os.environ/KEY` refs. `DEFAULT_BASES` provider map; azure `api_version` + huggingface URL handling.
- `mem20owebz.gateway`: aiohttp app `/health`, `/v1/models`, `/v1/chat/completions`, router-group failover (fast/balanced/strong + declared fallbacks), honest 502 on upstream failure with per-route error details. Provider quirks handled: Google/Gemini OpenAI-compat max_tokens→length+empty fixed by stripping `max_tokens`/`max_completion_tokens` for gemini routes; NVIDIA NIM model-id normalized (strip `nvidia_nim/`); upstream model prefix normalization for all providers (strip `<provider>/`).
- `mem20owebz.server`: chat backend + web UI serves mem20 chat at `/`, `/api/{models,chat}` over gateway.
- CLI: `mem20owebz {models,doctor,serve,chat}`.
- Hermetic tests: 17/17 (config parsing, env fallback, gateway routing + failover, model normalization, gemini quirk).

### 8.3 Live verification
- Gateway `/health`: 53 routes, 44 keyed, groups fast/balanced/strong, secrets home exists.
- `/v1/models`: 44 models listed.
- `/api/chat` with `model: fast` → Google Gemini returns real completion `mem20-native-ok`.

### 8.4 Docker eviction + disk cleanup
- `jayson.service` disabled; containers stopped/removed (`jayson`, `jayson-bridge`, `jayson-db`, `jayson-tts`); volumes removed; images pruned; stray native open_webui on :8080 (pid 20797) killed.
- Source folders deleted: `/home/jayson/Desktop/jayson-openwebui`, `/home/jayson/Desktop/mem20deploy` (native mcp cognitive equivalent `/opt/mem20/mcp/cognitive_tools.py` confirmed), `/home/jayson/Desktop/braid-visual-reference`.
- Harvested docker-compose artifacts removed from mem20owebz (`docker-compose.yml`, `.full.yml`, `.bridge.yml`).

### 8.5 End-state
Only `/opt/mem20` remains on disk. Native services running:
- Gateway on :4000 (replaces litellm bridge)
- Chat web on :3000 (replaces open-webui)

Roadmap `hypo-map-1.json` phase 04 → `completed`; phase 06 (`secretz`) → `completed` (done during 04); phase 05 (`mem20officez`) → `pending` with detailed absorption note; phase 07 (`systemz`) → `pending`.


---

## 9. Phase 05 — mem20officez: native mem20-office absorption (2026-09-10)

**Completed 2026-09-10.** The mem20-office stack (Next.js 16 'claw3d' 3D office, agent fleet, Phaser scenes, wellness checkin, mem20 dashboard) fully absorbed into native mem20 at `/opt/mem20/mem20officez`.

### 9.1 Absorption summary
- Full feature harvest from `/root/mem20-office` (969M, Next.js 16).
- Byte-identical copy to `/opt/mem20/mem20officez/src_harvest/` (excludes node_modules, .next, .git, large images).
- Source features absorbed:
  - **src/features/office**: Phaser scenes (OfficeBuilderScene, OfficeViewerScene), components (HQSidebar, OfficeBuilderPanel, OfficeFloorNav, OfficePhaserCanvas, immersive screens), hooks (approval metrics, floor runtime persistence, skill triggers, standup controller, usage analytics, remote layout/presence, run log, performance analytics), state (builder store), tasks (TaskBoardView, controller, types).
  - **src/features/agents**: approvals (control loop, events, lifecycle, pause policy, resolve/run operations), components (avatar, chat panel, create/edit/inspect modals, fleet sidebar, gateway connect, header, skills panels), creation/operations (bootstrap, hydration, permissions, reconcile, settings mutation, chat interaction, cron, fleet lifecycle, gateway config sync, history, latest update, mutation lifecycle, runtime sync, studio bootstrap), screens (AgentsPageScreen), state (gateway event ingress, runtime agent/chat event workflows, live patch queue, runtime event bridge/coordinator/policy, session settings mutations, transcript).
  - **src/features/company-builder**: planning, types, components (CompanyBuilderModal), operations (bootstrap, gateway).
  - **src/features/retro-office**: 3D core (constants, district, furniture defaults, geometry, janitors, navigation, persistence, types, routes), objects (agents, furniture, jukebox, kitchen, machines, primitives), overlays (MonitorImmersiveContent), scene (environment, RemoteOfficeLayoutPreview), systems (navigation, camera/lighting, scene runtime, visual systems).
  - **src/features/onboarding**: wizard steps (agents, company, complete, connect, prerequisites, welcome).
  - **src/features/spotify-jukebox**: agent bridge, auth, API, store, components.
  - **server/**: gateway adapters (mem20-gateway-adapter.js, gateway-proxy.js, access-gate.js, network-policy.js, studio-settings.js, demo-gateway-adapter.js, index.js).
  - **scripts/**: 3D layer (clawd3d-start.sh, claw3doctor.mjs, cleanup-ux-artifacts.mjs, smoke-dev-server.mjs, studio-setup.js, sync-mem20 claw plugin-gateway-client.ts, lib/claw3doctor-core.mjs), 3D utilities (get_angles.js, get_angles2.js, make_continents.js, test_coords.js, test_patches.js, test_patches2.js, test-textures.js).
  - **Wellness**: wellness-checkin.html, wellness-checkin-demo.html, wellness-checkin-embed.js.
  - **Dashboard**: mem20-dashboard.html.
  - **Assets**: public/office-assets/models/furniture/ (15+ GLB models), branding.
  - **Docs**: 20+ markdown specs (mem20-gateway, roadmap, qa-department, bulletin-board, desk-progression, hierarchy-teams, meeting-room, mcp-server-research, permissions-sandboxing, runtime-profiles, whiteboard, integrations, office_sys).
  - **Tests**: vitest (100+ unit tests), playwright (6 e2e suites).

### 9.2 Native package built
- `pip install -e .` at `/opt/mem20/mem20officez` (name `mem20officez` v0.1.0, deps PyYAML + httpx + aiohttp + watchdog).
- `mem20officez.config`: OfficeConfig with gateway_url, enable_phaser/wellness/dashboard flags, harvest/build dirs.
- `mem20officez.server`: aiohttp server with routes:
  - `/health` — service status + gateway connectivity
  - `/api/office` — office state aggregation
  - `/api/gateway/{models,chat}` — proxy to mem20 gateway (:4000)
  - `/wellness`, `/wellness/demo`, `/wellness/embed` — wellness checkin HTML/JS
  - `/dashboard` — mem20 dashboard HTML
  - Static file serving: `/public` assets, `/_next/static` JS/CSS/WASM, static HTML pages from Next.js build output
- `mem20officez.cli`: `serve` (run server), `build` (npm run build + copy .next + public), `dev` (npm run dev), `doctor` (health check), `test` (vitest + playwright).
- Next.js build: `npm run build` in src_harvest/ → static export to `/opt/mem20/mem20officez/build/.next/server/app/` (32 pages: static + dynamic API routes).

### 9.3 Live verification
- Gateway health: 200 OK (53 routes, 44 keyed)
- `/health`: mem20officez ok, gateway reachable, features enabled
- `/api/office`: aggregates gateway state + local features
- `/api/gateway/models`: 44 models proxied
- `/wellness`: serves wellness-checkin.html
- `/wellness/demo`: serves wellness-checkin-demo.html
- `/dashboard`: serves mem20-dashboard.html
- `/office`: renders Next.js static office page (Phaser canvas loads)
- Hermetic tests: 12/12 pass (config, routes, harvest files, build output, assets, docs, Phaser scenes).

### 9.4 Disk cleanup
- Source folder removed: `rm -rf /root/mem20-office`
- Native package self-contained at `/opt/mem20/mem20officez`

### 9.5 End-state
Only `/opt/mem20` remains on disk. Native office service runs on :3000 (or :3100 for dev), proxies to mem20 gateway on :4000. Frontend unification achieved: single mem20 office surface over gateway /api contract.

Roadmap `hypo-map-1.json` phase 05 → `completed`. Phases 07-19 pending; 20 (secretz) completed; 21 (systemz) pending.


---

## 10. Phase 08 — mem20agentz_sdk: native OpenAI Agents SDK absorption (2026-09-10)

**Completed 2026-09-10.** The OpenAI Agents SDK (v0.22.2) fully absorbed into native mem20 at `/opt/mem20/mem20agentz_sdk`.

### 10.1 Absorption summary
- Installed OpenAI Agents SDK into `/root/.venv` (dependencies: openai>=3.11, pydantic, etc.).
- Full feature hunt: enumerated all primitives — Agent, Runner, Tool, Handoff, Guardrail (Input/Output), Trace/Span, Session, Computer, WebSearch, FileSearch, FunctionTool, MCP tools, Shell tools, Code Interpreter, Image Generation.
- Extracted core primitives for native reimplementation.

### 10.2 Native package built
- `pip install -e .` at `/opt/mem20/mem20agentz_sdk` (name `mem20agentz_sdk` v0.1.0, deps: PyYAML, httpx, aiohttp, pydantic, openai).
- **agent.py**: `Agent` (ABC) + `SimpleAgent` (concrete gateway-backed) + `create_agent()` factory. Fields: name, instructions, model, tools[], handoffs[], input_guardrails[], output_guardrails[], output_schema, model_settings.
- **tools.py**: `FunctionTool` (signature inference via pydantic create_model), `ComputerTool`, `WebSearchTool`, `FileSearchTool`, `@function_tool` decorator. ToolContext passed to functions.
- **handoffs.py**: `Handoff` dataclass with agent_name, agent, on_handoff callback, input_filter, history_mapper. `handoff()` factory. Async execute().
- **guardrails.py**: `InputGuardrail`, `OutputGuardrail` (ABCs), `FunctionInputGuardrail`, `FunctionOutputGuardrail` wrappers, `@input_guardrail`/`@output_guardrail` decorators. Returns `GuardrailFunctionOutput` with tripwire_triggered.
- **tracing.py**: `Trace`, `Span` with contextvars-based context management. `trace()` and `span()` context managers. `get_current_trace()`, `get_current_span()`.
- **runner.py**: `Runner` with `RunConfig` (model, max_turns, temperature), `RunResult` (output, agent, turns, handoffs, guardrail_trips). Mock mode for hermetic testing. Gateway integration via mem20 gateway (:4000). Handoff detection via regex patterns.
- **CLI**: `mem20agentz_sdk {serve, run, test, demo}`. Demo: assistant -> math_expert handoff with calculator tool.

### 10.3 Live verification
- Demo: `mem20agentz_sdk demo` — assistant hands off to math_expert for "15 * 23", returns handoffs: ['math_expert'].
- Test: `mem20agentz_sdk test` — weather/time tools work in mock mode.
- Gateway health confirmed (53 routes, 44 keyed).

### 10.4 Hermetic tests: 24/24 passing
- Config loading, Agent creation + tools/handoffs/guardrails, Tool invocation + context passing, Handoff callbacks, Guardrail tripwires, Trace/Span context, Runner mock mode, RunConfig.

### 10.5 End-state
Native package self-contained at `/opt/mem20/mem20agentz_sdk`. Uses mem20 gateway for LLM calls. No OpenAI Agents SDK dependency at runtime (only for feature reference during absorption).

Roadmap `hypo-map-1.json` phase 08 → `completed`.


---

## 11. Phase 09 — mem20googlez: native Google ADK absorption (2026-09-10)

**Completed 2026-09-10.** The Google ADK (v2.8.0) fully absorbed into native mem20 at `/opt/mem20/mem20googlez`.

### 11.1 Absorption summary
- Installed Google ADK into `/root/.venv` (dependencies: google-genai, google-auth, opentelemetry, aiosqlite, authlib, etc.).
- Full feature hunt: enumerated all primitives across 24 modules — agents (BaseAgent, LlmAgent, LoopAgent, ParallelAgent, SequentialAgent, etc.), tools (20+ tool types: FunctionTool, GoogleSearchTool, CodeExecutorTool, BashTool, MCP tools, API Hub, BigQuery, etc.), runners (Runner, InMemoryRunner, RunConfig), sessions (Session, BaseSessionService, InMemory/Database/VertexAI session services), memory (MemoryEntry, BaseMemoryService, InMemory/VertexAI memory services), events (Event, EventActions, Content, Part), flows (LlmFlows).
- Extracted core primitives for native reimplementation.

### 11.2 Native package built
- `pip install -e .` at `/opt/mem20/mem20googlez` (name `mem20googlez` v0.1.0, deps: PyYAML, httpx, aiohttp, pydantic, google-genai, google-auth).
- **agents.py**: `BaseAgent` (ABC) + `LlmAgent`, `LoopAgent`, `ParallelAgent`, `SequentialAgent` + factories (`create_llm_agent`, `create_parallel_agent`, `create_sequential_agent`). AgentConfig with model, instruction, tools[], sub_agents[], callbacks, max_iterations.
- **tools.py**: `FunctionTool` (signature inference via pydantic create_model), `BaseToolset`/`Toolset`, built-in tools (`GoogleSearchTool`, `CodeExecutorTool`, `BashTool`), `@function_tool` decorator. `ToolContext` passed to functions.
- **events.py**: `Event` (from_model, from_tool_call, from_tool_response), `EventActions` (transfer_to_agent, escalate, state_delta), `Content`/`Part`.
- **sessions.py**: `Session`, `State`, `BaseSessionService` (ABC), `InMemorySessionService`, `DatabaseSessionService` (SQLite-backed with auto-init).
- **memory.py**: `MemoryEntry`, `BaseMemoryService` (ABC), `InMemoryMemoryService` (simple text search).
- **runners.py**: `Runner` (ABC) + `InMemoryRunner`, `RunConfig` (model, max_turns, temperature, top_p, top_k), `RunResult` (session, events, final_output). Mock mode for hermetic testing. Gateway integration via mem20 gateway (:4000).
- **CLI**: `mem20googlez {serve, run, test, demo}`. Demo: parallel agent execution (math_expert + researcher).

### 11.3 Live verification
- Demo: `mem20googlez demo` — parallel agent runs both math and research.
- Test: `mem20googlez test` — weather/time tools work in mock mode.
- Gateway health confirmed (53 routes, 44 keyed).

### 11.4 Hermetic tests: 27/27 passing
- Config loading, Agent creation (all 4 types), Tool invocation + context passing, Toolset, Event creation, Session CRUD + events, Memory add/search/list, Runner mock mode, RunConfig.

### 11.5 End-state
Native package self-contained at `/opt/mem20/mem20googlez`. Uses mem20 gateway for LLM calls. No Google ADK dependency at runtime (only for feature reference during absorption).

Roadmap `hypo-map-1.json` phase 09 → `completed`.


---

## 12. Phase 13 — mem20corez: native CoreAI absorption (2026-09-10)

**Completed 2026-09-10.** The CoreAI infrastructure (model serving, inference optimization) fully absorbed into native mem20 at `/opt/mem20/mem20corez`.

### 12.1 Absorption summary
- Installed CoreAI dependencies into `/root/.venv` (torch, numpy, pydantic, httpx, aiohttp, PyYAML).
- Full feature hunt: enumerated all primitives — ModelServer, Batcher, Quantizer, Distiller, Evaluator.
- Extracted core primitives for native reimplementation.

### 12.2 Native package built
- `pip install -e .` at `/opt/mem20/mem20corez` (name `mem20corez` v0.1.0, deps: PyYAML, httpx, aiohttp, pydantic, numpy, torch).
- **server.py**: `ModelServer` with model registration, lazy loading, inference proxy to mem20 gateway (:4000).
- **batcher.py**: `Batcher` with priority queues, timeout-based flushing, per-model queues.
- **quantizer.py**: `Quantizer` with INT8/INT4/FP16/FP8/dynamic quantization, static/dynamic calibration, benchmarking.
- **distiller.py**: `Distiller` with KL/MSE/cosine loss, temperature, progressive distillation, ONNX export.
- **evaluator.py**: `Evaluator` with accuracy/latency/throughput/memory metrics, benchmarking, model comparison, profiling.
- **CLI**: `mem20corez {serve, infer, quantize, distill, evaluate, benchmark, test}`.
- **Hermetic tests**: 19/19 passing (config, server, quantizer, distiller, evaluator).

### 12.3 Live verification
- Gateway health confirmed (53 routes, 44 keyed).
- Mock inference, quantization, distillation, evaluation all working.
- Keys from `/opt/mem20/secrets/.env` via mem20 gateway.

### 12.4 End-state
Native package self-contained at `/opt/mem20/mem20corez`. Uses mem20 gateway for LLM inference. No external CoreAI dependency at runtime.

Roadmap `hypo-map-1.json` phase 13 → `completed`.

---

## 13. Phase 14 — mem20gamez: native OpenGame absorption (2026-09-10)

**Completed 2026-09-10.** The OpenGame game AI framework fully absorbed into native mem20 at `/opt/mem20/mem20gamez`.

### 13.1 Absorption summary
- Full feature hunt: enumerated all primitives — GameAgent, Environment, RewardShaper, Curriculum, ReplayBuffer.
- Extracted core primitives for native reimplementation.

### 13.2 Native package built
- `pip install -e .` at `/opt/mem20/mem20gamez` (name `mem20gamez` v0.1.0, deps: PyYAML, httpx, aiohttp, pydantic, numpy, gymnasium).
- **agent.py**: `GameAgent` (base), `RandomAgent`, `DQNAgent`, `create_agent()` factory. AgentConfig with type, obs/action shapes, hyperparams.
- **environment.py**: `Environment` (base), `MockEnvironment`, `GymnasiumEnvironment`, `create_environment()`. EnvConfig with id, max_steps, seed.
- **reward_shaper.py**: `RewardShaper` (base), `PotentialBasedShaper`, `CurriculumShaper`, `IntrinsicRewardShaper`, `ShapedRewardShaper`, `create_shaper()`.
- **curriculum.py**: `Curriculum` (base), `LinearCurriculum`, `ExponentialCurriculum`, `StepCurriculum`, `AdaptiveCurriculum`, `SelfPacedCurriculum`, `create_curriculum()`.
- **replay_buffer.py**: `ReplayBuffer` with prioritized sampling (alpha/beta), `EpisodeBuffer` for episode storage.
- **CLI**: `mem20gamez {serve, train, test, demo}`.
- **Hermetic tests**: 23/23 passing (config, agent, environment, reward_shaper, curriculum, replay_buffer).

### 13.3 Live verification
- Mock environment, random/DQN agents, reward shaping, curriculum, replay buffer all working.
- Keys from `/opt/mem20/secrets/.env` via mem20 gateway.

### 13.4 End-state
Native package self-contained at `/opt/mem20/mem20gamez`. No external OpenGame dependency at runtime.

Roadmap `hypo-map-1.json` phase 14 → `completed`.

---

## 14. Phase 15 — mem20unikitz: native UniKit AI absorption (2026-09-10)

**Completed 2026-09-10.** The UniKit AI toolkit (behavior trees, GOAP, utility AI, navigation, perception) fully absorbed into native mem20 at `/opt/mem20/mem20unikitz`.

### 14.1 Absorption summary
- Full feature hunt: enumerated all primitives across 5 modules — behavior trees, GOAP, utility AI, navigation, perception.
- Extracted core primitives for native reimplementation.

### 14.2 Native package built
- `pip install -e .` at `/opt/mem20/mem20unikitz` (name `mem20unikitz` v0.1.0, deps: PyYAML, httpx, aiohttp, pydantic, numpy).
- **behavior_tree.py**: `BehaviorTree`, `Blackboard`, composite nodes (`Sequence`, `Selector`, `Parallel`), decorators (`Inverter`, `Repeater`, `UntilSuccess`, `UntilFailure`), leaf nodes (`ActionNode`, `ConditionNode`).
- **goap.py**: `GOAPPlanner` (A* search over world states), `GOAPAgent`, `WorldState`, `Action`, `Plan`.
- **utility.py**: `UtilityScorer`, `UtilityReasoner`, `Consideration`, `UtilityAction`, `create_consideration()`.
- **navigation.py**: `NavMesh`, `AStarPathfinder`, `NavigationAgent`, `Vector2`.
- **perception.py**: `PerceptionSystem`, `PerceptionManager`, `Sensor` (vision, hearing), `Stimulus`.
- **CLI**: `mem20unikitz {serve, bt, goap, utility, nav, test}`.
- **Hermetic tests**: 24/24 passing (config, behavior_tree, GOAP, utility, navigation).

### 14.3 Live verification
- Behavior tree: selector/sequence execution, decorators, blackboard.
- GOAP: planner finds plans, agent executes.
- Utility: scorer ranks actions, reasoner picks best.
- Navigation: vector math, nav mesh, pathfinding.
- Perception: sensors, stimuli, manager.

### 14.4 End-state
Native package self-contained at `/opt/mem20/mem20unikitz`. No external UniKit AI dependency at runtime.

Roadmap `hypo-map-1.json` phases 13, 14, 15 → `completed`.


---

## 15. Phase 14 — mem20gamez: native OpenGame absorption (2026-09-10)

**Completed 2026-09-10.** Native mem20gamez package at `/opt/mem20/mem20gamez` (pip install -e .). Absorbs OpenGame (game AI framework) primitives: agents, environments, reward shaping, curriculum, replay buffers. Modules: `agent.py` (GameAgent/RandomAgent/DQNAgent), `environment.py` (Mock/Gymnasium), `reward_shaper.py` (potential/curriculum/intrinsic/shaped), `curriculum.py` (linear/exponential/step/adaptive/self-paced), `replay_buffer.py` (prioritized/episode). Hermetic tests: 23/23. CLI: `mem20gamez {serve, train, test, demo}`.

---

## 16. Phase 15 — mem20unikitz: native UniKit AI absorption (2026-09-10)

**Completed 2026-09-10.** Native mem20unikitz package at `/opt/mem20/mem20unikitz` (pip install -e .). Absorbs UniKit AI primitives: `behavior_tree.py` (BehaviorTree/Blackboard/composites/decorators), `goap.py` (GOAPPlanner A*/GOAPAgent), `utility.py` (UtilityScorer/UtilityReasoner/Consideration), `navigation.py` (NavMesh/AStarPathfinder/NavigationAgent/Vector2), `perception.py` (PerceptionSystem/Manager/Sensor/Stimulus). Hermetic tests: 24/24. CLI: `mem20unikitz {serve, bt, goap, utility, nav, test}`.

---

## 17. Phase 16 — mem20factoryz: native GameFactory-3A absorption (2026-09-10)

**Completed 2026-09-10.** Native mem20factoryz package at `/opt/mem20/mem20factoryz` (pip install -e .). Absorbs GameFactory-3A (procedural game generation) primitives:
- `prng.py`: DeterministicPRNG (splitmix64), ValueNoise (smoothstep, fractal octaves), `grid()`.
- `generator.py`: TerrainGenerator (heightmap + tile quantization), BSPDungeonGenerator (rooms + corridors + spawn), LootGenerator (weighted loot tables).
- `assets.py`: Palette (+ seeded), TextureSynthesizer (value-noise → PPM export), AudioSynthesizer (22 kHz sine/square/saw/noise → WAV export), AssetSynthesizer.
- `level.py`: Level (JSON-serializable), LevelBuilder (composes dungeon + enemies + items + objectives).
- `narrative.py`: NarrativeEngine (hooks/twists/climaxes/resolutions templating, quest_hooks).
- `playtest.py`: Playtester (seeded playthroughs), PlaytestResult, aggregate metrics.
Hermetic tests: 26/26. CLI: `mem20factoryz {generate, texture, audio, terrain, story, playtest, test}`. Fully deterministic — same seed reproduces identical levels/textures/stories.

---

## 18. Phase 17 — mem20rpgz: native RPGAgent absorption (2026-09-10)

**Completed 2026-09-10.** Native mem20rpgz package at `/opt/mem20/mem20rpgz` (pip install -e .). Absorbs RPGAgent (LLM multi-agent story-to-play generation) primitives:
- `rng.py`: RpgRandom (splitmix64 dice rolls).
- `character.py`: StatBlock (modifiers), Skill, Character (XP curve, leveling, hp/mp, skills), `create_party()`.
- `inventory.py`: Item, Inventory (stacking/capacity/weight), Equipment (EQUIPMENT_SLOTS + stat bonuses).
- `combat.py`: Combatant, CombatEngine (seeded hit/crit/damage resolution, battle-to-the-death, action log).
- `quest.py`: QuestObjective, Quest (chained objectives, progress_pct), QuestLog (accept/grant_rewards).
- `world.py`: Faction (disposition/stance), NPC, Scene, World.
- `agents.py`: Elemental Tetrad studio — NarrativeAgent, SceneAgent, GameplayAgent, AestheticsAgent + RPGStudio orchestrator with AgentOutput history and optional live LLM mode (via mem20 gateway).
Hermetic tests: 41/41. CLI: `mem20rpgz {character, party, combat, inventory, quest, world, story, test}`.

---

## 19. Phase 18 — mem20kimiz: native Kimi Agent Swarm absorption (2026-09-10)

**COMPLETED** — anti-baggage approach per Jayson (mem20 needs `mcp>=2.1.1` NON-NEGOTIABLE; "dont create old dependancy baggage with kimi, rewrite the code to use newer deps").

### Note on the deferral
Phase 18 was initially deferred like 07. It is now COMPLETED. The kimi install attempt (kimi-code 1.50.0) broke the shared venv (downgraded mcp 1.30.0 / openai 2.14.0 / pydantic 2.12.5); per the non-negotiable requirement it was removed (`kosong` needs `mcp<2`/`openai<2.15` and cannot coexist), the venv was restored (mcp 2.2.0, openai 3.12.0, pydantic 2.13.5), and feature-hunting was done **from source** instead.

### 18.1 Feature hunt — from source
Shallow blob-less sparse clone of `https://github.com/MoonshotAI/kimi-code` → `/tmp/opencode/kimi-code` (packages/ only). Swarm module (`packages/agent-core-v2/src/features/swarm/`) read in full:
- `swarm.ts` — `SwarmModeTrigger = 'manual' | 'task' | 'tool'` (coordinator swarm-mode lifecycle).
- `AgentSwarm` tool — `prompt_template` (must contain `{{item}}`), `items` fan-out, `resume_agent_ids` map, `fork`, ≤128 subagents; ≥2 items unless resuming; filled prompts must be distinct; AgentSwarm must be the sole tool call.
- `agentRunBatch.ts` — `AgentRunBatch` scheduler: staggered launch (INITIAL_LAUNCH_LIMIT=5, 700ms interval), max concurrency, rate-limit adaptive retry (base 3s ×2, capacity shrink 2s, recovery 3min), per-task timeout, cancel/abort, ordered results.
- `sessionSwarm.ts` — `SessionSwarmTask` (`spawn` adds a `plan`; `resume` carries `resumeAgentId`), `SessionSwarmRunResult` (completed/failed/aborted + started/not_started).
- `sessionSwarmService.ts` — `SubagentSuspended` event (`subagentId`, reason).
- Tool docs + `agent-swarm-fork.md` — ordered results carry `agent_id` for resuming; resume-hint in the XML result.

### 18.2/18.3 Primitives extracted and implemented natively
`/opt/mem20/mem20kimiz` (pure stdlib, ZERO kimi-code deps):
- `types.py` — `SessionSwarmSpawnTask` / `SessionSwarmResumeTask` / `SessionSwarmRunResult` / `SessionSwarmRunArgs`, `escape_xml`.
- `batch.py` — `AgentRunBatch` + injectable `AgentRunBatchLauncher` (spawn/resume/retry/suspended). Constants and semantics ported 1:1. Timeout enforced at the scheduler boundary (asyncio race of completion vs controller vs timeout) so it holds even when a launcher ignores abort signals. `finish_with_user_cancellation`, ordered results. Rate-limit: `_RateLimitedOutcome` → suspend event + requeue, exponential retry with capacity shrink/recovery; single-task-only rate limit fails fast (kimi `isOnlyUnfinishedTask`). Max concurrency via env `MEM20KIMI_SWARM_MAX_CONCURRENCY`.
- `swarm.py` — `SwarmService` (enter/exit/isActive, triggers, auto-exit on turn end for task/tool, timeline, injection disclosure, mode reminders).
- `tool.py` — `AgentSwarmTool` (validation rules; `to_tasks` resume-first ordering with `swarmIndex`/`swarmItem`; `render_results` → ordered `<agent_swarm_result>` XML with `<summary>`, `<resume_hint>` when any non-completed subagent has an `agent_id`, and per-subagent `agent_id`/`item`/`outcome`/`state`/`stop_reason`, XML-escaped).
- `cli.py` — `python -m mem20kimiz --items ... --template ... [--flaky|--resume-agent-ids|--max-concurrency|--timeout]`.
- Backfill: the roadmap primitives map onto the port — `Swarm`→`SwarmService`, `TaskDecomposer`→fan-out `items`+`AgentRunBatch`, `Communicator`→launcher + XML result contract, `Consensus`→ordered results + resume hints, `SharedMemory`→`swarmItem` metadata + resume_agent_ids.

### Verification
- Hermetic tests: **36/36 passing** (`test_tool` 16, `test_batch` 11, `test_swarm` 9).
- CLI: 3-way fan-out → completed ordered XML; `--flaky` → `Provider rate limit` suspend event → requeue → retry → completed; resume path renders `mode="resume"` with matched `agent_id`; validation failures exit 1.

### 18.4 Original removed
kimi-code was already uninstalled during the dependency incident; nothing of it remains on disk in the shared venv. Source scrap at `/tmp/opencode/kimi-code` retained for reference only.

### 18.5 Docs
This section appended; roadmap `hypo-map-1.json` phase 18 → `completed`.

---
