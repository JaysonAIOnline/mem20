"""Hermetic tests for mem20googlez.

Production paths hit real endpoints (Ollama / LiteLLM). These tests exercise
the same code paths with an in-process ``FakeProvider`` (documented in
``runners.py``) and local loopback HTTP (``httpx.MockTransport``) so the suite
runs anywhere with no network and no model download.
"""

from __future__ import annotations

import asyncio
import json
import tempfile

import httpx
import pytest
from httpx import ASGITransport, AsyncClient, MockTransport

from mem20googlez import (
    AgentConfig,
    AgentType,
    DatabaseSessionService,
    Event,
    EventActions,
    FileMemoryService,
    Flow,
    GoogleADKConfig,
    GoogleSearchTool,
    InMemoryMemoryService,
    InMemoryRunner,
    InMemorySessionService,
    LoopAgent,
    OllamaProvider,
    ParallelAgent,
    RunConfig,
    RunResult,
    SequentialAgent,
    Session,
    Toolset,
    create_app,
    create_llm_agent,
    function_tool,
    resolve_provider,
    run_agent,
)
from mem20googlez.memory import MemoryEntry
from mem20googlez.providers import ModelProvider, ModelResponse, ModelToolCall
from mem20googlez.runners import events_to_messages
from mem20googlez.tools import ToolContext


class FakeProvider(ModelProvider):
    """In-process, scripted provider — hermetic twin of the HTTP providers."""

    name: str = "fake"

    def __init__(self, script: list[ModelResponse]):
        self.script = list(script)
        self.calls: list[dict] = []
        self._model = "fake-1"

    @property
    def model(self) -> str:
        return self._model

    async def generate(self, messages, tools=None, model=None):
        self.calls.append({"messages": list(messages), "tools": tools, "model": model})
        if not self.script:
            return ModelResponse(text="(script exhausted)")
        return self.script.pop(0)

    async def health(self):
        return True, "fake provider always reachable"


def _tool_reply(name: str, args: dict) -> ModelResponse:
    return ModelResponse(tool_calls=[ModelToolCall(id=name, name=name, arguments=args)])


def _text_reply(text: str) -> ModelResponse:
    return ModelResponse(text=text)


@pytest.fixture
def tmp_dir(tmp_path):
    return str(tmp_path)


@pytest.fixture
def basic_cfg(tmp_dir):
    from mem20googlez.config import GoogleADKConfig

    return GoogleADKConfig(
        session_db_path=str(tempfile.mkdtemp()) + "/sessions.db",
        memory_dir=tmp_dir,
    )


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def test_config_defaults():
    cfg = GoogleADKConfig()
    assert cfg.port == 8002
    assert cfg.gateway_url == "http://127.0.0.1:4000"
    assert cfg.ollama_url == "http://127.0.0.1:11434"
    assert cfg.default_model == "qwen2.5-coder:0.5b"
    assert cfg.enable_sessions is True
    assert cfg.enable_memory is True


def test_config_load_from_yaml(tmp_dir):
    path = f"{tmp_dir}/cfg.yaml"
    with open(path, "w") as f:
        f.write("port: 9000\ngateway_url: \"http://localhost:4100\"\n")
    cfg = GoogleADKConfig.load(path)
    assert cfg.port == 9000
    assert cfg.gateway_url == "http://localhost:4100"


def test_config_roundtrip_save(tmp_dir):
    cfg = GoogleADKConfig(port=9001)
    path = f"{tmp_dir}/cfg2.yaml"
    cfg.save(path)
    cfg2 = GoogleADKConfig.load(path)
    assert cfg2.port == 9001


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


def test_create_llm_agent():
    agent = create_llm_agent(name="test", instruction="Test agent", model="fast")
    assert agent.name == "test"
    assert agent.config.instruction == "Test agent"
    assert agent.config.model == "fast"
    assert agent.agent_type == AgentType.LLM


def test_create_loop_agent():
    sub = [create_llm_agent(name=f"sub{i}") for i in range(2)]
    agent = LoopAgent(name="loop", sub_agents=sub, max_iterations=5)
    assert len(agent.config.sub_agents) == 2
    assert agent.config.max_iterations == 5
    assert agent.agent_type == AgentType.LOOP


def test_create_parallel_agent():
    sub = [create_llm_agent(name=f"sub{i}") for i in range(2)]
    agent = ParallelAgent(name="parallel", sub_agents=sub)
    assert len(agent.config.sub_agents) == 2
    assert agent.agent_type == AgentType.PARALLEL


