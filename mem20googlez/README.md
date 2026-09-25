# mem20googlez

`mem20googlez` is a native, local Google ADK-style runtime. It provides agents,
executable tools, a real assistant/tool/result loop, persistent sessions,
file-backed memory, sequential flows, and a FastAPI service.

Production model calls are HTTP calls to a local endpoint. The default resolver
checks Ollama first and uses the OpenAI-compatible mem20/LiteLLM gateway on port
4000 when Ollama is unavailable. No model download or paid API is required.

## Install

```bash
cd /opt/mem20/mem20googlez
/root/.venv/bin/python -m pip install -e ".[dev]"
```

The package console command is `/root/.venv/bin/mem20googlez`.

## Local model

The default local model is `qwen2.5-coder:0.5b` at `http://127.0.0.1:11434`.
Check the endpoint and the installed model with:

```bash
/root/.venv/bin/mem20googlez health
/root/.venv/bin/mem20googlez run --provider ollama --agent chat --input "Reply with the word ready."
```

Configuration can be supplied with `--config`, `MEM20GOOGLEZ_CONFIG`, or
`MEM20GOOGLEZ_*` environment variables. The important settings are
`MEM20GOOGLEZ_OLLAMA_URL`, `MEM20GOOGLEZ_GATEWAY_URL`,
`MEM20GOOGLEZ_DEFAULT_MODEL`, `MEM20GOOGLEZ_SESSION_DB`, and
`MEM20GOOGLEZ_MEMORY_DIR`.

## Library use

```python
import asyncio

from mem20googlez import DurableRunner, LlmAgent, function_tool


@function_tool
def add(a: int, b: int) -> int:
    return a + b


async def main():
    agent = LlmAgent(
        name="calculator",
        instruction="Use add for arithmetic, then state the result.",
        tools=[add],
    )
    runner = DurableRunner(agent, app_name="demo")
    result = await runner.run("user-1", input="What is 7 plus 9?")
    print(result.final_output)


asyncio.run(main())
```

`DurableRunner` uses SQLite for sessions and JSON files for memory. A new
runner with the same configuration can load the same conversation after a
process restart. `InMemoryRunner` is an explicitly ephemeral library helper and
is not used by the production CLI or service.

## Flows

```python
import asyncio

from mem20googlez import Flow, LlmAgent

plan = LlmAgent(name="plan", instruction="Create a short implementation plan.")
review = LlmAgent(name="review", instruction="Review the plan and mark it DONE.")
flow = Flow("plan-review", [plan, review])
result = asyncio.run(flow.run("build a persistent memory service"))
print(result.final_output)
```

The output of each agent is the input to the next agent. Passing a durable
runner or session and memory services to `Flow` persists every step.

## HTTP service

```bash
/root/.venv/bin/mem20googlez serve --host 127.0.0.1 --port 8002
```

Endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Resolve the real provider and check its health |
| GET | `/` | Service, storage, agents, and endpoint information |
| GET | `/agents` | List registered agents and executable tools |
| POST | `/agents/{name}/run` | Run an agent with `{"input":"...", "user_id":"...", "session_id":"..."}` |
| GET | `/sessions` | List persisted sessions; optional `app_name` and `user_id` filters |
| GET | `/sessions/{id}` | Read a persisted session and all events |

Example:

```bash
curl -sS http://127.0.0.1:8002/health
curl -sS http://127.0.0.1:8002/agents
curl -sS http://127.0.0.1:8002/agents/chat/run \
  -H 'content-type: application/json' \
  -d '{"input":"Reply with the number 42.","user_id":"curl"}'
```

The service unit is `mem20googlez-serve.service`. It runs the installed
`/root/.venv/bin/mem20googlez serve` command under systemd; after installation:

```bash
systemctl status mem20googlez-serve.service
systemctl is-active mem20googlez-serve.service
```

## Tests

The hermetic suite injects a deterministic in-process provider into the same
runner and ASGI application code. That provider exists only in the test module
and is not imported by production modules. The production path always resolves
an HTTP provider unless a caller explicitly injects a provider object.

```bash
cd /opt/mem20/mem20googlez
/root/.venv/bin/python -m pytest -q
```

The suite covers executable tools, the assistant/tool/final-answer loop,
cross-runner SQLite session persistence, file memory persistence, A-to-B flows,
and the HTTP endpoints. A real local-endpoint smoke test can be run explicitly:

```bash
MEM20GOOGLEZ_REAL_TESTS=1 /root/.venv/bin/python -m pytest -q -m real
```
