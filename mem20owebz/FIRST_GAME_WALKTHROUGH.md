# First Game Walkthrough — Idea → Installable Game

Human-led journey with Jayson supervising AI work.  
Follow in order. Do not skip QA gates.

---

## Phase 0 — Setup (once)

1. Install dependencies (`DEPENDENCIES.md`)
2. `docker compose -f docker-compose.full.yml up -d`
3. Open WebUI: admin account, TTS → Kokoro, Connections → bridge
4. Paste tools from `tools/openwebui_tools/` (factory tools first: production run, tight loop, QA, polish)
5. Optional: add API keys in `.env` (`CREDITS.md`)
6. Optional extras: accessibility, store listing, status dashboard tools

**You are ready when:** chat works, bridge lists models, production run tool is enabled.


---

## Phase 1 — Production input (HUMAN)

1. Copy `PRODUCTION_PACKAGE_TEMPLATE.md` → `projects/my_first_game/PRODUCTION_PACKAGE.md`
2. Fill **minimum [HUMAN]**:
   - Pitch (1.1)
   - Genre (1.3)
   - Platforms (1.5)
   - Scope in/out (1.6)
   - Pillars (2.1)
   - Vertical slice definition (12.1–12.2)
   - Sign-off (18)
3. Ask Jayson: *“Expand all [AI] sections for this package; do not change [HUMAN] decisions.”*
4. Review expansions; correct anything wrong

**Gate:** You approve the package. No generation yet.

---

## Phase 2 — Start orchestration

**Detailed tool usage:** see [`pipelines/games/production_run.md`](pipelines/games/production_run.md) (install tool, exact prompt, stage-by-stage, advance rules).

### Short version
1. Enable `production_run_orchestrator_tool`
2. Paste the start prompt from that guide with your package
3. Allow only `production_run_advance` after QA PASS


Paste the AI execution brief from package §19, e.g.:

```
Load production package: projects/my_first_game/PRODUCTION_PACKAGE.md
Genre pipeline: <your genre>
Supervision: every handoff
Start Stage 1. Tight Agent Loop + QA every handoff.
```

Use:
- `rpg_orchestrator_tool` or genre pipeline in `pipelines/games/genre_pipelines.md`
- `agent_loop_tight_tool` for each chunk of work

**Gate:** First stage QA PASS (World / Track / Arena — whatever stage 1 is).

---

## Phase 3 — Design spine (AI under supervision)

Order depends on genre; typical RPG/Adventure:

| Step | Agent focus | You check |
|------|-------------|-----------|
| World / track | Regions, rules | Pillars still true? |
| Systems | Core loop numbers | Fun on paper? |
| Quests / races / missions | P0 list only | Slice-sized? |
| Narrative | Tone + key scenes | Matches theme? |

After each: `qa_inspect` → fix → `handoff`.

**Gate:** Design docs support the vertical slice only (resist scope creep).

---

## Phase 4 — Levels / UI / VR (if needed)

- Levels: follow `pipelines/games/text_to_level.md`
- UI: `text_image_to_ui.md`
- VR targets: `text_to_vr.md`

**You play-read** the blockout/wireframe docs as if you were implementing tomorrow.

**Gate:** Level/UI specs have no soft-locks and list only P0 assets.

---

## Phase 5 — Assets (controlled flood)

1. Create folder tree from `pipelines/games/asset_assembly.md`
2. Create empty `manifests/assets_master.csv`
3. Generate art/audio **into `_incoming` only**
4. For each batch:
   - Assign asset IDs
   - Manifest row
   - QA Art/3D or Audio
   - Move to canonical folder when validated
5. Use Text/Image→3D, Blender, screenshots, Kokoro/TTS tools as needed

**Human rule:** If you can’t find an asset in 10 seconds from the manifest, the structure is wrong—fix before generating more.

**Gate:** All **P0** assets `validated` (not merely incoming).

---

## Phase 6 — Assemble in engine

1. Create engine project under `projects/my_first_game/engine_project/`
2. Import **only validated** assets
3. Build the **vertical slice scene** (one playable path)
4. Wire input, win/lose, simple save if required
5. Update `scenes_index.json` + manifest status → `integrated`

**Gate:** Cold boot → complete critical path once on your machine.

---

## Phase 7 — Final polish team (94%+)

1. Tool: `final_polish_team_tool` → `start_final_polish`
2. Score each package section
3. Rework gaps (max rounds as configured)
4. `polish_round_summary` until average ≥ 94% and **0 Criticals**
5. `qa_gate` → ALLOW_DELIVERY

**Gate:** Fidelity target met. You agree the game matches *your* package, not a random AI detour.

---

## Phase 8 — Build & installable package

1. Follow `asset_assembly.md` Stages E–F
2. Build platform targets you checked in the package
3. Produce installer/portable package under `release/installer/`
4. Write `README_PLAYER.md` (install, controls, how to finish the slice)
5. QA Export checklist (`export_targets.md`)

**Gate (human playtest journey):**

### Your personal QA test journey
1. Copy build to a clean folder (or second machine if possible)
2. Install using only `README_PLAYER.md`
3. Start game with no debug menus
4. Complete critical path **without** looking at design docs
5. Note every confusion, bug, or missing asset
6. If anything is Critical → back to Phase 7
7. If completable and acceptable → sign release notes

---

## Phase 9 — Done (Idea → Game)

You have finished when:

- [ ] Installable artifact exists
- [ ] Manifest lists every shipped asset
- [ ] Final polish passed
- [ ] You completed the cold playtest journey
- [ ] Known issues documented honestly

Celebrate. Then either expand content with new package version **or** start the next game with a tighter slice.

---

## Quick reference — tools by phase

| Phase | Tools / docs |
|-------|----------------|
| 1 | PRODUCTION_PACKAGE_TEMPLATE |
| 2–3 | rpg_orchestrator, genre_pipelines, tight loop, QA |
| 4 | text_to_level, text_image_to_ui, text_to_vr |
| 5 | text_image_to_3d, screenshots, audio tools, asset_assembly |
| 6 | Unity/Blender tools, engine |
| 7 | final_polish_team, qa_agents |
| 8 | export_targets, asset_assembly Stage F |
| 9 | Human playtest journey (this doc) |

---

## Advice for the first game only

- Prefer **tiny** vertical slice over “whole open world”
- One region, one loop, few characters
- Generate fewer assets; polish harder
- The production package is the boss—not the model’s improvisation
