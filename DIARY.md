# DIARY.md — capabilities and how to use them (mem20 estate)

## mem20sensez — Phase 1 sense-organs (gap mapper / replanner / digital twin)

Built on the real UCG (mem20ucgz, port 8781), real mem20 memory store, and real
mem20langz StateGraph. CLI: `fs-sense`, server on 127.0.0.1:8784 (systemd user
unit, auto-start at boot).

- `fs-sense gap --goal '<human goal>'` — REAL token coverage over the live UCG:
  `matched` = capabilities whose id/name/provider/tags/inputs/outputs cover the
  goal's vocabulary, `missing_tokens` = the honest capability gap,
  `coverage_ratio` = covered/total tokens. No fabricated capability sets.
- `fs-sense replan --goal '...' [--phases a,b,c] [--journal]` — deterministic
  phase re-plan: every phase keeps identity/rank, matched caps are pinned as
  captured, missing tokens become explicit gap nodes (`needs-gap-fill`), order
  is monotone (ready phases + fewest gaps first, stable sort). `plan_id` is a
  sha256 of the plan; `--journal` commits a `phase.replan` node to braid.
- `fs-sense twin` — Personal Workflow Twin digest: reads the live Pickle
  self-model (topic `self_model`) and recent memory threads from the real mem20
  memory store; returns identity snapshot + active threads + recommendations.
- `fs-sense accelerate --action <declare|attest|admit|growth|progress|summary|revoke|simulate> --human 'id' [--goal '...']`
  — Human Capability Accelerator (RM-150): Ed25519 human trust bridge.
  `declare` issues a challenge nonce; `attest` verifies the human's Ed25519
  signature over it; `admit` auto-provisions a fresh credential on join (the
  human/device trust bridge: attest before admitting, provision on join);
  `growth` records a measurable delta against a skill metric; `progress`
  aggregates growth events; `summary` reports totals; `simulate` replays
  success/malformed/disconnect/overload/provider-loss/restart against the real
  runtime. Real crypto only (cryptography Ed25519 + secrets), data persisted in
  the mem20 store (`human_capability.json` + history).
- `fs-sense enroll --action <declare|attest|enroll|provision|validate|revoke|list|simulate> --device 'id'`
  — Device Enrollment Autopilot (RM-151): Ed25519 device trust bridge with a
  resumable state machine new→challenge→attested→enrolled→provisioned→validated.
  `declare` issues nonce; `attest` verifies key possession; `enroll` admits the
  attested device; `provision` auto-issues a credential; `validate` re-proves
  liveness by signing a fresh server nonce; `simulate` replays the six
  scenarios; persisted in `device_enrollment.json` + history.
- `fs-sense exec [--steps 'json'] [--initial 'json'] [--journal]` — Execution
  Digital Twin: builds a REAL mem20langz StateGraph from the step list
  (checkpointed via InMemorySaver), records pre/post state deltas per step
  (reversible), reports speculative branch candidates; `--journal` commits an
  `exec.twin` plan node to braid.
- `fs-sense descriptors` — print the five UCG capability cards
  (cap.sense-gap.v1, cap.sense-replan.v1, cap.sense-twin.v1,
  cap.sense-accel.v1, cap.sense-enroll.v1).
- `fs-sense serve --port 8784` — HTTP server: GET `/health`,
  GET `/.well-known/card`, POST `/gap` `{goal}`, POST `/replan`
  `{goal, phases?, journal?}`, POST `/twin` `{}`, POST `/exec`
  `{steps?, initial?, journal?}`.
- `fs-sense health` — health check against the running server (UCG count +
  braid availability).

Integration points:
- UCG: registered as cap.sense-gap.v1 / cap.sense-replan.v1 / cap.sense-twin.v1
  (all braid-journaled, prove() verified).
- Braid: gap/replan/exec can journal `phase.replan` / `exec.twin.replan` nodes
  (op `write:fact`, target `sense:<id>`); registration used op
  `write:capability`.
