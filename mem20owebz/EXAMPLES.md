# Jayson — Concrete Code Examples

Practical, copy-paste ready examples for tools, agents, and pipelines.

---

## 1. Minimal Agent Loop (ReAct-style)

Use this pattern when building custom agents that call tools.

```python
# examples/simple_agent_loop.py
import json
from typing import Callable

def run_agent(user_query: str, llm_call: Callable, tools: dict, max_steps: int = 8):
    """
    Simple ReAct-style agent loop.
    llm_call(messages) -> dict with 'content' and optional 'tool_calls'
    tools = {"tool_name": callable}
    """
    messages = [{"role": "user", "content": user_query}]

    for step in range(max_steps):
        response = llm_call(messages)

        # If the model wants to call tools
        tool_calls = response.get("tool_calls") or []
        if not tool_calls:
            return response.get("content", "")

        messages.append({"role": "assistant", "content": response.get("content"), "tool_calls": tool_calls})

        for call in tool_calls:
            name = call["function"]["name"]
            args = json.loads(call["function"]["arguments"])
            result = tools[name](**args) if name in tools else f"Unknown tool: {name}"
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id", name),
                "content": str(result)
            })

    return "Reached max steps without final answer."
```

---

## 2. Open WebUI Tool Example (already in the package style)

This is the format Jayson expects for custom tools:

```python
"""
title: Example Weather Tool
author: Jayson
version: 1.0
"""

from pydantic import BaseModel, Field

class Tools:
    class Valves(BaseModel):
        api_key: str = Field(default="", description="Optional API key")

    def __init__(self):
        self.valves = self.Valves()

    def get_weather(self, city: str) -> str:
        """
        Get current weather for a city.
        :param city: City name
        """
        # Replace with real API call
        return f"Weather in {city}: 22°C, clear skies (example)"
```

Paste into **Admin → Functions → Tools**.

---

## 3. Calling the Model Bridge from Python

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:4000/v1",
    api_key="jayson-bridge-secret-change-me"
)

# Use a router group
response = client.chat.completions.create(
    model="fast",          # or "balanced", "strong", or any specific model
    messages=[{"role": "user", "content": "Explain quantum entanglement simply"}]
)

print(response.choices[0].message.content)
```

---

## 4. Simple MCP-style Tool Server (FastAPI)

```python
# examples/simple_mcp_server.py
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class ToolCall(BaseModel):
    name: str
    arguments: dict

@app.post("/tools/call")
def call_tool(body: ToolCall):
    if body.name == "add_numbers":
        a = body.arguments.get("a", 0)
        b = body.arguments.get("b", 0)
        return {"result": a + b}
    return {"error": "unknown tool"}

@app.get("/tools")
def list_tools():
    return {
        "tools": [
            {
                "name": "add_numbers",
                "description": "Add two numbers",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "a": {"type": "number"},
                        "b": {"type": "number"}
                    },
                    "required": ["a", "b"]
                }
            }
        ]
    }
```

Run with:
```bash
uvicorn examples.simple_mcp_server:app --port 8090
```

Then point Jayson / MCP config at it.

---

## 5. 3D Screenshots Tool (already provided)

See:
```
tools/openwebui_tools/3d_screenshots_tool.py
```

Usage idea in chat:
> “Take screenshots of this .glb from 6 angles and describe the model”

---

## 6. Video Understanding Tool (already provided)

See:
```
tools/openwebui_tools/video_understanding_tool.py
```

Usage idea:
> “Transcribe this video and summarize the key visual moments”

---

## 7. Basic RAG Pattern (for Knowledge Bases)

```python
# Conceptual pattern — Open WebUI already has Knowledge Bases
def simple_rag(query: str, documents: list[str], llm_call, top_k: int = 3):
    # 1. Retrieve (replace with real embeddings + vector search)
    scored = sorted(documents, key=lambda d: query.lower() in d.lower(), reverse=True)
    context = "\n\n".join(scored[:top_k])

    # 2. Generate
    prompt = f"""Use the following context to answer the question.
Context:
{context}

Question: {query}
Answer:"""
    return llm_call([{"role": "user", "content": prompt}])
```

In practice, prefer Open WebUI’s built-in Knowledge feature.

---

## 8. System Prompt Tip

Put this (or the content of `system-prompt.txt`) into the model’s system prompt in Open WebUI for consistent behavior:

```
You are Jayson. Be direct, helpful, and tool-aware.
When a task needs tools, use them.
For 3D work use the Blender / screenshots tools.
For video use the video understanding tool.
Prefer accurate, up-to-date information.
```

---

## Where to put custom code

| Type of code              | Recommended location              |
|---------------------------|-----------------------------------|
| Open WebUI Tools          | Admin → Functions / Tools         |
| Helper scripts            | `examples/` (create this folder)  |
| MCP servers               | Separate process / Docker         |
| Blender scripts           | `tools/blender/`                  |
| Agent frameworks          | See `agents/` folder              |

These examples are intentionally minimal so you can extend them.
