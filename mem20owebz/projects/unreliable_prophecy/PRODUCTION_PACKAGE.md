# GAME PRODUCTION PACKAGE — THE UNRELIABLE PROPHECY

> **Purpose:** Filled production package for Jayson 2.0 beta.  
> Source material: Unreliable_Prophecy_COMPLETE_PACKAGE (GDD v1.0 / Expanded v1.1, Final Production Pack, Production Detail, Completeness Supplement, Team Starter Pack).  
> Sections marked **[HUMAN]** reflect creator decisions already locked in the source docs.  
> Sections marked **[AI]** expanded from source material for pipeline consumption.  
> Supervision mode: human-in-the-loop (recommended for first vertical slice).

**How this package was produced**
1. Source PDFs extracted and consolidated.
2. All [HUMAN] intent fields filled from definitive production packs.
3. [AI] sections expanded with concrete numbers, asset IDs, quest templates, and technical bindings taken directly from the design docs.
4. Ready for `start_rpg_project` / Adventure + light RPG genre pipeline.

---

# 0. DOCUMENT CONTROL

| Field | Value |
|-------|--------|
| Package version | 1.0 (filled from Unreliable Prophecy Complete Package) |
| Game working title | The Unreliable Prophecy |
| Codename | UnreliableProphecy / UP |
| Date started | 2026-08-21 (source package date) |
| Last updated | 2026-08-23 |
| Owner (human) | Creator / Design Lead (from source pack) |
| Supervision mode | human-in-the-loop |
| Target vertical slice date | End of Week 7 content (v0.5.0_VerticalSlice) |
| Target content-complete date | Post vertical-slice full production (see milestones) |

---

# 1. HIGH-LEVEL INTENT — [HUMAN]

## 1.1 One-sentence pitch
> A story-driven 3D adventure in which you are declared the Chosen One by a deeply tired celestial bureaucracy, then must save the world while keeping the paperwork in order.

## 1.2 Player fantasy
What does it *feel* like to play?
> Players feel trapped in the universe’s worst group project — one that happens to involve ancient evils, reluctant heroes, and an endless supply of forms. The tone balances genuine warmth between companions with institutional absurdity. Dry, bureaucratic humor; shared irritation that slowly becomes reluctant loyalty.

## 1.3 Genre & subgenre
Primary: Adventure  
Secondary: Light RPG / Bureaucratic Fantasy  
Hybrid: Story-driven 3D adventure with light real-time combat, companion banter, and living document systems.

## 1.4 Perspective & camera
- [x] 3rd person
- [ ] 1st person
- [ ] Isometric / top-down
- [ ] Fixed camera
- [ ] Hybrid: ___

Third-person over-the-shoulder / adventure camera (Cinemachine). Readable combat and exploration.

## 1.5 Platforms (export targets)
Check all that apply:
- [x] Windows
- [ ] Linux
- [ ] Android
- [ ] Meta Quest 2
- [ ] Meta Quest 3
- [ ] PS4 VR
- [ ] PS5 VR (PSVR2)
- [ ] PS3 (legacy/constraints only)
- [ ] Other: ___

Primary target: Windows standalone (x86_64). Controller + keyboard/mouse support from day one. Later platforms possible after vertical slice.

## 1.6 Primary engine — [HUMAN] **REQUIRED**
Must match §11.1. Production Run will not advance past ASSEMBLY without this.

- [ ] Godot 4.x
- [x] Unity
- [ ] Unreal Engine
- [ ] Custom / other: ________

**Editor version:** Unity 6 or latest LTS + URP (Universal Render Pipeline). Linear color space. IL2CPP for release builds.

## 1.7 Scope guardrails — [HUMAN]

Must ship in vertical slice:
> Quietvale complete (house → square → Bureaucrat scene → woods combat → leave gate; all 10 tutorial steps).  
> Bureaucracy Hills playable end-to-end (critical path + 1 side quest).  
> 2 companions functional (Old Wizard + 1 other) with follow + ≥3 banter lines each.  
> Guidebook with ≥8 readable entries.  
> 1 full Bureaucrat amendment delivery (text + mechanical effect).  
> Quest system: accept, track, complete, turn-in.  
> Inventory with ≥5 distinct obtainable items + pickup.  
> Prophecy Binder UI: original text + ≥1 amendment displayed.  
> Quest Tracker live updates.  
> Save/Load round-trip (save in Hills → quit → load → correct state).  
> Main menu with New Game + Continue/Load.

Explicitly out of scope for v1 / vertical slice:
> Forest of Unhelpful Trees, City of Forms, Overflow Archives, Ruins of Previous Chosen Ones, Final Administrative Zone.  
> Full companion roster and personal quests.  
> New Game+, secret ending, departmental reputation UI, final boss multi-phase combat.  
> Full music implementation, heavy VFX polish, accessibility beyond basic subtitles.  
> Multiplayer, VR, mobile, console ports.

Hard constraints (time, team size, engine, budget, rating):
> Single-player only. Light systems (no deep skill trees or complex economies). Deliberately achievable scope. Target rating suitable for dry institutional humor (T / Teen equivalent — mild fantasy violence, no gore focus, language restrained). Week-by-week prototype plan assumes small team / solo + AI assistance via Jayson.

---

# 2. PILLARS & TONE — [HUMAN + AI]