- A2A fleet (via mem20crewz A2AClient): `ucg` peer queries like
  `"who provides capability gap mapper"` resolve to cap.sense-gap.v1;
  `"who provides dynamic phase replanner"` → cap.sense-replan.v1; `"who
  provides digital twin"` → cap.rm-014 + cap.sense-twin.v1; `"who provides
  device enrollment autopilot"` → cap.sense-enroll.v1; `"who provides human
  capability accelerator"` → cap.sense-accel.v1.
- Honesty rule: all matching is exact-token over real registered capabilities;
  multi-word naturals ("capability gap mapping") need token-aligned wording.
- Server self-test: `/health` reports `{ok, capability, service,
  ucg_capabilities: N, braid: true}`.

Fixed this session (2026-09-23):
- sys.path shadowing: `braid_hook` no longer keeps `/opt/mem20` on sys.path
  after importing braid_bridge — it shadowed the venv editable mem20langz
  install (namespace `mem20langz` dir) and broke `from mem20langz import
  InMemorySaver`. The repo-root sys.path entry is now removed in a `finally`.
- `/twin` 500: `SenseService.twin` method was shadowed by the instance
  attribute `self.twin`; renamed attribute to `self.workflow_twin`.
- mktz braid journal repaired: `/opt/mem20/mem20mktz/.venv` lacked the compiled
  `braid_python` abi3 module; repo-root source dir shadowed as empty namespace
  package → `PyBraidEngine` AttributeError on journal. Fix (mirror verbatim):
  `/opt/mem20/mem20mktz/.venv/bin/pip install /opt/mem20/braid_python/target/wheels/braid_python-0.1.0-cp311-abi3-manylinux_2_34_x86_64.whl`.
  Verify: `BRAID_AVAILABLE True`, `journal('offer.published', ...)` → cid +
  `prove_cid(cid)=True`, estate bridge `prove(cid)=True`.

Other estate commands (unchanged):
- UCG server: `python -m mem20ucgz.api --port 8781 --db /opt/mem20/store/ucg/ucg.sqlite3`
- ZIMR demo: `cd /opt/mem20/mem20zimr && ./scripts/demo.sh`
- cv.infer server: `python -m mem20cviz.api --port 8783`
- mem20cviz demo: `cd /opt/mem20/mem20cviz && ./scripts/demo.sh`
- braid ledger: `python -c "import sys;sys.path.insert(0,'/opt/mem20');from braid_bridge import prove,read"`

## Persistence — all project servers via systemd (user units, auto-start at boot)

RULE: any server brought up in this project must be registered as a systemd user unit
so it survives reboots. Root has `Linger=yes`, so user units start at boot.
NOTE: systemctl --user needs `XDG_RUNTIME_DIR=/run/user/0` exported.

- UCG server (8781) — unit: `/root/.config/systemd/user/mem20ucgz.service` —
  access: `systemctl --user status mem20ucgz` / `systemctl --user restart mem20ucgz`
  — (WORKED) — enabled at boot, owns 127.0.0.1:8781, /health ok
- cv.infer server (8783) — unit: `/root/.config/systemd/user/mem20cviz.service` —
  access: `systemctl --user status mem20cviz` / `systemctl --user restart mem20cviz`
  — (WORKED) — enabled at boot, owns 127.0.0.1:8783, /health ok
- sense-organs server (8784) — unit: `/root/.config/systemd/user/mem20sensez.service` —
  access: `systemctl --user status mem20sensez` / `systemctl --user restart mem20sensez`
  — (WORKED) — enabled at boot, owns 127.0.0.1:8784, /health ok
- A2A resolve re-verified after systemd takeover (fleet queries for
  gap/replan/twin capabilities resolve to the sense caps) — (WORKED)

