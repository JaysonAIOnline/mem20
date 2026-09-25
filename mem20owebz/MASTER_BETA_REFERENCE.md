# Jayson 2.0-beta1 — Master Reference Document

This document consolidates all markdown documentation from the jayson-2.0-beta1 release.
Each section corresponds to a source file from the beta package.

---


## === START_HERE.md ===

# Jayson — Start Here

**Version: 2.0-beta1** — see [`JAYSON2.0.md`](JAYSON2.0.md) and [`INTEGRATION.md`](INTEGRATION.md)

Install first: [`DEPENDENCIES.md`](DEPENDENCIES.md)  
Keys: [`CREDITS.md`](CREDITS.md)  
First game: [`FIRST_GAME_WALKTHROUGH.md`](FIRST_GAME_WALKTHROUGH.md)  
Forced factory: [`pipelines/games/production_run.md`](pipelines/games/production_run.md)

---

## 1. Launch the stack

```bash
cd jayson-openwebui
docker compose -f docker-compose.full.yml up -d
```

Starts Jayson (Open WebUI), Kokoro TTS, and the LiteLLM model bridge.

## 2. First-time setup

1. Open the Jayson UI and create the **first user** (admin)
2. **Admin → Settings → Audio** — point TTS at the Kokoro service
3. **Admin → Connections** — add the model bridge (`/v1`, key from compose)
4. Change `WEBUI_SECRET_KEY` in compose to a long random string and recreate the Jayson container
5. Paste tools from `tools/openwebui_tools/` (see that README)
6. Optional: `.env` keys from CREDITS.md, then recreate the bridge

## 3. Make a game (happy path)

1. Copy `PRODUCTION_PACKAGE_TEMPLATE.md` → `projects/<game>/PRODUCTION_PACKAGE.md`
2. Fill **HUMAN** minimum: pitch, genre, **engine**, platforms, slice, sign-off
3. New chat → prompt in `pipelines/games/production_run.md`
4. QA every stage; `production_run_advance` only on PASS
5. Assets go `_incoming` → manifest → validate → engine (see `asset_assembly.md`)
6. Final polish ≥ 94% → installable under `release/installer/`

## 4. What this beta adds on top of 1.0

Godot path + export investigation · production run driver · assembly → installable · accessibility / loc / save schema / store listing · manifest linter · status dashboard · resource-bridge **catalog** (service in 3.0) · Unreal **4.0** with **real disk sizes** (not 1 TB folklore) · cloud assembly plan

## 5. Key docs

| Doc | Why |
|-----|-----|
| `INTEGRATION.md` | How pieces lock |
| `JAYSON2.0.md` | Branch policy + changelog |
| `JAYSON1.0.md` | Original system map |
| `CLOUD_ASSEMBLY.md` | Multi-cloud + free tiers |
| `CAPABILITIES.md` | What she can/can’t do |
| `pipelines/games/` | Genre, Godot, export, polish |

---

## === JAYSON2.0.md ===

# Jayson 2.0 — Working Branch

**All new edits go into 2.0 until we advance to 3.0.**

| Version | Zip | Role |
|---------|-----|------|
| 1.0 | `jayson-1.0.zip` | Frozen snapshot |
| **2.0** | `jayson-2.0.zip` | **Active development** |
| 3.0 | (future) | Next milestone — cloud assembly / Resource Bridge |
| 4.0 | (future) | **Unreal Engine pipeline** after a dedicated SSD (256–512 GB typical; 1 TB only for fat workstation) |

---

## 2.0 policy

1. Edit `jayson-openwebui/` → repack **`jayson-2.0.zip` only**
2. Leave `jayson-1.0.zip` frozen
3. Log changes in **Changelog** below
4. “Advance to 3.0” freezes 2.0 and opens 3.0
5. **Unreal is 4.0** — do not pull it into 2.0 or 3.0

---

## Changelog

### 2.0-beta1 — Integration beta
- Unified `INTEGRATION.md` + rewritten START_HERE / README / pipeline indexes / system prompt
- Extras: save/settings, localization, accessibility, store listing, modding/DLC, analytics
- Scripts: `lint_manifest.py`, `status_dashboard.py`
- CI sketch: Godot headless export
- Resource Bridge **catalog** (config + tool; FastAPI service stays 3.0)
- New tools: accessibility, store listing, status dashboard, resource bridge
- Version stamp: `VERSION` = `2.0-beta1`
- Artifact: **`jayson-2.0-beta1.zip`**

### 2.0.7 — Unreal disk size corrected
- Unreal is **not** ~1 TB by default
- Binary editor typically **40–70 GB** (trimmed) or **~100–130 GB** during default install
- Source builds **~160–350 GB**; 1 TB is a **full workstation** (multiple versions + DDC + fat projects), not the engine

### 2.0.6 — Unreal pushed to 4.0
- Unreal Engine pipeline **deferred to 4.0** (was 3.0)
- 3.0 stays cloud assembly / Resource Bridge / heavier integration

### 2.0.5 — Cloud assembly plan
- Added `CLOUD_ASSEMBLY.md`: free-tier inventory, best practices, interweave architecture, Jayson Resource Bridge (2nd bridge)

### 2.0.4 — Godot export pipeline investigation
- Added `pipelines/games/godot_export.md` (CLI, templates, Android/Quest, credentials, CI)
- Maps Jayson export matrix → real Godot 4 presets

### 2.0.3 — Unreal deferred (now superseded by 2.0.6 → 4.0)
- Originally tracked for 3.0; **moved to 4.0**
- 2.0 engines: Godot, Unity, Blender DCC

### 2.0.2 — Engine required on production package
- `PRODUCTION_PACKAGE_TEMPLATE.md`: **primary engine is REQUIRED** (§1.6 + §11.1)
- Production run Stage 0 PACKAGE_LOCK checks engine selection before ASSEMBLY

### 2.0.1 — Godot + roadmap
- **Godot 4.x integration:** `tools/godot/godot_tools.py`, `pipelines/games/godot_pipeline.md`
- Same asset_assembly / production_run binding as Unity path
- Documented high-value 2.0 addition candidates (below)

### 2.0.0 — Branch opened
- Copied from 1.0 + this policy file

---

## Engine matrix (current)

| Engine / DCC | Status |
|--------------|--------|
| Blender | Tools + 3D refine pipelines (2.0) |
| Unity | Tools + import notes (2.0) |
| **Godot 4** | Skeleton, import plan, export presets, slice checklist (2.0) |
| Unreal | **Deferred to 4.0** — dedicated SSD; not a free-tier fit |

---

## High-value additions for 2.0 (priority order)

### Already strong from 1.0
Production package, production run orchestrator, QA + 94% polish, assembly→installable, genres, bridge/router.

### Add next (recommended)

1. **Save/load + settings schema** pipeline (data tables the TechLead always reinvents)  
3. **Localization pack** pipeline (string tables, VO per locale)  
4. **Accessibility pass** agent (colorblind, subtitles, remapping, comfort)  
5. **CI build script templates** (Godot headless + Unity batchmode smoke builds)  
6. **Analytics/event dictionary** (optional — design events before code)  
7. **Modding / data-only DLC layout** (if you want post-ship content without full rebuild)  
8. **Automated manifest linter** (script: CSV paths exist, P0 all `validated`)  
9. **Store listing pack** (icons, screenshots, short/long description from package)  
10. **One-click “status dashboard” markdown** generator (stage, fidelity scores, blockers)

### 3.0 territory
- Cloud assembly execution (provision primary VM + block, R2 releases)
- Jayson Resource Bridge (2nd bridge for storage/compute)
- Heavier multi-cloud integration

### 4.0 territory
- **Unreal Engine pipeline** (skeleton, content rules, packing, export)
- Disk: **256–512 GB SSD** is enough for one binary editor + a slice; **~1 TB** only if source + multiple versions + DDC + fat content
- Full console cert automation (needs NDAs/SDKs on your hardware)
- Fully autonomous multi-day runs without human gates
- Real-time collaborative multi-user production board

### Storage note (Unreal — measured, not folklore)

| Setup | Typical disk |
|-------|----------------|
| Binary editor, Windows-only, trimmed | **40–70 GB** installed |
| Default launcher install (extra platforms) | **~100–130 GB** (download + extract overlap) |
| Source build of one version | **~160–350 GB** |
| Full workstation (2–3 versions + DDC + samples + projects) | Can approach **~1 TB** |

Epic’s installer reports the size of **checked components**. Community guidance: put the editor on a **256–512 GB SSD**.

Unreal stays **4.0** because it still wants a **dedicated fast disk + serious RAM/GPU**, not because the engine itself is 1 TB. Use Godot/Unity for 2.0 / 3.0. When a suitable SSD is mounted, say **advance to 4.0**.

---

## How to use Godot path

1. Production run → Stage 4 ASSEMBLY  
2. Call / follow `godot_project_skeleton`  
3. Import only **validated** assets (`godot_import_plan`)  
4. Slice scene checklist → QA Build  
5. `godot_export_presets` for your platform matrix  
6. Continue Stage 5–6 polish + release  

See `pipelines/games/godot_pipeline.md`.

---

## Read order

1. `START_HERE.md`  
2. `JAYSON2.0.md` (this file)  
3. `JAYSON1.0.md`  
4. `DEPENDENCIES.md` / `CREDITS.md`  
5. `FIRST_GAME_WALKTHROUGH.md`  
6. `pipelines/games/production_run.md`

---

## Standing goals (do not drop)

1. **Work on Jayson always** — product line stays active; 2.0 is the working tree until 3.0
2. **Cloud assembly** — see **`CLOUD_ASSEMBLY.md`**. **Owner has 2 Azure keys + 2 OCI keys.**
3. **Jayson 3.0** — cloud assembly / Resource Bridge
4. **Jayson 4.0** — Unreal pipeline after a dedicated SSD exists (256–512 GB typical)

When prioritising work: Jayson product first, cloud when needed to unblock engines/builds, Unreal only at 4.0.

---

## === JAYSON1.0.md ===

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

---

## === README.md ===

# Jayson 2.0-beta1

Self-hosted multi-model AI command center: chat, agents, assets, and **idea → installable game** pipelines.

**Start:** [`START_HERE.md`](START_HERE.md) · **Map:** [`INTEGRATION.md`](INTEGRATION.md) · **Policy:** [`JAYSON2.0.md`](JAYSON2.0.md)

```bash
docker compose -f docker-compose.full.yml up -d
```

## Stack

| Piece | Role |
|-------|------|
| Open WebUI (Jayson) | Chat, admin, tools |
| Kokoro TTS | Local voice |
| LiteLLM bridge | Free/paid models + router + usage DB |

## Game factory

Production package → orchestrator stages → QA gates → asset manifest → Godot/Unity assembly → polish ≥94% → installer.

Unreal is **4.0** (dedicated SSD; binary editor is tens–low hundreds of GB, not 1 TB).

## Layout

```
tools/openwebui_tools/   paste into Admin → Tools
tools/godot|unity|blender
pipelines/games/         genre, export, Godot, assembly, extras
scripts/                 manifest linter, status dashboard
resource_bridge/         2nd bridge catalog (service in 3.0)
ci/                      Godot export sketch
```

---

## === RECOMMENDED_SETUP.md ===

# Recommended Setup — Unlock Full Power

Do these in order after the basic launch.

## 1. Core is running
```bash
docker compose -f docker-compose.full.yml up -d
```

## 2. Connect the Model Bridge
Admin → Connections → Add OpenAI-compatible:
- Base URL: `http://host.docker.internal:4000/v1`
- Key: `jayson-bridge-secret-change-me`

## 3. Add free API keys
Set as environment variables (or in a `.env` file):

```bash
GROQ_API_KEY=
GEMINI_API_KEY=
OPENROUTER_API_KEY=
CLOUDFLARE_API_KEY=
CLOUDFLARE_ACCOUNT_ID=
DASHSCOPE_API_KEY=      # Alibaba / Qwen
NVIDIA_API_KEY=
TOGETHER_API_KEY=
```

Restart the bridge after adding keys.

## 4. Install the ready tools
Admin → Functions / Tools → create new and paste from:
- `tools/openwebui_tools/3d_screenshots_tool.py`
- `tools/openwebui_tools/video_understanding_tool.py`

## 5. Enable essential capabilities
- Web search (built-in or MCP)
- Image generation (Flux / SD / DALL·E / etc.)
- Memory features
- Open Terminal or Open WebUI Computer

## 6. Strong model mix
- One top reasoning model (Grok / Claude / GPT / strong local)
- One vision model
- One fast/cheap model via the bridge
- Optional: mem20 or mem20 claw plugin as agent model

## 7. Agent frameworks
See `agents/` folder for:
mem20, mem20 claw plugin, Open WebUI Computer, mem20 graph substrate, mem20 crews, AutoGen, etc.

## 8. Security
Change these before any public exposure:
- `WEBUI_SECRET_KEY`
- Bridge `master_key` in `bridge/litellm_config.yaml`

---

## === ADVANCED.md ===

# Jayson — Advanced Features Guide

This file covers everything beyond the basic setup.

---

## 1. Password Strength Rules

Already enabled in `docker-compose.yml`:

- Minimum 10 characters
- Must contain uppercase + lowercase + number + special character

You can change the regex if you want stricter/looser rules.

---

## 2. Completely Hide the Sign-Up Button

After you create your admin account:

1. Go to **Admin Panel → Settings → General**
2. Turn **Enable New Sign Ups** → **Off**
3. Save

The Sign Up button will disappear from the login page.

Alternatively you can set `ENABLE_SIGNUP=False` in docker-compose after the first user is created (and restart).

---

## 3. OAuth Login (Google / GitHub)

1. Create OAuth apps:
   - Google: https://console.cloud.google.com/apis/credentials
   - GitHub: https://github.com/settings/developers → OAuth Apps

2. Uncomment and fill these in `docker-compose.yml`:

```yaml
- ENABLE_OAUTH_SIGNUP=True
- GOOGLE_CLIENT_ID=...
- GOOGLE_CLIENT_SECRET=...
# or
- GITHUB_CLIENT_ID=...
- GITHUB_CLIENT_SECRET=...
- OAUTH_PROVIDER_NAME=GitHub
```

3. Restart the container.

You can keep email/password login at the same time or disable it.

---

## 4. Voice Mode + TTS (Ready to configure)

### Fastest (Browser)
- Just click the microphone icon → works immediately
- Uses browser speech recognition + browser TTS

### Better Quality (Recommended)

**Option A – OpenAI (easiest)**
1. Admin Panel → Settings → Audio
2. STT Engine: OpenAI
3. TTS Engine: OpenAI
4. Put your OpenAI key
5. Model: `tts-1` or `tts-1-hd`
6. Voice: `alloy`, `echo`, `nova`, `onyx`, etc.

**Option B – Fully Local (Kokoro / Piper)**
- Run a local TTS server (Kokoro Web or voicebox)
- Point Open WebUI Audio settings to `http://host.docker.internal:PORT/v1`

Voice Mode (hands-free continuous talk) is available once STT + TTS are configured.

---

## 5. Multimedia & Asset Handling

### Images
- Fully supported
- Upload / paste → vision models can analyze them

### Audio
- Upload → automatically transcribed
- Works with Voice Mode

### Video
- YouTube links work best (transcript extracted)
- Direct video files can be uploaded; transcription quality depends on your STT setup
- For better video understanding you can later add a custom pipeline that extracts frames + transcripts

### 3D Models (.glb, .gltf, .obj, .fbx…)
- You can upload the files
- The AI cannot natively understand 3D geometry yet

**Recommended next step for 3D:**
Create a custom Open WebUI Function / Tool that:
1. Takes a 3D file
2. Renders a few camera angles (using Blender headless or three.js)
3. Generates a text description
4. Injects the description + screenshots into the chat

I can help you build that function later if you want.

---

## 6. Better Video Transcription

1. Use a strong STT backend (OpenAI Whisper, faster-whisper, Deepgram, etc.)
2. In Admin → Settings → Audio set the STT engine
3. For long videos, Open WebUI will chunk them automatically (needs ffmpeg in the container — already present in most builds)

---

## 7. Custom Logo (PNG)

Current logo is `logo.svg` (clean wordmark + orange dot).

To use a PNG instead:
1. Create a transparent PNG (recommended 200×60 or square)
2. Place it as `logo.png` in this folder
3. Uncomment the PNG volume line in docker-compose.yml
4. Restart

---

## 8. Even More Aggressive CSS

The current `custom.css` already hides a lot of chrome.
If you want it even more minimal (almost pure chat), tell me and I can strip more elements (sidebar labels, version info, extra buttons, etc.).

---

## Quick Priority Checklist

- [x] Password strength rules
- [x] Ability to hide Sign Up
- [x] OAuth ready (Google + GitHub)
- [x] Voice Mode + TTS configuration path
- [x] Aggressive CSS
- [x] Logo
- [ ] Full 3D pipeline (needs custom function + renderer)
- [ ] Advanced video understanding pipeline

Tell me which of the remaining items you want me to build next.

---

## 9. Multi-Model Support

Open WebUI already supports multiple models at the same time.

### How to use multi-model
1. Connect several providers (Ollama + xAI + OpenAI + Anthropic…)
2. In a chat you can switch models or run side-by-side comparison
3. You can assign different models different roles (e.g. one for coding, one for 3D, one for vision)

### Recommended setup for Jayson
- Main conversational model (Grok / Claude / GPT)
- Vision model (for images & screenshots)
- Coding / tool-calling model (for Blender scripts)
- Optional: local small model for fast responses

Just add the corresponding API keys / Ollama models in Admin Panel or via environment variables.

---

## 10. Full Blender Control (3D Modeling)

See the dedicated folder: `blender/`

**Current status:**
- Architecture defined
- Example high-level tools written (`example_tools.py`)
- Jayson can be given tools to create objects, materials, render, export GLB, and run arbitrary `bpy` code

**To make it live:**
1. Install Blender 4.x on the host
2. Convert the example tools into Open WebUI Tools / Functions
3. Give Jayson the `blender_run_script` tool for full power
4. Optionally add automatic screenshot + description after every change

This is the path to “fully manipulate Blender”.

---

## === INTEGRATION.md ===

# Jayson 2.0-beta1 — Integration map

How the pieces lock together. If a doc disagrees with this file, **this file + `JAYSON2.0.md` win**.

## Version line

| Artifact | Role |
|----------|------|
| `jayson-1.0.zip` | Frozen 1.0 |
| `jayson-2.0.zip` | Working tree |
| **`jayson-2.0-beta1.zip`** | This integrated beta |

3.0 = cloud Resource Bridge service. 4.0 = Unreal (256–512 GB SSD typical).

## Control plane vs muscle

```
Human
  → Production Package (HUMAN sections)
    → Production Run Orchestrator (stages 0–7, QA to advance)
      → Genre / Godot / Unity / Blender / creative tools
        → asset_assembly (manifest is law)
          → Final polish (≥94%)
            → builds/ → release/installer/
              → Resource Bridge publishes to R2 (3.0)
```

