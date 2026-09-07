# mem20 Installation & Configuration Guide

> Complete guide to installing and configuring the mem20 MCP server.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation Methods](#installation-methods)
   - [pip (Python)](#pip-python)
   - [Docker](#docker)
   - [systemd (always-on)](#systemd-always-on)
   - [apt (.deb)](#apt-deb)
3. [Configuration](#configuration)
4. [Verifying Installation](#verifying-installation)
5. [Connecting MCP Hosts](#connecting-mcp-hosts)
6. [Optional Integrations](#optional-integrations)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

- **Python 3.11+** (3.14 recommended)
- **pip** or **uv** package manager
- **API key** for an OpenAI-compatible LLM endpoint (NVIDIA NIM, OpenAI, etc.)
- **~500MB disk** for the memory store + embeddings model

---

## Installation Methods

### pip (Python)

The simplest method — installs mem20 as a Python package with the `mem20-mcp` command.

```bash
# Clone the repository
git clone https://github.com/JaysonAIOnline/mem20.git
cd mem20

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install core dependencies
pip install -r requirements.txt

# Run the server
python mcp/mcp_server.py
```

Or install as a package:

```bash
pip install .
mem20-mcp   # starts the MCP server + :8080 health endpoint
```

### Docker

Best for isolated deployments and production.

```bash
# Build the image
docker build -t mem20 .

# Run with persistent storage
docker run -p 8080:8080 \
  -e MEM20_HEALTH_PORT=8080 \
  -v mem20-store:/data \
  mem20

# Or use docker compose
docker compose up -d

# Verify
curl http://localhost:8080/health
```

### systemd (always-on)

For production deployments that need auto-restart and logging.

```bash
# Run the installer
sudo ./install.sh --user $USER --dir /opt/mem20

# Check status
sudo systemctl status mem20

# View logs
sudo journalctl -u mem20 -f
```

The installer:
- Creates a virtualenv at `/opt/mem20/.venv`
- Installs dependencies
- Generates a systemd unit from `systemd/mem20.service.template`
- Enables and starts the service

### apt (.deb)

For Debian/Ubuntu systems.

```bash
# Build the package
make deb

# Install
sudo dpkg -i packaging/deb/mem20_*.deb

# Verify
sudo systemctl status mem20
mem20-health   # probes /health
```

---

## Configuration

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `MEM20_STORE_PATH` | `~/.mem20/store` | Memory engine module + store location |
| `MEM20_COG_PATH` | (mem20 `cog/` dir) | Cognitive engine location |
| `MEM20_LLM_BASE_URL` | `https://integrate.api.nvidia.com/v1` | LLM chat-completions base URL |
| `MEM20_LLM_MODEL` | (project default) | Model name |
| `NVAPI_KEY` / `NVIDIA_API_KEY` / `MEM20_LLM_API_KEY` | — | LLM bearer token (required) |
| `MEM20_ENV_FILE` | — | Optional `.env` to load API keys from |
| `MEM20_HEALTH_PORT` | `8080` | HTTP health endpoint port |
| `MEM20_HEALTH_DISABLE` | — | Set to `1` to disable HTTP health endpoint |
| `MEM20_LOG_LEVEL` | `INFO` | Logging level |
| `MEM20_FLAG_WORLDMODEL_20` | `1` (ON) | Kill-switch for world-model / self-model / affective / procedural tools |
| `MEM20_BLENDER_EXECUTABLE` | — | Path to Blender executable (optional) |
| `MEM20_UNITY_EXECUTABLE` | — | Path to Unity Editor executable (optional) |

### LLM Configuration

mem20 requires an OpenAI-compatible LLM endpoint. Default is NVIDIA NIM:

```bash
export MEM20_LLM_BASE_URL="https://integrate.api.nvidia.com/v1"
export NVAPI_KEY="your-nvidia-api-key"
```

For OpenAI:

```bash
export MEM20_LLM_BASE_URL="https://api.openai.com/v1"
export MEM20_LLM_API_KEY="sk-..."
export MEM20_LLM_MODEL="gpt-4o"
```

For local models (Ollama, vLLM, etc.):

```bash
export MEM20_LLM_BASE_URL="http://localhost:11434/v1"
export MEM20_LLM_API_KEY="not-needed"
export MEM20_LLM_MODEL="llama3"
```

### Store Path

The memory store persists all data. Back up this directory:

```bash
export MEM20_STORE_PATH="/path/to/your/store"
# Default: ~/.mem20/store
```

---

## Verifying Installation

### Health Check

```bash
curl http://localhost:8080/health
```

Expected response:
```json
{"status": "ok", "service": "mem20-mcp", ...}
```

### Metrics

```bash
curl http://localhost:8080/metrics
```

Returns tool counters, contamination rate, and event taxonomy.

### Readiness

```bash
curl http://localhost:8080/ready
```

### Test with Python

```python
import requests
r = requests.get("http://localhost:8080/health")
print(r.json())
```

---

## Connecting MCP Hosts

### Hermes Agent

```bash
hermes config set mcp.servers.mem20 '["python3", "/path/to/mem20/mcp/mcp_server.py"]'
```

### Claude Code / Cursor

```bash
claude mcp add mem20 -- python3 /path/to/mem20/mcp/mcp_server.py
```

### VS Code (MCP Extension)

Add to your VS Code settings:

```json
{
  "mcp.servers": {
    "mem20": {
      "command": "python3",
      "args": ["/path/to/mem20/mcp/mcp_server.py"]
    }
  }
}
```

### Generic MCP Client

Any MCP client can connect via stdio:

```bash
python3 /path/to/mem20/mcp/mcp_server.py
```

The server speaks JSON-RPC 2.0 over stdin/stdout.

---

## Optional Integrations

### Blender (3D Modeling)

Requires Blender installed and on PATH:

```bash
# Option 1: Blender on PATH
export MEM20_BLENDER_EXECUTABLE="/usr/bin/blender"

# Option 2: Set custom path
export MEM20_BLENDER_EXECUTABLE="/opt/blender/blender"
```

When Blender is absent, tools return an informative message instead of failing.

### Unity (Game Engine)

Requires Unity Editor installed:

```bash
export MEM20_UNITY_EXECUTABLE="/opt/unity/Editor/Unity"
```

### Adding Custom Integrations

Create a new mixin in `mcp/tools/<name>_tools.py`:

```python
from mcp.server import Server
import mcp_types as mt

class MyIntegrationMixin:
    def register_my_integration_tools(self):
        self.tools["my_tool"] = mt.Tool(
            name="my_tool",
            title="My Tool",
            description="Does something useful",
            inputSchema={
                "type": "object",
                "properties": {
                    "input": {"type": "string", "description": "Input data"}
                },
                "required": ["input"]
            }
        )
```

Then add to `Mem20MCPServer` in `mcp/server.py`.

---

## Troubleshooting

### Server won't start

```bash
# Check Python version
python3 --version  # must be 3.11+

# Check dependencies
pip install -r requirements.txt

# Check logs
MEM20_LOG_LEVEL=DEBUG python mcp/mcp_server.py
```

### Health endpoint not responding

```bash
# Check if port is in use
sudo lsof -i :8080

# Try different port
MEM20_HEALTH_PORT=9090 python mcp/mcp_server.py
```

### Memory system unavailable

```bash
# Check store path
ls -la ~/.mem20/store/

# Rebuild index
python -c "from memory import rebuild_index; rebuild_index()"
```

### Contamination detected

```bash
# Run audit
python -c "from memory import audit_contamination; print(audit_contamination())"
```

### LLM errors

```bash
# Verify API key
echo $NVAPI_KEY

# Test endpoint
curl $MEM20_LLM_BASE_URL/models \
  -H "Authorization: Bearer $NVAPI_KEY"
```