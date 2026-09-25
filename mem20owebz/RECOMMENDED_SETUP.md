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
