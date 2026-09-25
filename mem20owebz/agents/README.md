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
