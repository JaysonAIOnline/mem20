from __future__ import annotations

import asyncio
import os
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport, AsyncClient, MockTransport

from mem20googlez import (
    DatabaseSessionService,
    DurableRunner,
    FileMemoryService,
    Flow,
    GoogleADKConfig,
    LlmAgent,
    ModelProvider,
    ModelResponse,
    ModelToolCall,
    OllamaProvider,
    RunConfig,
    create_app,
    function_tool,
)


class DeterministicProvider(ModelProvider):
    name = "test-deterministic"

    def __init__(self, responses: list[ModelResponse]):
        self.responses = list(responses)
        self.calls: list[dict] = []
        self._model = "test-model"

    @property
    def model(self) -> str:
        return self._model

    async def generate(self, messages, tools=None, model=None, **kwargs):
        self.calls.append({"messages": list(messages), "tools": tools, "model": model})
        if self.responses:
            return self.responses.pop(0)
        return ModelResponse(text="")

    async def health(self):
        return True, "deterministic test provider"


def tool_response(name: str, arguments: dict) -> ModelResponse:
    return ModelResponse(tool_calls=[ModelToolCall(id=name, name=name, arguments=arguments)])


def text_response(text: str) -> ModelResponse:
    return ModelResponse(text=text)


@function_tool
def add(a: int, b: int) -> int:
    return a + b


def test_provider_http_client_parses_ollama_wire_response():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        payload = __import__("json").loads(request.content)
        assert payload["model"] == "qwen2.5-coder:0.5b"
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": "done",
                    "tool_calls": [
                        {"function": {"name": "add", "arguments": {"a": 2, "b": 3}}}
                    ],
                },
                "done_reason": "stop",
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=MockTransport(handler)) as client:
            provider = OllamaProvider("http://local", "qwen2.5-coder:0.5b", client=client)
            return await provider.generate([{"role": "user", "content": "add"}], [add.to_schema()])

    response = asyncio.run(run())
    assert response.text == "done"
    assert response.tool_calls[0].name == "add"
    assert response.tool_calls[0].arguments == {"a": 2, "b": 3}


def test_durable_runner_persists_session_and_memory_across_instances(tmp_path: Path):
    config = GoogleADKConfig(
        session_db_path=str(tmp_path / "sessions.db"),
        memory_dir=str(tmp_path / "memory"),
    )
    sessions = DatabaseSessionService(config.session_db_path)
    memory = FileMemoryService(config.memory_dir)
    agent = LlmAgent(name="memory-agent", instruction="Answer briefly.", tools=[add])
    first_provider = DeterministicProvider([text_response("first durable answer")])
    first = DurableRunner(
        agent,
        "durable-test",
        session_service=sessions,
        memory_service=memory,
        provider=first_provider,
        config_data=config,
    )
    first_result = asyncio.run(first.run("user-1", "fixed-session", "remember alpha"))
    assert first_result.error is None

    second_provider = DeterministicProvider([text_response("second durable answer")])
    second = DurableRunner(
        agent,
        "durable-test",
        session_service=sessions,
        memory_service=memory,
        provider=second_provider,
        config_data=config,
    )
    second_result = asyncio.run(second.run("user-1", "fixed-session", "what happened?"))
    assert second_result.error is None
    assert "remember alpha" in str(second_provider.calls[0]["messages"])
    assert len(second_result.session.events) == 4
    assert asyncio.run(memory.search_memory("durable-test", "user-1", "alpha"))
    assert asyncio.run(sessions.get_session("durable-test", "user-1", "fixed-session")) is not None


def test_flow_passes_first_agent_output_to_second_agent():
    first = LlmAgent(name="planner", instruction="Plan the work.")
    second = LlmAgent(name="reviewer", instruction="Review the plan.")
    provider = DeterministicProvider(
        [text_response("PLAN: ship the service"), text_response("DONE: service approved")]
    )
    flow = Flow("plan-review", [first, second])
    result = asyncio.run(flow.run("ship a service", provider=provider))
    assert result.final_output == "DONE: service approved"
    assert len(result.steps) == 2
    second_messages = str(provider.calls[1]["messages"])
    assert "PLAN: ship the service" in second_messages


def test_serve_uses_persistent_services(tmp_path: Path):
    config = GoogleADKConfig(
        session_db_path=str(tmp_path / "serve.db"),
        memory_dir=str(tmp_path / "serve-memory"),
    )
    sessions = DatabaseSessionService(config.session_db_path)
    memory = FileMemoryService(config.memory_dir)
    agent = LlmAgent(name="chat", instruction="Answer briefly.", model="test-model")
    provider = DeterministicProvider([text_response("served once"), text_response("served twice")])
    app = create_app(
        agents=[agent],
        config=config,
        provider=provider,
        session_service=sessions,
        memory_service=memory,
    )

    async def exercise():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first = await client.post(
                "/agents/chat/run",
                json={"input": "first", "user_id": "serve-user", "session_id": "serve-session"},
            )
            second = await client.post(
                "/agents/chat/run",
                json={"input": "second", "user_id": "serve-user", "session_id": "serve-session"},
            )
            listed = await client.get("/sessions")
            detail = await client.get("/sessions/serve-session")
            return first, second, listed, detail

    first, second, listed, detail = asyncio.run(exercise())
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["output"] == "served once"
    assert second.json()["output"] == "served twice"
    assert listed.json()["sessions"][0]["event_count"] == 4
    assert len(detail.json()["events"]) == 4


@pytest.mark.real
def test_real_ollama_agent_tool_loop(tmp_path: Path):
    if os.getenv("MEM20GOOGLEZ_REAL_TESTS") != "1":
        pytest.skip("set MEM20GOOGLEZ_REAL_TESTS=1 to call the local Ollama endpoint")
    config = GoogleADKConfig(
        session_db_path=str(tmp_path / "real.db"),
        memory_dir=str(tmp_path / "real-memory"),
    )
    agent = LlmAgent(
        name="real-calculator",
        instruction=(
            "Call the add tool when the user requests arithmetic. "
            "After the tool response, answer with only the numeric result."
        ),
        model=config.default_model,
        tools=[add],
    )
    provider = OllamaProvider(config.ollama_url, config.default_model)
    runner = DurableRunner(
        agent,
        "real-endpoint",
        config_data=config,
        provider=provider,
    )
    result = asyncio.run(
        runner.run(
            "real-user",
            input=(
                "You must call the add function. Set a to 7 and b to 9. "
                "Do not answer directly. After the tool result, answer only with 16."
            ),
            config=RunConfig(temperature=0.0, top_p=0.1, max_turns=4),
        )
    )
    assert result.error is None
    assert any(event.is_tool_call() for event in result.events)
    assert any(event.is_tool_response() for event in result.events)
    assert result.final_output == "16"
