# GAME PRODUCTION PACKAGE — INPUT TEMPLATE

> **Purpose:** Fill this file (or a copy) and feed it to Jayson.  
> The system will decompose it into pipelines, agent handoffs, asset jobs, QA gates, and export targets.  
> Sections marked **[HUMAN]** require creator decisions.  
> Sections marked **[AI]** can be drafted or expanded by any capable model, then supervised.

**How to use**
1. Copy this file → `projects/<game_name>/PRODUCTION_PACKAGE.md`
2. Fill **[HUMAN]** sections first (minimum viable intent)
3. Ask Jayson (or any AI) to expand **[AI]** sections
4. Run `start_rpg_project` / genre pipeline with this package as context
5. Every stage ends with QA gate before handoff

---

# 0. DOCUMENT CONTROL

| Field | Value |
|-------|--------|
| Package version | 1.0 |
| Game working title | |
| Codename | |
| Date started | |
| Last updated | |
| Owner (human) | |
| Supervision mode | human-in-the-loop / autonomous-with-QA-gates |
| Target vertical slice date | |
| Target content-complete date | |

---

# 1. HIGH-LEVEL INTENT — [HUMAN]

## 1.1 One-sentence pitch
> 

## 1.2 Player fantasy
What does it *feel* like to play?
> 

## 1.3 Genre & subgenre
Primary: (Racing / FPS / TPS / Adventure / Open World / RPG / Hybrid: ___)  
Secondary:
> 

## 1.4 Perspective & camera
- [ ] 1st person
- [ ] 3rd person
- [ ] Isometric / top-down
- [ ] Fixed camera
- [ ] Hybrid: ___

## 1.5 Platforms (export targets)
Check all that apply:
- [ ] Windows
- [ ] Linux
- [ ] Android
- [ ] Meta Quest 2
- [ ] Meta Quest 3
- [ ] PS4 VR
- [ ] PS5 VR (PSVR2)
- [ ] PS3 (legacy/constraints only)
- [ ] Other: ___

## 1.6 Primary engine — [HUMAN] **REQUIRED**
Must match §11.1. Production Run will not advance past ASSEMBLY without this.

- [ ] Godot 4.x
- [ ] Unity
- [ ] Unreal Engine
- [ ] Custom / other: ________

**Editor version:** 
> 

## 1.7 Scope guardrails — [HUMAN]

Must ship in vertical slice:
> 

Explicitly out of scope for v1:
> 

Hard constraints (time, team size, engine, budget, rating):
> 

---

# 2. PILLARS & TONE — [HUMAN + AI]

## 2.1 Design pillars (3–5) — [HUMAN]
1. 
2. 
3. 
4. 
5. 

## 2.2 Tone & rating — [HUMAN]
Tone keywords:  
Content rating target (E / T / M / etc.):  
Violence / language / horror limits:
> 

## 2.3 References (games, films, art) — [HUMAN]
| Reference | What to steal | What to avoid |
|-----------|---------------|---------------|
|  |  |  |
|  |  |  |

## 2.4 Pillar tests — [AI]
For each pillar, one playable test that proves it is present in the vertical slice.
> 

---

# 3. STORY & NARRATIVE — [AI expandable, HUMAN approves]

## 3.1 Logline
> 

## 3.2 Theme
> 

## 3.3 Story structure
Format: (3-act / 5-act / episodic / open-ended)  
Synopsis:
> 

## 3.4 Main quest outline
| Act/Chapter | Goal | Obstacle | Twist/Payoff |
|-------------|------|----------|--------------|
|  |  |  |  |

## 3.5 Side content policy
How much side content vs main path? Mandatory vs optional?
> 

## 3.6 Codex / lore delivery method
Environmental / items / NPCs / collectibles / none
> 

**Pipeline link:** Storyline Maker tool + NarrativeWriter agent + QA Narrative

---

# 4. CHARACTERS — [AI expandable, HUMAN approves]

## 4.1 Player character(s)
| ID | Name | Role | Fantasy | Arc | Abilities | Visual notes |
|----|------|------|---------|-----|-----------|--------------|
| PC1 |  |  |  |  |  |  |