## 2.1 Design pillars (3–5) — [HUMAN]
1. Story and character first — combat and systems support the narrative.
2. Humor that is dry, institutional, and understated rather than loud slapstick.
3. Bureaucracy as both obstacle and comedy engine.
4. Companion relationships that grow through shared irritation and reluctant loyalty.
5. A living Prophecy Binder that becomes messier and more contradictory as the game progresses.
6. (Supporting) Scope kept deliberately achievable: single-player, limited regions, light systems.

## 2.2 Tone & rating — [HUMAN]
Tone keywords: dry, institutional, bureaucratic, understated, reluctant, warm-under-the-absurdity, passive-aggressive celestial paperwork.  
Content rating target: T (Teen) / equivalent — mild fantasy combat, no graphic violence, language restrained to institutional irritation.  
Violence / language / horror limits: Combat is readable and short (10–25 s normal encounters). No body horror. Bureaucracy is the primary source of friction and comedy.

## 2.3 References (games, films, art) — [HUMAN]
| Reference | What to steal | What to avoid |
|-----------|---------------|---------------|
| AdventureQuest 3D | Accessible questing, light progression, friendly 3D adventure feel | Overly grindy loops, heavy MMO systems |
| The Belgariad (David Eddings) | Classic chosen-one journey structure, companion party dynamics | Pure high-fantasy solemnity |
| The Hitchhiker’s Guide to the Galaxy (Douglas Adams) | Dry institutional absurdity, sarcastic institutional memory (Guidebook) | Pure slapstick or pure cynicism without warmth |
| (Internal) Filing cabinets, stamps, forms as visual language | Everyday bureaucratic objects elevated to world-building | Cartoonish “evil paperwork” without tired realism |

## 2.4 Pillar tests — [AI]
For each pillar, one playable test that proves it is present in the vertical slice.
> 1. Story/character first: Within first 10 minutes the player receives Prophecy 47-B (Revised), signs forms, and acquires the Binder; combat is secondary to the scene.  
> 2. Dry humor: Bureaucrat dialogue and Guidebook entries land as understated institutional irritation (no punchline timing required).  
> 3. Bureaucracy as comedy engine: One full amendment delivery occurs mid-region and changes an objective or rule.  
> 4. Companion relationships: ≥3 banter lines fire between Old Wizard and second companion or Guidebook during Hills traversal.  
> 5. Living Binder: Prophecy Binder UI shows original text + at least one amendment with strikethrough / footnote visual.  
> 6. Achievable scope: Critical path from New Game → end of Bureaucracy Hills completes without soft-locks or missing P0 assets.

---

# 3. STORY & NARRATIVE — [AI expandable, HUMAN approves]

## 3.1 Logline
> An ordinary person in Quietvale is declared the Chosen One by an exhausted celestial bureaucrat and forced to carry Prophecy 47-B (Revised) while assembling a reluctant party, collecting contradictory amendments, and navigating a world where ancient evils still require permits.

## 3.2 Theme
> Destiny is subject to revision. Procedure outranks the fate of the world — until the paperwork itself becomes the obstacle that must be overcome (or signed). Shared irritation can become loyalty. The bureaucracy never really stops.

## 3.3 Story structure
Format: 3-act / chapter-based with authored main path + procedural side content.  
Synopsis:
> Prologue – Ordinary Life (Quietvale): Bureaucrat delivers Prophecy 47-B (Revised) and forces signatures.  
> Act 1 – The Reluctant Beginning: Leave home; Old Wizard + Guidebook join.  
> Act 2 – Gathering the Unwilling: Assemble remaining companions across regions; learn previous Chosen Ones mostly failed.  
> Act 3 – The Journey: Classic fantasy obstacles corrupted by bureaucracy (permits, user agreements, ineffective meetings).  
> Act 4 – Final Administrative Zone: Multi-phase confrontation at the Desk of Absolute Authority (combat + dialogue + forced forms).  
> Epilogue: World (probably) saved; certificates issued; bureaucracy continues. Secret path reveals Prophecy 47-C already in draft.

## 3.4 Main quest outline
| Act/Chapter | Goal | Obstacle | Twist/Payoff |
|-------------|------|----------|--------------|
| Ch 1 Ordinary Life | Survive tutorial & receive Binder | Forced signatures, first combat | Prophecy arrives; tone established |
| Ch 2 Leaving Home | Reach first region with companion | Strange events force departure | Old Wizard + Guidebook join |
| Ch 3 Bureaucracy Hills | Complete critical path + amendment | First major bureaucratic interference | Amendment changes rules mid-quest |
| Ch 4 Gathering the Party | Recruit remaining companions | Regional obstacles + forms | Party assembled; rivalries surface |
| Ch 5 Weight of Precedence | Explore Ruins of Previous Chosen Ones | Melancholy memorial + lore | Emotional turning point; failure rate revealed |
| Ch 6 The Approach | Final preparations & cohesion | Departmental rivalries | Party ready for climax |
| Ch 7 Final Administrative Zone | Multi-phase boss + form choice | Amendments mid-fight, Officers, zone debuffs | Sign (Compliant) or Refuse (Irregular) ending |
| Epilogue | Certificates & resolution | Bureaucracy continues | Possible secret ending (47-C) |

## 3.5 Side content policy
How much side content vs main path? Mandatory vs optional?
> Main path is fully authored and fixed so humor and character moments land. Side content is light, mostly optional, and heavily template-driven / procedural (department lost item, unauthorized creature filing reports, deliver form without opening, resolve contradictory orders). Personal companion quests are optional but required for secret ending. Overflow Archives is the primary procedural/lore side region.