Jayson chat UI can live on **OCI Always Free**. Engines need a **dedicated SSD**. Object storage (R2) is for **releases**, not Unreal DDC.

## Stage extras (optional, do not skip spine)

| When | Extra pipeline |
|------|----------------|
| Design | save_load_settings, analytics_events |
| Spaces | accessibility (esp. VR) |
| Assets | localization (if extra locales) |
| Assembly | `scripts/lint_manifest.py` |
| Polish | accessibility_tool + final_polish |
| Release | store_listing, godot_export, status dashboard |

## Engines (2.0-beta1)

Godot + Unity + Blender. Unreal = **4.0**.

## Hard rules

1. No stage skip without QA PASS  
2. No build from `_incoming`  
3. Manifest CSV is the only ship list  
4. Engine choice is required on the package  
5. Do not merge free-tier disks into one volume  

---

## === CLOUD_ASSEMBLY.md ===

# Cloud Assembly — Best Practices for AI + Jayson

**Standing goal #2.** Plan for multi-cloud storage/compute so Jayson and heavy engines can run.

Your accounts (as stated): **OCI ×2 · Azure ×2 · AWS · Cloudflare**

---

## 1. Critical truth: you cannot merge free tiers into one block disk

| Idea | Reality |
|------|---------|
| Glue OCI+Azure+AWS free disks into **one** EBS-like volume | **Impossible.** Block storage is local to a VM in one cloud/region |
| “Cluster” free object buckets into one filesystem | Only via **software overlay** (rclone, s3fs, LakeFS, custom index) — high latency, not suitable for Unreal editor DDC |
| Use Cloudflare as the Unreal drive | **No.** R2 is object storage; great for artifacts, not live engine installs |

**Rule for AI/game engines:**  
- **Hot path** (editor, compile, DerivedDataCache) = **one** paid/serious block volume next to **one** VM  
- **Cold path** (exports, backups, datasets, model weights) = object storage across clouds  

Free tiers are for **bootstrap and cold data**, not a live Unreal editor + DDC workspace.

---

## 2. Approximate free-tier storage inventory

*Verify in each console — offers change. Numbers are typical published ceilings, not a guarantee.*

| Cloud | Free-ish storage (ballpark) | Type | Unreal-capable? |
|-------|----------------------------|------|-----------------|
| **OCI ×2** | ~**200 GB block** per tenancy Always Free (home region); small object free tiers | Block + object | **Tight** — 200 GB can fit a **trimmed binary editor**, not a fat source build |
| **Azure ×2** | Trial **credits** + ~**2×64 GB** managed disks (12‑mo popular free style offers vary) | Block (with VM) | Small disks only |
| **AWS** | Often ~**30 GB EBS** class free-tier eligible (12 mo / credit programs vary post‑2025) + S3 free allowances | Block + object | Boot/dev only |
| **Cloudflare** | **R2 ~10 GB**/mo free storage + free egress | **Object only** | Artifacts/CDN only |

### Rough “combined free” math (optimistic)
```
OCI block:     200 + 200 = 400 GB
Azure disks:   ~64–128 GB ×2 accounts (if offers apply) ≈ 128–256 GB
AWS EBS:       ~30 GB
Cloudflare R2: ~10 GB object
--------------------------------
Block-ish sum: ~560–700 GB scattered, NOT one filesystem
Object free:   tens of GB
```

**Still not one filesystem.** Combined free ≠ one mount. Cross-cloud I/O will be slow and fragile.

A **trimmed Unreal binary editor** (~40–70 GB installed, ~100–130 GB during install) *could* fit on **one OCI 200 GB** volume. A **source build** (~160–350 GB) or multi-version workstation will not. Plan **256–512 GB SSD** for a comfortable 4.0 slice; **~1 TB** only for source + multiple versions + DDC + fat projects.

---

## 2.1 Unreal disk size (measured, not folklore)

| Setup | Typical disk |
|-------|----------------|
| Binary editor, Windows-only, extra platforms **off** | **40–70 GB** installed |
| Default Epic Launcher install | **~100–130 GB** (download + extract overlap; editor ends smaller) |
| Several versions side by side | **150–250+ GB** |
| **Source build** of one version | **~160–350 GB** (Intermediate + `.git` dominate) |
| One project + DDC / Intermediate / Saved | Tens of GB, grows with content |
| Full workstation (2–3 versions + samples + DDC + projects) | Can approach **~1 TB** |

Epic does **not** publish “1 TB required.” The installer reports the size of **checked components**. Community guidance: a **256–512 GB SSD** for the editor.

---

## 3. Best practices for AI workloads on multi-cloud

1. **One home region for compute** — pick primary cloud for the GPU/CPU build box  
2. **Block disk same AZ as VM** — never “remote block” across clouds  
3. **Object for everything portable** — builds, datasets, LoRA weights, `release/installer/`  
4. **Immutable releases** — versioned buckets (`s3://…/releases/v1.2.3/`)  
5. **Secrets never in buckets as plaintext** — use each cloud’s secret manager  
6. **Egress awareness** — Cloudflare R2 wins for free egress; AWS/Azure/OCI charge egress  
7. **Snapshots before engine upgrades**  
8. **Separate “brain” from “muscle”** — Jayson control plane can stay small; heavy jobs on the build VM  

---

## 4. Recommended architecture (interwoven, not fake-one-disk)

```
                    ┌─────────────────────────┐
                    │  Jayson control plane     │
                    │  (Open WebUI + LiteLLM    │
                    │   + Resource Bridge)      │
                    └───────────┬───────────────┘
                                │ API
          ┌─────────────────────┼─────────────────────┐
          ▼                     ▼                     ▼
   ┌──────────────┐     ┌──────────────┐      ┌──────────────┐
   │ HOT block     │     │ COLD object   │      │ COLD object  │
   │ Primary cloud │     │ R2 / S3 /     │      │ OCI / Azure  │
   │ VM + 256–512GB │     │ Azure blob    │      │ secondary    │
   │ SSD (1TB later │     │ builds, packs │      │ backups      │
   │ if fat Unreal) │     │               │      │              │
   └──────────────┘     └──────────────┘      └──────────────┘
```

### Role assignment (suggested)

| Role | Provider | Why |
|------|----------|-----|
| **Primary compute + block** | AWS **or** Azure **or** OCI (pick one with best GPU/price for you) | **256–512 GB SSD** for Godot/Unity + one Unreal binary; 1 TB only if source/multi-version |
| **Public artifact distribution** | **Cloudflare R2** | Free egress, installers, patches |
| **Secondary backup** | Other OCI or Azure account | Cross-cloud disaster copy |
| **Jayson always-on** | Small VM or existing home lab + Docker | Control plane; doesn’t need a fat engine disk |

### Interweaving pattern
- Nightly: build VM → upload `builds/` + `release/` → R2  
- Weekly: snapshot block volume; copy critical project zips → second cloud object  
- Jayson Resource Bridge tracks **where** each dataset lives (see §6)

---

## 5. Provisioning plan (phases)

### Phase A — Inventory (this week)
- [ ] Log into each account; note **real** free quotas remaining  
- [ ] Pick **primary cloud** for the build VM  
- [ ] Estimate monthly $ for **256–512 GB SSD** (quote 1 TB only if you want source Unreal)  

### Phase B — Hot path (Godot/Unity now; Unreal at 4.0)
- [ ] Create VM in primary cloud (enough RAM/CPU; GPU later if needed)  
- [ ] Attach **256–512 GB** SSD block volume (1 TB optional later)  
- [ ] Mount e.g. `/mnt/engines`, `/mnt/projects`  
- [ ] Install Godot first (small); Unreal when disk ready  
- [ ] Snapshots on schedule  

### Phase C — Cold path (free tiers woven)
- [ ] Cloudflare R2 bucket: `jayson-releases`  
- [ ] AWS S3 or OCI object: `jayson-backups`  
- [ ] Azure blob on second account: `jayson-cold`  
- [ ] `rclone` remotes for each; documented in bridge config  

### Phase D — Jayson integration
- [ ] Deploy **Resource Bridge** (second bridge, §6)  
- [ ] Register backends (block path via SSH/agent, object via S3 API)  
- [ ] Production Run Stage 6 writes to `builds/` then bridge publishes to R2  

### Phase E — Hardening
- [ ] Budget alerts on all clouds  
- [ ] No public buckets without intentional policy  
- [ ] Test restore from secondary backup once  

---

## 6. Second bridge: Jayson Resource Bridge

LiteLLM = **model** bridge.  
Resource Bridge = **storage/compute** bridge so Jayson can address multi-cloud without pretending it’s one disk.

### Responsibilities
- Catalog backends: `hot-block`, `r2-releases`, `oci-backup`, …  
- List/upload/download artifacts by logical URI: `jayson://releases/mygame/1.0.0/`  
- Optional: trigger remote build scripts on the hot VM (SSH/CI webhook)  
- Quotas & health: free-tier headroom warnings  
- **Never** mount cross-cloud block as local for Unreal  

### Suggested API (OpenAI-tool style for Open WebUI)

| Tool | Purpose |
|------|---------|
| `storage_list(backend, prefix)` | List objects/paths |
| `storage_put(backend, key, source)` | Upload build/artifact |
| `storage_get(backend, key, dest)` | Download to workspace |
| `storage_publish_release(project, version)` | Copy from hot `release/` → R2 |
| `compute_status(host)` | Is build VM up? Disk free? |
| `compute_run(host, command)` | Optional guarded remote command |

### Implementation sketch (2.0 → 3.0 Resource Bridge; Unreal in 4.0)
1. Small FastAPI service next to LiteLLM in compose  
2. Config YAML of backends (S3-compatible endpoints + SSH host for hot)  
3. Open WebUI tool wrapping HTTP calls  
4. Later: auth tokens per backend  

Logical layout:
```
jayson://hot/projects/<game>/...
jayson://releases/<game>/<version>/...
jayson://backups/<game>/<date>/...
```

---

## 7. What free tiers *are* good for

- Storing **production packages**, manifests, small assets  
- **Release** zips/APKs on R2  
- Backup of `PRODUCTION_PACKAGE.md` + git mirrors  
- Not: live Unreal DerivedDataCache on object storage; not: merging disks across clouds  

---

## 8. Decision checklist

| Question | Answer |
|----------|--------|
| Can free tiers fund Unreal install? | **Maybe a trimmed binary on OCI 200 GB**; not a source/multi-version workstation |
| Best free multi-cloud use? | Object cold storage + R2 distribution; **OCI Always Free** for the chat UI |
| Path to Unreal? | Dedicated **256–512 GB SSD** on one primary cloud (1 TB if you go source-heavy) |
| Jayson role? | Control plane + Resource Bridge; jobs on hot VM |

---

## 9. Next actions when you say “provision”

1. Choose primary cloud (AWS / Azure / OCI)  
2. Size VM + **256–512 GB** disk quote (1 TB only if source Unreal)  
3. Stand up R2 release bucket  
4. Scaffold Resource Bridge service in 2.0 compose  
5. Wire Production Run Stage 6 → publish  

Until then: develop on **Godot/Unity** local or small cloud disks; keep Unreal on the **4.0** track after block storage exists.

---

## Account inventory (owner-confirmed)

| Provider | Keys / accounts | Notes |
|----------|-----------------|--------|
| **Azure** | **2** | Two separate credentials/subscriptions — usable for primary or secondary roles |
| **OCI** | **2** | Two tenancies/keys — Always Free block can stack *per tenancy* (still separate volumes) |
| AWS | 1 (as stated earlier) | |
| Cloudflare | 1 (as stated earlier) | R2 object / Workers |

Do not assume keys are interchangeable across the pair; treat each as its own quota and IAM boundary.

---

## === DEPENDENCIES.md ===

# Dependency Installation — Jayson 1.0

Install these before or while bringing the stack up.

---

## 1. Required (core stack)

### Docker + Docker Compose

**Linux (Debian/Ubuntu example)**
```bash
sudo apt update
sudo apt install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
# log out and back in for group membership
```

**Verify**
```bash
docker --version
docker compose version
```

**Docker Desktop** (Windows/macOS): install from https://www.docker.com/products/docker-desktop/

You need a working Docker engine that can pull from `ghcr.io`.  
If pulls fail with `connection reset by peer`, fix network/proxy first (see below).

---

## 2. Launch stack (pulls images automatically)

```bash
cd jayson-openwebui
docker compose -f docker-compose.full.yml up -d
```

Images used:
- `ghcr.io/open-webui/open-webui:main`
- `ghcr.io/remsky/kokoro-fastapi:latest` (or current Kokoro image in compose)
- `ghcr.io/berriai/litellm:main-latest`

**If behind a proxy**, configure Docker proxy then retry:
```bash
sudo mkdir -p /etc/systemd/system/docker.service.d
sudo nano /etc/systemd/system/docker.service.d/http-proxy.conf
```
```ini
[Service]
Environment="HTTP_PROXY=http://USER:PASS@proxy:port"
Environment="HTTPS_PROXY=http://USER:PASS@proxy:port"
Environment="NO_PROXY=localhost,127.0.0.1,host.docker.internal"
```
```bash
sudo systemctl daemon-reload
sudo systemctl restart docker
docker compose -f docker-compose.full.yml pull
docker compose -f docker-compose.full.yml up -d
```

---

## 3. API keys (not software installs, but required for providers)

Create `.env` **in the same folder as** `docker-compose.full.yml`:

```bash
nano .env
```

See **`CREDITS.md`** for the full list. Minimum useful set:

```bash
GEMINI_API_KEY=
GROQ_API_KEY=
ANYAPI_API_KEY=
OPENROUTER_API_KEY=
HF_TOKEN=
```

Then recreate the bridge so it picks up env:

```bash
docker compose -f docker-compose.full.yml up -d --force-recreate jayson-bridge
```

---

## 4. Optional — local models (Ollama)

```bash
# Linux install script (official)
curl -fsSL https://ollama.com/install.sh | sh
ollama serve   # if not already a service
ollama pull llama3.2
ollama pull qwen2.5:14b
```

Bridge already points at `http://host.docker.internal:11434`.

---

## 5. Optional — host tools for 3D / pipelines

| Tool | Why | Install hint |
|------|-----|----------------|
| **Blender** | Refine AI-generated meshes | https://www.blender.org/download/ or `apt install blender` |
| **git** | Project versioning | `sudo apt install git` |
| **curl / wget** | API tests | usually preinstalled |
| **sqlite3** | Query bridge usage DB on host | `sudo apt install sqlite3` |

Python scripts on the host (examples / usage summary):

```bash
sudo apt install -y python3 python3-pip python3-venv
pip3 install openai   # for examples/simple_agent_loop.py talking to the bridge
```

---

## 6. Optional — Microsoft Foundry SDK (not required for bridge)

Only if you want Foundry-native agents/projects later:

```bash
pip install azure-ai-projects azure-identity openai
```

Bridge chat completions only need:

```bash
AZURE_API_KEY=
AZURE_API_BASE=https://YOUR-RESOURCE.openai.azure.com/
```

---

## 7. Optional — creative API CLIs

No local install required for Luma/Meshy/Tripo — keys go in `.env` or tool valves:

```bash
LUMA_API_KEY=
MESHY_API_KEY=
TRIPO_API_KEY=
ELEVENLABS_API_KEY=
```

---

## 8. Open WebUI post-install (manual steps)

1. Open http://localhost:3000 → create **first user** (becomes admin)
2. **Admin → Settings → Audio**  
   TTS base: `http://host.docker.internal:8880/v1`
3. **Admin → Connections** → add bridge  
   - URL: `http://host.docker.internal:4000/v1`  
   - Key: `jayson-bridge-secret-change-me`
4. **Admin → Functions / Tools** → paste each file from `tools/openwebui_tools/`
5. Change `WEBUI_SECRET_KEY` in compose and recreate `jayson` container

---

## 9. Verify installation

```bash
docker compose -f docker-compose.full.yml ps
curl -s http://localhost:3000 | head -c 200
curl -s http://localhost:4000/v1/models -H "Authorization: Bearer jayson-bridge-secret-change-me" | head
curl -s http://localhost:8880/v1/models || true
```

Usage summary (after some chat traffic):

```bash
python3 bridge/usage_summary.py
# or copy DB out of container first if path differs
```

---

## 10. Common missing-dependency symptoms

| Symptom | Likely fix |
|---------|------------|
| `ghcr.io` connection reset | Network/firewall/proxy; configure Docker proxy; retry pull |
| Bridge models empty | Missing/invalid keys in `.env`; recreate bridge |
| TTS silent | Audio URL not set to Kokoro; container not healthy |
| Ollama models missing | Ollama not running on host; firewall to 11434 |
| Tool paste errors | Paste full file including title docstring; enable tool |
| Azure/Foundry fails | Wrong deployment name or `AZURE_API_BASE` |

---

## 11. Disk / hardware notes

- Images + models need several GB free
- Local Ollama large models need RAM/VRAM (see `ORCHESTRATION_AND_TOOLS.md` quant guidance)
- Quest/Android/console **device SDKs** are **not** bundled — export pipelines document prep only unless you install platform SDKs yourself

---

## 12. One-shot bootstrap (Linux)

```bash
# Docker
sudo apt update && sudo apt install -y docker.io docker-compose-v2 python3 python3-pip sqlite3
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
# re-login

cd jayson-openwebui
# create .env with keys from CREDITS.md
docker compose -f docker-compose.full.yml up -d
```

Then finish section 8 (Open WebUI UI setup).

---

## === CREDITS.md ===

# API Keys to Gather

List of every API key used by the Jayson Model Bridge.  
You only need the ones you actually want to use — the rest can stay empty.

## Priority (best free tiers first)

| Priority | Provider              | Environment Variable          | Where to get the key                              | Notes |
|----------|-----------------------|-------------------------------|----------------------------------------------------|-------|
| 1        | Google AI Studio      | `GEMINI_API_KEY`              | https://aistudio.google.com/app/apikey             | Best overall free tier |
| 2        | Groq                  | `GROQ_API_KEY`                | https://console.groq.com/keys                      | Extremely fast |
| 3        | AnyAPI                | `ANYAPI_API_KEY`              | https://anyapi.ai or https://dash.anyapi.ai        | 300+ models through one key |
| 4        | OpenRouter            | `OPENROUTER_API_KEY`          | https://openrouter.ai/keys                         | Many free models |
| 5        | Cloudflare Workers AI | `CLOUDFLARE_API_KEY`          | https://dash.cloudflare.com → API Tokens           | Also needs Account ID |
|          |                       | `CLOUDFLARE_ACCOUNT_ID`       | Cloudflare dashboard → Overview                    | |
| 6        | Hugging Face          | `HF_TOKEN`                    | https://huggingface.co/settings/tokens             | Community models |
| 7        | DeepSeek              | `DEEPSEEK_API_KEY`            | https://platform.deepseek.com                      | Free credits |
| 8        | Mistral               | `MISTRAL_API_KEY`             | https://console.mistral.ai                         | Free tier |
| 9        | Qwen / Alibaba        | `DASHSCOPE_API_KEY`           | https://dashscope.console.aliyun.com               | Strong free quota |
| 10       | NVIDIA NIM            | `NVIDIA_API_KEY`              | https://build.nvidia.com                           | Free models |

