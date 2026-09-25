# Game Genre Pipelines

Specialized stage flows that plug into the RPG Orchestrator pattern (or run standalone).

## Shared spine (all genres)
1. Concept & pillars
2. Core loop
3. Vertical slice
4. Content expansion
5. Systems hardening
6. QA gate
7. Export targets
8. Release candidate

---

## Racing
**Agents:** TrackDesigner → VehicleSystems → AIDirector → Progression → ArtAudio → Tech → QA

**Core loop focus:** corner → exit speed → risk/reward → upgrade → next track

**Key deliverables:**
- Track list + lap targets
- Vehicle classes & handling models
- Opponent rubber-band rules
- Career / unlock tree
- Ghost/replay requirements

**Vertical slice:** 1 track, 1 car class, 3 AI, race start→finish, simple upgrade

---

## 1st Person Shooter (FPS)
**Agents:** ArenaDesigner → GunplaySystems → EnemyDirector → Progression → Narrative (light) → ArtAudio → Tech → QA

**Core loop focus:** peek → engage → reposition → reload/resource → objective

**Key deliverables:**
- Movement & TTK targets
- Weapon roster + recoil identities
- Enemy archetypes
- Encounter budget per space
- Map flow diagrams

**Vertical slice:** 1 map, 3 weapons, 3 enemy types, one complete objective

---

## 3rd Person Shooter (TPS)
**Agents:** same as FPS + CoverDesigner + CameraSystems

**Extra focus:**
- Cover quality & blind-fire rules
- Camera collision / shoulder swap
- Melee vs ranged spacing
- Companion AI (optional)

**Vertical slice:** 1 hub + 1 combat space, cover set, 2 weapons, camera stable under fire

---

## Adventure
**Agents:** WorldBuilder → PuzzleDesigner → NarrativeWriter → InventorySystems → ArtAudio → Tech → QA

**Core loop focus:** explore → observe → use item/ability → revelation → new area

**Key deliverables:**
- Region map with gated paths
- Puzzle verbs (unique interactions)
- Critical path item chain
- Lore delivery method (environmental vs dialogue)

**Vertical slice:** 1 region, 3 puzzles, 1 key story beat, no soft-locks

---

## Open World
**Agents:** WorldBuilder → ActivityDesigner → SystemsDesigner → QuestDesigner → DensityDirector → ArtAudio → Tech → QA

**Core loop focus:** traverse → spot activity → engage → reward → new horizon

**Key deliverables:**
- Biome list + traversal tools
- Activity taxonomy (combat, social, collect, story)
- Density rules (how often something interesting appears)
- Fast travel & difficulty scaling
- Main story vs side content balance

**Vertical slice:** 1 biome, 1 traversal tool, 3 activity types, 1 story mission, day/night or weather optional

---

## Handoff rule
Every genre stage ends with:
1. `check_step` (Tight Agent Loop)
2. `qa_inspect` (QA suite)
3. `handoff` to next agent only on PASS / PASS_WITH_NOTES