Adding a new server: write `/root/.config/systemd/user/<name>.service`
(Type=simple, ExecStart=full venv cmd, restart on-failure), then
`systemctl --user daemon-reload && systemctl --user enable --now <name>`,
then kill any orphan process holding the port.
- 2026-09-23 (session) — :8781 problem fix, estate-verbatim:
  - Root cause (verified, not guessed): mem20ucgz API package exists at
    /opt/mem20/mem20ucgz with serve() on :8781, but NO process was bound —
    server was never started. State  Recv-Q Send-Q Local Address:Port  Peer Address:PortProcess
LISTEN 0      5            0.0.0.0:4200       0.0.0.0:*    users:(("python3",pid=722,fd=3))
LISTEN 0      512        127.0.0.1:4096       0.0.0.0:*    users:(("opencode",pid=1119,fd=18))
LISTEN 0      2048       127.0.0.1:4100       0.0.0.0:*    users:(("python",pid=1120,fd=13))
LISTEN 0      5          127.0.0.1:4210       0.0.0.0:*    users:(("mem20agentz",pid=1121,fd=3))
LISTEN 0      2048       127.0.0.1:7747       0.0.0.0:*    users:(("python",pid=1126,fd=13))
LISTEN 0      5            0.0.0.0:8080       0.0.0.0:*    users:(("python",pid=79212,fd=4))
LISTEN 0      2048         0.0.0.0:8000       0.0.0.0:*    users:(("python",pid=723,fd=14))
LISTEN 0      5          127.0.0.1:8765       0.0.0.0:*    users:(("python",pid=729,fd=3))
LISTEN 0      4096       127.0.0.1:41577      0.0.0.0:*    users:(("containerd",pid=745,fd=11))
LISTEN 0      128          0.0.0.0:22         0.0.0.0:*    users:(("sshd",pid=783,fd=6))
LISTEN 0      5          127.0.0.1:8783       0.0.0.0:*    users:(("python",pid=738,fd=4))
LISTEN 0      5          127.0.0.1:8781       0.0.0.0:*    users:(("python",pid=737,fd=6))
LISTEN 0      5          127.0.0.1:8784       0.0.0.0:*    users:(("python",pid=110588,fd=3))
LISTEN 0      511        127.0.0.1:8221       0.0.0.0:*    users:(("MainThread",pid=1133,fd=25))
LISTEN 0      5            0.0.0.0:18779      0.0.0.0:*    users:(("python",pid=1131,fd=3))
LISTEN 0      5            0.0.0.0:18778      0.0.0.0:*    users:(("python",pid=1129,fd=4))
LISTEN 0      5            0.0.0.0:18785      0.0.0.0:*    users:(("python",pid=1129,fd=3))
LISTEN 0      128          0.0.0.0:3000       0.0.0.0:*    users:(("python",pid=1132,fd=6))
LISTEN 0      4096       127.0.0.1:20241      0.0.0.0:*    users:(("cloudflared",pid=6295,fd=11))
LISTEN 0      128          0.0.0.0:4000       0.0.0.0:*    users:(("python",pid=1128,fd=6))
LISTEN 0      128             [::]:22            [::]:*    users:(("sshd",pid=783,fd=7))
LISTEN 0      50                 *:1716             *:*    users:(("kdeconnectd",pid=66334,fd=20))
LISTEN 0      4096               *:11434            *:*    users:(("ollama",pid=725,fd=4))
LISTEN 0      511            [::1]:8221          [::]:*    users:(("MainThread",pid=1133,fd=24)) showed no 8781 owner; nothing invented.
  - Fix (estate's own documented boot, mirrored verbatim — DIARY tail:
    row "UCG server (8781): PYTHONPATH=src python -m mem20ucgz.api"):
    started mem20ucgz.api per its own README api.md serve(); :8781 now
    genuinely answers — curl /health -> {"ok": true}; /query returns the
    6 market descriptors with real ids.
  - Proved the flip gate honestly: no faked cids. Journal attempt via
    mem20mktz.braid_hook.journal(capability.upserted, cap.mkt-genome.v1, {..})
    FAILED with estate-runtime truth: braid_python has no PyBraidEngine
    on the mktz runtime (see failures.md). ucg_ok flips True ONLY because
    :8781 truly answers, never by fiat.