## Additional free / low-cost providers

| Provider         | Environment Variable     | Where to get the key                          |
|------------------|--------------------------|-----------------------------------------------|
| Together         | `TOGETHER_API_KEY`       | https://api.together.xyz                      |
| Cohere           | `COHERE_API_KEY`         | https://dashboard.cohere.com                  |
| SiliconFlow      | `SILICONFLOW_API_KEY`    | https://siliconflow.cn                        |
| Moonshot / Kimi  | `MOONSHOT_API_KEY`       | https://platform.moonshot.cn                  |
| Zhipu / Z.ai     | `ZHIPU_API_KEY`          | https://open.bigmodel.cn                      |
| SambaNova        | `SAMBANOVA_API_KEY`      | https://cloud.sambanova.ai                    |
| Cerebras         | `CEREBRAS_API_KEY`       | https://cloud.cerebras.ai                     |
| Fireworks        | `FIREWORKS_API_KEY`      | https://fireworks.ai                          |
| Novita           | `NOVITA_API_KEY`         | https://novita.ai                             |
| Microsoft Foundry | `AZURE_API_KEY`          | https://ai.azure.com / Azure Portal           |
|                   | `AZURE_API_BASE`         | Your Foundry / Azure OpenAI endpoint URL      |

## Local (no key needed)

| Provider | Notes                    |
|----------|--------------------------|
| Ollama   | Runs fully local         |

## How to use the keys

Create a `.env` file next to `docker-compose.full.yml`:

```bash
GEMINI_API_KEY=
GROQ_API_KEY=
ANYAPI_API_KEY=
OPENROUTER_API_KEY=
CLOUDFLARE_API_KEY=
CLOUDFLARE_ACCOUNT_ID=
HF_TOKEN=
DEEPSEEK_API_KEY=
MISTRAL_API_KEY=
DASHSCOPE_API_KEY=
NVIDIA_API_KEY=
TOGETHER_API_KEY=
COHERE_API_KEY=
SILICONFLOW_API_KEY=
MOONSHOT_API_KEY=
ZHIPU_API_KEY=
SAMBANOVA_API_KEY=
CEREBRAS_API_KEY=
FIREWORKS_API_KEY=
NOVITA_API_KEY=
AZURE_API_KEY=
AZURE_API_BASE=
LUMA_API_KEY=
MESHY_API_KEY=
TRIPO_API_KEY=
ELEVENLABS_API_KEY=
```

Then start:

```bash
docker compose -f docker-compose.full.yml up -d
```

Only fill in the keys you have. Empty ones are simply ignored.

## Recommended minimum set

For a strong free setup, get at least these four:

1. `GEMINI_API_KEY`
2. `GROQ_API_KEY`
3. `ANYAPI_API_KEY` (or `OPENROUTER_API_KEY`)
4. `HF_TOKEN`

## Microsoft Foundry SDK (optional, for later)

The Model Bridge only needs the Azure OpenAI-compatible endpoint (`AZURE_API_KEY` + `AZURE_API_BASE`).

If you later want Foundry-native features (Agent Service, evaluations, project connections, skills), install the Foundry SDK:

```bash
pip install azure-ai-projects azure-identity openai
```

Docs: https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/develop/sdk-overview

### Creative generation keys (optional)

| Provider     | Env var            | Use |
|--------------|--------------------|-----|
| Luma         | `LUMA_API_KEY`     | Dream Machine video + 3D |
| Meshy        | `MESHY_API_KEY`    | Text/Image → 3D |
| Tripo        | `TRIPO_API_KEY`    | Fast 3D |
| ElevenLabs   | `ELEVENLABS_API_KEY` | Premium voices |

---

## === CAPABILITIES.md ===

# Jayson — Full Capability Map

Goal: One place to go. Ask for almost anything (within reason) and she can do it.

## Core Strengths (Already Built)

| Domain                    | Status | How |
|---------------------------|--------|-----|
| Conversation & reasoning  | Excellent | Multi-model (Grok, Claude, GPT, local…) |
| Voice (talk + listen)     | Strong | Local Kokoro TTS + browser/OpenAI STT |
| Vision (images)           | Strong | Any vision model + image upload |
| Documents & knowledge     | Excellent | RAG + Knowledge Bases |
| Code & terminal           | Strong | Open Terminal + tools + MCP |
| 3D modeling               | Strong | Blender tools + image-to-3D pipeline |
| Video understanding       | Good | Keyframe + transcript pipeline |
| Unity assets              | Good | Import pipeline |
| Multi-agent               | Excellent | mem20, mem20 claw plugin, mem20 crews, mem20 graph substrate… |
| MCP tools                 | Excellent | Streamable HTTP fully supported |

## High-Value Additions You Should Enable

### 1. Web Search & Browsing (Critical)
- Enable Open WebUI’s built-in web search, **or**
- Add a strong MCP server (Brave, Tavily, Firecrawl, Browserbase, etc.)
- This lets Jayson answer current events, research, and “look this up” requests.

### 2. Image Generation
- Connect Flux, SD3, DALL·E, Ideogram, or a local ComfyUI / Automatic1111 endpoint
- In Admin → Images / Image Generation
- Lets her create images, concept art, mockups, etc.

### 3. Long-term Memory
- Turn on Open WebUI Memory features
- Optionally connect a memory MCP or use mem20/mem20 claw plugin memory
- She will remember your preferences, projects, and past decisions.

### 4. File & Project Mastery
- Use Knowledge Bases for your important folders/docs
- Enable Open Terminal / Open WebUI Computer for real file system access
- She can read, edit, organize, and create files.

### 5. Automations & Scheduling
- Use Open WebUI Automations (or mem20 cron)
- Examples: daily briefing, monitor sites, generate reports, clean files

### 6. Recommended Model Lineup (Multi-model)
Keep several models available at once:

- **Main brain**: Grok / Claude / GPT-4o-class
- **Vision**: Any strong vision model
- **Fast/local**: Llama 3.3 / Qwen / DeepSeek
- **Agent**: mem20 or mem20 claw plugin
- **Coding**: A strong code model

## What She Can Realistically Do

- Research any topic and summarize with sources
- Write and debug code
- Create and refine 3D models from descriptions or photos
- Analyze videos and documents
- Generate images and iterate on them
- Control Blender and feed assets into Unity
- Manage files and projects
- Talk with high-quality voice
- Run multi-step agent workflows
- Remember context across sessions
- Browse the web and act on current information

## Still Limited (Honest)
- Real-time physical world control (robots, IoT) needs extra hardware/MCP
- Fully automatic high-end 3D from a single photo still benefits from iteration
- Extremely long autonomous runs work better with mem20/mem20 claw plugin + scheduling

## Philosophy
Jayson is the **control center**.  
Different specialized agents and tools plug into her.  
You talk to one place — she routes to the right capability.

---

## === ORCHESTRATION_AND_TOOLS.md ===

# Agent Orchestration + Tool Integration for Jayson

## 1. Agent Orchestration Options

You have several layers of orchestration available:

### A. Native Open WebUI
- **Sub-agents**: Model can delegate focused tasks to parallel sub-agents
- **Multi-model chat**: Run different models side-by-side
- **Automations**: Scheduled / triggered workflows

### B. External Agent Frameworks (already documented in `agents/`)
| Framework       | Best orchestration style              |
|-----------------|---------------------------------------|
| mem20 Agent    | Persistent personal agent + skills    |
| mem20 claw plugin        | Multi-channel personal agent          |
| mem20 crews          | Role-based crews (researcher + coder) |
| mem20 graph substrate       | Stateful graphs, human-in-the-loop    |
| AutoGen / AG2   | Conversational multi-agent            |
| Open WebUI Computer | Full computer as the agent         |

### C. Recommended Orchestration Pattern for Jayson

```
User → Jayson (main brain)
         ├── Native tools + MCP
         ├── Sub-agents (parallel tasks)
         ├── mem20 / mem20 claw plugin (long autonomous work)
         ├── mem20 crews / mem20 graph substrate (structured multi-agent)
         └── Blender / Video / 3D pipelines
```

Jayson stays the single front door. Specialized agents and tools do the heavy lifting.

## 2. Tool Integration (How tools reach Jayson)

### Order of preference

1. **Native Open WebUI Tools / Functions**  
   (the ones in `tools/openwebui_tools/`)

2. **MCP Servers (Streamable HTTP)**  
   Best modern way. Add in Admin → Integrations.

3. **OpenAPI tool servers**

4. **Open Terminal / Open WebUI Computer**  
   Real shell + filesystem

5. **External agent frameworks**  
   That already have their own tools

### Essential tools to enable

- Web search / browsing
- Code interpreter / terminal
- File system access
- Blender tools
- 3D screenshots + video understanding tools
- Image generation
- Memory

## 3. Practical Examples

### Example 1 — Simple tool use
User: “Render this 3D model from 6 angles and describe it”
→ Jayson calls the 3D Screenshots tool → feeds images to vision model → returns description

### Example 2 — Multi-step research
User: “Research the latest open-source agent frameworks and compare them”
→ Web search tool + optional sub-agents for parallel reading → synthesis

### Example 3 — Full agent hand-off
User: “Build a small web app for tracking habits”
→ Jayson plans → hands off to mem20 or mem20 claw plugin (or mem20 crews crew) for the actual coding + testing loop

### Example 4 — 3D from photo (iterative)
User uploads photo → Image-to-3D pipeline → Blender refinement loop → export GLB → optional Unity import

### Example 5 — Video analysis
User drops video → Video understanding tool (transcript + key frames) → vision model + summary

## 4. Lowest Quantization That Still Works

Rule of thumb in 2026 for **tool-calling / agent work**:

| Quantization     | Usable for agents?          | Notes |
|------------------|-----------------------------|-------|
| **Q5_K_M / Q5**  | Excellent                   | Safest low quant |
| **Q4_K_M / Q4**  | Good (production floor)     | Most popular sweet spot |
| **Q3 / IQ3**     | Risky                       | Tool calling starts degrading |
| **Q2 / lower**   | Not recommended             | Frequent malformed calls |

### Recommended lowest practical models (local)

| VRAM        | Model recommendation                     | Quant      | Role |
|-------------|------------------------------------------|------------|------|
| 8 GB        | Qwen3 8B                                 | Q4_K_M    | Fast daily + light tools |
| 12–16 GB    | Qwen3 14B / 27B or Gemma 4 27B           | Q4_K_M    | Strong general + tools |
| 24 GB       | Qwen3 32B / GLM / Gemma 27–32B           | Q4_K_M or Q5 | Excellent agent work |
| 48 GB+      | Llama 3.3 70B / Qwen 72B class           | Q4_K_M    | Highest local quality |

**Key insight**: For agents, **Q4_K_M is the practical floor**.  
Going lower (Q3 and below) often hurts tool-call reliability more than it hurts normal chat.

### Cloud / API models
Prefer the strongest tool-calling models available (Qwen3.x, Claude, GPT, GLM, etc.) when quality matters more than cost.

## Summary Recommendation

1. Keep a strong main model (cloud or high-quant local)
2. Use Q4_K_M as the lowest quant for any local model that must call tools
3. Orchestrate via native sub-agents + mem20/mem20 claw plugin + mem20 crews/mem20 graph substrate as needed
4. Make tools available through MCP + native Functions
5. Let Jayson stay the single interface

---

## === EXAMPLES.md ===

# Jayson — Concrete Code Examples

Practical, copy-paste ready examples for tools, agents, and pipelines.

---

## 1. Minimal Agent Loop (ReAct-style)

Use this pattern when building custom agents that call tools.

```python
# examples/simple_agent_loop.py
import json
from typing import Callable

def run_agent(user_query: str, llm_call: Callable, tools: dict, max_steps: int = 8):
    """
    Simple ReAct-style agent loop.
    llm_call(messages) -> dict with 'content' and optional 'tool_calls'
    tools = {"tool_name": callable}
    """
    messages = [{"role": "user", "content": user_query}]

    for step in range(max_steps):
        response = llm_call(messages)

        # If the model wants to call tools
        tool_calls = response.get("tool_calls") or []
        if not tool_calls:
            return response.get("content", "")

        messages.append({"role": "assistant", "content": response.get("content"), "tool_calls": tool_calls})

        for call in tool_calls:
            name = call["function"]["name"]
            args = json.loads(call["function"]["arguments"])
            result = tools[name](**args) if name in tools else f"Unknown tool: {name}"
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id", name),
                "content": str(result)
            })

    return "Reached max steps without final answer."
```

---

## 2. Open WebUI Tool Example (already in the package style)

This is the format Jayson expects for custom tools:

```python
"""
title: Example Weather Tool
author: Jayson
version: 1.0
"""

from pydantic import BaseModel, Field

class Tools:
    class Valves(BaseModel):
        api_key: str = Field(default="", description="Optional API key")

    def __init__(self):
        self.valves = self.Valves()

    def get_weather(self, city: str) -> str:
        """
        Get current weather for a city.
        :param city: City name
        """
        # Replace with real API call
        return f"Weather in {city}: 22°C, clear skies (example)"
```

Paste into **Admin → Functions → Tools**.

---

## 3. Calling the Model Bridge from Python

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:4000/v1",
    api_key="jayson-bridge-secret-change-me"
)

# Use a router group
response = client.chat.completions.create(
    model="fast",          # or "balanced", "strong", or any specific model
    messages=[{"role": "user", "content": "Explain quantum entanglement simply"}]
)

print(response.choices[0].message.content)
```

---

## 4. Simple MCP-style Tool Server (FastAPI)

```python
# examples/simple_mcp_server.py
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class ToolCall(BaseModel):
    name: str
    arguments: dict

@app.post("/tools/call")
def call_tool(body: ToolCall):
    if body.name == "add_numbers":
        a = body.arguments.get("a", 0)
        b = body.arguments.get("b", 0)
        return {"result": a + b}
    return {"error": "unknown tool"}

@app.get("/tools")
def list_tools():
    return {
        "tools": [
            {
                "name": "add_numbers",
                "description": "Add two numbers",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "a": {"type": "number"},
                        "b": {"type": "number"}
                    },
                    "required": ["a", "b"]
                }
            }
        ]
    }
```

Run with:
```bash
uvicorn examples.simple_mcp_server:app --port 8090
```

Then point Jayson / MCP config at it.

---

## 5. 3D Screenshots Tool (already provided)

See:
```
tools/openwebui_tools/3d_screenshots_tool.py
```

Usage idea in chat:
> “Take screenshots of this .glb from 6 angles and describe the model”

---

## 6. Video Understanding Tool (already provided)

See:
```
tools/openwebui_tools/video_understanding_tool.py
```

Usage idea:
> “Transcribe this video and summarize the key visual moments”

---

## 7. Basic RAG Pattern (for Knowledge Bases)

```python
# Conceptual pattern — Open WebUI already has Knowledge Bases
def simple_rag(query: str, documents: list[str], llm_call, top_k: int = 3):
    # 1. Retrieve (replace with real embeddings + vector search)
    scored = sorted(documents, key=lambda d: query.lower() in d.lower(), reverse=True)
    context = "\n\n".join(scored[:top_k])

    # 2. Generate
    prompt = f"""Use the following context to answer the question.
Context:
{context}

Question: {query}
Answer:"""
    return llm_call([{"role": "user", "content": prompt}])
