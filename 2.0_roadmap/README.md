# mem20 2.0 Roadmap — Deliverables

Source: `/home/jayson/Desktop/2.0_Roadmap_Steps_08-20.zip` (steps 08–20).

This directory contains the deliverables for the 2.0 product roadmap. Each step
file (`step_XX.md`) holds the concrete artifacts for that step, grounded in the
current mem20 codebase (`mcp/`, `cog/`, `memory_engine/`). Steps that are
human/organizational activities (user research, GTM, beta, launch) are delivered
as **instruments and plans** (templates, guides, charters) rather than executed
results — those require real participants and cannot be performed by an agent.

## Index

| Step | Title | Type | Deliverable |
|------|-------|------|-------------|
| 08 | User Research & JTBD | human | `step_08.md` (interview guide, JTBD survey, persona + opportunity-map templates) |
| 09 | Competitive Benchmarking | human | `step_09.md` (feature/outcome matrix, white-space report templates) |
| 10 | Architecture Review & Scalability Audit | **engineering** | `step_10.md` + `adr/` + `tech_debt_register.md` |
| 11 | Outcome & Metrics Framework | **engineering** | `step_11.md` + `metrics_framework.md` |
| 12 | Prioritization & Themes | **engineering** | `step_12.md` + `prioritization.md` |
| 13 | Experience Vision & Prototyping | human/design | `step_13.md` (north-star narrative, prototype test plan) |
| 14 | Scope & Epic Breakdown | **engineering** | `step_14.md` + `epic_breakdown.md` |
| 15 | GTM & Positioning | human | `step_15.md` (positioning, launch narrative, beta criteria) |
| 16 | Instrumentation & Feedback Loop | **engineering** | `step_16.md` + `instrumentation_plan.md` (implemented in `mcp/health.py` `/metrics`) |
| 17 | Beta Program & Rollout | human | `step_17.md` (beta charter, feature-flag plan) |
| 18 | Change Management & Enablement | human | `step_18.md` (enablement curriculum, FAQ) |
| 19 | Launch & 30-Day Hypercare | human | `step_19.md` (launch runbook, hypercare process) |
| 20 | Post-Launch Learning & 2.1 Plan | human | `step_20.md` (learning report, next-horizon skeleton) |

## Engineering work already landed for this roadmap
- **Step 10**: modular MCP decomposition (`server.py` + per-domain mixins), no file > ~1.8k lines.
- **Step 11 / 16**: `/health` `/ready` `/metrics` endpoint with event taxonomy
  (`tool.call`, `tool.success`, `tool.error`), per-tool call/error counters, request
  totals, and `memory_system_available` flag.
- **Step 12**: epic breakdown ties each 2.0 theme to a codebase workstream.

## How to consume
- Product/design: read the `step_*.md` deliverables and the templates; execute the
  human steps with real participants.
- Engineering: read `adr/`, `tech_debt_register.md`, `epic_breakdown.md`,
  `instrumentation_plan.md`; the metrics endpoint is live and queryable.
