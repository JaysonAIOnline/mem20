# Jayson — The Complete Setup & Usage Guide (Noob-Friendly)

> One document that replaces `START_HERE.md`, `RECOMMENDED_SETUP.md`, and `ADVANCED.md`.
> Read it top to bottom the first time. After that, use the table of contents.

Jayson is your personal AI command center: a chat interface (Open WebUI) wired to a
model bridge (LiteLLM) that gives you ~42 free models across 20+ providers, plus local
high-quality voice (Kokoro TTS), 3D/Blender tools, video understanding, and agent frameworks.

---

## Table of Contents
1. [What you have](#1-what-you-have)
2. [First launch](#2-first-launch)
3. [Create your admin account](#3-create-your-admin-account)
4. [Connect the Model Bridge](#4-connect-the-model-bridge)
5. [Connect local voice (Kokoro TTS)](#5-connect-local-voice-kokoro-tts)
6. [Add your API keys](#6-add-your-api-keys)
7. [Install the built-in tools](#7-install-the-built-in-tools)
8. [Set the system prompt](#8-set-the-system-prompt)
9. [Enable web search, image gen, memory, terminal](#9-enable-web-search-image-gen-memory-terminal)
10. [Add MCP servers](#10-add-mcp-servers)
11. [Apply the theme & logo](#11-apply-the-theme--logo)
12. [Wire up agent frameworks](#12-wire-up-agent-frameworks)
13. [Security hardening (do this before exposing anywhere)](#13-security-hardening)
14. [Daily use & troubleshooting](#14-daily-use--troubleshooting)

---

## 1. What you have

Three Docker services (all defined in `docker-compose.full.yml`):

| Service | Image | Port | What it does |
|---------|-------|------|--------------|
| **jayson** | open-webui | 3000 | The chat UI you talk to |
| **jayson-tts** | kokoro-fastapi | 8880 | Local high-quality text-to-speech |
| **jayson-bridge** | litellm | 4000 | Routes your prompts to 20+ free AI providers |
| **jayson-db** | postgres:16 | 5432 | Database for the bridge (usage tracking, keys) |

Key folders:
- `tools/` — Blender + Unity Python tools
- `tools/openwebui_tools/` — paste-ready Open WebUI Tools (3D screenshots, video)
- `pipelines/` — 3D screenshot + video understanding Python pipelines
- `bridge/` — LiteLLM config + usage report script
- `agents/` — integration guides for 11 agent frameworks
- `custom.css`, `logo.svg`, `logo.png` — branding (already mounted)

---

## 2. First launch

```bash
cd /home/jayson/Desktop/jayson-openwebui
docker compose -f docker-compose.full.yml up -d
```

Wait ~60 seconds. The bridge runs database migrations on first boot, so give it time.
Check health:

```bash
# All four should say "Up"
docker ps --format '{{.Names}} {{.Status}}'

# Bridge should list models (expect ~42)
curl -s -H "Authorization: Bearer XONufny9qnunX0MquqDXJH0GxaOdda_KCyiEAG6Kut0" \
  http://localhost:4000/v1/models | python3 -c "import json,sys; print(len(json.load(sys.stdin)['data']),'models')"
```

Open the UI: **http://localhost:3000**

---

## 3. Create your admin account

The **first** person who signs up becomes the Admin.

1. Go to http://localhost:3000
2. Click **Sign up**
3. Pick a username + email + password

> Password must be **≥10 chars** with uppercase + lowercase + number + special char
> (enforced by `PASSWORD_VALIDATION_REGEX_PATTERN` in the compose file). Example: `Jayson#2026!`

4. You are now Admin.

**After you create the admin account**, disable public signup so randoms can't join:
- Admin Panel → Settings → General → **Enable New Sign Ups** → Off
- (Or set `ENABLE_SIGNUP=False` in the compose file and restart.)

---

## 4. Connect the Model Bridge

This makes all ~42 free models appear in Jayson's model picker.

1. Admin Panel → **Connections** (or Settings → Connections)
2. Click **+ Add Connection** → choose **OpenAI-compatible**
3. Fill in:
   - **Name:** `Jayson Bridge`
   - **Base URL:** `http://host.docker.internal:4000/v1`
   - **API Key:** `XONufny9qnunX0MquqDXJH0GxaOdda_KCyiEAG6Kut0`
   - **Model(s):** leave blank to auto-load all, or type `fast`, `balanced`, `strong`
4. Save.

The bridge exposes router groups `fast` / `balanced` / `strong` (auto-failover between providers)
plus individual models like `gemini/gemini-2.5-pro`, `deepseek/reasoner`, `xai/grok-4`, `azure/gpt-4o`,
`bedrock/claude`, `oci/cohere-command`, `ollama/llama3.2`, etc.

> If `host.docker.internal` doesn't resolve on your host, use the bridge container IP
> (`docker inspect jayson-bridge --format '{{.NetworkSettings.Networks.jayson-openwebui_default.IPAddress}}'`)
> instead, e.g. `http://172.x.x.x:4000/v1`.

---

## 5. Connect local voice (Kokoro TTS)

1. Admin Panel → **Settings** → **Audio**
2. TTS Engine: **OpenAI**
3. API Base URL: `http://host.docker.internal:8880/v1`
4. API Key: any value (e.g. `not-needed`)
5. Voice: pick a Kokoro voice (e.g. `af_heart`, `am_michael`)
6. (Optional) STT Engine: OpenAI or browser — for hands-free Voice Mode.

Now message read-aloud and Voice Mode use local, high-quality, private TTS.

---

## 6. Add your API keys

All keys live in the `.env` file next to `docker-compose.full.yml`. The file already has
a slot for every provider. Open it and paste your real keys (the values currently there
are placeholders — replace them).

Providers you confirmed you have verified free-tier access to:
**Azure, AWS, Oracle/OCI, Cloudflare**, plus the standard free set (Google AI Studio,
Groq, OpenRouter, Hugging Face, DeepSeek, Mistral, Qwen/DashScope, NVIDIA NIM, Together,
Cohere, xAI/Grok, AnyAPI, SiliconFlow, Moonshot, Zhipu, SambaNova, Cerebras, Fireworks, Novita).

After editing `.env`, restart the bridge so it picks up the new keys:

```bash
docker compose -f docker-compose.full.yml up -d jayson-bridge
```

> Never commit `.env` to git. It holds secrets. A backup copy is made automatically
> before edits (look for `/tmp/env_*.bak`).

See `CREDITS.md` for where to get each key.

---

## 7. Install the built-in tools

These let Jayson render 3D models and analyze videos. Paste them into Open WebUI.

1. Admin Panel → **Functions** (or **Tools**) → **+ New Function**
2. Type: **Python Function (Tool)**
3. Paste the full contents of `tools/openwebui_tools/3d_screenshots_tool.py`
4. Save & Enable. Repeat for `tools/openwebui_tools/video_understanding_tool.py`.

> Requires **Blender 4.x** installed on the host and in PATH for the 3D tool to work.
> Check: `blender --version`. The video tool needs `ffmpeg` (usually present) and
> optionally `faster-whisper` for local transcription.

You can also install the Blender/Unity tools from `tools/blender/blender_tools.py` and
`tools/unity/unity_tools.py` the same way.

---

## 8. Set the system prompt

1. Admin Panel → **Settings** → **General** → **System Prompt**
2. Paste the contents of `system-prompt.txt`
3. Save.

(You can edit it to taste — it defines Jayson's personality and when to use tools.)

---

## 9. Enable web search, image gen, memory, terminal

These are Open WebUI features you turn on in the Admin Panel:

- **Web search:** Settings → Web Search → enable + pick a provider (Brave/Tavily/Firecrawl),
  or add a search MCP server (see next section).
- **Image generation:** Settings → Images → set an image-gen endpoint (your own ComfyUI /
  Automatic1111, or an OpenAI-compatible image API).
- **Memory:** Settings → Memory → enable long-term memory so Jayson remembers you.
- **Open Terminal:** Settings → Tools → enable **Open Terminal** (or Open WebUI Computer)
  so Jayson can run shell commands on the host.

---

## 10. Add MCP servers

MCP (Streamable HTTP) lets Jayson use external tool servers (filesystem, GitHub, browser…).

1. Admin Panel → **Settings** → **Integrations**
2. Click **+ Add Server**
3. Type: **MCP (Streamable HTTP)**  ← important, not "OpenAPI"
4. URL: `http://host.docker.internal:PORT/mcp` (or `http://mcp-server:PORT/mcp`)
5. ID: short lowercase (e.g. `filesystem`)
6. Save. Restart Open WebUI if prompted.

Recommended servers to add (run them as separate containers or processes):
- **Filesystem** — read/write your machine
- **GitHub** — repo operations
- **Playwright / browser** — web browsing
- **Database** — SQL queries
- **Custom Blender MCP** — if you build one

---

## 11. Apply the theme & logo

Already done — `custom.css` (dark Grok-style) and `logo.svg`/`logo.png` are mounted into
the container via the compose file. If you edit `custom.css`, restart Jayson:

```bash
docker compose -f docker-compose.full.yml restart jayson
```

To go even more minimal, see `ADVANCED.md` → "Even More Aggressive CSS".

---

## 12. Wire up agent frameworks

Jayson is the front door; specialized agents do heavy lifting. All 11 frameworks in
`agents/` follow the same pattern: install the framework → expose it as an
OpenAI-compatible `/v1` endpoint → add it in Admin → Connections.

Priority order (from `agents/README.md`):
1. **mem20 Agent** (full guide in `MEM20_INTEGRATION.md`) — already on this machine
   (`mem20` CLI present). Enable its API server, then add `http://host.docker.internal:8642/v1`.
2. **mem20 claw plugin** or **Open WebUI Computer** — turnkey personal agents.
3. **mem20 crews / mem20 graph substrate** — when you want custom multi-agent or stateful logic.

Each `agents/<framework>.md` has the exact install + connect steps.

---

## 13. Security hardening

Do this **before** exposing Jayson to any network beyond localhost:

1. **WEBUI_SECRET_KEY** — already set to a random value in `docker-compose.full.yml`.
   Keep it secret; rotate if leaked.
2. **Bridge master_key** — already changed from the default in `bridge/litellm_config.yaml`.
   Same key you pasted in step 4.
3. **Disable signup** after creating your admin (step 3).
4. **Postgres password** — set in the compose file (`${POSTGRES_PASSWORD}`). Change it and
   update the two `DATABASE_URL` lines (compose + bridge config) together.
5. **Reverse proxy** — put Jayson behind nginx/Caddy with TLS if accessed remotely.
6. **API keys** — never share your `.env`. Each provider key is a credential.

---

## 14. Daily use & troubleshooting

**Start / stop:**
```bash
docker compose -f docker-compose.full.yml up -d      # start all
docker compose -f docker-compose.full.yml down      # stop all
```

**Check the bridge is serving models:**
```bash
curl -s -H "Authorization: Bearer XONufny9qnunX0MquqDXJH0GxaOdda_KCyiEAG6Kut0" \
  http://localhost:4000/v1/models | python3 -c "import json,sys; print(len(json.load(sys.stdin)['data']),'models')"
```
If it returns empty, the bridge is still booting (DB migrations). Wait up to 90s.

**Bridge usage report:**
```bash
docker compose -f docker-compose.full.yml exec jayson-bridge python bridge/usage_summary.py
```

**Common fixes:**
- *Model errors "Invalid API Key"* → the key in `.env` for that provider is wrong/placeholder. Fix it, restart bridge.
- *3D tool does nothing* → Blender not installed/on PATH. Install Blender 4.x.
- *TTS silent* → check Audio settings point to `:8880/v1`; the kokoro container is up.
- *Can't reach `host.docker.internal`* → use the container IP instead.

**Backups:**
- Chat data: Docker volume `jayson-data`
- Bridge DB: Docker volume `bridge-db`
- Your keys: the `.env` file (keep a secure copy)

Enjoy. Jayson is the one place to get things done.