```

In practice, prefer Open WebUI’s built-in Knowledge feature.

---

## 8. System Prompt Tip

Put this (or the content of `system-prompt.txt`) into the model’s system prompt in Open WebUI for consistent behavior:

```
You are Jayson. Be direct, helpful, and tool-aware.
When a task needs tools, use them.
For 3D work use the Blender / screenshots tools.
For video use the video understanding tool.
Prefer accurate, up-to-date information.
```

---

## Where to put custom code

| Type of code              | Recommended location              |
|---------------------------|-----------------------------------|
| Open WebUI Tools          | Admin → Functions / Tools         |
| Helper scripts            | `examples/` (create this folder)  |
| MCP servers               | Separate process / Docker         |
| Blender scripts           | `tools/blender/`                  |
| Agent frameworks          | See `agents/` folder              |

These examples are intentionally minimal so you can extend them.

---

## === PRODUCTION_PACKAGE_TEMPLATE.md ===

# GAME PRODUCTION PACKAGE — INPUT TEMPLATE

> **Purpose:** Fill this file (or a copy) and feed it to Jayson.  
> The system will decompose it into pipelines, agent handoffs, asset jobs, QA gates, and export targets.  
> Sections marked **[HUMAN]** require creator decisions.  
> Sections marked **[AI]** can be drafted or expanded by any capable model, then supervised.

**How to use**
1. Copy this file → `projects/<game_name>/PRODUCTION_PACKAGE.md`
2. Fill **[HUMAN]** sections first (minimum viable intent)
3. Ask Jayson (or any AI) to expand **[AI]** sections
4. Run `start_rpg_project` / genre pipeline with this package as context
5. Every stage ends with QA gate before handoff

---

# 0. DOCUMENT CONTROL

| Field | Value |
|-------|--------|
| Package version | 1.0 |
| Game working title | |
| Codename | |
| Date started | |
| Last updated | |
| Owner (human) | |
| Supervision mode | human-in-the-loop / autonomous-with-QA-gates |
| Target vertical slice date | |
| Target content-complete date | |

---

# 1. HIGH-LEVEL INTENT — [HUMAN]

## 1.1 One-sentence pitch
> 

## 1.2 Player fantasy
What does it *feel* like to play?
> 

## 1.3 Genre & subgenre
Primary: (Racing / FPS / TPS / Adventure / Open World / RPG / Hybrid: ___)  
Secondary:
> 

## 1.4 Perspective & camera
- [ ] 1st person
- [ ] 3rd person
- [ ] Isometric / top-down
- [ ] Fixed camera
- [ ] Hybrid: ___

## 1.5 Platforms (export targets)
Check all that apply:
- [ ] Windows
- [ ] Linux
- [ ] Android
- [ ] Meta Quest 2
- [ ] Meta Quest 3
- [ ] PS4 VR
- [ ] PS5 VR (PSVR2)
- [ ] PS3 (legacy/constraints only)
- [ ] Other: ___

## 1.6 Primary engine — [HUMAN] **REQUIRED**
Must match §11.1. Production Run will not advance past ASSEMBLY without this.

- [ ] Godot 4.x
- [ ] Unity
- [ ] Unreal Engine
- [ ] Custom / other: ________

**Editor version:** 
> 

## 1.7 Scope guardrails — [HUMAN]

Must ship in vertical slice:
> 

Explicitly out of scope for v1:
> 

Hard constraints (time, team size, engine, budget, rating):
> 

---

# 2. PILLARS & TONE — [HUMAN + AI]

## 2.1 Design pillars (3–5) — [HUMAN]
1. 
2. 
3. 
4. 
5. 

## 2.2 Tone & rating — [HUMAN]
Tone keywords:  
Content rating target (E / T / M / etc.):  
Violence / language / horror limits:
> 

## 2.3 References (games, films, art) — [HUMAN]
| Reference | What to steal | What to avoid |
|-----------|---------------|---------------|
|  |  |  |
|  |  |  |

## 2.4 Pillar tests — [AI]
For each pillar, one playable test that proves it is present in the vertical slice.
> 

---

# 3. STORY & NARRATIVE — [AI expandable, HUMAN approves]

## 3.1 Logline
> 

## 3.2 Theme
> 

## 3.3 Story structure
Format: (3-act / 5-act / episodic / open-ended)  
Synopsis:
> 

## 3.4 Main quest outline
| Act/Chapter | Goal | Obstacle | Twist/Payoff |
|-------------|------|----------|--------------|
|  |  |  |  |

## 3.5 Side content policy
How much side content vs main path? Mandatory vs optional?
> 

## 3.6 Codex / lore delivery method
Environmental / items / NPCs / collectibles / none
> 

**Pipeline link:** Storyline Maker tool + NarrativeWriter agent + QA Narrative

---

# 4. CHARACTERS — [AI expandable, HUMAN approves]

## 4.1 Player character(s)
| ID | Name | Role | Fantasy | Arc | Abilities | Visual notes |
|----|------|------|---------|-----|-----------|--------------|
| PC1 |  |  |  |  |  |  |

## 4.2 Major NPCs
| ID | Name | Role | Want | Relationship to PC | Fate |
|----|------|------|------|--------------------|------|
|  |  |  |  |  |  |

## 4.3 Enemies / factions
| ID | Name | Function in combat/story | Hierarchy |
|----|------|--------------------------|-----------|
|  |  |  |  |

## 4.4 Character bible rules — [AI]
Voice, vocabulary limits, visual silhouette rules:
> 

**Pipeline link:** NarrativeWriter + ArtDirector + QA Narrative / Art

---

# 5. WORLD — [AI expandable]

## 5.1 Setting summary
> 

## 5.2 Regions / biomes / tracks / maps
| ID | Name | Purpose | Size intent | Unlock condition | Activities |
|----|------|---------|-------------|------------------|------------|
| R1 |  |  |  |  |  |

## 5.3 Traversal
Walk / climb / vehicle / flight / fast travel rules:
> 

## 5.4 Day/night, weather, living world (if any)
> 

**Pipeline link:** WorldBuilder agent + genre pipeline (Open World / Adventure / Racing tracks)

---

# 6. CORE LOOP & SYSTEMS — [AI expandable, HUMAN approves numbers]

## 6.1 Core loop (30–120 seconds)
Describe the repeated verb cycle:
> 

## 6.2 Combat / challenge model
(If non-combat: puzzles, racing lines, social, etc.)
- Time-to-kill targets:
- Player power curve:
- Failure / death penalty:
> 

## 6.3 Progression
XP / unlocks / gear / skill tree / prestige:
| System | What upgrades | Soft cap | Soft currency | Premium currency |
|--------|---------------|----------|---------------|------------------|
|  |  |  |  |  |

## 6.4 Economy
Sources sinks balance notes:
> 

## 6.5 Inventory / loadout / crafting (if any)
> 

## 6.6 AI / opponent rules
(Racing AI, enemy archetypes, companion AI)
> 

**Pipeline link:** SystemsDesigner + QuestDesigner + QA Systems

---

# 7. QUESTS / MISSIONS / ACTIVITIES — [AI]

## 7.1 Mission template
| Field | Description |
|-------|-------------|
| ID | |
| Name | |
| Type | main / side / daily / challenge |
| Start condition | |
| Objectives | |
| Fail states | |
| Rewards | |
| Estimated length | |

## 7.2 Mission list (vertical slice minimum)
| ID | Name | Type | Region | Status |
|----|------|------|--------|--------|
| M01 |  | main |  | draft |

## 7.3 Activity taxonomy (open world / hybrid)
Combat / exploration / collection / social / racing / other:
> 

**Pipeline link:** QuestDesigner + genre activity tables + QA

---

# 8. LEVEL / TRACK / ENCOUNTER DESIGN — [AI]

## 8.1 Space list
| ID | Name | Type | Encounters | Secrets | Performance budget notes |
|----|------|------|------------|---------|--------------------------|
| L01 |  |  |  |  |  |

## 8.2 Encounter recipes
| ID | Setup | Enemy mix | Player resources | Intended duration |
|----|-------|-----------|------------------|-------------------|
| E01 |  |  |  |  |

## 8.3 Puzzle verbs (adventure)
> 

**Pipeline link:** genre pipeline (FPS arenas, racing tracks, adventure gates)

---

# 9. ART & VISUAL ASSET LIST — [AI + HUMAN]

## 9.1 Art pillars
Silhouette / color / material language:
> 

## 9.2 Characters & creatures — models
| Asset ID | Description | Poly budget | Textures | Rig | Priority | Source (AI gen / human / stock) |
|----------|-------------|-------------|----------|-----|----------|----------------------------------|
| CH_PC1 |  |  |  |  | P0 |  |
| CH_NPC_ |  |  |  |  |  |  |
| CR_ |  |  |  |  |  |  |

## 9.3 Props / vehicles / weapons
| Asset ID | Description | Budget | Priority | Source |
|----------|-------------|--------|----------|--------|
| PR_ |  |  |  |  |
| VH_ |  |  |  |  |
| WP_ |  |  |  |  |

## 9.4 Environment kits
| Kit ID | Biome/Region | Modular pieces needed | Priority |
|--------|--------------|----------------------|----------|
| ENV_ |  |  |  |

## 9.5 Materials & textures
| Mat ID | Type | Maps needed (A/R/M/N/E) | Resolution | Shared? |
|--------|------|-------------------------|------------|---------|
| MAT_ |  |  |  |  |

## 9.6 UI / HUD / icons
| UI ID | Description | Priority |
|-------|-------------|----------|
| UI_ |  |  |

## 9.7 VFX
| FX ID | Description | Priority |
|-------|-------------|----------|
| FX_ |  |  |

**Pipeline link:** Text/Image→3D (Luma/Meshy/Tripo) + Blender tools + 3D Screenshots + ArtDirector + QA Art/3D

---

# 10. AUDIO ASSET LIST — [AI + HUMAN]

## 10.1 Voice
| Line set ID | Character | Approx # lines | Tone | Priority | TTS / human |
|-------------|-----------|----------------|------|----------|-------------|
| VO_ |  |  |  |  |  |

## 10.2 Music
| Track ID | Use (title/explore/combat/boss) | Length | Mood | Priority |
|----------|----------------------------------|--------|------|----------|
| MUS_ |  |  |  |  |

## 10.3 SFX
| SFX ID | Event | Priority |
|--------|-------|----------|
| SFX_ |  |  |

## 10.4 Mix targets
Dialogue vs music vs SFX levels / LUFS goals:
> 

**Pipeline link:** Audio & Video Gen tool + Kokoro TTS + QA Audio

---

# 11. TECHNICAL PLAN — [AI + HUMAN]

## 11.1 Engine / framework — [HUMAN] **REQUIRED**
Pick **one primary engine** before production run Stage 4 (ASSEMBLY). Secondary DCC tools are optional.

| Choice | Check one |
|--------|-----------|
| Godot 4.x | [ ] |
| Unity | [ ] |
| Unreal Engine | [ ] *(supported in Jayson **4.0** — dedicated SSD; binary editor ~40–130 GB, not 1 TB)* |
| Custom / other | [ ] (name: __________) |

**Primary engine:** 
> 

**Editor version (required):** 
> 

**Why this engine (short):** 
> 

**DCC / support tools (optional):** Blender [ ] · other: 
> 

**Pipeline binding:** Godot → `pipelines/games/godot_pipeline.md` + `tools/godot/` · Unity → `tools/unity/` · Blender assets → `tools/blender/` · Unreal → **4.0** (dedicated SSD after engine install; 256–512 GB typical)


## 11.2 Target frame rate & resolution per platform
| Platform | FPS | Res / dynamic res | Graphics tier |
|----------|-----|-------------------|---------------|
| Windows |  |  |  |
| Quest 3 |  |  |  |
| … |  |  |  |

## 11.3 Input maps
Keyboard/mouse / gamepad / touch / VR controllers:
> 

## 11.4 Save system
What is saved, when, cloud or local:
> 

## 11.5 Scene / streaming strategy
> 

## 11.6 Modding / data-driven content (optional)
> 

**Pipeline link:** TechLead agent + Unity tools + export_targets.md

---

# 12. VERTICAL SLICE DEFINITION — [HUMAN REQUIRED]

## 12.1 Slice must include
- [ ] Playable start → goal → end
- [ ] One complete core-loop demonstration
- [ ] Listed P0 assets only
- [ ] One QA pass with no critical blockers

Exact slice description:
> 

## 12.2 Slice success criteria
> 

## 12.3 Slice exclusion list
> 

---

# 13. PRODUCTION PIPELINE BINDING — [SYSTEM]

Map package sections → Jayson agents/tools (do not delete).

| Package section | Primary agent / tool | QA agent |
|-----------------|----------------------|----------|
| Story (3) | Storyline Maker + NarrativeWriter | QA Narrative |
| Characters (4) | NarrativeWriter + ArtDirector | QA Narrative / Art |
| World (5) | WorldBuilder | QA Design |
| Systems (6) | SystemsDesigner | QA Systems |
| Quests (7) | QuestDesigner | QA Design |
| Levels (8) | Genre pipeline agents | QA Design |
| 3D assets (9) | Text/Image→3D + Blender + Screenshots | QA Art/3D |
| Audio (10) | Audio tool + Kokoro | QA Audio |
| Tech (11) | TechLead | QA Build |
| Slice (12) | Orchestrator | QA Build + QA Gate |
| Engine (1.6 / 11.1) | TechLead + engine pipeline | Must be set before ASSEMBLY |
| Exports (14) | Export pipeline | QA Export |

**Loop rule:** PLAN → ACT → CHECK → QA → HANDOFF (Tight Agent Loop tool)

---

# 14. EXPORT MATRIX — [HUMAN selects, AI fills constraints]

| Platform | In scope? | Input | Res/FPS target | SDK available? | Status (PREP_ONLY / BUILD) |
|----------|-----------|-------|----------------|----------------|----------------------------|
| Windows |  |  |  | n/a |  |
| Linux |  |  |  | n/a |  |
| Android |  |  |  |  |  |
| Quest 2 |  |  |  |  |  |
| Quest 3 |  |  |  |  |  |
| PS4 VR |  |  |  |  |  |
| PS5 VR |  |  |  |  |  |
| PS3 |  |  |  | legacy | PREP_ONLY |

Per-platform notes:
> 

**Pipeline link:** `pipelines/games/export_targets.md` + QA Export

---

# 15. QA & DELIVERY GATES — [SYSTEM]

## 15.1 Mandatory gates
1. Section-level `qa_inspect` on every major deliverable  
2. Stage `qa_gate` before handoff  
3. Final delivery gate before “done” or export package

## 15.2 Severity definitions
- **Critical:** Soft-lock, crash, data loss, unplayable controls  
- **Major:** Broken core loop, missing P0 asset, narrative contradiction  
- **Minor:** Polish, typos, non-blocking balance  

## 15.3 Delivery checklist
- [ ] Vertical slice criteria met
- [ ] All P0 assets present or explicitly waived
- [ ] No open Critical QA items
- [ ] Export profiles written for selected platforms
- [ ] Known limitations documented

---

# 16. RISK REGISTER — [AI + HUMAN]

| Risk | Impact | Likelihood | Mitigation | Owner |
|------|--------|------------|------------|-------|
|  |  |  |  |  |

---

# 17. MILESTONES — [HUMAN]

| Milestone | Date | Exit criteria |
|-----------|------|---------------|
| Package approved |  | HUMAN sign-off on sections 1, 2, 12 |
| Vertical slice playable |  | Section 12 criteria |
| Content complete (v1) |  | All P0 missions + assets |
| Release candidate |  | QA gate ALLOW_DELIVERY |

---

# 18. HUMAN CREATOR ONLY — FINAL SIGN-OFF

| Question | Answer |
|----------|--------|
| I approve the pillars and scope | YES / NO |
| I approve the vertical slice definition | YES / NO |
| I accept listed out-of-scope items | YES / NO |
| Supervision frequency | every handoff / daily / end of stage |
| Name / date |  |

---

# 19. AI EXECUTION BRIEF (paste to Jayson)

When this package is filled enough to start, give Jayson:

```
Load production package: projects/<game>/PRODUCTION_PACKAGE.md
Genre pipeline: <Racing|FPS|TPS|Adventure|OpenWorld|RPG>
Start orchestrator with supervision mode: <mode>
Begin Stage 1. Use Tight Agent Loop. QA gate every handoff.
Expand only [AI] sections; do not change [HUMAN] decisions without asking.
```

---

# 20. APPENDIX — MINIMUM FILL TO START

If short on time, HUMAN must complete at least:
- 1.1 Pitch
- 1.3 Genre
- 1.5 Platforms
- 1.6 Scope guardrails
- 2.1 Pillars
- 12.1–12.2 Vertical slice
- 18 Sign-off

Everything else can be drafted by AI and revised under supervision.

---

## === PRODUCTION_PACKAGE_EXAMPLE_MIN.md ===

# EXAMPLE — Minimal filled package (illustrative only)

Game working title: **Ash Circuit**  
Genre: Racing + light Adventure  
**Engine: Godot 4.x** (editor version: pin in §11.1)  
Platforms: Windows, Linux, Quest 3  

## Pitch
Street racing through a decaying arcology where shortcuts are illegal tunnels controlled by rival crews.

## Pillars
1. Risk = faster lines through dangerous shortcuts  
2. Cars feel heavy but readable  
3. Every crew has a visual and audio identity  

## Vertical slice
One night circuit (2 laps), 1 player car, 3 AI, 1 shortcut tunnel, start grid → finish podium, simple upgrade between failed runs.

## Out of scope v1
Story mode, multiplayer, damage simulation beyond visual scrapes, weather.

## AI brief
```
Load production package: projects/ash_circuit/PRODUCTION_PACKAGE.md
Genre pipeline: Racing
Start orchestrator with supervision mode: every handoff
Begin Stage 1 World/Track. Tight Agent Loop + QA gates.
```

---

## === PRODUCTION_REQUIREMENTS.md ===

# Jayson Production Package — Reusable Requirements Template

> **REUSE INSTRUCTIONS**
> 1. **Never edit this file in place for a real game.** It is the master template.
> 2. Copy it for each project:
>    ```bash
>    cp PRODUCTION_REQUIREMENTS.md projects/MyGame_production_requirements.md
>    ```
> 3. Fill only the copy. Keep this original clean for the next project.
> 4. Feed the **filled copy** to Jayson / the Orchestrator.
> 5. One project = one filled requirements file. Multiple games = multiple copies.
> 6. Version the filled file when major pillars change (`_v1`, `_v2`, …).
> 7. Any AI helping fill a copy must preserve all `[[HUMAN]]` fields the creator still owns.

---

# Jayson Production Package — Requirements Template

**Purpose:**  
This file is the **single input** a human (or any AI) fills out so Jayson can decompose, schedule, and execute a game production package with supervision.

**How to use:**
1. Copy this file → rename to `PROJECTNAME_production_requirements.md`
2. Fill every `[[HUMAN]]` section (required)
3. Optionally refine `[[AI_MAY_DRAFT]]` sections
4. Feed the completed file to Jayson / Orchestrator
5. System runs pipelines + agents; human supervises gates

**Rules for any AI helping write this package:**
- Never invent platform SDK secrets or claim certified console builds without human confirmation
- Prefer concrete, testable deliverables over vague vision
- Every asset must have an owner stage and acceptance criteria
- Mark unknowns as `TBD` with a question, do not silently skip
- Align with existing Jayson pipelines: RPG/Genre orchestrator, Storyline Maker, Text/Image→3D, Audio/Video, QA gates, Export targets

---

# 0. Document Control

| Field | Value |
|-------|--------|
| Project codename | [[HUMAN]] |
| Working title | [[HUMAN]] |
| Version of this requirements doc | 1.0 |
| Date | [[HUMAN]] |
| Primary creator / owner | [[HUMAN]] |
| Supervision mode | human-in-the-loop at every QA gate |
| Target ship quality | vertical slice / alpha / beta / release [[HUMAN]] |

---

# 1. Elevator Pitch & Pillars

## 1.1 One-sentence pitch
[[HUMAN]]  
*(Example: "A third-person open-world mystery where memory is a resource you spend to change the past.")*

## 1.2 Player fantasy
[[HUMAN]]  
What does it *feel* like to play?

## 1.3 Design pillars (3–5, non-negotiable)
1. [[HUMAN]]
2. [[HUMAN]]
3. [[HUMAN]]
4. [[AI_MAY_DRAFT]]
5. [[AI_MAY_DRAFT]]

## 1.4 Explicit non-goals
[[HUMAN]]  
*(What this game is NOT)*

---

# 2. Genre & Structure

## 2.1 Primary genre pipeline
Pick one (or primary + secondary):

- [ ] Racing
- [ ] 1st Person Shooter
- [ ] 3rd Person Shooter
- [ ] Adventure
- [ ] Open World
- [ ] RPG (use RPG Orchestrator)
- [ ] Hybrid — describe: [[HUMAN]]

## 2.2 Perspective & camera
[[HUMAN]]  
*(first-person / third-person / isometric / top-down / fixed / hybrid)*

## 2.3 Session length targets
| Session type | Target |
|--------------|--------|
| One meaningful loop | [[HUMAN]] minutes |
| Main story total | [[HUMAN]] hours |
| Completionist | [[HUMAN]] hours |

## 2.4 Platforms (export targets)
Check all that apply:

- [ ] Windows
- [ ] Linux
- [ ] Android
- [ ] Meta Quest 2
- [ ] Meta Quest 3
- [ ] PS4 VR
- [ ] PS5 VR
- [ ] PS3 (legacy constraints only)
- [ ] Other: [[HUMAN]]

**Primary launch platform:** [[HUMAN]]

---

# 3. Story & Narrative

> Use with Storyline Maker tool + NarrativeWriter agent + QA Narrative.

## 3.1 Logline
[[HUMAN]]

## 3.2 Theme
[[HUMAN]]

## 3.3 Tone & rating
[[HUMAN]]  
*(tone words + content rating intent)*

## 3.4 Story structure
- Acts: [[HUMAN]] (usually 3)
- Structure reference: [[AI_MAY_DRAFT]] (Hero’s Journey / Mystery / Gauntlet / etc.)

## 3.5 Main plot beats (must play)
| Beat | Summary | Required? |
|------|---------|-----------|
| Opening | [[HUMAN]] | Yes |
| Inciting incident | [[HUMAN]] | Yes |
| Midpoint | [[HUMAN]] | Yes |
| Low point | [[HUMAN]] | Yes |
| Climax | [[HUMAN]] | Yes |
| Resolution | [[HUMAN]] | Yes |

## 3.6 Characters

### Protagonist
| Field | Value |
|-------|--------|
| Name | [[HUMAN]] |
| Want | [[HUMAN]] |
| Need | [[HUMAN]] |
| Arc | [[HUMAN]] |
| Visual brief | [[HUMAN]] |
| Voice brief | [[HUMAN]] |

### Antagonist
| Field | Value |
|-------|--------|
| Name | [[HUMAN]] |
| Goal | [[HUMAN]] |
| Method | [[HUMAN]] |
| Visual brief | [[HUMAN]] |

### Supporting cast (repeat blocks as needed)
| Name | Role | Function in story | Visual | Voice |
|------|------|-------------------|--------|-------|
| [[HUMAN]] | | | | |

## 3.7 Codex / lore delivery method
[[HUMAN]]  
*(environmental, collectible, dialogue, optional)*

---

# 4. Gameplay Systems

> SystemsDesigner agent + QA Systems.

## 4.1 Core loop (one paragraph)
[[HUMAN]]

## 4.2 Verbs the player can do
| Verb | Description | Unlock condition |
|------|-------------|------------------|
| [[HUMAN]] | | |
| [[AI_MAY_DRAFT]] | | |

## 4.3 Combat / challenge (if any)
| Topic | Spec |
|-------|------|
| Camera during combat | [[HUMAN]] |
| Time-to-kill target | [[HUMAN]] |
| Player resources | [[HUMAN]] |
| Enemy archetypes (list) | [[HUMAN]] |
| Failure state | [[HUMAN]] |
| Assist options | [[HUMAN]] |

## 4.4 Progression
| Topic | Spec |
|-------|------|
| XP / unlock model | [[HUMAN]] |
| Player power curve | [[HUMAN]] |
| Economy (sources/sinks) | [[HUMAN]] |
| Meta-progression? | [[HUMAN]] |

## 4.5 Inventory / crafting / skills
[[HUMAN]] or `None`

## 4.6 AI directors / systems
[[HUMAN]]  
*(enemy director, rubber-banding, density director, etc.)*

---

# 5. World & Content

## 5.1 Space breakdown
| Space / Region | Purpose | Size intent | Must-have activities |
|----------------|---------|-------------|----------------------|
| [[HUMAN]] | | | |

## 5.2 Quest / mission list (minimum viable)
| ID | Name | Type | Summary | Reward |
|----|------|------|---------|--------|
| MQ01 | [[HUMAN]] | Main | | |
| SQ01 | [[HUMAN]] | Side | | |

## 5.3 Collectibles / activities taxonomy
[[AI_MAY_DRAFT]] aligned to genre pipeline

---

# 6. Asset Bible (AI-executable)

> Every row should be producible by existing tools/agents (3D pipeline, audio tools, storyline, etc.) or marked `HUMAN_ONLY`.

## 6.1 Characters / creatures — models
| Asset ID | Description | Poly/style target | Source method | Priority | Acceptance criteria |
|----------|-------------|-------------------|---------------|----------|---------------------|
| CHAR_PROTAG | [[HUMAN]] | stylized mid | Text/Image→3D + Blender | P0 | Centered, textured, screenshots pass QA Art |
| CHAR_ANTAG | [[HUMAN]] | | | P0 | |
| [[AI_MAY_DRAFT]] | | | | | |

## 6.2 Props / environment kits
| Asset ID | Description | Method | Priority | Acceptance |
|----------|-------------|--------|----------|------------|
| PROP_ | [[HUMAN]] | | P1 | |
| ENV_ | [[HUMAN]] | | P1 | |

## 6.3 Materials & textures
| Mat ID | Used on | Style notes | Maps needed | Priority |
|--------|---------|-------------|-------------|----------|
| MAT_ | [[HUMAN]] | | albedo/normal/roughness | P0 |

## 6.4 Animation / moveset (if needed)
| Anim ID | Owner | Description | Priority |
|---------|-------|-------------|----------|
| AN_ | [[HUMAN]] | idle/walk/run/attack… | P0 |

## 6.5 UI / HUD
| Element | Description | Priority |
|---------|-------------|----------|
| HUD_ | [[HUMAN]] | P0 |
| MENU_ | [[HUMAN]] | P0 |

## 6.6 Audio — voice
| Line set | Character | Approx # lines | Voice direction | Method |
|----------|-----------|----------------|-----------------|--------|
| VO_PROTAG | [[HUMAN]] | | | Kokoro / ElevenLabs |

## 6.7 Audio — music & SFX
| Cue ID | Type | Mood / use | Method | Priority |
|--------|------|------------|--------|----------|
| MUS_ | music | | external / tool | P1 |
| SFX_ | sfx | | | P0 |

## 6.8 Cinematics / video (optional)
| Shot ID | Description | Method | Priority |
|---------|-------------|--------|----------|
| CIN_ | [[HUMAN]] | Luma / external | P2 |

---

# 7. Technical Requirements

## 7.1 Engine / stack
[[HUMAN]]  
*(Unity / Unreal / Godot / custom / undecided)*

## 7.2 Target performance
| Platform | Resolution | FPS target | Notes |
|----------|------------|------------|-------|
| Primary | [[HUMAN]] | [[HUMAN]] | |
| VR (if any) | | | comfort requirements [[HUMAN]] |

## 7.3 Input
| Platform | Input methods |
|----------|---------------|
| [[HUMAN]] | keyboard/mouse, gamepad, touch, VR controllers |

## 7.4 Save system
[[HUMAN]]

## 7.5 Accessibility minimums
[[HUMAN]]  
*(subtitles, colorblind, difficulty, motion sickness options)*

---

# 8. Production Plan (system-executable)

## 8.1 Vertical slice definition (must ship first)
[[HUMAN]]  
Exact playable path from boot → meaningful end state.

## 8.2 Stage order (default)
1. World / Concept lock
2. Systems lock for slice
3. Narrative for slice
4. Art & audio for slice
5. Implementation
6. QA gate
7. Expand content
8. Export prep per platform
9. Final QA gate

## 8.3 Agent assignments
| Stage | Primary agent | Supporting tools |
|-------|---------------|------------------|
| World | WorldBuilder | Storyline Maker, Knowledge |
| Systems | SystemsDesigner | Tight Agent Loop |
| Quests | QuestDesigner | Storyline Maker |
| Narrative | NarrativeWriter | Storyline Maker |
| Art | ArtDirector | Text/Image→3D, Screenshots, Luma |
| Audio | (ArtDirector / Audio) | Audio tools, Kokoro |
| Tech | TechLead | Unity/Blender tools |
| QA | QA suite | qa_inspect + qa_gate |
| Export | TechLead + QA Export | export_targets pipeline |

## 8.4 Supervision checkpoints (human)
Human **must** approve:
- [ ] Pillars & non-goals
- [ ] Vertical slice definition
- [ ] Story climax
- [ ] Each QA gate FAIL resolution
- [ ] Any real platform SDK submission

---

# 9. Acceptance & QA

## 9.1 Global acceptance criteria
- [ ] Vertical slice completable without developer help
- [ ] All P0 assets pass QA Art / QA Audio
- [ ] Systems numbers documented and tunable
- [ ] No known soft-locks on critical path
- [ ] Export checklist filled for each selected platform
- [ ] Final `qa_gate` = ALLOW_DELIVERY

## 9.2 Deliverable package contents
1. This requirements file (completed)
2. World bible + systems doc + quest list
3. Asset folders (models, textures, audio)
4. Build or PREP_ONLY export notes per platform
5. QA reports (PASS/FAIL history)
6. Known issues list

---

# 10. Human Creator Section (required)

> Everything below is **only** for the human. AIs must not overwrite without explicit permission.

## 10.1 Personal vision notes
[[HUMAN]]

## 10.2 Must-keep ideas (sacred)
[[HUMAN]]

## 10.3 Hard constraints (time, money, skill, hardware)
[[HUMAN]]

## 10.4 References (games, films, art)
[[HUMAN]]

## 10.5 Open questions for the AI team
1. [[HUMAN]]
2. [[HUMAN]]
3. [[HUMAN]]

## 10.6 Sign-off
- Creator name: [[HUMAN]]
- Date: [[HUMAN]]
- “I approve this requirements doc as the source of truth for supervised production.”  
  Signature/ack: [[HUMAN]]

---

# 11. AI Execution Appendix (do not delete)

When this file is fed to Jayson:

1. Parse sections 1–9 into tasks  
2. `start_rpg_project` or genre pipeline as appropriate  
3. For each stage: Tight Agent Loop → produce artifacts → `qa_inspect` → human gate if required → `handoff`  
4. Produce assets via Text/Image→3D, Audio, Storyline, Blender, Unity tools  
5. Run export target checklists  
6. Stop on any FAIL until fixed  
7. Final delivery only after `qa_gate` ALLOW_DELIVERY + human sign-off on section 10

**End of template**

---

## === FIRST_GAME_WALKTHROUGH.md ===

# First Game Walkthrough — Idea → Installable Game

Human-led journey with Jayson supervising AI work.  
Follow in order. Do not skip QA gates.

---

## Phase 0 — Setup (once)

1. Install dependencies (`DEPENDENCIES.md`)
2. `docker compose -f docker-compose.full.yml up -d`
3. Open WebUI: admin account, TTS → Kokoro, Connections → bridge
4. Paste tools from `tools/openwebui_tools/` (factory tools first: production run, tight loop, QA, polish)
5. Optional: add API keys in `.env` (`CREDITS.md`)
6. Optional extras: accessibility, store listing, status dashboard tools

**You are ready when:** chat works, bridge lists models, production run tool is enabled.


---

## Phase 1 — Production input (HUMAN)

1. Copy `PRODUCTION_PACKAGE_TEMPLATE.md` → `projects/my_first_game/PRODUCTION_PACKAGE.md`
2. Fill **minimum [HUMAN]**:
   - Pitch (1.1)
   - Genre (1.3)
   - Platforms (1.5)
   - Scope in/out (1.6)
   - Pillars (2.1)
   - Vertical slice definition (12.1–12.2)
   - Sign-off (18)
3. Ask Jayson: *“Expand all [AI] sections for this package; do not change [HUMAN] decisions.”*
4. Review expansions; correct anything wrong

**Gate:** You approve the package. No generation yet.

---

## Phase 2 — Start orchestration

**Detailed tool usage:** see [`pipelines/games/production_run.md`](pipelines/games/production_run.md) (install tool, exact prompt, stage-by-stage, advance rules).

### Short version
1. Enable `production_run_orchestrator_tool`
2. Paste the start prompt from that guide with your package
3. Allow only `production_run_advance` after QA PASS


Paste the AI execution brief from package §19, e.g.:

```
Load production package: projects/my_first_game/PRODUCTION_PACKAGE.md
Genre pipeline: <your genre>
Supervision: every handoff
Start Stage 1. Tight Agent Loop + QA every handoff.
```

Use:
- `rpg_orchestrator_tool` or genre pipeline in `pipelines/games/genre_pipelines.md`
- `agent_loop_tight_tool` for each chunk of work

**Gate:** First stage QA PASS (World / Track / Arena — whatever stage 1 is).

---

## Phase 3 — Design spine (AI under supervision)

Order depends on genre; typical RPG/Adventure:

| Step | Agent focus | You check |
|------|-------------|-----------|
| World / track | Regions, rules | Pillars still true? |
| Systems | Core loop numbers | Fun on paper? |
| Quests / races / missions | P0 list only | Slice-sized? |
| Narrative | Tone + key scenes | Matches theme? |

After each: `qa_inspect` → fix → `handoff`.

**Gate:** Design docs support the vertical slice only (resist scope creep).

---

## Phase 4 — Levels / UI / VR (if needed)

- Levels: follow `pipelines/games/text_to_level.md`
- UI: `text_image_to_ui.md`
- VR targets: `text_to_vr.md`

**You play-read** the blockout/wireframe docs as if you were implementing tomorrow.

**Gate:** Level/UI specs have no soft-locks and list only P0 assets.

---

## Phase 5 — Assets (controlled flood)

1. Create folder tree from `pipelines/games/asset_assembly.md`
2. Create empty `manifests/assets_master.csv`
3. Generate art/audio **into `_incoming` only**
4. For each batch:
   - Assign asset IDs
   - Manifest row
   - QA Art/3D or Audio
   - Move to canonical folder when validated
5. Use Text/Image→3D, Blender, screenshots, Kokoro/TTS tools as needed

**Human rule:** If you can’t find an asset in 10 seconds from the manifest, the structure is wrong—fix before generating more.

**Gate:** All **P0** assets `validated` (not merely incoming).

---

## Phase 6 — Assemble in engine

1. Create engine project under `projects/my_first_game/engine_project/`
2. Import **only validated** assets
3. Build the **vertical slice scene** (one playable path)
4. Wire input, win/lose, simple save if required
5. Update `scenes_index.json` + manifest status → `integrated`

**Gate:** Cold boot → complete critical path once on your machine.

---

## Phase 7 — Final polish team (94%+)

1. Tool: `final_polish_team_tool` → `start_final_polish`
2. Score each package section
3. Rework gaps (max rounds as configured)
4. `polish_round_summary` until average ≥ 94% and **0 Criticals**
5. `qa_gate` → ALLOW_DELIVERY

**Gate:** Fidelity target met. You agree the game matches *your* package, not a random AI detour.

---

## Phase 8 — Build & installable package

1. Follow `asset_assembly.md` Stages E–F
2. Build platform targets you checked in the package
3. Produce installer/portable package under `release/installer/`
4. Write `README_PLAYER.md` (install, controls, how to finish the slice)
5. QA Export checklist (`export_targets.md`)

**Gate (human playtest journey):**

### Your personal QA test journey
1. Copy build to a clean folder (or second machine if possible)
2. Install using only `README_PLAYER.md`
3. Start game with no debug menus
4. Complete critical path **without** looking at design docs
5. Note every confusion, bug, or missing asset
6. If anything is Critical → back to Phase 7
7. If completable and acceptable → sign release notes

---

## Phase 9 — Done (Idea → Game)

You have finished when:

- [ ] Installable artifact exists
- [ ] Manifest lists every shipped asset
- [ ] Final polish passed
- [ ] You completed the cold playtest journey
- [ ] Known issues documented honestly

Celebrate. Then either expand content with new package version **or** start the next game with a tighter slice.

---

## Quick reference — tools by phase

| Phase | Tools / docs |
|-------|----------------|
| 1 | PRODUCTION_PACKAGE_TEMPLATE |
| 2–3 | rpg_orchestrator, genre_pipelines, tight loop, QA |
| 4 | text_to_level, text_image_to_ui, text_to_vr |
| 5 | text_image_to_3d, screenshots, audio tools, asset_assembly |
| 6 | Unity/Blender tools, engine |
| 7 | final_polish_team, qa_agents |
| 8 | export_targets, asset_assembly Stage F |
| 9 | Human playtest journey (this doc) |

---

## Advice for the first game only

- Prefer **tiny** vertical slice over “whole open world”
- One region, one loop, few characters
- Generate fewer assets; polish harder
- The production package is the boss—not the model’s improvisation

---

## === MEM20_INTEGRATION.md ===

# mem20 Agent Integration with Jayson (Open WebUI)

**mem20 Agent** is a powerful autonomous agent with terminal, file system, browser, memory, skills, and MCP support.

You can use Open WebUI (Jayson) as a beautiful frontend for mem20.

## How it works

```
You → Jayson (Open WebUI) → mem20 gateway → Tools + Reasoning → Response
```

mem20 does the actual agent work (tools, planning, memory).  
Jayson provides the polished chat interface, multi-user support, and branding.

## Quick Setup

### 1. Install & enable mem20 API server

```bash
mem20 config set GATEWAY_ENABLED true
mem20 config set GATEWAY_KEY your-strong-secret-key
```

Default port is usually `8642`.

### 2. Point Jayson to mem20

Add mem20 as an OpenAI-compatible endpoint:

**Option A – docker-compose**
```yaml
environment:
  - OPENAI_API_BASE_URL=http://host.docker.internal:8642/v1
  - OPENAI_API_KEY=your-strong-secret-key
