# Step 14 — Detailed Scope Definition & Epic Breakdown

**Type:** engineering. **Status:** DONE (`epic_breakdown.md` produced).

## Deliverables
- **5 epics** (E1 Safety … E5 Docs) with stories + codebase anchors.
- **Dependency matrix** and **DoR/DoD**.
- Maps directly to Step 12 themes and Step 10 tech-debt items.

## Key scope decisions
- Net-new 2.0 engine behavior limited to E3 (world-model `do()`/`counterfactual()`
  + self-model continuity) — already prototyped in `memory_engine/memory.py`.
- **Deferred:** exposing E3 via new MCP tools. User explicitly rejected adding
  MCP tools for 8.1; surface via engine API + a 2.0 tool module only if Step 08
  validates demand. This keeps the 97-tool surface stable for 1.0.
- Integrations (E4) stay Blender/Unity; Figma waits on Step 09 spec.

## Engineering tie-in
All DONE/TODO states in `epic_breakdown.md` are current vs. the live tree.