## 3.6 Codex / lore delivery method
Environmental / items / NPCs / collectibles / none
> Primary: Guidebook (sentient, sarcastic institutional memory) + Prophecy Binder (living document with amendments). Secondary: readable lore notes, Failed Prophecy Fragments, hidden memo in Quiet Reading Room of Overflow Archives, environmental filing cabinets and stamps. NPCs deliver dry commentary.

**Pipeline link:** Storyline Maker tool + NarrativeWriter agent + QA Narrative

---

# 4. CHARACTERS — [AI expandable, HUMAN approves]

## 4.1 Player character(s)
| ID | Name | Role | Fantasy | Arc | Abilities | Visual notes |
|----|------|------|---------|-----|-----------|--------------|
| PC1 | (Player-named / Ordinary) | Reluctant Chosen One | Ordinary person forced into destiny paperwork | From quiet life → exasperated but increasingly competent carrier of contradictions | Basic melee + 2 abilities (light damage / utility); light progression | Ordinary civilian silhouette; no special powers at start; dry dialogue |

## 4.2 Major NPCs
| ID | Name | Role | Want | Relationship to PC | Fate |
|----|------|------|------|--------------------|------|
| NPC_Bureaucrat | Recurring Celestial Bureaucrat | Amendment delivery, passive-aggressive procedure | Perfect documentation above all | Forced contact; occasional tiny humanity | Continues after ending; larger binder needed |
| NPC_Director | Acting Director of Destiny Affairs | Off-screen author of hidden memo | Quietly close the file / start 47-C | Never meets PC in base game | Initiates Prophecy 47-C |
| NPC_Villager | Quietvale villagers | Tone setters | Ordinary life | Early commentary | Remain in Quietvale |

## 4.3 Enemies / factions
| ID | Name | Function in combat/story | Hierarchy |
|----|------|--------------------------|-----------|
| EN_MisfiledSkeleton | Misfiled Skeleton | Tier-1 trash, wrong-badge flavor | Common |
| EN_InkBlot | Ink Blot Swarm | DoT / slow, common | Common |
| EN_UnauthorizedImp | Unauthorized Imp | Fast, stamp attempt | Tier-2 |
| EN_ComplianceOfficer | Archive / Standard Compliance Officer | Inspect → stun → paperwork barrage; scales | Elite / mid-late |
| EN_PaperElemental | Paper Elemental | Mini-boss (Overflow Archives); 3 phases, regen + forms | Boss |
| EN_StampGolem | Stamp Golem | Optional heavy; auth required | Optional boss |
| EN_FinalBoss | Desk of Absolute Authority / Final Boss | 4-phase (NG+ extra); amendments mid-fight | Climax |
| FAC_PropheticContinuity | Prophetic Continuity | “As It Was Written.” Preserve original wording | Department |
| FAC_NarrativeOversight | Narrative Oversight | “Make It Matter.” Drama over practicality | Department |
| FAC_CelestialCompliance | Celestial Compliance | “If It Isn’t Documented, It Didn’t Happen.” | Department |
| FAC_DestinyAffairs | Destiny Affairs | “Resolved With Minimum Effort.” | Department |

## 4.4 Character bible rules — [AI]
Voice, vocabulary limits, visual silhouette rules:
> Player: dry, reluctant, increasingly exasperated; limited meaningful choices.  
> Old Wizard: cynical, tired of prophecies, ancient mentor; magic support.  
> Organized Sorceress: competent, administrative, unimpressed; control/utility.  
> Charming Rogue: opportunist, profit-minded, stationery thief; stealth/utility.  
> Big Warrior: straightforward, confused by bureaucracy; frontline damage.  
> Guidebook: flat, superior, institutional memory; often wrong, sarcastic footnotes.  
> Bureaucrat: tired, precise, passive-aggressive; never jokes about documentation.  
> Compliance Officer: near-monotone, formal, prefers inspection before combat.  
Visual: Silhouettes readable at adventure distance; filing-cabinet / stamp / binder motifs for bureaucratic elements; companions have clear role silhouettes (staff, organized robes, cloak, large frame, floating book).

**Pipeline link:** NarrativeWriter + ArtDirector + QA Narrative / Art

---

# 5. WORLD — [AI expandable]

## 5.1 Setting summary
> A fantasy world overlaid with a living celestial bureaucracy. Ordinary villages exist alongside filing-cabinet landscapes, passive-aggressive forests, administrative hub cities, and archives of previous failed Chosen Ones. Destiny is documented, revised, and frequently misfiled.

## 5.2 Regions / biomes / tracks / maps
| ID | Name | Purpose | Size intent | Unlock condition | Activities |
|----|------|---------|-------------|------------------|------------|
| R1 | Quietvale | Starter village / tutorial + tone | Small, complete | Start | Tutorial (10 steps), first combat, Binder acquisition |
| R2 | Bureaucracy Hills | First major region, amendments begin | Medium, critical path + 1 side | After Quietvale gate | Main quest, 1 side quest, amendment delivery, loot |
| R3 | Forest of Unhelpful Trees | Exploration + companion dynamics | Medium | After Hills / mid Act 2 | Exploration, banter, light combat |
| R4 | City of Forms | Party assembly, major story hub | Large hub (concentric rings) | Mid-game | Recruitment, shops, queues, Department of Previous Failures |
| R5 | Overflow Archives | Optional procedural + lore | Compact multi-level | Mid-game unlock from City | Procedural side content, Paper Elemental, hidden memo |
| R6 | Ruins of Previous Chosen Ones | Emotional turning point | Medium memorial | Late Act 2 / Act 3 | Lore, melancholy, party cohesion |
| R7 | Final Administrative Zone | Climax multi-phase confrontation | Arena + zones | End of Act 3 | Final boss, form choice, endings |

