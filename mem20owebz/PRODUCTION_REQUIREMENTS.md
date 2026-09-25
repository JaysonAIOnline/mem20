# Jayson Production Package — Reusable Requirements Template

> **REUSE INSTRUCTIONS**
> 1. **Never edit this file in place for a real game.** It is the master template.
> 2. Copy it for each project:
>    ```bash
>    cp PRODUCTION_REQUIREMENTS.md projects/MyGame_production_requirements.md
>    ```
> 3. Fill only the copy. Keep this original clean for the next project.
> 4. Feed the **filled copy** to Jayson / the Orchestrator.
> 5. One project = one filled requirements file. Multiple games = multiple copies.
> 6. Version the filled file when major pillars change (`_v1`, `_v2`, …).
> 7. Any AI helping fill a copy must preserve all `[[HUMAN]]` fields the creator still owns.

---

# Jayson Production Package — Requirements Template

**Purpose:**  
This file is the **single input** a human (or any AI) fills out so Jayson can decompose, schedule, and execute a game production package with supervision.

**How to use:**
1. Copy this file → rename to `PROJECTNAME_production_requirements.md`
2. Fill every `[[HUMAN]]` section (required)
3. Optionally refine `[[AI_MAY_DRAFT]]` sections
4. Feed the completed file to Jayson / Orchestrator
5. System runs pipelines + agents; human supervises gates

**Rules for any AI helping write this package:**
- Never invent platform SDK secrets or claim certified console builds without human confirmation
- Prefer concrete, testable deliverables over vague vision
- Every asset must have an owner stage and acceptance criteria
- Mark unknowns as `TBD` with a question, do not silently skip
- Align with existing Jayson pipelines: RPG/Genre orchestrator, Storyline Maker, Text/Image→3D, Audio/Video, QA gates, Export targets

---

# 0. Document Control

| Field | Value |
|-------|--------|
| Project codename | [[HUMAN]] |
| Working title | [[HUMAN]] |
| Version of this requirements doc | 1.0 |
| Date | [[HUMAN]] |
| Primary creator / owner | [[HUMAN]] |
| Supervision mode | human-in-the-loop at every QA gate |
| Target ship quality | vertical slice / alpha / beta / release [[HUMAN]] |

---

# 1. Elevator Pitch & Pillars

## 1.1 One-sentence pitch
[[HUMAN]]  
*(Example: "A third-person open-world mystery where memory is a resource you spend to change the past.")*

## 1.2 Player fantasy
[[HUMAN]]  
What does it *feel* like to play?

## 1.3 Design pillars (3–5, non-negotiable)
1. [[HUMAN]]
2. [[HUMAN]]
3. [[HUMAN]]
4. [[AI_MAY_DRAFT]]
5. [[AI_MAY_DRAFT]]

## 1.4 Explicit non-goals
[[HUMAN]]  
*(What this game is NOT)*

---

# 2. Genre & Structure

## 2.1 Primary genre pipeline
Pick one (or primary + secondary):

- [ ] Racing
- [ ] 1st Person Shooter
- [ ] 3rd Person Shooter
- [ ] Adventure
- [ ] Open World
- [ ] RPG (use RPG Orchestrator)
- [ ] Hybrid — describe: [[HUMAN]]

## 2.2 Perspective & camera
[[HUMAN]]  
*(first-person / third-person / isometric / top-down / fixed / hybrid)*

## 2.3 Session length targets
| Session type | Target |
|--------------|--------|
| One meaningful loop | [[HUMAN]] minutes |
| Main story total | [[HUMAN]] hours |
| Completionist | [[HUMAN]] hours |

## 2.4 Platforms (export targets)
Check all that apply:

- [ ] Windows
- [ ] Linux
- [ ] Android
- [ ] Meta Quest 2
- [ ] Meta Quest 3
- [ ] PS4 VR
- [ ] PS5 VR
- [ ] PS3 (legacy constraints only)
- [ ] Other: [[HUMAN]]

**Primary launch platform:** [[HUMAN]]

---

# 3. Story & Narrative

> Use with Storyline Maker tool + NarrativeWriter agent + QA Narrative.

## 3.1 Logline
[[HUMAN]]

## 3.2 Theme
[[HUMAN]]

## 3.3 Tone & rating
[[HUMAN]]  
*(tone words + content rating intent)*

## 3.4 Story structure
- Acts: [[HUMAN]] (usually 3)
- Structure reference: [[AI_MAY_DRAFT]] (Hero’s Journey / Mystery / Gauntlet / etc.)