```

**Option B – Admin Panel**
- Go to Connections / Models
- API Base URL: `http://host.docker.internal:8642/v1`
- API Key: the key you set above

### 3. Start chatting

Select the mem20 model in the Jayson model dropdown.  
All tool calls will be handled by mem20.

## Why this combination is strong

- mem20 = powerful autonomous agent
- Jayson = beautiful UI + multi-user + your custom 3D/video/Blender tools
- You can run normal models and the mem20 agent side-by-side

---

## === TOOLS_AND_MCP.md ===

# Jayson — Tools + MCP (Streamable HTTP) Guide

This file gives you everything needed to activate the tools and connect modern MCP servers.

---

## 1. How to add MCP Servers (New Streamable HTTP Protocol)

Open WebUI has **native MCP support** (v0.6.31+).

### Steps

1. Go to **Admin Panel → Settings → Integrations** (sometimes called External Tools / Tool Servers)
2. Click **+ Add Server**
3. Set these values carefully:

| Field | Value |
|-------|-------|
| **Type** | `MCP (Streamable HTTP)`  ← **important** |
| **URL** | `http://your-mcp-server:port/mcp` |
| **Auth** | None / Bearer / OAuth 2.1 (as required) |
| **ID** | short lowercase name (e.g. `blender`, `filesystem`) |
| **Name** | Human readable name |

4. Save. Restart Open WebUI if prompted.

> **Common mistake:** Choosing "OpenAPI" instead of **"MCP (Streamable HTTP)"**.  
> Always pick the MCP Streamable HTTP type for modern MCP servers.

### Example URLs

- Local MCP server running on host: `http://host.docker.internal:8000/mcp`
- Another container on same network: `http://mcp-blender:8000/mcp`
- Remote: `https://your-domain.com/mcp`

You can add as many MCP servers as you want.  
They appear as tools the model can call.

---

## 2. Recommended MCP Servers to add

You can connect any Streamable HTTP MCP server. Useful ones for Jayson:

- Filesystem MCP
- GitHub MCP
- Browser / Playwright MCP
- Database MCP
- Custom Blender MCP (if you build one)
- Any official or community MCP that speaks Streamable HTTP

---

## 3. Native Open WebUI Tools (Blender + 3D + Video)

These are Python Tools/Functions you paste directly into Open WebUI.

### How to install a Tool

1. Admin Panel → **Functions** or **Tools**
2. Create new
3. Paste the code below
4. Enable it
5. Make sure the model has tool calling enabled

---

### Tool A — Blender Control (Core)