## 2026-09-29 — /sb scoreboard (build + use)

### Use it
```sh
scoreboard -enroll AGENT                          # put on the board at 0
scoreboard -add AGENT "reason"                    # +1
scoreboard -del AGENT "reason"                    # -1
scoreboard --dsq AGENT "reason"                   # disqualify
scoreboard -reward AGENT ["reason"]               # +3, reason optional
scoreboard -remove AGENT                          # off the board, history kept
scoreboard -display                               # ranked table
scoreboard -history [AGENT]                       # event log, newest first
scoreboard -serve                                 # the web board
```
  - Every flag also accepts two dashes (`--add`, `--del`, ...).
  - A reason is REQUIRED for -add/-del/--dsq and must be ONE quoted argument.
    Forgetting the quotes is refused with the corrected command to paste.
  - Ledger location: `SB_SCOREBOARD_DB`, default `/sb/data/scoreboard.db`.
  - Web board: http://127.0.0.1:8892/ on this box. From elsewhere:
    `ssh -L 8892:127.0.0.1:8892 jnet1` then open the same URL.

### Operate it
```sh
systemctl status scoreboard        # the read-only page, :8892, loopback only
systemctl restart scoreboard
tail -f /var/log/scoreboard.log
curl -s http://127.0.0.1:8892/api/health
curl -s http://127.0.0.1:8892/api/board
```

### Verify it
```sh
cd /sb/backend && /root/.venv/bin/python -m pytest /sb/tests -q      # 61 passed
cd /opt/mem20/mem20sitemapz && /root/.venv/bin/python -m pytest tests -q  # 43 passed
sitemap search "scoreboard"      # -> mem20scoreboardz at /sb
sitemap show mem20scoreboardz    # -> location OUTSIDE the monorepo
```

### Notes
  - The page CANNOT write. Only GET routes exist, so any write verb returns 405.
    Use the CLI for every change.
  - Scores may go negative; nothing clamps them.
  - Ranks are dense: equal scores share a rank and the next rank skips.
  - Nothing is ever deleted. To correct a mark, issue a -del with the reason.

## 2026-09-29 — mem20 CLIs on the default PATH (estate gap)

### The gap
  - mem20 subsystems install their console scripts into /root/.venv/bin.
  - /etc/profile.d/thestack-env.sh puts that dir on the PATH of interactive
    login shells, so `sitemap` works when typed at a prompt.
  - It does NOT reach a default-PATH context: systemd units, cron, scripts
    run via `sh -c`, `ssh host 'cmd'`. There the tool is installed but simply
    "command not found".
  - Reproduce:  env -i PATH=/root/.local/bin:/usr/local/bin:/usr/bin:/bin \
        sh -c 'command -v sitemap'   -> nothing

### Fix / re-apply after a venv rebuild
```sh
/root/.venv/bin/python /opt/mem20/tools/mem20path.py            # dry run
/root/.venv/bin/python /opt/mem20/tools/mem20path.py --apply    # link them
/root/.venv/bin/python /opt/mem20/tools/mem20path.py --verify   # exits non-zero if any is missing
systemctl status mem20-path-links.service    # runs --apply + --verify at boot
```

### Verify
```sh
env -i PATH=/root/.local/bin:/usr/local/bin:/usr/bin:/bin sh -c 'command -v sitemap'
cd /opt/mem20 && /root/.venv/bin/python -m pytest tests/test_mem20path.py -q   # 17
```

### Notes
  - Only mem20-OWNED distributions are linked. `chroma` (chromadb), pytest,
    uvicorn etc. are third-party and deliberately left off the default PATH.
  - `mem20-metrics` is excluded on purpose: it is a blocking HTTP server, not
    a command, and would never return.
  - mem20path never overwrites a real file it did not create; it only manages
    its own symlinks.
