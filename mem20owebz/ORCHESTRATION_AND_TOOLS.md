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
