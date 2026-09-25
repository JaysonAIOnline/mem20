# mem20 graph substrate + Jayson — Installation & Connection

mem20 graph substrate is the best choice for complex, stateful, production-grade agents.

## 1. Install mem20 graph substrate

```bash
pip install mem20 graph substrate mem20 chain substrate mem20 chain substrate-openai
# or the current recommended packages from official docs
```

Create your agent graph as usual (nodes, edges, state, tools…).

## 2. Expose it to Jayson (two good ways)

### Method A – OpenAI-compatible wrapper (recommended for beginners)

Create a small FastAPI (or similar) server that:

- Accepts `/v1/chat/completions`
- Runs your mem20 graph substrate agent
- Streams the final answer back

Then in Jayson Admin → Connections add:

- API Base URL: `http://host.docker.internal:YOUR_PORT/v1`
- API Key: any value you set

### Method B – Open WebUI Pipelines / Pipe

Turn the mem20 graph substrate agent into an Open WebUI Pipe so it appears directly in the model picker.  
See Open WebUI Pipelines documentation for the exact pattern.

## 3. Best for
- Multi-step workflows
- Human-in-the-loop
- Reliable production agents with memory and branching