## 4.2 Major NPCs
| ID | Name | Role | Want | Relationship to PC | Fate |
|----|------|------|------|--------------------|------|
|  |  |  |  |  |  |

## 4.3 Enemies / factions
| ID | Name | Function in combat/story | Hierarchy |
|----|------|--------------------------|-----------|
|  |  |  |  |

## 4.4 Character bible rules — [AI]
Voice, vocabulary limits, visual silhouette rules:
> 

**Pipeline link:** NarrativeWriter + ArtDirector + QA Narrative / Art

---

# 5. WORLD — [AI expandable]

## 5.1 Setting summary
> 

## 5.2 Regions / biomes / tracks / maps
| ID | Name | Purpose | Size intent | Unlock condition | Activities |
|----|------|---------|-------------|------------------|------------|
| R1 |  |  |  |  |  |

## 5.3 Traversal
Walk / climb / vehicle / flight / fast travel rules:
> 

## 5.4 Day/night, weather, living world (if any)
> 

**Pipeline link:** WorldBuilder agent + genre pipeline (Open World / Adventure / Racing tracks)

---

# 6. CORE LOOP & SYSTEMS — [AI expandable, HUMAN approves numbers]

## 6.1 Core loop (30–120 seconds)
Describe the repeated verb cycle:
> 

## 6.2 Combat / challenge model
(If non-combat: puzzles, racing lines, social, etc.)
- Time-to-kill targets:
- Player power curve:
- Failure / death penalty:
> 

## 6.3 Progression
XP / unlocks / gear / skill tree / prestige:
| System | What upgrades | Soft cap | Soft currency | Premium currency |
|--------|---------------|----------|---------------|------------------|
|  |  |  |  |  |

## 6.4 Economy
Sources sinks balance notes:
> 

## 6.5 Inventory / loadout / crafting (if any)
> 

## 6.6 AI / opponent rules
(Racing AI, enemy archetypes, companion AI)
> 

**Pipeline link:** SystemsDesigner + QuestDesigner + QA Systems

---

# 7. QUESTS / MISSIONS / ACTIVITIES — [AI]

## 7.1 Mission template
| Field | Description |
|-------|-------------|
| ID | |
| Name | |
| Type | main / side / daily / challenge |
| Start condition | |
| Objectives | |
| Fail states | |
| Rewards | |
| Estimated length | |

## 7.2 Mission list (vertical slice minimum)
| ID | Name | Type | Region | Status |
|----|------|------|--------|--------|
| M01 |  | main |  | draft |

## 7.3 Activity taxonomy (open world / hybrid)
Combat / exploration / collection / social / racing / other:
> 

**Pipeline link:** QuestDesigner + genre activity tables + QA

---

# 8. LEVEL / TRACK / ENCOUNTER DESIGN — [AI]

## 8.1 Space list
| ID | Name | Type | Encounters | Secrets | Performance budget notes |
|----|------|------|------------|---------|--------------------------|
| L01 |  |  |  |  |  |

## 8.2 Encounter recipes
| ID | Setup | Enemy mix | Player resources | Intended duration |
|----|-------|-----------|------------------|-------------------|
| E01 |  |  |  |  |

## 8.3 Puzzle verbs (adventure)
> 

**Pipeline link:** genre pipeline (FPS arenas, racing tracks, adventure gates)

---

# 9. ART & VISUAL ASSET LIST — [AI + HUMAN]

## 9.1 Art pillars
Silhouette / color / material language:
> 

## 9.2 Characters & creatures — models
| Asset ID | Description | Poly budget | Textures | Rig | Priority | Source (AI gen / human / stock) |
|----------|-------------|-------------|----------|-----|----------|----------------------------------|
| CH_PC1 |  |  |  |  | P0 |  |
| CH_NPC_ |  |  |  |  |  |  |
| CR_ |  |  |  |  |  |  |

## 9.3 Props / vehicles / weapons
| Asset ID | Description | Budget | Priority | Source |
|----------|-------------|--------|----------|--------|
| PR_ |  |  |  |  |
| VH_ |  |  |  |  |
| WP_ |  |  |  |  |

