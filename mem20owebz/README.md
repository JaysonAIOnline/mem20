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
