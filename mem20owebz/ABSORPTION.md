# mem20owebz — Absorption Plan (phase 04, hypo-map-1)

**Status:** IN PROGRESS (green-lit by Jayson 2026-09-10 — "start #04 on the map, remember to transfer all features not found to mem20")
**Source:** `/home/jayson/Desktop/jayson-openwebui` (to be REMOVED from disk once verified — hard requirement, Jayson 2026-09-07)
**End-state rule:** ONLY `/opt/mem20` remains; every absorbed capability lives inside `/opt/mem20`. Keys read ONLY from `/opt/mem20/secrets/.env`.

## 1. Live stack snapshot (2026-09-10, before re-home)

| Component | How it runs | Port | PID/service | Data |
|---|---|---|---|---|
| Open WebUI (docker) | `ghcr.io/open-webui/open-webui:main` | 3000→8080 | `jayson.service` (oneshot, compose full.yml) | volume `jayson-data` |
| Open WebUI (native, STRAY duplicate) | `python3 -m uvicorn open_webui.main:app` | 8080 | pid 20797 | unknown/own store |
| LiteLLM bridge | `ghcr.io/berriai/litellm:main-latest` | 4000 | container `jayson-bridge` | Postgres 16 `jayson-db` (5432) + volume `bridge-usage` |
| Kokoro TTS | `ghcr.io/remsky/kokoro-fastapi-cpu` | 8880 | container `jayson-tts` | volume `tts-cache` |
| Postgres 16 | `postgres:16` | 5432 (internal) | container `jayson-db` | volume `bridge-db` |
| Ollama | native | 11434 | native | local models |

Bridge serves ~42 models via `bridge/litellm_config.yaml` (aliases: fast/balanced/strong + per-provider model names across Gemini, Groq, DeepSeek, AnyAPI, HuggingFace, Cloudflare, DashScope/Qwen, Mistral, xAI, Azure, AWS Bedrock, OCI, etc.).

## 2. Feature inventory — what this stack has that mem20 did NOT own before

Per Jason's instruction, EVERY feature below gets a home inside mem20 before the old install is removed.

### 2.1 Chat front-end (the point of phase 04)
- Open WebUI as the user-facing WebUI over mem20 backends — absorb by HOSTING under `/opt/mem20` (kept as-is, rebranded to mem20, wired to mem20 secrets). NOT re-implemented: this is the phase-04 charter ("keep as the user-facing WebUI").

### 2.2 Model gateway (LiteLLM)
- `bridge/litellm_config.yaml`: 20+ model routes, aliases, usage tracking on Postgres. → re-homed verbatim; reads keys from `/opt/mem20/secrets/.env`.
- `bridge/usage_summary.py`: usage reporting helper. → re-homed, wired to db from secrets.

### 2.3 Open WebUI pipelines + tools (the repo's OWN IP — features already partly present in mem20? audit needed)
- `tools/` (132 files): `openwebui_tools/` (10 tools: 3d_screenshots, video_understanding, accessibility, storyline_maker, agent_loop_tight, text_image_to_3d, status_dashboard, store_listing, audio_video_gen, production_run_orchestrator), plus `audio/`, `blender/`, `godot/`, `unity/`, `skill_pipelines/`, `production-pipeline-runner/`, `release/`.
- `pipelines/` (22 files): games (14 pipeline docs incl. godot_pipeline, godot_export, text_to_level, production_run, genre_pipelines, modding_dlc, export_targets, asset_assembly, text_to_vr, save_load_settings, localization, store_listing, accessibility, analytics_events, final_polish), `video_understanding/pipeline.py`, `3d_screenshots/pipeline.py`, `image_to_3d.md`, `rpg_orchestration.md`.
- `agents/` (11 framework guides): autogen, mem20 crews, mem20 graph substrate, llamaindex, mastra, openai-agents-sdk, mem20 claw plugin, openwebui-computer, pydantic-ai, smolagents.
- `tts/`, `resource_bridge/`, `scripts/`, `ci/` (godot-export.yml), `examples/` (simple_agent_loop.py), `blender/` (example_tools.py).
- Branding: `custom.css`, `logo.svg`, `logo.png`.
- Docs: GUIDE, CAPABILITIES, DEPENDENCIES, ORCHESTRATION_AND_TOOLS, JAYSON1.0/2.0, MASTER_BETA_REFERENCE, FIRST_GAME_WALKTHROUGH, CLOUD_ASSEMBLY, ADVANCED, EXAMPLES, MEM20_INTEGRATION, INTEGRATION, CHECKPOINT, CREDITS, PIPELINE_NOTES, pipeline_progress.
- `projects/unreliable_prophecy`: Unity game project (861M incl. Library/ — re-home SOURCE ONLY, exclude regenerable Library/).

### 2.4 Secret sprawl (cross-cutting, phase 06 — done EARLY per map)
Sources: `/root/.env` (46 keys), `/home/jayson/Desktop/jayson-openwebui/.env` (35 keys), mem20 `llm.py` `_ENV_CANDIDATES`, hardcoded in `docker-compose.full.yml` (WEBUI_SECRET_KEY, bridge master_key, Postgres pw). → all consolidated into `/opt/mem20/secrets/.env`; every piece reads from there. CHECKPOINT.md warns most jayson-.env values are PLACEHOLDERS — `/root/.env` is authoritative on conflict.

## 3. Execution steps (each verified before the next)

1. ✅ Recon + audit (this doc).
2. Scaffold `/opt/mem20/mem20owebz`; re-home content (compose, bridge, pipelines, tools, agents, branding, docs; projects source-only).
3. Build `/opt/mem20/secrets/.env` = union(/root/.env wins, jayson .env fills gaps) + app secrets (WEBUI_SECRET_KEY, LITELLM_MASTER_KEY, POSTGRES pw) → 600 perms.
4. Rewrite mem20-hosted `docker-compose.yml` (canonical = old `full.yml`): reuse existing named volumes (`jayson-data`, `bridge-usage`, `bridge-db`, `tts-cache`) and container names so it is a DROP-IN swap; `env_file` from secrets; `WEBUI_NAME=mem20`.
5. Swap services: stop+disable `jayson.service`; `docker compose down` old (no volume removal); create `mem20owebz.service` (oneshot, RemainAfterExit) pointing at `/opt/mem20/mem20owebz`; `up -d`; healthcheck.
6. Verify end-to-end: webui :3000 serves mem20-branded UI; bridge :4000 serves ~42 models with a real `POST /v1/chat/completions` through it; TTS :8880 up; ollama untouched. THEN cleanup.
7. Cleanup: kill stray native :8080 open_webui; `rm -rf /home/jayson/Desktop/jayson-openwebui`; no lingering process/py/systemd refs. Update map phase 04 → completed; record in mem20agentz/docs/PLAN.md; save to mem20.

## 4. Proof of "all features transferred"
Copy is byte-identical where possible; post-copy `diff` against source for text dirs before deletion is the verification gate (documented in PLAN.md §8).