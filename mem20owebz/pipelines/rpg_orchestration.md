# RPG Game Orchestrator — Pipeline & Agent Handoffs

Push a full RPG through specialist agents with clean handoffs.

## Agents

| Agent            | Responsibility                                      |
|------------------|-----------------------------------------------------|
| WorldBuilder     | Lore, map regions, factions, tone                   |
| SystemsDesigner  | Combat, progression, economy, skills                |
| QuestDesigner    | Main quest, side content, NPCs, pacing              |
| NarrativeWriter  | Dialogue, scenes, descriptions, codex               |
| ArtDirector      | Visual pillars, audio mood, UI direction            |
| TechLead         | Engine plan, vertical slice, milestones             |
| PlaytestLead     | Fun tests, balance, iteration backlog               |

## How to run

1. **Start the project**
   ```
   Use tool: start_rpg_project
   → project name + premise
   ```

2. **Give the first agent its prompt**
   ```
   Use tool: agent_prompt (WorldBuilder) + project context
   ```
   (Or use mem20 / mem20 claw plugin / mem20 crews with that role.)

3. **When the agent finishes a chunk**
   ```
   Use tool: handoff
   from_agent → to_agent
   summary + artifacts + blockers
   ```

4. **Repeat** until PlaytestLead loops back for expansions.

## Suggested agent backends

- Open WebUI multi-model chat (different system prompts per agent)
- mem20 crews crew with one agent per role
- mem20 graph substrate state machine (stage = node)
- mem20 / mem20 claw plugin for longer autonomous runs
- Sub-agents inside Open WebUI for parallel research

## Tie-ins to other Jayson tools

| Stage            | Also use                          |
|------------------|-----------------------------------|
| Narrative        | Storyline Maker                   |
| Art              | Text/Image → 3D, Luma, screenshots |
| Audio            | Audio & Video Gen + Kokoro TTS    |
| World / Quests   | Knowledge bases for continuity    |
| Tech             | Blender + Unity tools             |

## Vertical slice goal

Aim for one playable loop early:
- One region
- One combat encounter
- One short quest
- One character art pass
- Basic save / load plan

Then expand with more handoffs.
