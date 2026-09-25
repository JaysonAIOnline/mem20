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
