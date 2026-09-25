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
