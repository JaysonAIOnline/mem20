# TODO.md — mem30 project (workspace /home/jayson/Desktop/6)

## Phase 0 — Foundation (DONE, verified 2026-09-20)
- [x] UCG server (mem20ucgz) on 8781 — tests 11/11, 20 descriptors braid-journaled
- [x] ZIMR (mem20zimr) runtime, demo hello_py build+sign+launch — tests 15/15
- [x] Braid journaling wired into UCG event plane; prove(cid) verified
- [x] UCG published as A2A fleet peer `ucg`; ranked text query works
- [x] CV-inference gap closed: mem20cviz built REAL (classical CV math, honest sim mode), cap.cv-inference.v1 registered + A2A-discoverable — tests 17/17
- [x] Servers persisted via systemd user units (mem20ucgz@8781, mem20cviz@8783), auto-start at boot

## Next — Phase 1 sense-organs (roadmap: mem30-absorption, phase "sense-organs")
- [x] Personal Workflow Twin (Pickle self-model + memory + RM-140/141/008) — mem20sensez workflow_twin, live /twin over real memory store, verified 2026-09-23
- [x] Execution Digital Twin (RM-052 reversible + RM-053 speculative via mem20langz) — mem20sensez exec_twin on real mem20langz StateGraph + InMemorySaver, pre/post deltas, verified 2026-09-23
- [x] Capability Gap Mapper (RM-200) on UCG — mem20sensez gapper, real token coverage over live UCG, verified 2026-09-23
- [x] Dynamic Phase Replanner (RM-199) on gap events — mem20sensez replanner, deterministic plan_id + braid-journaled phase.replan, verified 2026-09-23
- [x] Human Capability Accelerator (RM-150) — mem20sensez accelerator: Ed25519 human trust bridge (declare→attest→admit, auto-provision credential), measurable growth tracking + simulator, verified 2026-09-23
- [x] Device Enrollment Autopilot (RM-151) — mem20sensez enroller: Ed25519 device trust bridge (declare→attest→enroll→provision→validate + revoke), simulator, verified 2026-09-23
- Exit: goal query → missing-capability list + replanned phase graph, braid-reproducible — DONE for gap+replan chain (fs-sense gap/replan with --journal, A2A-discoverable, tests 8/8)
- sense capabilities registered + braid-journaled in UCG (gap/replan/twin/accel/enroll), server on 8784 persisted via systemd (mem20sensez.service), endpoint + A2A fleet queries verified — tests now 22/22

## Standing rules
- Any new server → systemd user unit FIRST (see /opt/mem20/DIARY.md → Persistence)
- Truth logs: CONFWORK.md (verified only), failures.md (every failure), DIARY.md (every command)
- No fakes, no stubs masquerading as real; honest sim markers (simulated:true)
- 2026-09-23: [x] :8781 UCG server genuinely up (mem20ucgz.api serve, own documented
  boot, curl /health {"ok": true}) — the 8781 blocker, estate-fixed.
- 2026-09-23: [x] market offers journaled as real braid cids — FIXED. Root cause:
  mktz venv lacked the compiled braid_python abi3 module; repo-root's source dir
  (/opt/mem20/braid_python, no __init__.py) shadowed as empty namespace module →
  no PyBraidEngine. Fix: pip-installed the estate's abi3 wheel
  (braid_python-0.1.0-cp311-abi3...) into /opt/mem20/mem20mktz/.venv.
  Verified: journal('offer.published',...) → cid br25166abf..., prove=True,
  depth 449, readable via estate bridge.
