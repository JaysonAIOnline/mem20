# Text → Level Generator Pipeline

Turn a written description into a structured, buildable level package.

## Inputs
- Level brief (from Production Package §8 or free text)
- Genre constraints (FPS / TPS / Adventure / Open World / Racing)
- Performance budget (platform from export matrix)

## Stages
1. **Parse brief** — extract goals, mood, encounters, secrets, traversal
2. **Space graph** — rooms/zones/nodes + connections + chokepoints
3. **Encounter placement** — recipes from package + difficulty curve
4. **Landmark & readability pass** — player never lost for >N seconds
5. **Cover / race line / puzzle verbs** — genre-specific layer
6. **Asset request list** — props, kits, lights tied to Asset IDs
7. **Blockout spec** — dimensions, heights, sightlines (engine-agnostic)
8. **QA Level** — `qa_inspect(deliverable_type="level")`
9. **Handoff** to TechLead / ArtDirector

## Output artifacts
- `level_<id>_graph.json`
- `level_<id>_blockout.md`
- `level_<id>_encounters.json`
- `level_<id>_asset_pull_list.csv`
- QA report

## Agent roles
LevelDesigner → EncounterDesigner → ArtDirector (kit bash) → QA Design → TechLead
