# project


## 2026-09-05T01:08:01.830800+00:00  (pri=normal, tags=['altimator', 'glb', 'service-bay', 'car'])
Altimator Service Bay v2 app lives at /home/jayson/altimanator/app. Entry: src/main.tsx mounts TanStack Router SPA. Dev server on :7391 only (never port 8080 — that's mem20 MCP). Real Altima GLB parts: 123+ per-part GLBs in app/public/models/altima-2000/{body,chassis,engine-ka24de,engine-vq30de,fasteners,interior}. v2 car is procedurally drawn in src/components/garage/car.tsx which the user calls 'the ugly grok one'. User chose: load the real GLB parts per-part, interactive (removable/explosable), photoreal. Legacy app used single merged altima_2000.glb (42MB).


## 2026-09-05T02:54:54.860070+00:00  (pri=normal, tags=['altimanator', 'glb', 'checkpoint', 'blocked'])
Altimator Service Bay v2 session checkpoint (2026-09-05): Task was to load real GLB parts per-part into the 3D bay. Key findings: dev server on :7391; GLB files live at public/models/altima-2000/{body,chassis,interior}/{partId}.glb (filenames = hyphenated part ids) but assets.ts BASE = "/assets/altima-2000" (WRONG PATH) and loads disabled behind localStorage "twin-glb"==="1". engine-ka24de/engine-vq30de/fasteners folders are EMPTY (0 files); sway-bar.glb, wheel-rl.glb, taillight-l.glb are corrupt. Parts are normalized+origin-centered: NO placement manifest exists anywhere. User overrode my concern that parts are unusable ("i saw it built already it looked fine") — vertex counts are NOT a valid quality proxy; door-fl/rocker-l render as real shapes. User then said "ok stop" before further work. Unfinished: manifest.json generation, placement calibration, fixing assets.ts path, wiring GlbPart/InstancePlacedPart into scene.


## 2026-09-05T11:55:46.692695+00:00  (pri=normal, tags=['altimanator', 'verification', 'rule', 'jayson'])
Rule (from Jayson): ALWAYS recheck the live/actual state during every new scan before reporting anything as broken or wrong. Never reuse stale session-checkpoint findings. Prior failure: repeated stale notes claiming assets.ts BASE path was wrong (/assets/altima-2000) for ~21h when it was already fixed to /models/altima-2000 and pointed correctly to real GLBs at public/models/altima-2000/{folder}/{id}.glb. Verify current files/paths/code before reporting.


## 2026-09-05T16:30:18.073651+00:00  (pri=normal, tags=['AGS-OS', 'design-review', 'zip', 'gemini'])
Reviewed user's AGS-OS blueprint zip (/home/jayson/Downloads/autonomous_studio_blueprint.zip). It is an architectural design doc for an autonomous game studio OS (300 Hermes workers, Box A creation / Box B adversarial validation, SQLite ToT substrate, Quest 3/Unity target). User explicitly said DON'T BUILD. Wrote 00_GEMINI_DESIGN_REVIEW.md note and zipped it back in. Key findings in review: (1) schema mismatch — 05_hermes_router.py queries design_nodes table which 04 kernel never creates; (2) tot_core_ledger is a work-log DAG not real Tree-of-Thought (no eval/prune); (3) apply_adversarial_validation writes scores but nothing gates/merges on them; recommendations: WAL+busy_timeout, start 8-12 workers not 300, add epistemic_status per node, frame-time budget constraint, implement postmortem→prompt-patch loop, define deploy+rollback, sanitize role_id prompt interpolation.
