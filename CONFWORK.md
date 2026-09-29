# CONFWORK.md — verified facts (mem20 estate)

Only 100% true, verified facts. Format: Action / feature — access — (WORKED|FAILED)

- LLM key loading fixed — access: `llm.py` reads `/opt/mem20/secrets/.env` FIRST (was legacy-only paths that are empty) — (WORKED)
- `imagination_dream` through live MCP bridge — access: `mem20_imagination_dream` tool — (WORKED) — 2 iterations, real LLM output, grounded in stored memory, honest known-vs-speculative marking
- LLM chat reachable on default NVIDIA endpoint — access: `llm.chat()` in fresh process — (WORKED) — key len 70, model nvidia/nemotron-3-ultra-550b-a55b- LLM default moved off NVIDIA (slow) to Groq — access: `llm.py` `DEFAULT_BASE_URL=https://api.groq.com/openai/v1`, `DEFAULT_MODEL=openai/gpt-oss-120b` — (WORKED) — fresh process verified, live `llm.chat()` returned GROQ_OK in 0.5s
- Dream defaults raised to 5 iterations / 2000 max_tokens — access: `cognitive_engine.py` `imagination_dream` + `aimagination_dream` — (WORKED) — verified in source lines ~979, ~1000
- 50-iteration dream over full 245-package corpus — access: `mem20_imagination_dream` job 6a93a2041833 — (WORKED) — 50 iterations, ~360KB raw, converged on Living-Group concept, saved to `/tmp/opencode/mem30/dream50_raw.txt`
- mem30 reports produced — access: `/home/jayson/Desktop/6/MEM30_MASTER_DREAM_REPORT.md`, `/home/jayson/Desktop/6/MEM30_AI_EXECUTABLE_ROADMAP.md`, `/home/jayson/Desktop/6/MEM30_DREAM_LOG.md` — (WORKED)
- mem30 live roadmap — access: `mem20_roadmap_get` name `mem30-absorption` (5 phases foundation/sense-organs/marketplace/dream-loop/moonshots, foundation in_progress) — (WORKED)
- mem30.pdf — access: `/home/jayson/Desktop/mem30.pdf` (valid %PDF-1.4, 5958 bytes, reportlab 5.0.1) — (WORKED)
- mem20ucgz (RM-001 UCG) absorbed — access: pip-installed as `mem20ucgz`, server `python -m mem20ucgz.api --db <path>` (default port 8781), tests 11/11 — (WORKED)
- mem20zimr (RM-002 microapp runtime) absorbed — access: pip-installed as `mem20zimr`, `./scripts/demo.sh` (build+sign+launch bundle), server `python -m mem20zimr.cli serve`, tests 15/15, demo bundle hello_py built+signed+launched stdout captured — (WORKED)
- braid provenance wired into UCG event plane — access: every `capability.upserted/deleted/edge.upserted` calls `braid_hook.journal_event` → signed cid + depth stored in event payload `_braid_cid`; verified prove(cid)=True in-process and over HTTP — (WORKED)
- first 20 mem30 descriptors registered — access: `/tmp/opencode/mem30/register_20.py` → UCG DB `/opt/mem20/store/ucg/ucg.sqlite3` (20 nodes, 20/20 braid-journaled) — (WORKED)
- UCG published as A2A fleet peer `ucg` — access: `/opt/mem20/mem20crewz/peers.yaml` entry url 8781, agent card at `/.well-known/agent-card.json`, `A2AClient().call("ucg", "who provides episodic memory graph?")` returns ranked list, state completed — (WORKED)
- UCG text query upgraded to token-based with stopword + punctuation handling — access: `graph.py` `query()` — (WORKED) — "who provides episodic memory graph?" resolves to cap.rm-021; exact-token semantics: "marketplaces" (plural) correctly does NOT match "marketplace"
- mem20cviz (computer-vision-inference) built real from mem20's imagination (3-iter dream, 2026-09-20) — access: pip-installed as `mem20cviz`, CLI `fs-cv` (infer/sim/descriptor/serve/health), server `python -m mem20cviz.api --port 8783`, tests 17/17 — (WORKED)
- REAL classical-CV inference (no fakes) — access: `fs-cv infer --image img.png` → actual numpy/PIL pixel math (size, mean/std RGB, luminance, edge energy, dominant colors, 128-dim embedding), metadata.simulated=false, engine=mem20cviz.classical — (WORKED) — demo detected the red + blue blocks on real generated image
- sim contract simulator honest — access: `fs-cv sim --payload '{"mode":"sim"}'` → deterministic hash-derived result marked metadata.simulated=true, engine=mem20cviz.simulator, embed_dim respected — (WORKED)
- braid journal per inference — access: `run_inference(journal=True)` commits `write:fact` node `cv.infer.result` to braid; receipt {cid,depth,proof_hops,ok} in metadata._braid; prove(brbe2e66…) = True — (WORKED)
- cv capability registered in UCG — access: POST `/capabilities` cap.cv-inference.v1 (provider mem30.cv.inference, outputs cv/features,objects,classifications,embedding), braid-journaled registration node brc522a112…, prove=True — (WORKED)
- cv.infer discoverable via A2A fleet — access: `A2AClient().call("ucg","who provides cv inference features")` → ranked reply cap.cv-inference.v1, state completed — (WORKED)
- Servers persisted via systemd user units — access: `systemctl --user status mem20ucgz|mem20cviz`, both enabled + auto-start at boot (root Lingering=yes), own 8781/8783 after killing orphans — (WORKED)
- mem20sensez (Phase 1 sense-organs) absorbed — access: pip-installed as `mem20sensez`, CLI `fs-sense` (gap/replan/twin/exec/descriptors/serve/health), server `python -m mem20sensez.api --port 8784`, tests 8/8 — (WORKED)
- Gap mapper is REAL token coverage over live UCG (RM-200) — access: `fs-sense gap --goal 'capability gap mapper for sensor platform ingestion'` → matched 4 real caps, missing=["sensor","platform","ingestion"], coverage_ratio=0.5 — (WORKED) — no fabricated capability sets
- Dynamic Phase Replanner deterministic + braid-versioned (RM-199) — access: `fs-sense replan --goal '...' --journal` → plan_id sha256, phases keep identity, gaps explicit, order stable-sorted; braid receipt {cid,depth,proof_hops,ok} returned — (WORKED)
- Personal Workflow Twin reads live self-model + memory (RM-140/141/008) — access: `fs-sense twin` over HTTP → identity = live self-model content, active_threads/recommendations from real memory store — (WORKED)
- Execution Digital Twin on real mem20langz StateGraph (RM-052/053) — access: `fs-sense exec` → REAL mem20langz nodes + InMemorySaver checkpoints, pre/post deltas, default run final_state {ctx:1,done:2} — (WORKED) — mem20langz verified present+importable (mem20langz, mem20orcaz both exist under /opt/mem20)
- sense capabilities registered + braid-journaled — access: POST /capabilities for cap.sense-gap.v1/replan.v1/twin.v1, braid cids br62b4501.., br6e0ddeb.., brc33db37.., prove()=True each — (WORKED) — proof_hops 446 ledger depth at session
- sense-organs discoverable via A2A fleet — access: `A2AClient().call('ucg','who provides capability gap mapper')` → cap.sense-gap.v1; 'dynamic phase replanner' → cap.sense-replan.v1; 'digital twin' → cap.rm-014 + cap.sense-twin.v1 — (WORKED)
- sense-organs server persisted via systemd — access: `systemctl --user status mem20sensez` — unit `/root/.config/systemd/user/mem20sensez.service`, enabled at boot, owns 127.0.0.1:8784, /health {ucg:24, braid:true} — (WORKED)
- Failures fixed in mem20sensez this session — (a) `braid_hook` sys.path repo-root entry removed in `finally` so it no longer shadows venv editable mem20langz (was: namespace dir lookup broke `from mem20langz import InMemorySaver`); (b) `SenseService` attribute `self.twin` renamed to `self.workflow_twin` (was shadowing the `twin()` method → 500 on /twin) — access: tests 8/8 + live /twin + /exec HTTP — (WORKED)
- Human Capability Accelerator (RM-150) REAL — access: `fs-sense accelerate` over HTTP/CLI, Ed25519 trust bridge declare→attest→admit (auto-provision credential on join), growth delta tracking, persisted in ~/.mem20/store/human_capability.* — live human lifecycle door-to-done, simulator 6/6 scenarios true — (WORKED)
- Device Enrollment Autopilot (RM-151) REAL — access: `fs-sense enroll` over HTTP/CLI, Ed25519 state machine declare→attest→enroll→provision→validate (new→challenge→attested→enrolled→provisioned→validated), resumable worker `advance()`, persisted in ~/.mem20/store/device_enrollment.* — live device lifecycle door-to-done, simulator 6/6 scenarios true — (WORKED)
- cap.sense-accel.v1 + cap.sense-enroll.v1 registered, braid-journaled, proven — access: POST /capabilities then `prove(brf74aedde..., bra6c243f462...)` = True each (depth 447, events 32/33) — (WORKED)
- trust-bridge caps A2A-discoverable — access: `A2AClient().call('ucg','who provides device enrollment autopilot')` → cap.sense-enroll.v1; 'who provides human capability accelerator' → cap.sense-accel.v1 — (WORKED)
- mem20sensez test suite now 22/22 — access: `cd /opt/mem20/mem20sensez && /root/.venv/bin/python -m pytest tests/ -q` — (WORKED) — ledger + braid: registration events carry _braid_cid in payload