```python
"""
title: Blender Control
author: Jayson
version: 1.0.0
description: Create objects, materials, cameras, render and export from Blender
requirements: 
"""

import subprocess
import tempfile
import os
from pathlib import Path

BLENDER = "blender"
OUT = Path.home() / "jayson_3d" / "blender"
OUT.mkdir(parents=True, exist_ok=True)

def run_blender(code: str, timeout=180):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        path = f.name
    try:
        r = subprocess.run([BLENDER, "--background", "--python", path],
                           capture_output=True, text=True, timeout=timeout)
        return {"success": r.returncode == 0, "stdout": r.stdout[-2000:], "stderr": r.stderr[-1000:]}
    finally:
        os.unlink(path)

class Tools:
    def create_cube(self, name: str = "Cube", size: float = 2.0) -> str:
        """Create a cube in Blender"""
        code = f'''
import bpy
bpy.ops.mesh.primitive_cube_add(size={size})
bpy.context.active_object.name = "{name}"
bpy.ops.wm.save_as_mainfile(filepath=r"{OUT}/scene.blend")
print("Created {name}")
'''
        return str(run_blender(code))

    def render_scene(self, filename: str = "render.png") -> str:
        """Render the current Blender scene"""
        out = OUT / filename
        code = f'''
import bpy
bpy.context.scene.render.filepath = r"{out}"
bpy.ops.render.render(write_still=True)
print("Rendered to {out}")
'''
        return str(run_blender(code, timeout=300))

    def export_glb(self, filename: str = "model.glb") -> str:
        """Export current scene as GLB"""
        out = OUT / filename
        code = f'''
import bpy
bpy.ops.export_scene.gltf(filepath=r"{out}", export_format='GLB')
print("Exported {out}")
'''
        return str(run_blender(code))

    def run_bpy(self, python_code: str) -> str:
        """Run arbitrary Blender Python (bpy) code. Full power."""
        code = f'''
import bpy
from mathutils import Vector, Euler
{python_code}
bpy.ops.wm.save_as_mainfile(filepath=r"{OUT}/scene.blend")
print("Script finished")
'''
        return str(run_blender(code, timeout=300))
```

---

### Tool B — 3D Model → Screenshots + Description

Use the more complete version from `pipelines/3d_screenshots/pipeline.py`.  
You can wrap the main function `model_to_screenshots_and_description` as a Tool the same way.

---

### Tool C — Video Understanding

Wrap `full_video_understanding` from `pipelines/video_understanding/pipeline.py` the same way.

---

## 4. Blender API + Unity API style

The tools above already expose a clean “API” that Jayson can call:

**Blender side**
- `create_cube`, `render_scene`, `export_glb`, `run_bpy` (full bpy access)

**Unity side**
- Use the `import_asset` tool to bring any GLB/FBX into a Unity project
- Then open the project

This is the practical way to give Jayson both Blender and Unity power without needing a live running Editor API.

---

## 5. Quick Checklist

- [ ] Start full stack (`docker-compose.full.yml`)
- [ ] Add MCP servers via **Admin → Integrations → MCP (Streamable HTTP)**
- [ ] Install the Blender Tool above
- [ ] (Optional) Install 3D screenshots + Video tools
- [ ] Enable tool calling on your main model
- [ ] Test: “Create a red metallic cube and render it”

Jayson is now ready for modern MCP servers + real 3D tool use.

---

## === agents/README.md ===

# Jayson — Agent Frameworks Integration Hub

This folder contains installation + connection guides for major AI agent frameworks.

## Frameworks Included

| Framework              | File                     | Installation detail level |
|------------------------|--------------------------|---------------------------|
| mem20 Agent           | `../MEM20_INTEGRATION.md` | Full                     |
| mem20 claw plugin               | `mem20 claw plugin.md`            | Expanded                 |
| Open WebUI Computer    | `openwebui-computer.md`  | Expanded                 |
| mem20 graph substrate              | `mem20 graph substrate.md`           | Expanded                 |
| mem20 crews                 | `mem20 crews.md`              | Expanded                 |
| AutoGen / AG2          | `autogen.md`             | Medium                   |
| Pydantic AI            | `pydantic-ai.md`         | Medium                   |
| smolagents             | `smolagents.md`          | Medium                   |
| OpenAI Agents SDK      | `openai-agents-sdk.md`   | Medium                   |
| LlamaIndex Workflows   | `llamaindex.md`          | Medium                   |
| Mastra                 | `mastra.md`              | Medium                   |

## Three main connection methods (used by almost all)

1. **OpenAI-compatible API** (easiest)  
   Point Jayson at the agent’s `/v1` endpoint.

2. **Open WebUI Pipe / Pipeline**  
   Make the agent appear as a selectable model.

3. **MCP (Streamable HTTP)**  
   Already fully supported in Jayson (see `TOOLS_AND_MCP.md`).

## Recommended order to try

1. mem20 (already documented)
2. mem20 claw plugin or Open WebUI Computer (turnkey personal agents)
3. mem20 crews or mem20 graph substrate (when you want custom multi-agent or stateful logic)

Start with one, get it working, then add more.

---

## === agents/autogen.md ===

# AutoGen / AG2 + Jayson — Installation & Connection

## 1. Install
```bash
pip install autogen-agentchat autogen-ext
# or follow current official AG2 / AutoGen docs
```

## 2. Connect
Same pattern as mem20 crews and mem20 graph substrate:

- Build your multi-agent conversation / group chat
- Wrap it in a small OpenAI-compatible `/v1/chat/completions` server
- Add the endpoint in Jayson Admin → Connections

Alternatively turn it into an Open WebUI Pipe.

## Best for
Conversational multi-agent systems where agents talk to each other in natural language turns.

---

## === agents/mem20 crews.md ===

# mem20 crews + Jayson — Installation & Connection

mem20 crews is excellent for role-based multi-agent teams (researcher + writer + reviewer, etc.).

## 1. Install mem20 crews

```bash
pip install mem20 crews mem20 crews-tools
```

Create your agents and crew as usual.

## 2. Connect to Jayson

### Easiest method – OpenAI-compatible wrapper

1. Write a small server that receives a chat message
2. Runs your mem20 crews crew with that message as the task
3. Returns the final result in OpenAI chat completions format

Then add it in Jayson:

- Admin → Connections
- API Base URL: `http://host.docker.internal:PORT/v1`
- API Key: whatever you choose

### Alternative
Turn the crew into an Open WebUI Pipe so it shows up as a model.

## 3. Best for
- Fast multi-agent prototypes
- Clear division of labor between agents
- Collaborative task solving

---

## === agents/mem20 graph substrate.md ===

# mem20 graph substrate + Jayson — Installation & Connection

mem20 graph substrate is the best choice for complex, stateful, production-grade agents.

## 1. Install mem20 graph substrate

```bash
pip install mem20 graph substrate mem20 chain substrate mem20 chain substrate-openai
# or the current recommended packages from official docs
```

Create your agent graph as usual (nodes, edges, state, tools…).

## 2. Expose it to Jayson (two good ways)

### Method A – OpenAI-compatible wrapper (recommended for beginners)

Create a small FastAPI (or similar) server that:

- Accepts `/v1/chat/completions`
- Runs your mem20 graph substrate agent
- Streams the final answer back

Then in Jayson Admin → Connections add:

- API Base URL: `http://host.docker.internal:YOUR_PORT/v1`
- API Key: any value you set

### Method B – Open WebUI Pipelines / Pipe

Turn the mem20 graph substrate agent into an Open WebUI Pipe so it appears directly in the model picker.  
See Open WebUI Pipelines documentation for the exact pattern.

## 3. Best for
- Multi-step workflows
- Human-in-the-loop
- Reliable production agents with memory and branching

---

## === agents/llamaindex.md ===

# LlamaIndex Workflows + Jayson

LlamaIndex is excellent when your agents are **document / knowledge / RAG heavy**.

## Connection Methods
- OpenAI-compatible wrapper
- Open WebUI Pipe
- Strong native support for tools and MCP

## Best for
- Knowledge bases
- Document Q&A agents
- Research agents that need to retrieve and synthesize information

---

## === agents/mastra.md ===

# Mastra + Jayson

Mastra is a strong **TypeScript-first** agent framework.

## Connection Methods
- OpenAI-compatible API
- MCP
- Can be wrapped for Open WebUI

## Best for
- TypeScript teams
- Full-stack JS/TS projects
- When you prefer TS over Python for agent logic

---

## === agents/openai-agents-sdk.md ===

# OpenAI Agents SDK + Jayson

The official lightweight Agents SDK from OpenAI (evolved from Swarm).

## Connection Methods
- Native OpenAI style (very easy)
- Can be exposed as a custom endpoint
- Works with any model provider that is OpenAI-compatible

## Best for
- Minimal boilerplate
- Quick single or multi-agent setups
- Teams already comfortable with OpenAI patterns

---

## === agents/mem20 claw plugin.md ===

# mem20 claw plugin + Jayson — Installation & Connection

mem20 claw plugin is one of the strongest turnkey personal agents in 2026.

## 1. Install mem20 claw plugin

Go to the official mem20 claw plugin repository / website and follow the current installation instructions.

Common methods:
- Official install script
- Docker
- Package manager

After installation, start the mem20 claw plugin service and **enable its OpenAI-compatible API server**.

Note:
- The port it is listening on (often something like 3001, 8080, or custom)
- The API key it generates

## 2. Connect to Jayson

1. Open Jayson → **Admin Panel → Connections**
2. Click Add Connection / OpenAI
3. Fill in:
   - **API Base URL**: `http://host.docker.internal:PORT/v1`
   - **API Key**: the key from mem20 claw plugin
4. Save

The mem20 claw plugin model will appear in the model selector.

## 3. Use it

Select the mem20 claw plugin model in any chat.  
Jayson is the frontend; mem20 claw plugin runs the actual agent (tools, skills, memory, channels…).

You can run mem20 claw plugin side-by-side with mem20 and your Blender/3D tools.

---

## === agents/openwebui-computer.md ===

# Open WebUI Computer + Jayson — Installation & Connection

This is the official computer/agent companion made by the Open WebUI team.  
It gives the agent a real computer (files, terminal, browser, git, etc.).

## 1. Install Open WebUI Computer

Open WebUI Computer is a **separate project** from the main Open WebUI.

1. Go to the official Open WebUI Computer repository / docs
2. Follow the installation instructions (usually Docker-based)
3. Start a workspace

It will expose an OpenAI-compatible gateway for that workspace.

## 2. Connect to Jayson

1. In Jayson go to **Admin Panel → Connections**
2. Add a new OpenAI-compatible connection
3. Use the URL and key provided by your Open WebUI Computer workspace
   - Typical form: `http://host.docker.internal:PORT/v1`

4. Save

Each workspace appears as a selectable model that has full computer access.

## 3. Why this is powerful

- Native fit with Jayson
- Real file system + terminal + browser
- Designed to work as the “action layer” while Jayson is the control / chat layer
- Excellent for coding and system tasks together with your 3D tools

---

## === agents/pydantic-ai.md ===

# Pydantic AI + Jayson

Pydantic AI is a clean, type-safe Python agent framework.

## Connection Methods
- Easy to wrap as OpenAI-compatible
- Excellent for structured outputs
- Works well with MCP

## Why it’s nice with Jayson
Very little boilerplate. You get strong typing and validation while still being able to expose the agent as a normal model in Jayson.

---

## === agents/smolagents.md ===

# smolagents (Hugging Face) + Jayson — Installation & Connection

## 1. Install
```bash
pip install smolagents
```

## 2. Connect
Create a simple agent with tools, then expose it via:

- A small OpenAI-compatible server, **or**
- An Open WebUI Pipe

Add the resulting endpoint in Jayson Admin → Connections.

## Best for
Minimal, transparent agents that write and run code to solve tasks. Great with local models.

---

## === blender/README.md ===

# Jayson ↔ Blender Integration

Goal: Let Jayson fully manipulate Blender (create objects, materials, lighting, cameras, render, export).

## Architecture (Recommended)

```
User → Jayson (Open WebUI)
         ↓
   Tool / Function call
         ↓
   Python script generated
         ↓
   Blender headless (--background --python script.py)
         ↓
   Result (render image / .glb / .blend / log)
         ↓
   Back to chat
```

## Requirements on the host machine

1. **Blender 4.x** installed and available in PATH
   ```bash
   blender --version
   ```

2. Preferably a GPU for faster rendering (Cycles/EEVEE)

3. Open WebUI must be able to execute commands on the host  
   (easiest via **Open Terminal** feature or custom tools that call `subprocess`)

## How Jayson will control Blender

### Method 1 – High-level Tools (Recommended)
We create specific tools such as:

- `blender_create_object`
- `blender_add_material`
- `blender_set_camera`
- `blender_render`
- `blender_export_glb`
- `blender_run_script` (raw Python power)

### Method 2 – Free-form Python
Jayson writes full `bpy` scripts and executes them.  
This gives almost complete control.

### Method 3 – Open Terminal
If you enable Open Terminal / Computer feature, Jayson can directly run:
```bash
blender --background --python /tmp/scene.py
```

## Current Limitations

- No real-time interactive viewport streaming (yet)
- Complex animations and physics need careful scripting
- Very large scenes can be slow without GPU

## Next Steps I can build for you

1. Ready-to-install Open WebUI **Tools / Functions** for Blender
2. A library of high-level commands
3. Automatic screenshot + description after every major change
4. GLB / FBX / USD export helpers
5. Material and lighting presets

Tell me how deep you want to go and I will generate the actual tool code.

---

## === bridge/README.md ===

# Jayson Model Bridge — Full Free Provider Set

Expanded with providers from:
https://github.com/12britz/awesome-free-models

## Providers included

| Provider              | Env Variable              |
|-----------------------|---------------------------|
| AnyAPI                | `ANYAPI_API_KEY`          |
| Google AI Studio      | `GEMINI_API_KEY`          |
| Groq                  | `GROQ_API_KEY`            |
| Hugging Face          | `HF_TOKEN`                |
| Cloudflare            | `CLOUDFLARE_API_KEY` + `CLOUDFLARE_ACCOUNT_ID` |
| Qwen / Alibaba        | `DASHSCOPE_API_KEY`       |
| Mistral               | `MISTRAL_API_KEY`         |
| DeepSeek              | `DEEPSEEK_API_KEY`        |
| OpenRouter            | `OPENROUTER_API_KEY`      |
| NVIDIA NIM            | `NVIDIA_API_KEY`          |
| Together              | `TOGETHER_API_KEY`        |
| Cohere                | `COHERE_API_KEY`          |
| SiliconFlow           | `SILICONFLOW_API_KEY`     |
| Moonshot / Kimi       | `MOONSHOT_API_KEY`        |
| Zhipu / Z.ai          | `ZHIPU_API_KEY`           |
| SambaNova             | `SAMBANOVA_API_KEY`       |
| Cerebras              | `CEREBRAS_API_KEY`        |
| Fireworks             | `FIREWORKS_API_KEY`       |
| Novita                | `NOVITA_API_KEY`          |
| Microsoft Foundry     | `AZURE_API_KEY` + `AZURE_API_BASE` |
| Ollama (local)        | (none)                    |

## Router groups
- `fast` / `balanced` / `strong`

## Start
```bash
docker compose -f docker-compose.full.yml up -d
```

## Connect to Jayson
- Base URL: `http://host.docker.internal:4000/v1`
- Key: `jayson-bridge-secret-change-me`

Only the providers you give keys for will work. The rest stay available for when you add keys later.

## Microsoft Foundry SDK note

The bridge uses the OpenAI-compatible Azure/Foundry endpoint only.
For deeper Foundry features (agents, evaluations, projects) install later:

```bash
pip install azure-ai-projects azure-identity openai
```

---

## === ci/README.md ===

# CI sketches

- `godot-export.yml` — headless export reminder. Pin editor **and** templates to the same version.
- Unity batchmode is project-specific; keep on the Unity path when you have a license.
- Do not commit `export_credentials.cfg`.

---

## === pipelines/README.md ===

# Jayson Advanced Pipelines

## 1. 3D Model → Screenshots + Description

**Location:** `pipelines/3d_screenshots/pipeline.py`

**What it does:**
- Takes any 3D model (GLB, OBJ, FBX, BLEND)
- Renders 6 clean angles (front, back, left, right, top, 3/4)
- Prepares a vision prompt so Jayson (or any vision model) can write a detailed description

**Main function:** `model_to_screenshots_and_description(model_path)`

**Typical flow:**
1. User or previous step provides a .glb
2. Call the pipeline → get images
3. Feed images + vision prompt to a vision model
4. Get rich text description of the 3D asset

---

## 2. Advanced Video Understanding

**Location:** `pipelines/video_understanding/pipeline.py`

**What it does:**
- Extracts audio and transcribes it
- Extracts key frames
- Prepares everything for a vision model + final summary

**Main function:** `full_video_understanding(video_path)`

**Requires:** `ffmpeg` (usually already present)

**Optional:** `faster-whisper` for local transcription

---

## 3. Local High-Quality TTS (Kokoro)

**Location:** `tts/` + `docker-compose.full.yml`

**How to start:**
```bash
docker compose -f docker-compose.full.yml up -d
```

TTS will be available at: `http://localhost:8880`

**Configure in Open WebUI:**
1. Admin Panel → Settings → Audio
2. TTS Engine: OpenAI
3. API Base URL: `http://host.docker.internal:8880/v1` (or `http://jayson-tts:8880/v1` from inside the network)
4. API Key: any value (or leave as needed by the image)
5. Choose a Kokoro voice

Now Voice Mode and message read-aloud will use high-quality local TTS.

---

## Activation Order Recommendation

1. Start the full stack (`docker-compose.full.yml`)
2. Configure Audio in Admin Panel (point to the TTS service)
3. Turn the Python pipelines into Open WebUI Tools / Functions
4. Give Jayson access to the 3D screenshot and video tools

---

## === pipelines/image_to_3d.md ===

# Text / Image → 3D Pipeline (Enhanced)

Extra effort path for turning text or pictures into usable 3D assets.

## Recommended order (2026)

### A. Text → 3D
1. Write a precise prompt (shape, materials, style, “single clean object, centered”).
2. Call the **Text & Image to 3D** tool (`text_to_3d`) with provider:
   - **Luma** (Dream Machine / Genie) – cinematic quality
   - **Meshy** – dedicated 3D, good retopo
   - **Tripo** – fast characters/objects
3. Download `.glb`
4. Refine in Blender (Jayson Blender tools)
5. Run **3D Screenshots** tool for multi-angle review
6. Iterate prompt or sculpt until good enough
7. Optional: import to Unity

### B. Image → 3D
1. Upload image (or describe it clearly)
2. Call `image_to_3d` on the same tool
3. Same refinement loop as above

## Provider keys (add to `.env` or tool valves)

```bash
LUMA_API_KEY=
MESHY_API_KEY=
TRIPO_API_KEY=
```

