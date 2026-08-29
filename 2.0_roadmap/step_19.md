# Step 19 — Launch & 30-Day Hypercare

**Type:** human (runbook/templates). **Goal:** a safe GA + a hypercare window that
catches regressions fast.

## Deliverables (templates)
1. **Launch runbook:** pre-flight (contamination audit = 0, `/ready` = 200),
   deploy RC→prod zip, flip `MEM20_FLAG_WORLDMODEL_20` per beta plan, post on
   `/metrics`.
2. **Hypercare process (30 days):** daily contamination + error-rate review from
   `/metrics`; rollback trigger = any contamination incident OR error rate > 1%.
3. **Rollback plan:** redeploy `MEM20-Production-RELEASE-ENDUSER.zip` (1.0-stable).
4. **30-day review agenda:** metrics vs Step 11 targets; promote/demote flags.

## Engineering input available now
- `/health` `/ready` `/metrics` are the launch gates (ADR-0003).
- `audit_contamination()` is the hard rollback trigger (CLEAN 0.0 today).
- Both zips are built and on the Desktop.

## Not executable by agent
Executing the launch and watching the dashboard needs on-call/ops.