City of Forms layout: Outer Queue District → Commercial & Services → Official District (Permit Office, Department of Previous Failures, Amendment Office) → Upper Offices (Narrative Oversight, Destiny Affairs).  
Overflow Archives: Entrance Hall → Main Stacks → Unsorted Wing → Deep Storage (Paper Elemental) → Quiet Reading Room (hidden memo) → Return corridor.

## 5.3 Traversal
Walk / climb / vehicle / flight / fast travel rules:
> Primarily walk + sprint (1.4×, limited stamina). Light environmental interaction. No vehicles or flight in base design. Fast travel / region transition via gates with autosave hints. Climbing limited to designed paths if present.

## 5.4 Day/night, weather, living world (if any)
> Static or light day cycle for tone (Quietvale morning ambient). No dynamic weather required for vertical slice. Living world expressed through Compliance Officer patrols, departmental rivalries, and procedural ambient commentary rather than full simulation.

**Pipeline link:** WorldBuilder agent + genre pipeline (Adventure)

---

# 6. CORE LOOP & SYSTEMS — [AI expandable, HUMAN approves numbers]

## 6.1 Core loop (30–120 seconds)
Describe the repeated verb cycle:
> 1. Enter region or receive main story objective.  
> 2. Explore, talk to NPCs, accept side content.  
> 3. Fight enemies and complete light objectives.  
> 4. Experience companion dialogue and story scenes.  
> 5. Turn in quests, upgrade gear, read new Guidebook entries.  
> 6. Advance when main story requires it (or receive amendment that changes rules).

## 6.2 Combat / challenge model
(If non-combat: puzzles, racing lines, social, etc.)
- Time-to-kill targets: Normal encounters 10–25 seconds.
- Player power curve: Light. Tier 0 (Quietvale) → Tier 5 (Final). Procedural gear + basic abilities.
- Failure / death penalty: Respawn at checkpoint / region entrance with full HP + short tip (tutorial woods). No heavy loss for vertical slice.

Player baseline (Tier 0): Max HP 100 · Basic Attack 8–12 · Interval 0.9 s · Ability 1 (light) 18 dmg / 6 s CD · Ability 2 (utility) 4 s CD · Sprint 1.4× / 5 s stamina.  
Companion contribution (approx): Wizard 15 magic / 8 s · Sorceress 10% party DR aura · Rogue 12 backstab / 10 s · Warrior 20 / 7 s + aggro · Guidebook occasional debuff/info.

Difficulty levers: primarily amendment frequency and Officer spawn rate (preserves comedy timing).

## 6.3 Progression
XP / unlocks / gear / skill tree / prestige:
| System | What upgrades | Soft cap | Soft currency | Premium currency |
|--------|---------------|----------|---------------|------------------|
| Gear | Procedural + unique items by region tier | Tier 5 | None formal | None |
| Abilities | Small fixed set; light scaling | Fixed | — | — |
| Guidebook / Binder | Collectible entries + amendments | All collected | — | — |
| Reputation (4 depts) | Thresholds affect dialogue, interference, content | ±50 extremes | — | — |
| Personal quests | Companion stories (optional, secret ending) | 5 total | — | — |

No deep skill tree. Light progression only.

## 6.4 Economy
Sources sinks balance notes:
> Loot-driven. Enemies drop 0–2 items. Quest-critical items guaranteed on first completion. Unique pity (guaranteed by 4th eligible kill). ~85% procedural gear (prefix + base + suffix + humorous description); ~15% named unique chance on uncommon+. Bureaucratic tag on ~15% of procedural gear. Consumables (tonics, ink, forms) as soft sinks. No formal gold economy required for slice.

## 6.5 Inventory / loadout / crafting (if any)
> Basic inventory. ≥5 distinct obtainable items in vertical slice. Pickup, equip procedural gear. No crafting system in base design. Prophecy Binder is a special inventory/UI object (world prop + openable UI).

## 6.6 AI / opponent rules
(Racing AI, enemy archetypes, companion AI)
> Companions: follow + banter (priority, cooldown 90–120 s, one-shot flags).  
> Enemies: Idle → Detect → Chase → Attack → (Compliance: Inspect first if not hostile) → Paperwork Barrage at low HP → optional Flee & Report.  
> Compliance Officers call backup if fight lasts too long; permanently raise hostility if they escape.  
> Paper Elemental: 3 phases (adds → regen weak points → form drop Reject/Accept).  
> Final Boss: 4 phases (Opening Arguments → Procedural Escalation → Interdepartmental Conflict → Final Review form choice).

**Pipeline link:** SystemsDesigner + QuestDesigner + QA Systems

---

# 7. QUESTS / MISSIONS / ACTIVITIES — [AI]

## 7.1 Mission template
| Field | Description |
|-------|-------------|
| ID | e.g. M01, SQ_PROC_01 |
| Name | Display title |
| Type | main / side / daily / challenge / personal |
| Start condition | Region + trigger / NPC / amendment |
| Objectives | Ordered or unordered list |
| Fail states | Soft (return later) preferred; hard only for main path |
| Rewards | Items, Guidebook entry, reputation, amendment |
| Estimated length | 2–15 min typical side; main chapters longer |