## Quality tips
- One main subject per generation
- Mention topology hopes (“clean quad mesh”, “game ready”)
- Always review with screenshots before declaring done
- Multiple iterations beat one perfect first try

## Related tools
- `tools/openwebui_tools/text_image_to_3d_tool.py`
- `tools/openwebui_tools/3d_screenshots_tool.py`
- `tools/blender/blender_tools.py`
- `tools/unity/unity_tools.py`

---

## === pipelines/rpg_orchestration.md ===

# RPG Game Orchestrator — Pipeline & Agent Handoffs

Push a full RPG through specialist agents with clean handoffs.

## Agents

| Agent            | Responsibility                                      |
|------------------|-----------------------------------------------------|
| WorldBuilder     | Lore, map regions, factions, tone                   |
| SystemsDesigner  | Combat, progression, economy, skills                |
| QuestDesigner    | Main quest, side content, NPCs, pacing              |
| NarrativeWriter  | Dialogue, scenes, descriptions, codex               |
| ArtDirector      | Visual pillars, audio mood, UI direction            |
| TechLead         | Engine plan, vertical slice, milestones             |
| PlaytestLead     | Fun tests, balance, iteration backlog               |

## How to run

1. **Start the project**
   ```
   Use tool: start_rpg_project
   → project name + premise
   ```

2. **Give the first agent its prompt**
   ```
   Use tool: agent_prompt (WorldBuilder) + project context
   ```
   (Or use mem20 / mem20 claw plugin / mem20 crews with that role.)

3. **When the agent finishes a chunk**
   ```
   Use tool: handoff
   from_agent → to_agent
   summary + artifacts + blockers
   ```

4. **Repeat** until PlaytestLead loops back for expansions.

## Suggested agent backends

- Open WebUI multi-model chat (different system prompts per agent)
- mem20 crews crew with one agent per role
- mem20 graph substrate state machine (stage = node)
- mem20 / mem20 claw plugin for longer autonomous runs
- Sub-agents inside Open WebUI for parallel research

## Tie-ins to other Jayson tools

| Stage            | Also use                          |
|------------------|-----------------------------------|
| Narrative        | Storyline Maker                   |
| Art              | Text/Image → 3D, Luma, screenshots |
| Audio            | Audio & Video Gen + Kokoro TTS    |
| World / Quests   | Knowledge bases for continuity    |
| Tech             | Blender + Unity tools             |

## Vertical slice goal

Aim for one playable loop early:
- One region
- One combat encounter
- One short quest
- One character art pass
- Basic save / load plan

Then expand with more handoffs.

---

## === pipelines/games/README.md ===

# Games pipelines

## Spine (do not skip)

| Doc | Purpose |
|-----|---------|
| `production_run.md` | Forced idea→game driver + how to use |
| `asset_assembly.md` | Intake → manifest → integrate → installer |
| `final_polish.md` | 94%+ fidelity team |
| `genre_pipelines.md` | Racing, FPS, TPS, Adventure, Open World |
| `export_targets.md` | Windows, Linux, Android, Quest, PS VR notes |
| `godot_pipeline.md` / `godot_export.md` | Godot 4 assembly + real export CLI |
| `../rpg_orchestration.md` | RPG stage agents |

## Generators

| Doc | Purpose |
|-----|---------|
| `text_to_level.md` | Text → level package |
| `text_image_to_ui.md` | Text/Image → UI kit |
| `text_to_vr.md` | Text → VR-safe spec |

## Extras (2.0-beta1)

| Doc | Purpose |
|-----|---------|
| `save_load_settings.md` | Save/settings schema |
| `localization.md` | String tables / VO keys |
| `accessibility.md` | A11y checklist |
| `store_listing.md` | Store copy + art list |
| `modding_dlc.md` | Data-only mods/DLC |
| `analytics_events.md` | Event dictionary |

## Order
1. Package + engine choice  
2. Production run Stage 0  
3. Tight loop + QA each stage  
4. `scripts/lint_manifest.py` before assemble  
5. Polish + accessibility  
6. Export + store listing  

---

## === pipelines/games/accessibility.md ===

# Accessibility Pass

Run before FINAL_POLISH. Tool: `accessibility_tool.py`

## Checklist
- [ ] Subtitles on/off + size
- [ ] Colorblind presets (deuteranopia, protanopia, tritanopia) — never color-only signals
- [ ] Remappable controls
- [ ] Invert look / hold-to-toggle
- [ ] UI contrast vs art pillars
- [ ] Flash/intensity options if VFX heavy
- [ ] VR: comfort vignette, snap/smooth turn (see text_to_vr.md)
- [ ] Screen reader notes for menus (desktop)

## Output
`qa/accessibility_report.md` — FAIL if color-only win/lose or no remapping on keyboard+gamepad slice.

---

## === pipelines/games/analytics_events.md ===

# Analytics Event Dictionary

Optional. Design events **before** code.

| event | when | props |
|-------|------|--------|
| session_start | boot | platform, version |
| tutorial_step | each beat | step_id |
| run_end | fail/win | duration, cause |
| economy_sink | spend | item, amount |
| economy_source | gain | item, amount |

No PII. Vertical slice can log to local JSON. Cloud analytics is post-ship.

---

## === pipelines/games/asset_assembly.md ===

# Asset Assembly & Management Pipeline

**Goal:** After a successful production run, turn scattered AI outputs into a **clean, installable game**—not 30,000 loose files and not 300 assets dumped in one folder.

## Core principle

```
idea → production package → pipelines → staged assets → assembled project → build → installable package
```

Every asset gets an **ID**, a **home folder**, and a **manifest entry** before it is allowed near a build.

---

## 1. Canonical project layout

Use this tree (engine-agnostic). Map folders into Unity/Unreal/Godot as needed.

```
projects/<game_name>/
├── PRODUCTION_PACKAGE.md          # source of truth
├── manifests/
│   ├── assets_master.csv          # every asset ID, path, status
│   ├── scenes_index.json
│   └── build_manifest.json
├── design/
│   ├── narrative/
│   ├── systems/
│   ├── levels/
│   └── ui/
├── art/
│   ├── characters/
│   ├── creatures/
│   ├── props/
│   ├── weapons/
│   ├── vehicles/
│   ├── environments/
│   │   └── <region_id>/
│   ├── materials/
│   ├── textures/
│   ├── ui/
│   ├── vfx/
│   └── _incoming/                 # quarantine for new AI dumps
├── audio/
│   ├── voice/<character_id>/
│   ├── music/
│   ├── sfx/
│   └── _incoming/
├── levels/
│   └── <level_id>/
│       ├── blockout/
│       ├── art/
│       └── data/
├── code/ or engine_project/       # actual game project
├── builds/
│   ├── windows/
│   ├── linux/
│   ├── android/
│   └── quest/
├── qa/
│   ├── reports/
│   └── playtest_notes/
└── release/
    ├── installer/                 # final installable artifacts
    └── notes/
```

**Rule:** Nothing goes straight into `engine_project` from a generator. It lands in `_incoming/`, gets IDed, validated, then moved.

---

## 2. Asset ID scheme

Format: `<TYPE>_<NAME>_<VARIANT>`

| Prefix | Type |
|--------|------|
| CH_ | Character |
| CR_ | Creature |
| PR_ | Prop |
| WP_ | Weapon |
| VH_ | Vehicle |
| ENV_ | Environment kit piece |
| MAT_ | Material |
| TEX_ | Texture set |
| UI_ | UI element |
| FX_ | VFX |
| VO_ | Voice line set |
| MUS_ | Music track |
| SFX_ | Sound effect |
| LVL_ | Level |
| SCN_ | Scene |

Example: `CH_PC1_HERO_A`, `PR_CRATE_METAL_01`, `LVL_DOCKS_01`

---

## 3. Master manifest (`assets_master.csv`)

Required columns:

```
asset_id,type,name,path,source,package_section,priority,status,qa_status,notes
```

Statuses: `incoming` → `validated` → `integrated` → `ship` | `cut`

**Pipeline step:** every generator output must append/update a row before handoff.

---

## 4. Assembly stages

### Stage A — Intake
1. Drop AI outputs into `art/_incoming` or `audio/_incoming`
2. Run naming pass (assign asset_id)
3. Deduplicate (same mesh renamed 12 times → one canonical)
4. Record in manifest as `incoming`

### Stage B — Validate
1. QA Art/3D or QA Audio on each P0 item
2. Check scale, origin, poly budget, naming
3. Status → `validated` or back to rework

### Stage C — Integrate
1. Move to canonical folder under `art/` / `audio/` / `levels/`
2. Import into engine project **via script or documented steps**
3. Hook into scene / prefab / data table
4. Status → `integrated`

### Stage D — Scene assembly
1. Build scenes only from **integrated** assets
2. Update `scenes_index.json`
3. Vertical-slice scene must boot with P0 only

### Stage E — Build packaging
1. Engine build → `builds/<platform>/`
2. Strip debug/dev-only content
3. Write `build_manifest.json` (version, commit, asset set hash)
4. QA Build + QA Export

### Stage F — Installable release
| Platform | Package form |
|----------|----------------|
| Windows | Installer (e.g. NSIS/Inno) or portable zip + README |
| Linux | AppImage or tar.gz + launch script |
| Android | Signed APK/AAB |
| Quest | Store package / sideload APK per Meta process |

Output goes to `release/installer/` with:
- `README_PLAYER.md` (how to install/play)
- `KNOWN_ISSUES.md`
- version number matching production milestone

---

## 5. Agents / tools for assembly

| Role | Job |
|------|-----|
| IntakeLibrarian | Sort `_incoming`, assign IDs, update CSV |
| Deduper | Find duplicate assets |
| IntegrationTech | Move validated → engine, wire references |
| SceneAssembler | Compose levels from integrated assets only |
| BuildEngineer | Produce platform builds |
| ReleaseManager | Create installable package + player-facing docs |
| QAGateCaptain | Block release if manifest has open Criticals |

Use Tight Agent Loop on each stage; Final Polish before Stage F.

---

## 6. Anti-chaos rules (non-negotiable)

1. **No flat folders** of hundreds of files  
2. **No build from `_incoming`**  
3. **P0 assets only** in vertical slice builds  
4. **Manifest is law** — if it’s not in the CSV, it doesn’t ship  
5. **One owner path per asset_id**  
6. **Human signs** production package + final release checklist  

---

## 7. Success definition: “Idea to game”

You are done when:

- [ ] Production package [HUMAN] sections signed  
- [ ] Vertical slice criteria met  
- [ ] Final polish ≥ 94% fidelity, 0 Criticals  
- [ ] `assets_master.csv` has every shipped asset  
- [ ] Installable package exists under `release/installer/`  
- [ ] A cold player can install and complete the critical path using only `README_PLAYER.md`  

---

## === pipelines/games/export_targets.md ===

# Export / Target Platform Pipelines

Realistic export guidance for builds leaving the Jayson production pipeline.

> Note: Full official console certification requires platform NDAs/SDKs you must obtain yourself.
> These pipelines prepare content and checklists so exports are systematic.

## Common pre-export QA
- [ ] Critical path completable
- [ ] Resolution & UI scale defined
- [ ] Input map documented
- [ ] Performance budget target set
- [ ] Save/load verified
- [ ] QA gate PASS

---

## Windows
- Target: DX11/DX12 or Vulkan
- Controllers: Xbox layout baseline
- Package: installer or portable zip
- Checks: windowed/fullscreen, alt-tab, 16:9/ultrawide

## Linux
- Target: Vulkan preferred
- Package: AppImage / Flatpak notes
- Checks: gamepad via SDL, native vs Proton path documented

## Android
- Target: OpenGL ES / Vulkan
- Aspect ratios: 16:9, 18:9, 19.5:9, foldables if claimed
- Input: touch + optional controller
- Checks: thermal throttling plan, install size, permissions list
- Store: package id, version code, signed build checklist

---

## Meta Quest 2
- Target: Android (Quest)
- Render: forward, fixed foveated if used
- Refresh: 72/90 Hz targets documented
- Input: Touch controllers only unless hand-tracking claimed
- Checks: comfort (locomotion, vignetting), guardian-safe movement, performance headroom

## Meta Quest 3
- Same as Quest 2 plus:
- Higher res & optional color passthrough features if used
- Dynamic resolution policy
- Mixed reality boundary rules if MR features exist

---

## PlayStation VR (PS4 VR)
- Requires PS4 SDK / dev hardware (external)
- Checklist only in open pipeline:
  - Move / DualShock input mapping
  - Reprojection assumptions
  - Comfort modes
  - Tracking loss behavior

## PlayStation VR2 (PS5 VR)
- Requires PS5 SDK / dev hardware (external)
- Checklist:
  - Sense controller mapping
  - Eye/adaptive triggers usage (if any)
  - HDR / OLED brightness safety
  - Social screen (TV mirror) behavior

## PS3 (legacy)
- Historical/target only — modern Unity/Unreal do not ship PS3
- Pipeline role: asset constraint sheet (polycounts, textures, audio formats) if remastering or emulating
- Prefer documenting limits over claiming automated export

---

## Export handoff template
For each target produce:
1. `platform_profile.md` — constraints & input
2. `build_notes.md` — how to produce the build
3. `qa_export_report.json` — from QA Export agent
4. Binary or package path (when SDK available)

If SDK is not available, mark export as **PREP_ONLY** and keep asset/platform budgets enforced upstream.

---

## === pipelines/games/final_polish.md ===

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

---

## === pipelines/games/genre_pipelines.md ===

# Game Genre Pipelines

Specialized stage flows that plug into the RPG Orchestrator pattern (or run standalone).

## Shared spine (all genres)
1. Concept & pillars
2. Core loop
3. Vertical slice
4. Content expansion
5. Systems hardening
6. QA gate
7. Export targets
8. Release candidate

---

## Racing
**Agents:** TrackDesigner → VehicleSystems → AIDirector → Progression → ArtAudio → Tech → QA

**Core loop focus:** corner → exit speed → risk/reward → upgrade → next track

**Key deliverables:**
- Track list + lap targets
- Vehicle classes & handling models
- Opponent rubber-band rules
- Career / unlock tree
- Ghost/replay requirements

**Vertical slice:** 1 track, 1 car class, 3 AI, race start→finish, simple upgrade

---

## 1st Person Shooter (FPS)
**Agents:** ArenaDesigner → GunplaySystems → EnemyDirector → Progression → Narrative (light) → ArtAudio → Tech → QA

**Core loop focus:** peek → engage → reposition → reload/resource → objective

**Key deliverables:**
- Movement & TTK targets
- Weapon roster + recoil identities
- Enemy archetypes
- Encounter budget per space
- Map flow diagrams

**Vertical slice:** 1 map, 3 weapons, 3 enemy types, one complete objective

---

## 3rd Person Shooter (TPS)
**Agents:** same as FPS + CoverDesigner + CameraSystems

**Extra focus:**
- Cover quality & blind-fire rules
- Camera collision / shoulder swap
- Melee vs ranged spacing
- Companion AI (optional)

**Vertical slice:** 1 hub + 1 combat space, cover set, 2 weapons, camera stable under fire

---

## Adventure
**Agents:** WorldBuilder → PuzzleDesigner → NarrativeWriter → InventorySystems → ArtAudio → Tech → QA

**Core loop focus:** explore → observe → use item/ability → revelation → new area

**Key deliverables:**
- Region map with gated paths
- Puzzle verbs (unique interactions)
- Critical path item chain
- Lore delivery method (environmental vs dialogue)

**Vertical slice:** 1 region, 3 puzzles, 1 key story beat, no soft-locks

---

## Open World
**Agents:** WorldBuilder → ActivityDesigner → SystemsDesigner → QuestDesigner → DensityDirector → ArtAudio → Tech → QA

**Core loop focus:** traverse → spot activity → engage → reward → new horizon

**Key deliverables:**
- Biome list + traversal tools
- Activity taxonomy (combat, social, collect, story)
- Density rules (how often something interesting appears)
- Fast travel & difficulty scaling
- Main story vs side content balance

**Vertical slice:** 1 biome, 1 traversal tool, 3 activity types, 1 story mission, day/night or weather optional

---

## Handoff rule
Every genre stage ends with:
1. `check_step` (Tight Agent Loop)
2. `qa_inspect` (QA suite)
3. `handoff` to next agent only on PASS / PASS_WITH_NOTES

---

## === pipelines/games/godot_export.md ===

# Godot Export Pipelines — Investigation (2.0)

How Godot 4 actually ships builds, mapped to Jayson `export_targets` + `asset_assembly`.

---

## 1. Mental model

| Piece | Role |
|-------|------|
| **Editor binary** | Required for `--export-*` (not an export template alone) |
| **Export templates** | Must **match editor version exactly** (Editor → Manage Export Templates) |
| **`export_presets.cfg`** | Per-platform presets (safe to commit) |
| **`.godot/export_credentials.cfg`** | Keystores/passwords (**do not commit**) |
| **Output path** | Relative to **project path**, not shell cwd |

Jayson stages: only export **after** ASSEMBLY + QA Build; outputs land under `builds/<platform>/` then `release/installer/`.

---

## 2. Platforms vs Jayson matrix

| Jayson target | Godot support | Notes |
|---------------|---------------|--------|
| Windows | First-class | Preset "Windows Desktop" → `.exe` (+ optional `.pck`) |
| Linux | First-class | `.x86_64` binary typical |
| Android | First-class | JDK **17**, Android SDK, templates, keystore; APK (test) or AAB (Play) |
| Meta Quest 2/3 | Via **Android** | OpenXR, Gradle build, Meta/vendor XR features; developer mode + ADB |
| PS VR / PS3 | **Not** native Godot | Stay PREP_ONLY / other engine |
| Web | Supported | `.zip`; not a Quest substitute |

---

## 3. One-time machine setup

### Desktop (Windows / Linux export)
1. Install Godot **editor** (version pinned in Production Package §11.1)
2. Install **export templates** for that exact version
3. Create presets: Project → Export → Add → Windows / Linux
4. Set **Export Path** e.g. `../../builds/windows/GameName.exe`

### Android (+ Quest)
1. **OpenJDK 17** (21 often breaks Gradle for Godot)
2. Android SDK (command-line tools + platform packages)
3. Editor Settings → Export → Android: **Java SDK path**, **Android SDK path**
4. Project → Install Android Build Template (if using Gradle / custom build)
5. Keystore for release:
   ```bash
   keytool -v -genkey -keystore mygame.keystore -alias mygame -keyalg RSA -validity 10000
   ```
6. Preset: package name `com.studio.game`, XR Mode **OpenXR** for Quest, enable Gradle when required

### Quest-specific
- Separate Android preset named e.g. `Meta Quest`
- XR Mode: OpenXR; vendor plugins as needed (Godot 4.6+ vendor plugin optional but useful for stores)
- Device: developer mode, ADB visible
- Still an APK/AAB pipeline — not a separate Godot “Quest export type”

---

## 4. CLI export (CI / production run Stage 6)

