# Final Polish Team — 94%+ Fidelity to Production Package

After content is “complete,” run this campaign before delivery/export.

## Goal
Average fidelity **≥ 94%** to the filled `PRODUCTION_PACKAGE` with **zero Critical** gaps.

## Team
| Agent | Focus |
|-------|--------|
| FidelityAuditor | Score every section vs package |
| ConsistencyEditor | Canon / naming / continuity |
| SystemsBalancer | Loop & numbers |
| NarrativePolisher | Story / quests / tone |
| ArtAssetAuditor | P0 meshes, mats, UI art |
| AudioAuditor | VO / music / SFX |
| LevelFlowAuditor | Levels / tracks / soft-locks |
| UIUXAuditor | HUD / menus |
| VRComfortAuditor | VR-only targets |
| ExportReadiness | Platform matrix |
| IntegrationLead | Prioritize rework |
| QAGateCaptain | Final ALLOW / BLOCK |

## Protocol
1. `start_final_polish` with package summary + deliverable inventory  
2. Score each major section with `score_fidelity`  
3. Rework gaps using Tight Agent Loop + specialist agents  
4. `polish_round_summary` each round  
5. Repeat up to max rounds  
6. `qa_gate` only when average ≥ 94% and no Criticals  

## Related pipelines
- Text → Level: `text_to_level.md`
- Text/Image → UI: `text_image_to_ui.md`
- Text → VR: `text_to_vr.md`
- Export: `export_targets.md`
- QA tool: `qa_agents_tool.py`
