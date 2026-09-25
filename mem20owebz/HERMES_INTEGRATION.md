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