Editor binary + headless:

```bash
# From anywhere; path points at project.godot directory
godot --headless --path projects/<game>/engine_project \
  --export-release "Windows Desktop" builds/windows/GameName.exe

godot --headless --path projects/<game>/engine_project \
  --export-release "Linux/X11" builds/linux/GameName.x86_64

godot --headless --path projects/<game>/engine_project \
  --export-release "Android" builds/android/GameName.apk
```

Also available:
```bash
godot --headless --path <project> --export-debug "Windows Desktop" builds/windows/GameName_debug.exe
godot --headless --path <project> --export-pack "Windows Desktop" builds/windows/GameName.pck
```

**Rules**
- Preset **name** must match `export_presets.cfg` exactly (quote if spaces)
- Output path is relative to **project**, or absolute
- Templates must be installed or export fails silently/with error

---

## 5. Recommended preset set for Jayson projects

| Preset name | Platform | Export path pattern |
|-------------|----------|---------------------|
| Windows Desktop | Windows | `res://../../builds/windows/<Game>.exe` or absolute under `builds/windows/` |
| Linux/X11 | Linux | `builds/linux/<Game>.x86_64` |
| Android | Phone/sideload | `builds/android/<Game>.apk` |
| Android Play | Store | `builds/android/<Game>.aab` |
| Meta Quest | Android+OpenXR | `builds/quest/<Game>.apk` |

After export, **ReleaseManager** copies into `release/installer/` with `README_PLAYER.md`.

---

## 6. Pipeline binding (production run)

```
Stage 4 ASSEMBLY  → Godot project + integrated assets only
Stage 5 POLISH    → still engine-open, fix issues
Stage 6 RELEASE   → CLI or editor export per preset in package matrix
                  → QA Export
                  → human cold install test
```

Hard rules:
- Never export from `_incoming`
- Never commit `export_credentials.cfg`
- Pin Godot version in Production Package §11.1
- Android/Quest needs JDK17 + SDK on the **build machine** (your cloud VM later)

---

## 7. CI sketch (optional 2.0 follow-up)

```yaml
# Conceptual — pin URLs to your Godot version
- install Godot editor + export templates (same version)
- checkout project (export_presets.cfg committed)
- inject credentials on runner only
- godot --headless --path . --export-release "Linux/X11" builds/linux/game.x86_64
- upload builds/
```

Community actions exist (e.g. godot-export GitHub Action patterns); pin versions carefully.

---

## 8. Gaps / honesty

| Want | Reality |
|------|---------|
| One button all platforms | Editor “Export All” or multiple CLI calls; official per-preset CLI |
| Quest as first-class | Android + OpenXR + device setup |
| PS VR / PS3 | Not Godot native → PREP_ONLY |
| Secrets in git | Use `export_credentials.cfg` local/CI secrets only |

---

## 9. Quick checklist before first export

- [ ] Editor version == template version  
- [ ] Presets exist with correct names  
- [ ] Export paths under `builds/<platform>/`  
- [ ] Desktop: smoke run executable  
- [ ] Android: JDK17 + SDK paths set  
- [ ] Release keystore only on secure machine  
- [ ] Quest: OpenXR preset + device ADB  
- [ ] Manifest + QA Export signed off  

See also: `godot_pipeline.md`, `export_targets.md`, `asset_assembly.md`.

---

## === pipelines/games/godot_pipeline.md ===

# Godot Pipeline (Jayson 2.0)

Parallel to Unity/Blender paths — same assembly rules, Godot 4.x as the engine.

## When to choose Godot
- 2D, 3D, or hybrid without license fees
- Fast iteration, one executable editor
- Desktop + Android (+ Quest via Android) exports

## Binding to production run
| Stage | Godot action |
|-------|----------------|
| ASSET_PRODUCTION | Still use `_incoming` → validate → manifest |
| ASSEMBLY | `godot_project_skeleton` → import validated only → slice scene |
| RELEASE_PACKAGE | `godot_export_presets` → `builds/<platform>/` → installer notes |

## Steps
1. Tool: `godot_project_skeleton`
2. Create Godot 4 project under `projects/<game>/engine_project/`
3. `godot_import_plan` for P0 asset IDs from `assets_master.csv`
4. Build vertical slice scene (`godot_slice_scene_checklist`)
5. QA Build (cold critical path)
6. Export presets per platform matrix
7. Final polish + production_run_advance

## CLI hints
```bash
godot --path projects/<game>/engine_project --editor
godot --path projects/<game>/engine_project --headless --quit
```

## Does not replace
- Platform SDKs for console / store signing  
- Asset_assembly quarantine rules  


## Export deep-dive
See **`godot_export.md`** for templates, CLI, Android/Quest, credentials, and CI notes investigated for 2.0.

---

## === pipelines/games/localization.md ===

# Localization Pack

## Inputs
Production package language list (default: source language only).

## String table
| key | en | notes | max_chars |
|-----|----|-------|-----------|
| ui.play | Play | HUD | 12 |
| ui.settings | Settings | | 16 |

## Rules
- Never concatenate sentences in code — use format tokens `{name}`
- VO lines get `VO_<id>` keys matching audio asset IDs
- Fonts must cover target scripts

## Outputs
- `design/loc/strings.csv`
- `design/loc/fonts.md`
- Optional: per-locale VO folder under `audio/voice/<locale>/`

Skip extra locales in vertical slice unless HUMAN asked.

---

## === pipelines/games/modding_dlc.md ===

# Modding / Data-only DLC Layout

Optional. Enable only if HUMAN checked modding in §11.6.

```
mods/_example/
  manifest.json    # id, version, depends
  data/            # tables, strings — no engine binaries
  assets/          # optional overlays
```

## Rules
- P0 slice ships **without** requiring mods
- Data-driven quests/economy prefer JSON/CSV the game already loads
- DLC = extra folders the assembler copies into `release/` as optional packs

---

## === pipelines/games/production_run.md ===

# Forced Production Run — How to Use It

This drives a **Production Package** through the full idea→game factory.  
Jayson will **not** do this reliably without this tool. Install it, then follow the steps below.

---

## 1. Install the tool (once)

1. Open Jayson → **Admin → Functions** (or **Tools**)
2. Create a new tool / function
3. Open the file:
   ```
   tools/openwebui_tools/production_run_orchestrator_tool.py
   ```
4. Copy the **entire** file and paste it into the tool editor
5. Save and **enable** it
6. Also enable (if not already):  
   `qa_agents_tool`, `agent_loop_tight_tool`, `final_polish_team_tool`,  
   `rpg_orchestrator_tool`, `status_dashboard_tool`, `accessibility_tool`,  
   and the creative tools you need

Confirm the tool appears in the chat tool list.

---

## 2. Prepare your package

1. Copy `PRODUCTION_PACKAGE_TEMPLATE.md` to:
   ```
   projects/<your_game>/PRODUCTION_PACKAGE.md
   ```
2. Fill at least the **[HUMAN]** minimum (pitch, genre, **engine**, platforms, scope, pillars, vertical slice, sign-off)
3. Optional: zip that project folder if you want an “upload package” workflow — you can still **paste** key sections into chat

---

## 3. Start the run (exact prompt)

In a **new chat**, with tools enabled, paste:

```
Start a production run.

Project name: my_first_game
Genre: RPG
Platforms: Windows, Linux

Production package:
<paste your filled HUMAN sections + any AI expansions here
 OR write: see projects/my_first_game/PRODUCTION_PACKAGE.md>

Instructions:
- Call tool start_production_run now
- Use Production Run Orchestrator for the whole project
- Do not skip stages
- At every stage use Tight Agent Loop (PLAN → ACT → CHECK)
- Run QA before every advance
- Only call production_run_advance when QA is PASS or PASS_WITH_NOTES
- Ask me before changing any [HUMAN] decisions
```

Jayson should call **`start_production_run`** and return the stage list, starting at **Stage 0 PACKAGE_LOCK**.

---

## 4. What each tool call means

| You want… | Tool function | When |
|-----------|---------------|------|
| Begin factory | `start_production_run` | Once at the start |
| See where you are | `production_run_status` | Anytime |
| Move to next stage | `production_run_advance` | Only after QA PASS |
| Read full rules | `production_run_playbook` | If the model drifts |

**Advance parameters (required):**
- `from_stage_id` — stage you finished (0–6)
- `qa_verdict` — `PASS` or `PASS_WITH_NOTES` (or `FAIL` to stay put)
- `evidence` — one short sentence of what was checked

If verdict is `FAIL`, the tool **refuses** to advance.

---

## 5. Stage-by-stage (what you do as human)

### Stage 0 — PACKAGE_LOCK
- **Jayson:** Confirms slice + sign-off  
- **You:** Type `approved` or fix the package  
- **QA:** Human sign-off  
- **Then:** `production_run_advance` from 0 → 1  

### Stage 1 — DESIGN_SPINE
- **Jayson:** World/systems/quests/narrative for the **slice only** (orchestrator + storyline tools)  
- **You:** Reject scope creep  
- **QA:** `qa_inspect` on design/systems/narrative  
- **Then:** advance 1 → 2  

### Stage 2 — SPACES_UI_VR
- **Jayson:** Level / UI / VR specs via those pipelines  
- **You:** Read blockouts for soft-locks  
- **QA:** level + ui (+ VR if needed)  
- **Then:** advance 2 → 3  

### Stage 3 — ASSET_PRODUCTION
- **Jayson:** Generate into `_incoming`, assign IDs, manifest  
- **You:** Enforce folder rules from `asset_assembly.md`  
- **QA:** all **P0** assets validated  
- **Then:** advance 3 → 4  

### Stage 4 — ASSEMBLY
- **Jayson:** Integrate validated assets, slice scene plan  
- **You:** Build/run in engine until critical path works  
- **QA:** build boots; critical path completable  
- **Then:** advance 4 → 5  

### Stage 5 — FINAL_POLISH
- **Jayson:** `start_final_polish`, score sections, rework gaps  
- **You:** Agree scores are honest  
- **QA:** average ≥ 94%, zero Criticals, `qa_gate` ALLOW  
- **Then:** advance 5 → 6  

### Stage 6 — RELEASE_PACKAGE
- **Jayson:** Build notes, installer layout, `README_PLAYER.md`  
- **You:** Cold install + playtest using only the player README  
- **QA:** export checklist + your playtest  
- **Then:** advance 6 → 7 DONE  

---

## 6. If Jayson tries to skip ahead

Say:

```
Stop. Check production_run_status.
You are not allowed to leave the current stage without qa_inspect PASS
and production_run_advance. Resume current stage only.
```

Or:

```
Call production_run_playbook and follow hard_rules.
```

---

## 7. Optional: zip upload workflow

1. Zip `projects/<game>/` (package + design + manifests)  
2. Upload the zip into chat (if your Open WebUI allows) **or** paste package text  
3. Same start prompt as §3  
4. Tell Jayson: *“Treat this zip/folder as the only source of truth; all new files must follow asset_assembly layout.”*

The orchestrator does not magically unpack binaries into Unity for you—it **forces the sequence** and QA. Engine builds stay on your machine under supervision.

---

## 8. Done means

- Stage 7 reached via advances (not by claiming it)  
- Installable artifact path documented under `release/installer/`  
- Manifest lists shipped assets  
- You completed the cold playtest in `FIRST_GAME_WALKTHROUGH.md` Phase 8–9  

---

## 9. Quick copy-paste card

```
Tools on: Production Run Orchestrator, QA, Tight Loop, Final Polish, Status Dashboard.

1) start_production_run
2) work stage with PLAN→ACT→CHECK
3) qa_inspect
4) production_run_advance only on PASS
5) repeat until DONE
```

---

## 10. Optional extras (do not skip the spine)

| Extra | When |
|-------|------|
| save_load_settings | Design / tech |
| accessibility | Before polish (required if VR) |
| lint_manifest.py | Before ASSEMBLY |
| localization | If extra locales |
| store_listing | After polish, with release |
| status_dashboard | Anytime — snapshot JSON → `qa/STATUS.md` |
| resource_bridge | Publish installer to R2 (catalog now; service in 3.0) |

---

## === pipelines/games/save_load_settings.md ===

# Save / Load + Settings Schema

Bind to production package §11.4. Run during DESIGN_SPINE or ASSEMBLY.

## Schema (engine-agnostic)

```json
{
  "save_version": 1,
  "slots": "unlimited | numbered",
  "autosave": {"enabled": true, "interval_sec": 120, "max_slots": 3},
  "what_is_saved": ["player_transform", "inventory", "quest_flags", "unlocks", "settings"],
  "settings": {
    "audio": ["master", "music", "sfx", "voice"],
    "video": ["resolution", "window_mode", "vsync", "quality_preset"],
    "gameplay": ["subtitles", "camera_sensitivity", "invert_y", "colorblind_mode"],
    "accessibility": ["see accessibility.md"]
  }
}
```

## Deliverables
- `design/systems/save_schema.json`
- `design/systems/settings_schema.json`
- TechLead implementation notes per engine (Godot: ConfigFile + user:// ; Unity: PlayerPrefs or JSON)

## QA
No silent overwrite of slot 0; corrupt save must fail safe to defaults.

---

## === pipelines/games/store_listing.md ===

# Store Listing Pack

Generate from Production Package after polish. Tool: `store_listing_tool.py`

## From package
- Title, short pitch, long description
- Genre tags, age rating, platforms
- Screenshots list (min 4), capsule/icon sizes
- Trailer beat sheet (optional)

## Platform sizes (common)
| Asset | Steam-like | Quest store | Play-like |
|-------|------------|-------------|-----------|
| Icon | 32/256 | 512 | 512 |
| Capsule | 616×353 | — | feature graphic 1024×500 |
| Screens | 1920×1080 | 16:9 | 16:9 |

Do not invent store accounts. This is copy + art request list only.

---

## === pipelines/games/text_image_to_ui.md ===

# Text / Image → UI Pipeline

Produce a coherent UI/HUD kit from text specs and/or reference images.

## Inputs
- UI list from Production Package §9.6
- Tone / art pillars
- Platform (desktop, mobile, VR safe zones)
- Optional reference screenshots

## Stages
1. **Inventory screens** — HUD, menus, inventory, dialogue, map, settings
2. **Information hierarchy** — what must be readable at a glance
3. **Layout wireframes** — text descriptions + grid rules (12-col / safe zones)
4. **Component library** — buttons, panels, bars, icons, fonts
5. **Visual pass** — color tokens from art pillars; state styles (idle/hover/active/disabled)
6. **Icon & texture request list** — sizes, export formats
7. **Platform adapt** — scale for Quest/Android vs 4K desktop
8. **QA** — readability, contrast, missing states
9. **Handoff** to TechLead (implementation) + ArtDirector

## Output artifacts
- `ui_screen_list.md`
- `ui_wireframes.md`
- `ui_tokens.json` (colors, spacing, type scale)
- `ui_component_spec.md`
- `ui_icon_asset_list.csv`
- QA report

## Agent roles
UIDesigner → ArtDirector → QA Design → TechLead

---

## === pipelines/games/text_to_level.md ===

# Text → Level Generator Pipeline

Turn a written description into a structured, buildable level package.

## Inputs
- Level brief (from Production Package §8 or free text)
- Genre constraints (FPS / TPS / Adventure / Open World / Racing)
- Performance budget (platform from export matrix)

## Stages
1. **Parse brief** — extract goals, mood, encounters, secrets, traversal
2. **Space graph** — rooms/zones/nodes + connections + chokepoints
3. **Encounter placement** — recipes from package + difficulty curve
4. **Landmark & readability pass** — player never lost for >N seconds
5. **Cover / race line / puzzle verbs** — genre-specific layer
6. **Asset request list** — props, kits, lights tied to Asset IDs
7. **Blockout spec** — dimensions, heights, sightlines (engine-agnostic)
8. **QA Level** — `qa_inspect(deliverable_type="level")`
9. **Handoff** to TechLead / ArtDirector

## Output artifacts
- `level_<id>_graph.json`
- `level_<id>_blockout.md`
- `level_<id>_encounters.json`
- `level_<id>_asset_pull_list.csv`
- QA report

## Agent roles
LevelDesigner → EncounterDesigner → ArtDirector (kit bash) → QA Design → TechLead

---

## === pipelines/games/text_to_vr.md ===

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

---

## === projects/README.md ===

# Projects

Put **filled** production packages here.

```
projects/<game_name>/
  PRODUCTION_PACKAGE.md
  manifests/assets_master.csv
  art/_incoming/   audio/_incoming/
  engine_project/    # Godot or Unity
  builds/  release/installer/  qa/
```

## Start

```bash
mkdir -p projects/my_first_game/manifests
cp ../PRODUCTION_PACKAGE_TEMPLATE.md projects/my_first_game/PRODUCTION_PACKAGE.md
```

Fill HUMAN sections (including **engine**). See `asset_assembly.md` and `FIRST_GAME_WALKTHROUGH.md`.

Do not mix two games in one folder.

---

## === resource_bridge/README.md ===

# Resource Bridge (2nd bridge)

LiteLLM = models. **This** = storage/compute catalog.

**Status in 2.0-beta1:** config + Open WebUI tool stub. Full FastAPI service is **3.0**.

See `CLOUD_ASSEMBLY.md` §6. Tool: `tools/openwebui_tools/resource_bridge_tool.py`.

---

## === scripts/README.md ===

# Scripts

| Script | Use |
|--------|-----|
| `lint_manifest.py` | `python3 scripts/lint_manifest.py projects/<game>/manifests/assets_master.csv [project_root]` |
| `status_dashboard.py` | `python3 scripts/status_dashboard.py snapshot.json projects/<game>/qa/STATUS.md` |

No extra pip packages required (stdlib only).

---

## === tools/README.md ===

# Jayson Tools

## Blender Tools
Location: `tools/blender/blender_tools.py`

Available functions:
- `create_object` — primitives
- `add_material`
- `set_camera`
- `render`
- `export_glb`
- `run_bpy` — full raw Blender Python power
- `clear_scene`

## Unity Tools
Location: `tools/unity/unity_tools.py`

Available functions:
- `create_project`
- `import_asset` (most useful — brings Blender GLB/FBX into Unity)
- `open_project`

## Image-to-3D Pipeline
See: `pipelines/image_to_3d.md`

## How to activate in Open WebUI

1. Open Admin Panel → Tools / Functions
2. Create new Tool / Function
3. Paste the relevant Python code
4. Give it a clear name and description so Jayson knows when to use it
5. Enable it for the models that should have access

For full power, also enable **Open Terminal** so Jayson can run Blender/Unity commands directly when needed.


## Godot (2.0)
- `tools/godot/godot_tools.py` — project skeleton, import plan, export presets, slice checklist
- Pipeline: `pipelines/games/godot_pipeline.md`
- Use with asset_assembly + production_run (same as Unity path)

---

## === tools/openwebui_tools/README.md ===

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

---

## VERSION FILE
```
2.0-beta1
```