def test_create_sequential_agent():
    sub = [create_llm_agent(name=f"sub{i}") for i in range(2)]
    agent = SequentialAgent(name="sequential", sub_agents=sub)
    assert len(agent.config.sub_agents) == 2
    assert agent.agent_type == AgentType.SEQUENTIAL


def test_agent_config():
    cfg = AgentConfig(name="test", model="balanced", temperature=0.7)
    assert cfg.model == "balanced"
    assert cfg.temperature == 0.7


def test_agent_tools_and_subagents():
    @function_tool
    def add(a: int, b: int) -> int:
        return a + b

    sub = create_llm_agent(name="sub")
    agent = create_llm_agent(name="top", tools=[add], sub_agents=[sub])
    assert agent.get_tool("add") is not None
    assert agent.get_sub_agent("sub").name == "sub"
    card = agent.to_card()
    assert card["name"] == "top"
    assert "add" in card["tools"]


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def test_function_tool_schema():
    @function_tool
    def add(a: int, b: int) -> int:
        return a + b

    assert add.name == "add"
    assert "a" in add.parameters_schema["properties"]
    assert "b" in add.parameters_schema["properties"]
    schema = add.to_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "add"


def test_function_tool_invoke():
    @function_tool
    def add(a: int, b: int) -> int:
        return a + b

    result = asyncio.run(add.run_async({"a": 2, "b": 3}, ToolContext()))
    assert result == 5


def test_function_tool_async():
    @function_tool
    async def slow(a: int) -> int:
        await asyncio.sleep(0)
        return a * 2

    result = asyncio.run(slow.run_async({"a": 4}, ToolContext()))
    assert result == 8


def test_tool_context_passed():
    received = {}

    @function_tool
    def with_context(*, ctx: ToolContext) -> str:
        received["ctx"] = ctx
        return "ok"

    asyncio.run(with_context.run_async({}, ToolContext(agent_name="test", session_id="123")))
    assert received["ctx"].agent_name == "test"
    assert received["ctx"].session_id == "123"


def test_toolset():
    @function_tool
    def tool1() -> str:
        return "1"

    @function_tool
    def tool2() -> str:
        return "2"

    toolset = Toolset([tool1, tool2])
    tools = asyncio.run(toolset.get_tools())
    assert len(tools) == 2


def test_code_executor_runs_real_python():
    tool = __import__("mem20googlez").CodeExecutorTool()
    result = asyncio.run(tool.run_async({"code": "print(6*7)", "timeout": 20}, ToolContext()))
    assert result["exit_code"] == 0
    assert result["output"].strip() == "42"


def test_bash_tool_runs_real_command():
    tool = __import__("mem20googlez").BashTool()
    result = asyncio.run(tool.run_async({"command": "echo mem20gz", "timeout": 20}, ToolContext()))
    assert result["exit_code"] == 0
    assert result["output"].strip() == "mem20gz"


