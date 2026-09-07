# mem20 2.0 — Human Execution Package

**Purpose:** everything a human (PM, researcher, GTM, support, ops) needs to
*execute* the 2.0 roadmap. The agent already produced the engineering work and
the analysis docs; this package is the **action kit** for the steps an agent
cannot do (recruit users, interview, benchmark competitors, launch, run beta,
enable, learn).

## How to use this package
1. Read this file top-to-bottom once.
2. For each step below, open the linked `steps/step_XX.md` and the matching
   `worksheets/` template.
3. Execute the step using the template; fill it in; save your outputs.
4. Feed outputs back: research → prioritization, metrics → dashboards, beta →
   launch gates. The "Feeds back into" line tells you where results go.

## Step execution map (what YOU do)

| Step | You do | Instrument / template | Feeds back into |
|------|--------|-----------------------|-----------------|
| 08 User Research | Recruit 25–40 users; run interviews; affinity-map | `steps/step_08.md`, `worksheets/interview_guide.md`, `worksheets/jtbd_survey.md` | Step 12 (RICE), Step 13 (proto) |
| 09 Competitive | Map 3–5 competitors on the feature/outcome matrix | `steps/step_09.md`, `worksheets/competitive_matrix.md` | Step 15 (positioning), Step 12 |
| 13 Prototype | Build/run a clickable MCP-client mock; test 3 scenarios | `steps/step_13.md` | Step 14 (scope) |
| 15 GTM | Write positioning + launch narrative; set beta criteria | `steps/step_15.md`, `worksheets/gtm_positioning.md` | Step 17 (beta) |
| 17 Beta | Seat 5–10 beta teams behind `MEM20_FLAG_*`; watch `/metrics` | `steps/step_17.md`, `worksheets/beta_charter.md` | Step 19 (launch) |
| 18 Enablement | Run training; publish FAQ + support docs | `steps/step_18.md`, `worksheets/enablement_curriculum.md` | GA readiness |
| 19 Launch | Run the launch runbook; 30-day hypercare | `steps/step_19.md`, `worksheets/launch_runbook.md` | Step 20 (learning) |
| 20 Learning | Write the learning report; seed 2.1 | `steps/step_20.md`, `worksheets/learning_report.md` | 2.1 planning |

## Engineering steps (already done — you just consume the outputs)
- **10 Architecture** — `steps/step_10.md` + `adr/`, `tech_debt_register.md`. Read for risks.
- **11 Metrics** — `steps/step_11.md`, `metrics_framework.md`. The dashboards are fed by `/metrics`.
- **12 Prioritization** — `steps/step_12.md`, `prioritization.md`. Your research updates this.
- **14 Epic breakdown** — `steps/step_14.md`, `epic_breakdown.md`. What engineering will build.
- **16 Instrumentation** — `steps/step_16.md`, `instrumentation_plan.md`. `/metrics` is live; watch it.

## Hard gates you must respect (from engineering)
- **Contamination firewall**: simulated memory must NEVER reach grounded recall.
  `/metrics` `contamination_rate` must stay `0.0`. Any incident = rollback.
- **Eval safety**: world-model rules are AST-restricted; no arbitrary code runs.
- **Scope guard**: 8.1 (world-model `do()`/`counterfactual`, `SelfModel`) ships only
  behind `MEM20_FLAG_WORLDMODEL_20=1` per beta plan. Don't enable for GA without research sign-off.

## Quick start (this week)
1. `steps/step_08.md` → send `worksheets/jtbd_survey.md` to your user list.
2. `steps/step_09.md` → fill `worksheets/competitive_matrix.md` from public info.
3. Hand research results to engineering to refresh `prioritization.md` (RICE).

Everything else sequences from there. Questions → engineering owns the `adr/`
and `tech_debt_register.md`; you own the `worksheets/`.
