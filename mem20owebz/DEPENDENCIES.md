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
