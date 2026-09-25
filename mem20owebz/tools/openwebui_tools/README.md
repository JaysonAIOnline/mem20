# Open WebUI Tools — paste into Admin → Functions / Tools

## Core factory

| File | Purpose |
|------|---------|
| `production_run_orchestrator_tool.py` | Force idea→game stages; advance only on QA PASS |
| `agent_loop_tight_tool.py` | PLAN → ACT → CHECK → HANDOFF |
| `qa_agents_tool.py` | Inspect before delivery |
| `final_polish_team_tool.py` | ≥94% fidelity vs package |
| `rpg_orchestrator_tool.py` | RPG stage handoffs |
| `status_dashboard_tool.py` | Snapshot for `scripts/status_dashboard.py` |

## Creative

| File | Purpose |
|------|---------|
| `storyline_maker_tool.py` | Story structure |
| `text_image_to_3d_tool.py` | Text/Image → 3D |
| `3d_screenshots_tool.py` | Mesh → shots + description |
| `video_understanding_tool.py` | Video → transcript + keyframes |
| `audio_video_gen_tool.py` | Speech / audio scenes / video plan |

## 2.0-beta1 extras

| File | Purpose |
|------|---------|
| `accessibility_tool.py` | A11y inspect |
| `store_listing_tool.py` | Store copy draft |
| `resource_bridge_tool.py` | Where artifacts live (catalog; service in 3.0) |

## Install
1. Admin → Functions / Tools → New  
2. Paste **entire** file  
3. Save and enable  

TTS: point Audio at Kokoro in the full compose stack.
