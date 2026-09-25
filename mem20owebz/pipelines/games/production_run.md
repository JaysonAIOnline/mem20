# Forced Production Run — How to Use It

This drives a **Production Package** through the full idea→game factory.  
Jayson will **not** do this reliably without this tool. Install it, then follow the steps below.

---

## 1. Install the tool (once)

1. Open Jayson → **Admin → Functions** (or **Tools**)
2. Create a new tool / function
3. Open the file:
   ```
   tools/openwebui_tools/production_run_orchestrator_tool.py
   ```
4. Copy the **entire** file and paste it into the tool editor
5. Save and **enable** it
6. Also enable (if not already):  
   `qa_agents_tool`, `agent_loop_tight_tool`, `final_polish_team_tool`,  
   `rpg_orchestrator_tool`, `status_dashboard_tool`, `accessibility_tool`,  
   and the creative tools you need

Confirm the tool appears in the chat tool list.

---

## 2. Prepare your package

1. Copy `PRODUCTION_PACKAGE_TEMPLATE.md` to:
   ```
   projects/<your_game>/PRODUCTION_PACKAGE.md
   ```
2. Fill at least the **[HUMAN]** minimum (pitch, genre, **engine**, platforms, scope, pillars, vertical slice, sign-off)
3. Optional: zip that project folder if you want an “upload package” workflow — you can still **paste** key sections into chat

---

## 3. Start the run (exact prompt)

In a **new chat**, with tools enabled, paste:

```
Start a production run.

Project name: my_first_game
Genre: RPG
Platforms: Windows, Linux

Production package:
<paste your filled HUMAN sections + any AI expansions here
 OR write: see projects/my_first_game/PRODUCTION_PACKAGE.md>

Instructions:
- Call tool start_production_run now
- Use Production Run Orchestrator for the whole project
- Do not skip stages
- At every stage use Tight Agent Loop (PLAN → ACT → CHECK)
- Run QA before every advance
- Only call production_run_advance when QA is PASS or PASS_WITH_NOTES
- Ask me before changing any [HUMAN] decisions
```

Jayson should call **`start_production_run`** and return the stage list, starting at **Stage 0 PACKAGE_LOCK**.

---

## 4. What each tool call means

| You want… | Tool function | When |
|-----------|---------------|------|
| Begin factory | `start_production_run` | Once at the start |
| See where you are | `production_run_status` | Anytime |
| Move to next stage | `production_run_advance` | Only after QA PASS |
| Read full rules | `production_run_playbook` | If the model drifts |

**Advance parameters (required):**
- `from_stage_id` — stage you finished (0–6)
- `qa_verdict` — `PASS` or `PASS_WITH_NOTES` (or `FAIL` to stay put)
- `evidence` — one short sentence of what was checked

If verdict is `FAIL`, the tool **refuses** to advance.

---

## 5. Stage-by-stage (what you do as human)

### Stage 0 — PACKAGE_LOCK
- **Jayson:** Confirms slice + sign-off  
- **You:** Type `approved` or fix the package  
- **QA:** Human sign-off  
- **Then:** `production_run_advance` from 0 → 1  

### Stage 1 — DESIGN_SPINE
- **Jayson:** World/systems/quests/narrative for the **slice only** (orchestrator + storyline tools)  
- **You:** Reject scope creep  
- **QA:** `qa_inspect` on design/systems/narrative  
- **Then:** advance 1 → 2  

### Stage 2 — SPACES_UI_VR
- **Jayson:** Level / UI / VR specs via those pipelines  
- **You:** Read blockouts for soft-locks  
- **QA:** level + ui (+ VR if needed)  
- **Then:** advance 2 → 3  

### Stage 3 — ASSET_PRODUCTION
- **Jayson:** Generate into `_incoming`, assign IDs, manifest  
- **You:** Enforce folder rules from `asset_assembly.md`  
- **QA:** all **P0** assets validated  
- **Then:** advance 3 → 4  

### Stage 4 — ASSEMBLY
- **Jayson:** Integrate validated assets, slice scene plan  
- **You:** Build/run in engine until critical path works  
- **QA:** build boots; critical path completable  
- **Then:** advance 4 → 5  

### Stage 5 — FINAL_POLISH
- **Jayson:** `start_final_polish`, score sections, rework gaps  
- **You:** Agree scores are honest  
- **QA:** average ≥ 94%, zero Criticals, `qa_gate` ALLOW  
- **Then:** advance 5 → 6  

### Stage 6 — RELEASE_PACKAGE
- **Jayson:** Build notes, installer layout, `README_PLAYER.md`  
- **You:** Cold install + playtest using only the player README  
- **QA:** export checklist + your playtest  
- **Then:** advance 6 → 7 DONE  

---

## 6. If Jayson tries to skip ahead

Say:

```
Stop. Check production_run_status.
You are not allowed to leave the current stage without qa_inspect PASS
and production_run_advance. Resume current stage only.
```

Or:

```
Call production_run_playbook and follow hard_rules.
```

---

## 7. Optional: zip upload workflow

1. Zip `projects/<game>/` (package + design + manifests)  
2. Upload the zip into chat (if your Open WebUI allows) **or** paste package text  
3. Same start prompt as §3  
4. Tell Jayson: *“Treat this zip/folder as the only source of truth; all new files must follow asset_assembly layout.”*

The orchestrator does not magically unpack binaries into Unity for you—it **forces the sequence** and QA. Engine builds stay on your machine under supervision.

---

## 8. Done means

- Stage 7 reached via advances (not by claiming it)  
- Installable artifact path documented under `release/installer/`  
- Manifest lists shipped assets  
- You completed the cold playtest in `FIRST_GAME_WALKTHROUGH.md` Phase 8–9  

---

## 9. Quick copy-paste card

```
Tools on: Production Run Orchestrator, QA, Tight Loop, Final Polish, Status Dashboard.

1) start_production_run
2) work stage with PLAN→ACT→CHECK
3) qa_inspect
4) production_run_advance only on PASS
5) repeat until DONE
```

---

## 10. Optional extras (do not skip the spine)

| Extra | When |
|-------|------|
| save_load_settings | Design / tech |
| accessibility | Before polish (required if VR) |
| lint_manifest.py | Before ASSEMBLY |
| localization | If extra locales |
| store_listing | After polish, with release |
| status_dashboard | Anytime — snapshot JSON → `qa/STATUS.md` |
| resource_bridge | Publish installer to R2 (catalog now; service in 3.0) |