## 7.2 Mission list (vertical slice minimum)
| ID | Name | Type | Region | Status |
|----|------|------|--------|--------|
| M01 | Ordinary Life / Prophecy Arrival | main | Quietvale | draft / authored |
| M02 | Leaving Home | main | Quietvale → Hills | draft |
| M03 | Bureaucracy Hills Critical Path | main | Bureaucracy Hills | draft |
| SQ01 | (Authored or generated side) | side | Bureaucracy Hills | draft |
| AMD01 | First Amendment Delivery | main/system | Bureaucracy Hills | draft |

Procedural side-quest templates (examples):
- “The Department of {Department} has lost {Item}. Retrieve them from {Location} before {Deadline}.”
- “An unauthorized {Creature} has been filing incorrect reports in {Location}. Correct the situation.”
- “Deliver Form {Code} to {NPC}. Do not open the form.”
- “Two departments have issued opposing orders regarding {Location}. Resolve the contradiction without creating new paperwork.”

## 7.3 Activity taxonomy (open world / hybrid)
Combat / exploration / collection / social / racing / other:
> Combat (light real-time), exploration (regions + Archives), collection (Amendments, Guidebook entries, forms, procedural gear), social (companion banter + personal quests), bureaucratic interaction (forms, permits, Counter-File “This Chaos Has Not Been Approved.”).

**Pipeline link:** QuestDesigner + genre activity tables + QA

---

# 8. LEVEL / TRACK / ENCOUNTER DESIGN — [AI]

## 8.1 Space list
| ID | Name | Type | Encounters | Secrets | Performance budget notes |
|----|------|------|------------|---------|--------------------------|
| L01 | Quietvale (house + square + woods) | Tutorial region | 1–2 weak enemies | None required | Low; tutorial fail-safes |
| L02 | Bureaucracy Hills (path + annex) | Main region | Common + 1 elite possible | Side quest location | Medium; filing-cabinet props |
| L03 | Overflow Archives (full) | Optional side | Paper Elemental + trash | Hidden memo (Quiet Reading Room) | Compact; multi-level stacks |
| L04 | Final Administrative Zone | Climax arena | Final Boss + Officers + zones | Form choice paths | Higher; departmental zone debuffs |

## 8.2 Encounter recipes
| ID | Setup | Enemy mix | Player resources | Intended duration |
|----|-------|-----------|------------------|-------------------|
| E01 | Woods tutorial | Misfiled Skeleton (Tier 1) | Full HP, basic attack | <15 s, low damage |
| E02 | Hills common | Ink Blot / Unauthorized Imp | Standard | 10–25 s |
| E03 | Compliance Officer | Elite Officer (inspect first) | Documents if available | Variable; can escalate |
| E04 | Paper Elemental | Boss 3 phases + adds | Full party if available | Multi-minute |
| E05 | Final Boss | 4 phases + amendments + Officers | Full party + form choice | Climax length |

## 8.3 Puzzle verbs (adventure)
> Light environmental interaction, form/permit gates, Counter-File protocol push-back, department rivalry exploitation, “do not open the form” delivery tension. No pure logic puzzles required for vertical slice.

**Pipeline link:** genre pipeline (Adventure) + QA Design

---

# 9. ART & VISUAL ASSET LIST — [AI + HUMAN]

## 9.1 Art pillars
Silhouette / color / material language:
> Readable silhouettes at adventure distance. Warm Quietvale morning light vs institutional office-drone of Hills/Archives. Filing cabinets, stamps, binders, wrinkled celestial robes as recurring motifs. Materials: parchment, ink, wood, stone, metal stamps. Avoid pure cartoon or pure grimdark; tired realism with dry humor.

## 9.2 Characters & creatures — models
| Asset ID | Description | Poly budget | Textures | Rig | Priority | Source (AI gen / human / stock) |
|----------|-------------|-------------|----------|-----|----------|----------------------------------|
| CH_PC1 | Player body + idle/walk/run/attack | ≤20k tris | A/N/M | Yes | P0 | AI gen / human |
| CH_Wizard | Old Wizard companion + follow anims | ≤20k | A/N/M | Yes | P0 | AI gen / human |
| CH_Companion2 | 1 additional companion placeholder | ≤20k | A/N/M | Yes | P0 | Placeholder OK |
| CH_Bureaucrat | Unique celestial bureaucrat | ≤20k | A/N/M | Yes | P0 | AI gen / human |
| CH_Compliance | Compliance Officer | ≤15k | A/N/M | Yes | P1 | AI gen |
| CR_MisfiledSkeleton | Enemy + death | ≤10k | A/N/M | Yes | P0 | AI gen / stock |
| CR_InkBlot | Swarm enemy | Low | Simple | Simple | P1 | AI gen |
| CR_PaperElemental | Mini-boss | Higher | A/N/M | Yes | P2 | AI gen |
| CR_StampGolem | Optional boss | Higher | A/N/M | Yes | P2 | AI gen |

## 9.3 Props / vehicles / weapons
| Asset ID | Description | Budget | Priority | Source |
|----------|-------------|--------|----------|--------|
| PR_Binder | Prophecy Binder (world + UI art) | Low | P0 | AI / human |
| PR_FilingCabinet | Hills / Archives modular | Medium | P0 | AI / kit |
| PR_Desk | Bureaucrat / annex desks | Low | P0 | AI |
| PR_Forms | Loose forms, stamps, receipts | Low | P0/P1 | AI |
| WP_BasicMelee | Player starter weapon | Low | P0 | AI |