def test_google_search_parses_real_response():
    html = (
        '<a class="result__a" href="https://example.com/a">First <b>Hit</b></a>'
        '<a class="result__snippet">a snippet here</a>'
        '<a class="result__a" href="https://example.com/b">Second Hit</a>'
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    client = httpx.AsyncClient(transport=MockTransport(handler))
    tool = GoogleSearchTool(client=client)
    result = asyncio.run(tool.run_async({"query": "mem20", "max_results": 2}, ToolContext()))
    assert result["count"] == 2
    assert result["results"][0]["title"] == "First Hit"
    assert result["results"][0]["url"] == "https://example.com/a"
    assert result["results"][1]["title"] == "Second Hit"


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


def test_event_from_model():
    evt = Event.from_model("inv123", "user", "Hello")
    assert evt.author == "user"
    assert evt.content.parts[0].text == "Hello"


def test_event_from_tool_call_and_response():
    call = Event.from_tool_call("inv123", "model", "my_tool", {"x": 1})
    assert call.is_tool_call()
    assert call.tool_call()["name"] == "my_tool"
    assert call.tool_call()["arguments"] == {"x": 1}

    resp = Event.from_tool_response("inv123", "tool", "my_tool", {"result": "ok"})
    assert resp.is_tool_response()
    assert resp.tool_response()["name"] == "my_tool"
    assert resp.tool_response()["response"] == {"result": "ok"}


def test_event_actions():
    actions = EventActions(transfer_to_agent="other", escalate=True, state_delta={"key": "value"})
    assert actions.transfer_to_agent == "other"
    assert actions.escalate is True


def test_event_serialization_roundtrip():
    evt = Event.from_tool_call("inv1", "model", "calc", {"a": 1})
    evt.actions = EventActions(escalate=True)
    data = evt.to_dict()
    # Must be plain-JSON serializable (DatabaseSessionService depends on this).
    json.dumps(data)
    evt2 = Event.from_dict(data)
    assert evt2.author == evt.author
    assert evt2.tool_call() == evt.tool_call()
    assert evt2.actions.escalate is True
    assert evt2.timestamp == evt.timestamp


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def test_session_creation_and_state():
    session = Session(id="s1", app_name="app", user_id="user")
    assert session.state.data == {}
    session.state.set("key", "value")
    assert session.state.get("key") == "value"


def test_session_add_event():
    session = Session(id="s1", app_name="app", user_id="user")
    evt = Event.from_model("inv1", "user", "Hi")
    session.add_event(evt)
    assert len(session.events) == 1
    assert session.get_last_output() == "Hi"  # last event text, regardless of author


def test_in_memory_session_service():
    service = InMemorySessionService()
    session = asyncio.run(service.create_session("app", "user"))
    assert session.app_name == "app"
    assert session.user_id == "user"
    got = asyncio.run(service.get_session("app", "user", session.id))
    assert got.id == session.id
    listings = asyncio.run(service.list_sessions("app", "user"))
    assert len(listings) == 1
    deleted = asyncio.run(service.delete_session("app", "user", session.id))
    assert deleted is True


def test_database_session_service_persists_across_instances(tmp_dir):
    db = f"{tmp_dir}/sessions.db"
    svc1 = DatabaseSessionService(db)
    session = asyncio.run(svc1.create_session("app", "user", session_id="fixed1"))
    asyncio.run(svc1.append_event(session, Event.from_model("inv1", "user", "hello")))
    asyncio.run(svc1.append_event(session, Event.from_tool_call("inv1", "model", "calc", {"a": 1})))
    asyncio.run(svc1.append_event(session, Event.from_tool_response("inv1", "tool", "calc", {"result": 2})))
    asyncio.run(svc1.append_event(session, Event.from_model("inv1", "model", "answer=2")))

    # New instance reads back everything (real persistence).
    svc2 = DatabaseSessionService(db)
    restored = asyncio.run(svc2.get_session("app", "user", "fixed1"))
    assert restored is not None
    assert [e.text() for e in restored.events[:1]] == ["hello"]
    assert restored.events[1].tool_call()["name"] == "calc"
    assert restored.events[2].tool_response()["response"] == {"result": 2}
    assert restored.get_last_output() == "answer=2"


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


def test_memory_entry():
    entry = MemoryEntry(content="test", author="user")
    d = entry.to_dict()
    json.dumps(d)
    assert d["content"] == "test"
    assert MemoryEntry.from_dict(d).content == "test"


def test_in_memory_memory_service():
    service = InMemoryMemoryService()
    asyncio.run(service.add_memory("app", "user", "session1", MemoryEntry(content="blue sky", author="user")))
    found = asyncio.run(service.search_memory("app", "user", "sky", limit=5))
    assert len(found) == 1
    assert found[0].content == "blue sky"
    entries = asyncio.run(service.list_memories("app", "user", limit=10))
    assert len(entries) == 1


def test_file_memory_service_persists_across_instances(tmp_dir):
    svc1 = FileMemoryService(memory_dir=tmp_dir)
    asyncio.run(svc1.add_memory("app", "user", "session1", MemoryEntry(content="persisted fact", author="user")))

    # New instance reads the same file (real disk persistence).
    svc2 = FileMemoryService(memory_dir=tmp_dir)
    found = asyncio.run(svc2.search_memory("app", "user", "persisted", limit=5))
    assert len(found) == 1
    assert found[0].content == "persisted fact"
    listed = asyncio.run(svc2.list_memories("app", "user"))
    assert len(listed) == 1


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


def test_parse_tool_call_text_known_tool():
    tools = [{"function": {"name": "calc"}}]
    parsed = OllamaProvider._parse_tool_call_text('{"name": "calc", "arguments": {"a": 1}}', tools)
    assert parsed is not None
    assert parsed.name == "calc"
    assert parsed.arguments == {"a": 1}


def test_parse_tool_call_text_fenced_json_known_tool():
    tools = [{"function": {"name": "calc"}}]
    fenced = '```json\n{"name": "calc", "arguments": {"a": 1, "b": 2}}\n```'
    parsed = OllamaProvider._parse_tool_call_text(fenced, tools)
    assert parsed is not None
    assert parsed.name == "calc"
    assert parsed.arguments == {"a": 1, "b": 2}


def test_translate_messages_tool_arguments_as_object():
    # This Ollama build rejects stringified "arguments" on the assistant
    # tool-call message; translate them to parsed objects.
    prov = OllamaProvider(url="http://example.invalid")
    out = prov._translate_messages(
        [
            {"role": "assistant", "content": "", "tool_calls": [{"id": "t1", "name": "calc", "arguments": {"a": 1}}]},
            {"role": "tool", "tool_call_id": "t1", "name": "calc", "content": '{"result": 1}'},
        ]
    )
    assert out[0]["tool_calls"][0]["function"]["arguments"] == {"a": 1}
    assert not isinstance(out[0]["tool_calls"][0]["function"]["arguments"], str)
    assert out[1]["role"] == "tool"
    assert out[1]["tool_name"] == "calc"


def test_parse_tool_call_text_unknown_tool_rejected():
    tools = [{"function": {"name": "calc"}}]
    # Model naming a tool we did not advertise must NOT become a call.
    assert OllamaProvider._parse_tool_call_text('{"name": "do_evil", "arguments": {}}', tools) is None
    assert OllamaProvider._parse_tool_call_text("no json here", tools) is None


def test_resolve_provider_forced():
    cfg = GoogleADKConfig()
    ollama = asyncio.run(resolve_provider(cfg, provider="ollama"))
    assert ollama.name == "ollama"
    assert ollama.url == "http://127.0.0.1:11434"
    gateway = asyncio.run(resolve_provider(cfg, provider="openai"))
    assert gateway.name == "gateway"
    assert gateway.base_url == "http://127.0.0.1:4000"


# ---------------------------------------------------------------------------
# Runners
# ---------------------------------------------------------------------------


def test_run_config_and_result():
    cfg = RunConfig(model="balanced", max_turns=5, temperature=0.7)
    assert cfg.model == "balanced"
    assert cfg.max_turns == 5
    assert cfg.temperature == 0.7
    session = Session(id="s1", app_name="app", user_id="user")
    result = RunResult(session=session, events=[], final_output="test")
    assert result.final_output == "test"


def test_events_to_messages():
    events = [
        Event.from_model("inv1", "user", "add"),
        Event.from_tool_call("inv1", "model", "add", {"a": 1, "b": 2}),
        Event.from_tool_response("inv1", "tool", "add", {"result": 3}),
        Event.from_model("inv1", "model", "the answer is 3"),
    ]
    msgs = events_to_messages(events)
    assert msgs[0] == {"role": "user", "content": "add"}
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["tool_calls"][0]["name"] == "add"
    assert msgs[2]["role"] == "tool"
    assert msgs[3] == {"role": "assistant", "content": "the answer is 3"}


def test_run_agent_tool_loop_hermetic():
    @function_tool
    def add(a: int, b: int) -> int:
        return a + b

    agent = create_llm_agent(name="calc", instruction="Use add.", tools=[add], model="fast")
    provider = FakeProvider(
        [
            _tool_reply("add", {"a": 2, "b": 3}),
            _text_reply("the sum is 5"),
        ]
    )
    session = Session(id="s1", app_name="calc", user_id="u")
    events = asyncio.run(run_agent(agent, session, "2+3?", RunConfig(), provider=provider, max_turns=5))

    by_author = [e for e in events]
    assert by_author[0].is_tool_call()
    assert by_author[0].tool_call()["name"] == "add"
    assert by_author[1].is_tool_response()
    assert by_author[1].tool_response()["response"] == 5
    assert by_author[2].text() == "the sum is 5"
    assert len(provider.calls) == 2


def test_run_agent_unknown_tool_handled():
    agent = create_llm_agent(name="a", instruction="try tools", model="fast")
    provider = FakeProvider([_tool_reply("no_such_tool", {})])
    events = asyncio.run(run_agent(agent, None, "go", RunConfig(max_turns=2), provider=provider))
    # The unknown call still gets a real function_response with an error payload.
    assert events[0].is_tool_call()
    assert events[1].is_tool_response()
    payload = events[1].tool_response()["response"]
    assert "unknown tool" in payload["error"]
    assert len(provider.calls) >= 1  # loop continues only while the model issues calls


def test_run_agent_max_turns_cap():
    agent = create_llm_agent(name="loop", model="fast")
    # Provider always asks for a tool — budget must stop the loop.
    provider = FakeProvider([_tool_reply("tool_any", {})] * 100)
    budget = 3
    events = asyncio.run(run_agent(agent, None, "spin", RunConfig(max_turns=budget), provider=provider))
    assert len(provider.calls) <= budget
    assert len(events) >= 1


def test_in_memory_runner_end_to_end():
    @function_tool
    def add(a: int, b: int) -> int:
        return a + b

    agent = create_llm_agent(name="calc", instruction="Use add.", tools=[add], model="fast")
    provider = FakeProvider(
        [
            _tool_reply("add", {"a": 7, "b": 8}),
            _text_reply("the sum is 15"),
        ]
    )
    runner = InMemoryRunner(agent=agent, app_name="calc", config_data=GoogleADKConfig(), provider=provider)
    result = asyncio.run(runner.run("u1", input="7+8?"))
    assert result.error is None
    assert result.final_output == "the sum is 15"
    # Session memory carries the user event + agent events: user, tool call, tool result, model text.
    assert [e.author for e in result.session.events] == ["user", "model", "tool", "model"]


def test_streaming_yields_events():
    agent = create_llm_agent(name="calc", model="fast")
    provider = FakeProvider([_text_reply("streamed reply")])
    runner = InMemoryRunner(agent=agent, app_name="calc", provider=provider)

    async def collect():
        out = []
        async for evt in runner.run_stream_async(agent, Session(id="s1", app_name="calc", user_id="u"), "hi"):
            out.append(evt)
        return out

    events = asyncio.run(collect())
    assert any(e.text() == "streamed reply" for e in events)


# ---------------------------------------------------------------------------
# Flows
# ---------------------------------------------------------------------------


def test_flow_chain_a_to_b():
    agent_a = create_llm_agent(name="plan", instruction="Draft a plan.", model="fast")
    agent_b = create_llm_agent(name="review", instruction="Review on top.", model="fast")
    provider = FakeProvider(
        [
            _text_reply("plan: build a memory system"),
            _text_reply("DONE: memory system plan approved"),
        ]
    )
    flow = Flow("plan-review", [agent_a, agent_b])
    result = asyncio.run(flow.run(input="build memory", provider=provider))
    assert result.final_output == "DONE: memory system plan approved"
    assert len(result.steps) == 2
    assert result.steps[0].agent.name == "plan"
    assert result.steps[0].output == "plan: build a memory system"
    assert result.steps[1].agent.name == "review"
    # Step outputs feed the next agent's input.
    b_input = provider.calls[1]["messages"]
    assert any("plan: build a memory system" in m.get("content", "") for m in b_input)


# ---------------------------------------------------------------------------
# Serving
# ---------------------------------------------------------------------------


@pytest.fixture
def test_app():
    agent = create_llm_agent(name="chat", instruction="Assistant.", model="fast")
    provider = FakeProvider(
        [
            _text_reply("hello from chat"),
            _text_reply("remembered reply"),
        ]
    )
    config = GoogleADKConfig()
    app = create_app(agents=[agent], config=config, provider=provider)
    return app, provider


async def test_serve_health(test_app):
    app, _ = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["provider"] == "fake"


async def test_serve_agents_list(test_app):
    app, _ = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/agents")
    assert r.status_code == 200
    assert r.json()["agents"][0]["name"] == "chat"


async def test_serve_agent_run_and_session(test_app):
    app, _ = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/agents/chat/run",
            json={"input": "hi", "user_id": "u1"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["output"] == "hello from chat"
        assert len(body["events"]) >= 1
        session_id = body["session_id"]

        # Same session id resumes with history.
        r2 = await client.post(
            "/agents/chat/run",
            json={"input": "again", "user_id": "u1", "session_id": session_id},
        )
        assert r2.status_code == 200
        assert r2.json()["output"] == "remembered reply"

        # Sessions list shows the resumed session.
        ls = await client.get("/sessions")
        ids = [s["id"] for s in ls.json()["sessions"]]
        assert session_id in ids

        # And its detail exposes the accumulated events.
        det = await client.get(f"/sessions/{session_id}")
        assert det.status_code == 200
        assert len(det.json()["events"]) >= 2


async def test_serve_unknown_agent_404(test_app):
    app, _ = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/agents/nope/run", json={"input": "hi"})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Composites
# ---------------------------------------------------------------------------


def test_sequential_agent_runs_chain():
    a = create_llm_agent(name="a", model="fast")
    b = create_llm_agent(name="b", model="fast")
    seq = SequentialAgent(name="seq", sub_agents=[a, b])
    provider = FakeProvider([_text_reply("from a"), _text_reply("from b")])
    session = Session(id="s1", app_name="seq", user_id="u")
    events = asyncio.run(seq.run_async(session, "go", provider=provider))
    assert any(e.text() == "from a" for e in events)
    assert any(e.text() == "from b" for e in events)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))