# Worksheet — Launch Runbook & Hypercare (Step 19)

## Pre-flight (all must be green)
- [ ] `audit_contamination()` → `contamination_rate = 0.0`
- [ ] `curl /ready` → 200
- [ ] Deploy `MEM20-Production-RELEASE-ENDUSER.zip`
- [ ] `MEM20_FLAG_WORLDMODEL_20` set per beta decision (default OFF)

## Launch
- [ ] Promote RC → prod zip on both hosts.
- [ ] Announce (use `worksheets/gtm_positioning.md` narrative).
- [ ] Open `/metrics` watchboard.

## Hypercare — 30 days
Daily review from `/metrics`:
- [ ] `contamination_rate == 0.0` (else **rollback now**)
- [ ] `tool_errors_total / tool_calls_total < 0.01`
- [ ] `memory_system_available == true`

Rollback trigger: any contamination incident OR error rate > 1%.
Rollback action: redeploy `MEM20-Production-RELEASE-ENDUSER.zip` (prior stable).

## 30-day review agenda
- [ ] Metrics vs `metrics_framework.md` targets.
- [ ] Promote / demote `MEM20_FLAG_*` features.
- [ ] Write `worksheets/learning_report.md`.