## 9.4 Environment kits
| Kit ID | Biome/Region | Modular pieces needed | Priority |
|--------|--------------|----------------------|----------|
| ENV_ |  |  |  |

## 9.5 Materials & textures
| Mat ID | Type | Maps needed (A/R/M/N/E) | Resolution | Shared? |
|--------|------|-------------------------|------------|---------|
| MAT_ |  |  |  |  |

## 9.6 UI / HUD / icons
| UI ID | Description | Priority |
|-------|-------------|----------|
| UI_ |  |  |

## 9.7 VFX
| FX ID | Description | Priority |
|-------|-------------|----------|
| FX_ |  |  |

**Pipeline link:** Text/Image→3D (Luma/Meshy/Tripo) + Blender tools + 3D Screenshots + ArtDirector + QA Art/3D

---

# 10. AUDIO ASSET LIST — [AI + HUMAN]

## 10.1 Voice
| Line set ID | Character | Approx # lines | Tone | Priority | TTS / human |
|-------------|-----------|----------------|------|----------|-------------|
| VO_ |  |  |  |  |  |

## 10.2 Music
| Track ID | Use (title/explore/combat/boss) | Length | Mood | Priority |
|----------|----------------------------------|--------|------|----------|
| MUS_ |  |  |  |  |

## 10.3 SFX
| SFX ID | Event | Priority |
|--------|-------|----------|
| SFX_ |  |  |

## 10.4 Mix targets
Dialogue vs music vs SFX levels / LUFS goals:
> 

**Pipeline link:** Audio & Video Gen tool + Kokoro TTS + QA Audio

---

# 11. TECHNICAL PLAN — [AI + HUMAN]

## 11.1 Engine / framework — [HUMAN] **REQUIRED**
Pick **one primary engine** before production run Stage 4 (ASSEMBLY). Secondary DCC tools are optional.

| Choice | Check one |
|--------|-----------|
| Godot 4.x | [ ] |
| Unity | [ ] |
| Unreal Engine | [ ] *(supported in Jayson **4.0** — dedicated SSD; binary editor ~40–130 GB, not 1 TB)* |
| Custom / other | [ ] (name: __________) |

**Primary engine:** 
> 

**Editor version (required):** 
> 

**Why this engine (short):** 
> 

**DCC / support tools (optional):** Blender [ ] · other: 
> 

**Pipeline binding:** Godot → `pipelines/games/godot_pipeline.md` + `tools/godot/` · Unity → `tools/unity/` · Blender assets → `tools/blender/` · Unreal → **4.0** (dedicated SSD after engine install; 256–512 GB typical)


## 11.2 Target frame rate & resolution per platform
| Platform | FPS | Res / dynamic res | Graphics tier |
|----------|-----|-------------------|---------------|
| Windows |  |  |  |
| Quest 3 |  |  |  |
| … |  |  |  |

## 11.3 Input maps
Keyboard/mouse / gamepad / touch / VR controllers:
> 

## 11.4 Save system
What is saved, when, cloud or local:
> 

## 11.5 Scene / streaming strategy
> 

## 11.6 Modding / data-driven content (optional)
> 

**Pipeline link:** TechLead agent + Unity tools + export_targets.md

---

# 12. VERTICAL SLICE DEFINITION — [HUMAN REQUIRED]

## 12.1 Slice must include
- [ ] Playable start → goal → end
- [ ] One complete core-loop demonstration
- [ ] Listed P0 assets only
- [ ] One QA pass with no critical blockers

Exact slice description:
> 

## 12.2 Slice success criteria
> 

## 12.3 Slice exclusion list
> 

---

# 13. PRODUCTION PIPELINE BINDING — [SYSTEM]

Map package sections → Jayson agents/tools (do not delete).

