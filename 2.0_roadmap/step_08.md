# Step 08 — Deep User Research & JTBD

**Type:** human (instrument). **Goal:** understand who relies on mem20 and the
jobs they hire it for, before committing 2.0 scope.

## Deliverables (provided as instruments — execute with real participants)
1. **Interview guide** (8–10 semi-structured questions): when do you reach for
   mem20; what fails today; how do you trust a recalled memory; what would make
   you stop using it; where does it fit your stack.
2. **JTBD one-line template:** "When [situation], I want to [motivation], so I
   can [outcome]." Capture 25–40 responses.
3. **Persona template:** role, memory scale, trust sensitivity, integration needs.
4. **Outcome Opportunity Map:** plot pain frequency × severity to rank jobs.
5. **Affinity-map template:** cluster verbatims into themes feeding Step 12.

## How engineering supports this step
- Export an anonymized **usage log** from `/metrics` (`tool_calls` per tool) to
  seed the "what do they actually use" half of the research — complements interviews.
- Provide a `MEM20_RESEARCH_EXPORT=1` flag (future) to dump per-session tool
  histograms without PII.

## Not executable by agent
Recruiting participants, conducting interviews, and affinity mapping require
human researchers. This file is the instrument set, not the results.