## 3.5 Main plot beats (must play)
| Beat | Summary | Required? |
|------|---------|-----------|
| Opening | [[HUMAN]] | Yes |
| Inciting incident | [[HUMAN]] | Yes |
| Midpoint | [[HUMAN]] | Yes |
| Low point | [[HUMAN]] | Yes |
| Climax | [[HUMAN]] | Yes |
| Resolution | [[HUMAN]] | Yes |

## 3.6 Characters

### Protagonist
| Field | Value |
|-------|--------|
| Name | [[HUMAN]] |
| Want | [[HUMAN]] |
| Need | [[HUMAN]] |
| Arc | [[HUMAN]] |
| Visual brief | [[HUMAN]] |
| Voice brief | [[HUMAN]] |

### Antagonist
| Field | Value |
|-------|--------|
| Name | [[HUMAN]] |
| Goal | [[HUMAN]] |
| Method | [[HUMAN]] |
| Visual brief | [[HUMAN]] |

### Supporting cast (repeat blocks as needed)
| Name | Role | Function in story | Visual | Voice |
|------|------|-------------------|--------|-------|
| [[HUMAN]] | | | | |

## 3.7 Codex / lore delivery method
[[HUMAN]]  
*(environmental, collectible, dialogue, optional)*

---

# 4. Gameplay Systems

> SystemsDesigner agent + QA Systems.

## 4.1 Core loop (one paragraph)
[[HUMAN]]

## 4.2 Verbs the player can do
| Verb | Description | Unlock condition |
|------|-------------|------------------|
| [[HUMAN]] | | |
| [[AI_MAY_DRAFT]] | | |

## 4.3 Combat / challenge (if any)
| Topic | Spec |
|-------|------|
| Camera during combat | [[HUMAN]] |
| Time-to-kill target | [[HUMAN]] |
| Player resources | [[HUMAN]] |
| Enemy archetypes (list) | [[HUMAN]] |
| Failure state | [[HUMAN]] |
| Assist options | [[HUMAN]] |

## 4.4 Progression
| Topic | Spec |
|-------|------|
| XP / unlock model | [[HUMAN]] |
| Player power curve | [[HUMAN]] |
| Economy (sources/sinks) | [[HUMAN]] |
| Meta-progression? | [[HUMAN]] |

## 4.5 Inventory / crafting / skills
[[HUMAN]] or `None`

## 4.6 AI directors / systems
[[HUMAN]]  
*(enemy director, rubber-banding, density director, etc.)*

---

# 5. World & Content

## 5.1 Space breakdown
| Space / Region | Purpose | Size intent | Must-have activities |
|----------------|---------|-------------|----------------------|
| [[HUMAN]] | | | |

## 5.2 Quest / mission list (minimum viable)
| ID | Name | Type | Summary | Reward |
|----|------|------|---------|--------|
| MQ01 | [[HUMAN]] | Main | | |
| SQ01 | [[HUMAN]] | Side | | |

## 5.3 Collectibles / activities taxonomy
[[AI_MAY_DRAFT]] aligned to genre pipeline

---

# 6. Asset Bible (AI-executable)

> Every row should be producible by existing tools/agents (3D pipeline, audio tools, storyline, etc.) or marked `HUMAN_ONLY`.

## 6.1 Characters / creatures — models
| Asset ID | Description | Poly/style target | Source method | Priority | Acceptance criteria |
|----------|-------------|-------------------|---------------|----------|---------------------|
| CHAR_PROTAG | [[HUMAN]] | stylized mid | Text/Image→3D + Blender | P0 | Centered, textured, screenshots pass QA Art |
| CHAR_ANTAG | [[HUMAN]] | | | P0 | |
| [[AI_MAY_DRAFT]] | | | | | |

## 6.2 Props / environment kits
| Asset ID | Description | Method | Priority | Acceptance |
|----------|-------------|--------|----------|------------|
| PROP_ | [[HUMAN]] | | P1 | |
| ENV_ | [[HUMAN]] | | P1 | |

## 6.3 Materials & textures
| Mat ID | Used on | Style notes | Maps needed | Priority |
|--------|---------|-------------|-------------|----------|
| MAT_ | [[HUMAN]] | | albedo/normal/roughness | P0 |

## 6.4 Animation / moveset (if needed)
| Anim ID | Owner | Description | Priority |
|---------|-------|-------------|----------|
| AN_ | [[HUMAN]] | idle/walk/run/attack… | P0 |

## 6.5 UI / HUD
| Element | Description | Priority |
|---------|-------------|----------|
| HUD_ | [[HUMAN]] | P0 |
| MENU_ | [[HUMAN]] | P0 |

## 6.6 Audio — voice
| Line set | Character | Approx # lines | Voice direction | Method |
|----------|-----------|----------------|-----------------|--------|
| VO_PROTAG | [[HUMAN]] | | | Kokoro / ElevenLabs |