| Package section | Primary agent / tool | QA agent |
|-----------------|----------------------|----------|
| Story (3) | Storyline Maker + NarrativeWriter | QA Narrative |
| Characters (4) | NarrativeWriter + ArtDirector | QA Narrative / Art |
| World (5) | WorldBuilder | QA Design |
| Systems (6) | SystemsDesigner | QA Systems |
| Quests (7) | QuestDesigner | QA Design |
| Levels (8) | Genre pipeline agents | QA Design |
| 3D assets (9) | Text/Image→3D + Blender + Screenshots | QA Art/3D |
| Audio (10) | Audio tool + Kokoro | QA Audio |
| Tech (11) | TechLead | QA Build |
| Slice (12) | Orchestrator | QA Build + QA Gate |
| Engine (1.6 / 11.1) | TechLead + engine pipeline | Must be set before ASSEMBLY |
| Exports (14) | Export pipeline | QA Export |

**Loop rule:** PLAN → ACT → CHECK → QA → HANDOFF (Tight Agent Loop tool)

---

# 14. EXPORT MATRIX — [HUMAN selects, AI fills constraints]

| Platform | In scope? | Input | Res/FPS target | SDK available? | Status (PREP_ONLY / BUILD) |
|----------|-----------|-------|----------------|----------------|----------------------------|
| Windows |  |  |  | n/a |  |
| Linux |  |  |  | n/a |  |
| Android |  |  |  |  |  |
| Quest 2 |  |  |  |  |  |
| Quest 3 |  |  |  |  |  |
| PS4 VR |  |  |  |  |  |
| PS5 VR |  |  |  |  |  |
| PS3 |  |  |  | legacy | PREP_ONLY |

Per-platform notes:
> 

**Pipeline link:** `pipelines/games/export_targets.md` + QA Export

---

# 15. QA & DELIVERY GATES — [SYSTEM]

## 15.1 Mandatory gates
1. Section-level `qa_inspect` on every major deliverable  
2. Stage `qa_gate` before handoff  
3. Final delivery gate before “done” or export package

## 15.2 Severity definitions
- **Critical:** Soft-lock, crash, data loss, unplayable controls  
- **Major:** Broken core loop, missing P0 asset, narrative contradiction  
- **Minor:** Polish, typos, non-blocking balance  

## 15.3 Delivery checklist
- [ ] Vertical slice criteria met
- [ ] All P0 assets present or explicitly waived
- [ ] No open Critical QA items
- [ ] Export profiles written for selected platforms
- [ ] Known limitations documented

---

# 16. RISK REGISTER — [AI + HUMAN]

| Risk | Impact | Likelihood | Mitigation | Owner |
|------|--------|------------|------------|-------|
|  |  |  |  |  |

---

# 17. MILESTONES — [HUMAN]

| Milestone | Date | Exit criteria |
|-----------|------|---------------|
| Package approved |  | HUMAN sign-off on sections 1, 2, 12 |
| Vertical slice playable |  | Section 12 criteria |
| Content complete (v1) |  | All P0 missions + assets |
| Release candidate |  | QA gate ALLOW_DELIVERY |

---

# 18. HUMAN CREATOR ONLY — FINAL SIGN-OFF

| Question | Answer |
|----------|--------|
| I approve the pillars and scope | YES / NO |
| I approve the vertical slice definition | YES / NO |
| I accept listed out-of-scope items | YES / NO |
| Supervision frequency | every handoff / daily / end of stage |
| Name / date |  |

---

# 19. AI EXECUTION BRIEF (paste to Jayson)

When this package is filled enough to start, give Jayson:

```
Load production package: projects/<game>/PRODUCTION_PACKAGE.md
Genre pipeline: <Racing|FPS|TPS|Adventure|OpenWorld|RPG>
Start orchestrator with supervision mode: <mode>
Begin Stage 1. Use Tight Agent Loop. QA gate every handoff.
Expand only [AI] sections; do not change [HUMAN] decisions without asking.
```

---

# 20. APPENDIX — MINIMUM FILL TO START

If short on time, HUMAN must complete at least:
- 1.1 Pitch
- 1.3 Genre
- 1.5 Platforms
- 1.6 Scope guardrails
- 2.1 Pillars
- 12.1–12.2 Vertical slice
- 18 Sign-off

Everything else can be drafted by AI and revised under supervision.
