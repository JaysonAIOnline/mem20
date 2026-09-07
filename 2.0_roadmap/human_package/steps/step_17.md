# Step 17 — Beta Program & Rollout

**Type:** human (plan/templates). **Goal:** a controlled beta that exercises the
2.0 safety + cognitive-depth features before GA.

## Deliverables (templates)
1. **Beta charter:** scope (grounded recall, simulation fence, causal `do()`),
   duration (4 wks), success bar (0 contamination incidents in beta).
2. **Selection criteria:** 5–10 teams running stdio-MCP agents with memory pain
   (from Step 15 criteria).
3. **Feature-flag rollout plan:** ship `do()`/`counterfactual()` + `SelfModel`
   behind `MEM20_FLAG_WORLDMODEL_20=1`; default off for 1.0-compatible GA.
4. **Support playbook:** how to read `/metrics`, how to file a contamination report.

## Engineering input available now
- `MEM20_FLAG_*` pattern is the mechanism (defined in `instrumentation_plan.md`).
- `/metrics` + `audit_contamination()` are the beta health signals.

## Not executable by agent
Recruiting/seating beta customers and running the program needs a PM + support.