## 9.4 Environment kits
| Kit ID | Biome/Region | Modular pieces needed | Priority |
|--------|--------------|----------------------|----------|
| ENV_Quietvale | Starter village | House interior/exterior, square, gate, woods path, 1 tree set, 2 NPC placeholders | P0 |
| ENV_Hills | Bureaucracy Hills | Ground, filing-cabinet props, desk props, path, 1 annex exterior | P0 |
| ENV_Forest | Forest of Unhelpful Trees | Trees with faces / passive-aggressive props | P2 |
| ENV_City | City of Forms | Concentric district kits | P2 |
| ENV_Archives | Overflow Archives | Multi-level stacks, unsorted wing, reading room | P2 |
| ENV_Ruins | Ruins of Previous Chosen Ones | Melancholy memorial | P2 |
| ENV_Final | Final Administrative Zone | Arena + departmental zones | P2 |

## 9.5 Materials & textures
| Mat ID | Type | Maps needed (A/R/M/N/E) | Resolution | Shared? |
|--------|------|-------------------------|------------|---------|
| MAT_Parchment | UI / Binder / forms | A / N / M | 1k–2k | Yes |
| MAT_Wood | Quietvale / desks | A/R/M/N | 1k–2k | Yes |
| MAT_MetalStamp | Stamps / Officers | A/R/M/N | 1k | Yes |
| MAT_Ink | VFX / enemy | A / E | 512–1k | Yes |

## 9.6 UI / HUD / icons
| UI ID | Description | Priority |
|-------|-------------|----------|
| UI_Health | Health bar | P0 |
| UI_Interact | Interact prompt | P0 |
| UI_QuestTracker | Parchment-styled tracker (main bold, side below, stamp on complete, “Amendment Pending” tag) | P0 |
| UI_Binder | Open-binder layout (left original + strikethroughs, right amendments, Reliability Rating, Guidebook cross-ref) | P0 |
| UI_MainMenu | Title + New Game / Continue / Load / Options / Quit; slots show region, playtime, status; empty = “Empty – Awaiting Documentation.” | P0 |
| UI_DamageFlash | Hit feedback | P0 |

## 9.7 VFX
| FX ID | Description | Priority |
|-------|-------------|----------|
| FX_Hit | Basic hit | P1 |
| FX_Death | Enemy death | P1 |
| FX_AmendmentStamp | Stamp impact on Binder / mid-combat | P1 |
| FX_BureaucratPop | Soft pop of displaced air | P0 |

**Pipeline link:** Text/Image→3D (Luma/Meshy/Tripo) + Blender tools + 3D Screenshots + ArtDirector + QA Art/3D

---

# 10. AUDIO ASSET LIST — [AI + HUMAN]

## 10.1 Voice
| Line set ID | Character | Approx # lines | Tone | Priority | TTS / human |
|-------------|-----------|----------------|------|----------|-------------|
| VO_Bureaucrat | Celestial Bureaucrat | Opening + amendments + climax | Tired, precise | P0 (text + key lines) | TTS / human |
| VO_Wizard | Old Wizard | Banter + personal + key scenes | Cynical, weary | P0 (banter ≥3) | TTS |
| VO_Guidebook | Guidebook | ≥8 entries + secret line | Flat, superior, institutional | P0 | TTS |
| VO_Companions | Sorceress / Rogue / Warrior | Banter pairs | Role-appropriate | P1 | TTS |
| VO_Officer | Compliance Officer | Inspect / barrage lines | Near-monotone formal | P1 | TTS |
| VO_Narrator | Narrator (audiobook / trailer) | Key story beats | Calm, slightly dry | P1 (trailer) | TTS / human |

Cast suggested: Narrator (calm dry) · Player (reluctant) · Bureaucrat (tired precise) · Wizard (ancient weary) · Sorceress (crisp) · Rogue (light amused) · Warrior (straightforward warm) · Guidebook (flat superior) · Officer (monotone formal).

## 10.2 Music
| Track ID | Use (title/explore/combat/boss) | Length | Mood | Priority |
|----------|----------------------------------|--------|------|----------|
| MUS_Quietvale | Explore / morning | Loop | Sparse, almost none | P1 |
| MUS_Hills | Explore institutional | Loop | Low office-drone | P1 |
| MUS_Combat | Light combat | Short loop | Restrained | P1 |
| MUS_Boss | Final Administrative Zone | Multi-phase | Restrained tension + seal motifs | P2 |
| MUS_Secret | Secret ending | Short | Near silence + low drone → unresolved note | P2 |
| MUS_Menu | Main menu / stinger | Short | Institutional | P1 |

## 10.3 SFX
| SFX ID | Event | Priority |
|--------|-------|----------|
| SFX_Footsteps | Player / companions | P0 |
| SFX_AttackSwingHit | Combat | P0 |
| SFX_EnemyHitDeath | Combat | P0 |
| SFX_UIClick | UI | P0 |
| SFX_BureaucratPop | Appearance / vanish | P0 |
| SFX_AmbientQuietvale | Morning birds | P0 |
| SFX_AmbientHills | Office-drone / distant stamping | P0 |
| SFX_Stamp | Amendment / form stamp | P0 |
| SFX_Paper | Binder / forms | P1 |

## 10.4 Mix targets
Dialogue vs music vs SFX levels / LUFS goals:
> Dialogue peak ≈ –12 dBFS. Secret ending seal layers relative to dialogue: Base Sub-Drone –38 to –42 dB · Prophetic Continuity –28 idle / –22 speaking · Narrative Oversight –30 idle / –18–20 speaking · Celestial Compliance –26 idle / –20 speaking · Destiny Affairs –32 → –36. Full silence (1.5–3.5 s) before Guidebook honest line. Soft unresolved note under 47-C reveal; fades into ordinary morning birds.