## 6.7 Audio — music & SFX
| Cue ID | Type | Mood / use | Method | Priority |
|--------|------|------------|--------|----------|
| MUS_ | music | | external / tool | P1 |
| SFX_ | sfx | | | P0 |

## 6.8 Cinematics / video (optional)
| Shot ID | Description | Method | Priority |
|---------|-------------|--------|----------|
| CIN_ | [[HUMAN]] | Luma / external | P2 |

---

# 7. Technical Requirements

## 7.1 Engine / stack
[[HUMAN]]  
*(Unity / Unreal / Godot / custom / undecided)*

## 7.2 Target performance
| Platform | Resolution | FPS target | Notes |
|----------|------------|------------|-------|
| Primary | [[HUMAN]] | [[HUMAN]] | |
| VR (if any) | | | comfort requirements [[HUMAN]] |

## 7.3 Input
| Platform | Input methods |
|----------|---------------|
| [[HUMAN]] | keyboard/mouse, gamepad, touch, VR controllers |

## 7.4 Save system
[[HUMAN]]

## 7.5 Accessibility minimums
[[HUMAN]]  
*(subtitles, colorblind, difficulty, motion sickness options)*

---

# 8. Production Plan (system-executable)

## 8.1 Vertical slice definition (must ship first)
[[HUMAN]]  
Exact playable path from boot → meaningful end state.

## 8.2 Stage order (default)
1. World / Concept lock
2. Systems lock for slice
3. Narrative for slice
4. Art & audio for slice
5. Implementation
6. QA gate
7. Expand content
8. Export prep per platform
9. Final QA gate

## 8.3 Agent assignments
| Stage | Primary agent | Supporting tools |
|-------|---------------|------------------|
| World | WorldBuilder | Storyline Maker, Knowledge |
| Systems | SystemsDesigner | Tight Agent Loop |
| Quests | QuestDesigner | Storyline Maker |
| Narrative | NarrativeWriter | Storyline Maker |
| Art | ArtDirector | Text/Image→3D, Screenshots, Luma |
| Audio | (ArtDirector / Audio) | Audio tools, Kokoro |
| Tech | TechLead | Unity/Blender tools |
| QA | QA suite | qa_inspect + qa_gate |
| Export | TechLead + QA Export | export_targets pipeline |

## 8.4 Supervision checkpoints (human)
Human **must** approve:
- [ ] Pillars & non-goals
- [ ] Vertical slice definition
- [ ] Story climax
- [ ] Each QA gate FAIL resolution
- [ ] Any real platform SDK submission

---

# 9. Acceptance & QA

## 9.1 Global acceptance criteria
- [ ] Vertical slice completable without developer help
- [ ] All P0 assets pass QA Art / QA Audio
- [ ] Systems numbers documented and tunable
- [ ] No known soft-locks on critical path
- [ ] Export checklist filled for each selected platform
- [ ] Final `qa_gate` = ALLOW_DELIVERY

## 9.2 Deliverable package contents
1. This requirements file (completed)
2. World bible + systems doc + quest list
3. Asset folders (models, textures, audio)
4. Build or PREP_ONLY export notes per platform
5. QA reports (PASS/FAIL history)
6. Known issues list

---

# 10. Human Creator Section (required)

> Everything below is **only** for the human. AIs must not overwrite without explicit permission.

## 10.1 Personal vision notes
[[HUMAN]]

## 10.2 Must-keep ideas (sacred)
[[HUMAN]]

## 10.3 Hard constraints (time, money, skill, hardware)
[[HUMAN]]

## 10.4 References (games, films, art)
[[HUMAN]]

## 10.5 Open questions for the AI team
1. [[HUMAN]]
2. [[HUMAN]]
3. [[HUMAN]]

## 10.6 Sign-off
- Creator name: [[HUMAN]]
- Date: [[HUMAN]]
- “I approve this requirements doc as the source of truth for supervised production.”  
  Signature/ack: [[HUMAN]]

---

# 11. AI Execution Appendix (do not delete)

When this file is fed to Jayson:

1. Parse sections 1–9 into tasks  
2. `start_rpg_project` or genre pipeline as appropriate  
3. For each stage: Tight Agent Loop → produce artifacts → `qa_inspect` → human gate if required → `handoff`  
4. Produce assets via Text/Image→3D, Audio, Storyline, Blender, Unity tools  
5. Run export target checklists  
6. Stop on any FAIL until fixed  
7. Final delivery only after `qa_gate` ALLOW_DELIVERY + human sign-off on section 10

**End of template**