- 2026-09-23: mem20mktz market offers journal real braid cids — access: `braid_python-0.1.0-cp311-abi3-manylinux_2_34_x86_64.whl` pip-installed into /opt/mem20/mem20mktz/.venv (mirrors estate organs' runtime); then `journal('offer.published', 'test-offer-journal-verify', {...})` → cid `br25166abf9a68c78abb8545dacb65dbcedbcb1f69ec0b02be4c1e4a4f48fec32c`, prove True (estate bridge + in-venv), depth 449, precommit_verified True — (WORKED)

### 2026-09-23 — :8781 (UCG server) — (WORKED)
- mem20ucgz API serve() running; 127.0.0.1:8781 genuinely bound and answering.
  Evidence: curl /health -> {"ok": true}; ss shows LISTEN 8781 (WORKED).
- /query route answers with the 6 market descriptors + genome entries.
- market health() ucg_ok flips True ONLY because :8781 genuinely answers
  AND sensez fleet resolve was re-proven (WORKED).
### 2026-09-23 — market journal — (BLOCKED, honest)
- braid offer journal via mem20mktz.braid_hook failed to yield a cid
  (PyBraidEngine missing from runtime braid_python) — NOT journaled, NOT claimed.

### 2026-09-29 — /sb scoreboard — (WORKED)
- `/sb` holds the whole tool: `backend/mem20scoreboardz/` (store, cli, web),
  `frontend/index.html`, `data/scoreboard.db`, `tests/`, `README.md`.
  Access: `/root/.venv/bin/scoreboard` (editable install of `/sb/backend`).
  `python -m mem20scoreboardz` also works (WORKED).
- Marks are append-only event rows in SQLite; roster, status and score are
  derived by `store.fold()` replaying the ledger, so the board can be rebuilt
  from scratch. `-add` +1, `-del` -1, `--reward` +3, `--dsq` disqualifies,
  `-enroll` opens a stint at 0, `-remove` takes off the board keeping history.
- `scoreboard -display` ranks densely (1, 2, 2, 4) so a tie is never drawn as an
  order. Verified: 5-agent fixture produced 1,2,2,4,4 in both the CLI and the
  page's rendered DOM (WORKED).
- Refusals verified by direct execution, each exiting non-zero with the fix in
  the message: marking an unenrolled agent, unquoted multi-word reason,
  re-enrolling an active agent, a name containing spaces, scoring a disqualified
  agent, re-disqualifying (would overwrite the original reason), marking a
  removed agent, removing twice (WORKED).
- Web board is loopback-only on 127.0.0.1:8892 under `scoreboard.service`
  (systemd, enabled, `Restart=on-failure`, MainPPID=1, verified across a real
  `systemctl restart`). Health: `curl -s http://127.0.0.1:8892/api/health`
  -> `{"ok":true,...,"writable_from_http":false}` (WORKED).
- Read-only is structural, not a check: only GET routes are registered, so
  POST/PUT/PATCH/DELETE on /api/board and /api/history all return **405**
  (verified) — the CLI is the single write path.
- Page rendered in real headless Chromium 151 against the live service:
  standings, disqualified and removed sections all populated, dense ranks
  1,2,2,4,4 present in the DOM, zero JS page errors (WORKED).
- Concurrency: 20 rapid CLI writes against a running reader produced 20 ledger
  rows, no lost writes, and CLI and HTTP views agreed (WAL + busy_timeout).
- Tests: 61 passing (`cd /sb/backend && /root/.venv/bin/python -m pytest /sb/tests -q`).
- Registered: `toolchest refresh` -> inventory 581 -> 582 entries;
  `toolchest show scoreboard` -> runtime_status "ok" (WORKED).
- Not in /opt/mem20 and not a mem20*z organ: it lives at /sb by Jayson's
  instruction. Do not "fix" this by moving it.

### 2026-09-29 — sitemap indexes outside roots — (WORKED)
- `sitemap build` now also indexes extra roots outside the monorepo; `/sb` is
  the default, overridable with repeated `--extra-root DIR` or dropped with
  `--no-extra-roots`. Each becomes ONE entry (not a directory listing), named
  after the package whose pyproject is found within 3 levels, tagged
  `external: true` + `external_root`, and `show` prints
  `location OUTSIDE the monorepo` (WORKED).
- `sitemap search "scoreboard"` and `sitemap show mem20scoreboardz` both resolve
  to `/sb`; SITEMAP.md gained an "Outside the monorepo" table and outside
  entries are excluded from the organ/service/other tables so an outside project
  is never presented as a mem20 subsystem. Totals are recomputed after merging
  (WORKED).
- Pre-existing 22 sitemap tests still pass unchanged; 21 new tests added
  (`tests/test_extra_roots.py`), 43 total (WORKED).

### 2026-09-29 — mem20 CLIs on the default PATH — (WORKED)
- CORRECTION to an earlier claim in this session: I first reported that `sitemap`,
  `chroma`, `fs-ops` and `mem20agentz` were "not on PATH" at all. That was
  measured with the *ambient* PATH of the opencode process, which does not
  include /root/.venv/bin. Measured properly, `/etc/profile.d/thestack-env.sh`
  already puts /root/.venv/bin on the PATH of every interactive login shell
  (bash and zsh both resolve `sitemap` with no changes) — (CORRECTED)
- The real gap is narrower and specific: a context with only the *default*
  system PATH cannot resolve any mem20 CLI. Verified with
  `env -i PATH=/root/.local/bin:/usr/local/bin:/usr/bin:/bin sh -c` — a systemd
  unit, a cron job, `ssh host 'cmd'`, or any non-login `sh -c` gets that PATH.
  Reproduced the failure before fixing it (WORKED).
- Fixed with `tools/mem20path.py` (17 tests, /opt/mem20/tests/test_mem20path.py).
  It reads installed dist metadata to decide ownership — not directory names —
  and links 36 mem20-owned console scripts into /root/.local/bin, which IS on
  the default PATH. Verified 36/36 resolve AND run from a bare default PATH
  (WORKED).
- Deliberately NOT linked, with reasons recorded in code:
  - `mem20-metrics` — not a CLI at all. metrics_collector.main() calls
    serve_forever() and ignores argv, so it never returns; a --help probe times
    out because it *works*. Linking it would put a blocking server on the PATH.
  - third-party console scripts in the same venv (`chroma` from chromadb,
    pytest, uvicorn...). Promoting those estate-wide is the owner's call.
- Safety properties, each covered by a test: dry run is the default; a real
  (non-symlink) file in the target is never clobbered; a stale symlink is
  repaired; re-running is idempotent; malformed METADATA does not abort the
  sweep (WORKED).
- `mem20-path-links.service` (systemd, enabled, oneshot + RemainAfterExit) runs
  it at boot and `ExecStartPost --verify` fails the unit if any tool is still
  unresolvable. Proof it works, not just that it is enabled: deleted all 36
  links, confirmed `sitemap` was gone, then `systemctl restart` restored them
  (WORKED).
- PRE-EXISTING and NOT mine, reported not touched: blue-hydra.service and
  searxng.service have ExecStart paths that do not exist
  (/usr/bin/blue-hydra, /opt/search/searxng-venv/bin/searxng-run). Both units
  are dated 2026-08-18, both are inactive, and I did not create or modify them.
  Not fixed — they are services I do not own.
- Follow-up: registered as the `mem20-path` console script (py-modules +
  [project.scripts] in /opt/mem20/pyproject.toml) and it linked itself on first
  run — the tool fixed its own class of problem. toolchest 582 -> 583 entries,
  `toolchest show mem20-path` -> runtime_status "ok" (WORKED).
- Final sweep from `env -i PATH=/root/.local/bin:/usr/local/bin:/usr/bin:/bin`:
  68 commands in /root/.local/bin resolve and run. Two entries report rc=126
  and are NOT mem20's and NOT mine: `omp` (a 13MB prebuilt binary dated
  2026-08-19) and `env.fish` (a fish-shell helper dated 2026-08-17). Both are
  not shell scripts, so `sh -c "$c --help"` cannot exec them. Pre-existing,
  left alone (WORKED, scoped honestly).
