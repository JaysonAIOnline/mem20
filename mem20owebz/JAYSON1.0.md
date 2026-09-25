# Jayson 1.0 — Release Notes & System Map

Personal AI command center built across this design conversation.  
One place to talk, route models, run agents, make assets, orchestrate games, and gate delivery with QA.

---

## 1. What Jayson 1.0 is

Jayson is a self-hosted stack around **Open WebUI** with:

- Multi-model access through a **LiteLLM bridge** (free + paid providers)
- **Token router** (`fast` / `balanced` / `strong`)
- Local **Kokoro TTS**
- Creative tools (3D, video, audio, storyline)
- **Multi-agent game orchestration** with handoffs
- Genre pipelines + platform export checklists
- **Production package template** the system can decompose and execute under supervision
- **QA agents** that must pass before delivery

---

## 1.1 Dependencies

See **`DEPENDENCIES.md`** for Docker, proxy, Ollama, Blender, Python, and post-install UI steps.

---

## 2. Core stack

| Service | Role | Default |
|---------|------|---------|
| Open WebUI (`jayson`) | Chat UI, tools, admin, knowledge | http://localhost:3000 |
| Kokoro TTS | Local high-quality speech | http://localhost:8880 |
| LiteLLM bridge | Model aggregator + router + usage DB | http://localhost:4000 |

**Start**
```bash
cd jayson-openwebui
docker compose -f docker-compose.full.yml up -d
```

**Connect bridge in Admin → Connections**
- Base URL: `http://host.docker.internal:4000/v1`
- Key: `jayson-bridge-secret-change-me`

**API keys:** see `CREDITS.md` and place a `.env` next to `docker-compose.full.yml`.

---

## 3. Model bridge & free providers

Configured in `bridge/litellm_config.yaml`:

- AnyAPI.ai  
- Google AI Studio (Gemini)  
- Groq  
- Hugging Face  
- Cloudflare Workers AI  
- Qwen / DashScope (Alibaba)  
- Mistral, DeepSeek, OpenRouter  
- NVIDIA NIM, Together, Cohere  
- SiliconFlow, Moonshot/Kimi, Zhipu, SambaNova, Cerebras, Fireworks, Novita  
- Microsoft Foundry / Azure (OpenAI-compatible path)  
- Local Ollama  

**Router groups:** `fast` · `balanced` · `strong` (with fallbacks)

**Usage tracking:** SQLite via bridge + `bridge/usage_summary.py`

**Foundry note:** Bridge uses Azure OpenAI-compatible endpoint only. Full Foundry SDK is optional for later agent-native features (`CREDITS.md`).

---

## 4. Tools (Admin → Functions / Tools)

Paste from `tools/openwebui_tools/`:

| Tool | Purpose |
|------|---------|
| `3d_screenshots_tool.py` | 3D model → multi-angle screenshots + description |
| `video_understanding_tool.py` | Video → transcript + keyframe understanding |
| `storyline_maker_tool.py` | Premise → acts, scenes, characters, beats |
| `text_image_to_3d_tool.py` | Text/Image → 3D (Luma, Meshy, Tripo) + Blender refine plan |
| `audio_video_gen_tool.py` | Text→speech, audio scenes, text→video (incl. Luma Dream) |
| `rpg_orchestrator_tool.py` | RPG stages + agent handoffs |
| `agent_loop_tight_tool.py` | PLAN → ACT → CHECK → HANDOFF loops |
| `qa_agents_tool.py` | QA inspect + delivery gate |

Also: `tools/blender/`, `tools/unity/`, MCP guidance in `TOOLS_AND_MCP.md`.

---

## 5. Pipelines

| Path | Content |
|------|---------|
| `pipelines/image_to_3d.md` | Iterative text/image → 3D |
| `pipelines/rpg_orchestration.md` | World→systems→quests→narrative→art→tech→playtest |
| `pipelines/games/genre_pipelines.md` | Racing, FPS, TPS, Adventure, Open World |
| `pipelines/games/export_targets.md` | Windows, Linux, Android, Quest 2/3, PS VR, PS VR2, PS3 notes |
| `pipelines/3d_screenshots/` | Screenshot pipeline code |
| `pipelines/video_understanding/` | Video pipeline code |

