# Step 18 — Change Management & Enablement

**Type:** human (templates). **Goal:** users adopt 2.0 without breaking 1.0 flows.

## Deliverables (templates)
1. **Enablement curriculum:** (a) what's new in 2.0, (b) grounded vs simulated
   mental model, (c) reading `/metrics`, (d) safety guarantees from ADR-0002.
2. **Support doc set:** deploy with systemd, health-probe wiring, troubleshooting.
3. **FAQ:** "Will my 1.0 tools break?" (no — 97-tool surface stable); "Can
   simulated memories leak into recall?" (no — firewall + CLEAN audit).
4. **Internal briefing:** one-pager for stakeholders (contamination = 0, uptime
   probe live).

## Engineering input available now
- `README.md`, `proof/audit_response.md`, `2.0_roadmap/README.md` are the source
  material for the curriculum.
- The two shipped zips (`MEM20-Final-RC.zip`, `MEM20-Production-RELEASE-ENDUSER.zip`)
  are the enablement artifacts.

## Not executable by agent
Running training and writing final customer-facing copy needs enablement/tech-comm.
