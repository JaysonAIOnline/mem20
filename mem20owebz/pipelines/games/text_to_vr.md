# Text → VR Experience Pipeline

Convert a text concept into a VR-safe design package (Quest / PSVR-class targets).

## Inputs
- Experience brief + comfort requirements
- Target headset(s) from export matrix
- Locomotion preference (teleport / smooth / hybrid)

## Stages
1. **Comfort & safety** — locomotion, vignette, height calibration, guardian/play space
2. **Interaction model** — controllers, hands, UI in-world vs panel
3. **Scene graph** — rooms/spaces at real-world scale
4. **Performance budget** — poly/draw call targets per headset
5. **UI in VR** — diegetic vs floating panels; gaze/point select rules
6. **Audio spatial plan** — critical cues must be localizable
7. **Onboarding** — first 60 seconds teach controls without text walls
8. **Asset list** — optimized meshes, baked lighting policy
9. **QA Export + comfort checklist**
10. **Handoff** to TechLead / QA Build

## Output artifacts
- `vr_comfort_spec.md`
- `vr_interaction_map.md`
- `vr_scene_graph.json`
- `vr_perf_budget.md`
- `vr_onboarding_script.md`
- QA Export report

## Hard rules
- Never assume desktop FPS camera rules
- Prefer sitting/standing modes documented
- Mark PREP_ONLY if platform SDK not available