**Rule:** every stage uses Tight Loop + QA; handoff only on PASS / PASS_WITH_NOTES.

---

## 6. Production package (major 1.0 input)

| File | Role |
|------|------|
| `PRODUCTION_PACKAGE_TEMPLATE.md` | Full game input the system can decompose |
| `PRODUCTION_PACKAGE_EXAMPLE_MIN.md` | Minimal filled example |

Template includes:

- Human-only intent, pillars, scope, vertical slice, sign-off  
- AI-expandable story, characters, world, systems, quests, levels  
- Full asset lists (models, materials, textures, UI, VFX)  
- Audio lists (VO, music, SFX)  
- Tech plan, export matrix, QA gates, risks, milestones  
- Binding table to all agents/tools built in this project  

**Minimum to start:** pitch, genre, platforms, scope, pillars, vertical slice, human sign-off.

---

## 7. Agent frameworks

Guides in `agents/`:

mem20 · mem20 claw plugin · Open WebUI Computer · mem20 graph substrate · mem20 crews · AutoGen · Pydantic AI · smolagents · OpenAI Agents SDK · LlamaIndex · Mastra  

Connection patterns: OpenAI-compatible endpoint, Open WebUI Pipe, MCP Streamable HTTP.

---

## 8. Audio stance (“decent audio guy”)

- Default: **local Kokoro** (in full compose)  
- Open WebUI Audio → `http://host.docker.internal:8880/v1`  
- Premium path: ElevenLabs / OpenAI when keys exist  
- Tooling for narration + music/SFX scene plans  

---

## 9. QA before delivery

`qa_agents_tool.py` specialties: design, narrative, systems, art/3D, audio, export, build  

Final `qa_gate` can **BLOCK_DELIVERY** until failures are cleared.

---

## 10. Docs index (read in this order)

1. `START_HERE.md` — launch  
2. `JAYSON1.0.md` — this file  
3. `CREDITS.md` — API keys to gather  
4. `PRODUCTION_PACKAGE_TEMPLATE.md` — feed the system a game  
5. `RECOMMENDED_SETUP.md` — power-up checklist  
6. `CAPABILITIES.md` — what she can/can’t do  
7. `ORCHESTRATION_AND_TOOLS.md` — agents, tools, quant floors  
8. `pipelines/games/` — genre + export  
9. `EXAMPLES.md` — concrete code samples  
10. `bridge/README.md` — model router  

---

## 11. Design principles locked in 1.0

1. **One front door** — talk to Jayson; specialists and tools work behind her  
2. **Free models first** — bridge aggregates; paid keys optional  
3. **Pipelines over one-shots** — especially 3D and games  
4. **Handoffs are explicit** — orchestrator + tight loops  
5. **QA is mandatory** — no silent delivery  
6. **Human owns intent** — production package [HUMAN] sections are sacred  
7. **Honest limits** — console SDKs/NDAs marked PREP_ONLY when not available  

---

## 12. Quick start after unzip

```bash
unzip jayson-full-clean.zip
cd jayson-openwebui
cp CREDITS.md notes-keys.md   # optional checklist
# create .env with keys you have
docker compose -f docker-compose.full.yml up -d
```

Then:

1. Open http://localhost:3000 — create admin  
2. Point TTS to Kokoro  
3. Add bridge connection  
4. Paste tools from `tools/openwebui_tools/`  
5. Copy `PRODUCTION_PACKAGE_TEMPLATE.md` for your first project  

---

## 13. Version

**Jayson 1.0** — conversation-complete package: bridge, router, creative tools, game orchestration, genre/export pipelines, production template, QA suite, documentation set.

Not the end of the road — the first version that matches the full vision closely enough to build real projects on.