**Pipeline link:** Audio & Video Gen tool + Kokoro TTS + QA Audio

---

# 11. TECHNICAL PLAN — [AI + HUMAN]

## 11.1 Engine / framework — [HUMAN] **REQUIRED**
Pick **one primary engine** before production run Stage 4 (ASSEMBLY). Secondary DCC tools are optional.

| Choice | Check one |
|--------|-----------|
| Godot 4.x | [ ] |
| Unity | [x] |
| Unreal Engine | [ ] |
| Custom / other | [ ] (name: __________) |

**Primary engine:** Unity  
**Editor version (required):** Unity 6 or latest LTS + URP  
**Why this engine (short):** Source package and Team Starter Pack specify Unity (LTS or 6) + URP, Input System, Cinemachine, TextMeshPro, AI Navigation, DOTween. Matches week-by-week prototype plan and existing code structure prototypes (ScriptableObject QuestTemplate, ReputationManager, SaveSystem JSON, etc.).  
**DCC / support tools (optional):** Blender [x] · other: Aseprite (UI), Audacity / DAW (audio)  
**Pipeline binding:** Unity → `tools/unity/` · Blender assets → `tools/blender/` · Text/Image→3D + 3D Screenshots tools available.

## 11.2 Target frame rate & resolution per platform
| Platform | FPS | Res / dynamic res | Graphics tier |
|----------|-----|-------------------|---------------|
| Windows | 60 | 1920×1080 target; scale down for min spec | URP medium/high |

VSync off for testing. Stable framerate on minimum target spec in Quietvale + Bureaucracy Hills required for slice acceptance.

## 11.3 Input maps
Keyboard/mouse / gamepad / touch / VR controllers:
> Keyboard/mouse + gamepad from day one. Move WASD / stick · Interact E / button · Sprint · Abilities · Open Binder · Open Quest Tracker. No VR or touch required.

## 11.4 Save system
What is saved, when, cloud or local:
> Local JSON + backup recovery + version field (Application.persistentDataPath). Save slots (3) show region, playtime, timestamp, short status. Autosave on region transition / tutorial gate. Round-trip required: save in Hills → quit → load → correct position, quests, inventory, amendment list. Version field for future migration.

## 11.5 Scene / streaming strategy
> Scene list (slice): 0 Boot (managers) · 1 MainMenu · 2 Quietvale · 3 BureaucracyHills. Later regions additive. Addressables optional if content grows. No heavy streaming required for vertical slice.

## 11.6 Modding / data-driven content (optional)
> Heavy use of ScriptableObjects (QuestTemplate + QuestGenerator, ItemTemplate + ItemGenerator, dialogue, amendments, enemies). Procedural systems support side content without touching authored main path. Data-driven enough for future expansion / light modding of templates.

**Pipeline link:** TechLead agent + Unity tools + export_targets.md

---

# 12. VERTICAL SLICE DEFINITION — [HUMAN REQUIRED]

## 12.1 Slice must include
- [x] Playable start → goal → end
- [x] One complete core-loop demonstration
- [x] Listed P0 assets only
- [x] One QA pass with no critical blockers

Exact slice description:
> New Game → complete Quietvale (all 10 tutorial steps: wake, exit, square, Bureaucrat, Binder, path, first enemy, ability, tracker, leave gate) → Bureaucracy Hills end-to-end (critical path + 1 side quest + 1 full amendment delivery) → 2 companions functional (Old Wizard + 1 other) with follow + ≥3 banter lines each → Guidebook ≥8 entries → Inventory ≥5 items → Prophecy Binder UI (original + ≥1 amendment) → Quest Tracker live → Save/Load round-trip → Main menu New Game + Continue/Load.  
> Feel: tone clear in first 10 minutes; combat 10–25 s readable; no soft-locks; stable FPS; no placeholder/debug strings on critical path in release configuration.

## 12.2 Slice success criteria
> Acceptance Test:  
> 1. New Game → finish Quietvale → Binder + tutorial flags correct.  
> 2. Hills → amendment → side quest → loot procedural item.  
> 3. Save → quit → load → state intact.  
> 4. ≥3 companion/Guidebook lines fire.  
> 5. Die once, respawn correctly.  
> 6. Reach end of Hills critical path with zero critical console errors.  
> Definition of Done: All above pass on a clean player build (not only Editor). Version tag: UnreliableProphecy_v0.5.0_VerticalSlice. Known-issues list published with no Critical/High blockers.

## 12.3 Slice exclusion list
> Forest, City, Archives, Ruins, Final Zone; full companion roster; personal quests; New Game+; secret ending; full reputation UI; final boss; full music implementation; heavy VFX polish.

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
| Levels (8) | Genre pipeline agents (Adventure) | QA Design |
| 3D assets (9) | Text/Image→3D + Blender + Screenshots | QA Art/3D |
| Audio (10) | Audio tool + Kokoro | QA Audio |
| Tech (11) | TechLead | QA Build |
| Slice (12) | Orchestrator | QA Build + QA Gate |
| Engine (1.6 / 11.1) | TechLead + engine pipeline (Unity) | Must be set before ASSEMBLY |
| Exports (14) | Export pipeline | QA Export |

**Loop rule:** PLAN → ACT → CHECK → QA → HANDOFF (Tight Agent Loop tool)

---

# 14. EXPORT MATRIX — [HUMAN selects, AI fills constraints]

