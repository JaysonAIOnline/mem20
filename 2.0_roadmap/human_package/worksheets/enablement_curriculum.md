# Worksheet — Enablement Curriculum (Step 18)

## Session 1 — What's new in 2.0 (30 min)
- Grounded vs simulated mental model (the firewall).
- Live `/metrics`: what to watch.
- Safety guarantees from `adr/0002-contamination-firewall.md`.

## Session 2 — Running mem20 (30 min)
- systemd deploy (`systemd/` unit).
- Health probes: `/health` `/ready` `/metrics`.
- Troubleshooting: contamination incident → rollback.

## Session 3 — For builders (45 min)
- Adding a tool (one domain module; see `README.md` "Adding a tool").
- Feature flags `MEM20_FLAG_*` for staged rollout.

## FAQ (publish)
- **Will my 1.0 tools break?** No — 97-tool surface is stable.
- **Can simulated memories leak into recall?** No — firewall + CLEAN audit.
- **Where's the proof?** `proof/audit_response.md`.

## Assets to publish
- `README.md`, `proof/audit_response.md`, `2.0_roadmap/README.md`,
  `human_package/HUMAN_PACKAGE.md`.
