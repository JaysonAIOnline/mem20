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