| Platform | In scope? | Input | Res/FPS target | SDK available? | Status (PREP_ONLY / BUILD) |
|----------|-----------|-------|----------------|----------------|----------------------------|
| Windows | Yes | KBM + Gamepad | 1920×1080 / 60 | n/a | BUILD (primary) |
| Linux | No (post-slice) | — | — | n/a | PREP_ONLY |
| Android | No | — | — | — | PREP_ONLY |
| Quest 2 | No | — | — | — | PREP_ONLY |
| Quest 3 | No | — | — | — | PREP_ONLY |
| PS4 VR | No | — | — | — | PREP_ONLY |
| PS5 VR | No | — | — | — | PREP_ONLY |
| PS3 | No | — | — | legacy | PREP_ONLY |

Per-platform notes:
> Primary: Windows standalone x86_64. Build Settings: Boot, MainMenu, Quietvale, BureaucracyHills. Output: Builds/Windows/v0.5.0_VerticalSlice/. Zip + README with controls and known issues. Development Build only for internal; uncheck for acceptance.

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
| Scope creep beyond Quietvale + Hills | High – delays slice | Medium | Hard exclusion list; P0-only asset list | Human / Orchestrator |
| Tone drift into slapstick | Medium – breaks pillar | Medium | Pillar tests + Narrative QA gate | NarrativeWriter + QA |
| Companion AI / banter timing issues | Medium – feels empty | Medium | Cooldown + priority system already designed; ≥3 lines required | Systems + Narrative |
| Save/Load state incompleteness | Critical – fails acceptance | Medium | Explicit round-trip test in acceptance script | TechLead |
| Amendment mid-combat interruption feel bad | Medium – breaks comedy | Low–Med | Scripted delivery + mechanical effect tested in slice | Systems + Narrative |
| Performance in Hills with props | Medium | Low | URP + poly budgets; FPS gate in acceptance | TechLead / Art |
| Procedural quest generation produces nonsense | Low–Med | Medium | Template validation + human review of generated content | QuestDesigner |

---

# 17. MILESTONES — [HUMAN]

| Milestone | Date | Exit criteria |
|-----------|------|---------------|
| Package approved | 2026-08-23 | HUMAN sign-off on sections 1, 2, 12 (this document) |
| Vertical slice playable | End Week 7 | Section 12 criteria + v0.5.0_VerticalSlice tag + no Critical/High |
| Content complete (v1) | TBD post-slice | All P0 missions + assets for full 7 regions + 5 companions + 3 endings |
| Release candidate | TBD | QA gate ALLOW_DELIVERY |

Week-by-week prototype plan (from GDD):  
Week 1: Project setup, third-person controller, camera, basic interaction, health  
Week 2: Combat, enemy, dialogue system, opening scene, first quest  
Week 3: Quest tracker UI, Prophecy Binder start, first companion, Bureaucrat appearance  
Week 4: Compliance Officers, inventory, City of Forms blockout, more companions  
Week 5: Department of Previous Failures, Binder UI, save/load, side quests  
Week 6: Final Administrative Zone blockout, multi-phase boss, ending choice  
Week 7: Full playthrough, polish, both endings, personal quests, known-issues list  

(Note: Vertical slice stops at Quietvale + Bureaucracy Hills; later weeks expand.)

---

# 18. HUMAN CREATOR ONLY — FINAL SIGN-OFF

| Question | Answer |
|----------|--------|
| I approve the pillars and scope | YES (locked from source Complete Package) |
| I approve the vertical slice definition | YES (definitive criteria from Final Production Pack) |
| I accept listed out-of-scope items | YES |
| Supervision frequency | every handoff (recommended for Jayson beta first run) |
| Name / date | Creator / 2026-08-23 (package filled for Jayson 2.0 beta) |

---

# 19. AI EXECUTION BRIEF (paste to Jayson)

When this package is filled enough to start, give Jayson:

```
Load production package: projects/unreliable_prophecy/PRODUCTION_PACKAGE.md
Genre pipeline: Adventure
Start orchestrator with supervision mode: human-in-the-loop
Begin Stage 1. Use Tight Agent Loop. QA gate every handoff.
Expand only [AI] sections; do not change [HUMAN] decisions without asking.
Primary engine: Unity (6 or latest LTS + URP). Target: Windows vertical slice (Quietvale + Bureaucracy Hills).
Priority: prove tone, core loop, Binder + amendment, 2 companions, save/load, no critical blockers.
Version target: UnreliableProphecy_v0.5.0_VerticalSlice
```

---

# 20. APPENDIX — MINIMUM FILL TO START

Completed (exceeds minimum):
- 1.1 Pitch ✓
- 1.3 Genre ✓
- 1.5 Platforms ✓
- 1.6 / 11.1 Engine ✓
- 1.7 Scope guardrails ✓
- 2.1 Pillars ✓
- 12.1–12.2 Vertical slice ✓
- 18 Sign-off ✓

Everything else expanded from the Unreliable Prophecy Complete Package for immediate Jayson consumption.

---

**Source documents used**
- Unreliable_Prophecy_Game_Design_Document.pdf (v1.0)
- Unreliable_Prophecy_GDD_Expanded.pdf (v1.1)
- Unreliable_Prophecy_Final_Production_Pack.pdf
- Unreliable_Prophecy_Production_Detail.pdf
- Unreliable_Prophecy_Completeness_Supplement.pdf
- Unreliable_Prophecy_Team_Starter_Pack.pdf
- Trailer 10s shot list (included in Final Production Pack)

**End of filled PRODUCTION_PACKAGE.md for The Unreliable Prophecy**
