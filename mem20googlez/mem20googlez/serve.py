from __future__ import annotations

import uuid

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .agents import BaseAgent, LlmAgent
from .config import GoogleADKConfig
from .memory import BaseMemoryService, FileMemoryService
from .providers import ModelProvider
from .runners import RunConfig, Runner
from .sessions import BaseSessionService, DatabaseSessionService
from .tools import BashTool, CodeExecutorTool, GoogleSearchTool


class RunRequest(BaseModel):
    input: str = ""
    session_id: str | None = None
    user_id: str = "default"


class RunResponse(BaseModel):
    session_id: str
    output: str
    events: list[dict]
    error: str | None = None


def default_registry() -> list[BaseAgent]:
    return [
        LlmAgent(
            name="chat",
            description="General-purpose assistant with executable web, code, and shell tools.",
            instruction=(
                "You are a helpful local assistant. Use an available tool when it "
                "provides verifiable information. Emit a real function call with "
                "concrete arguments when a tool is needed. After a tool result, "
                "give a concise plain-text answer based on that result."
            ),
            model="fast",
            tools=[GoogleSearchTool(), CodeExecutorTool(), BashTool()],
        ),
        LlmAgent(
            name="coder",
            description="Coding assistant that executes Python before reporting results.",
            instruction=(
                "You are a coding assistant. When code execution is needed, call "
                "code_executor with concrete code and then report its actual output. "
                "After the tool result, answer in plain text rather than JSON."
            ),
            model="fast",
            tools=[CodeExecutorTool()],
        ),
    ]


def _serialize_event(event) -> dict:
    return event.to_dict()


def _runner_last_output(events) -> str:
    for event in reversed(events):
        if event.author == "model" and event.text():
            return event.text()
    return ""


def create_app(
    agents: list[BaseAgent] | None = None,
    config: GoogleADKConfig | None = None,
    provider: ModelProvider | None = None,
    session_service: BaseSessionService | None = None,
    memory_service: BaseMemoryService | None = None,
) -> FastAPI:
    cfg = config or GoogleADKConfig.load()
    registry = list(agents) if agents is not None else default_registry()
    if not registry:
        raise ValueError("at least one agent is required")
    sessions = session_service or DatabaseSessionService(cfg.session_db_path)
    memories = memory_service or FileMemoryService(cfg.memory_dir)
    app = FastAPI(
        title="mem20googlez",
        description="Local Google ADK-style agents over real HTTP",
        version="0.2.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.state.config = cfg
    app.state.registry = registry
    app.state.session_service = sessions
    app.state.memory_service = memories
    app.state.provider = provider
    app.state.run_config = RunConfig(temperature=0.0, top_p=0.1, max_turns=8)

    async def active_provider() -> ModelProvider:
        if app.state.provider is None:
            from .providers import resolve_provider

            app.state.provider = await resolve_provider(cfg)
        return app.state.provider

    @app.get("/")
    async def root() -> dict:
        return {
            "service": "mem20googlez",
            "version": app.version,
            "agents": [agent.to_card() for agent in registry],
            "storage": {
                "sessions": cfg.session_db_path,
                "memory": cfg.memory_dir,
            },
            "endpoints": [
                "/health",
                "/agents",
                "/agents/{name}/run",
                "/sessions",
                "/sessions/{session_id}",
            ],
        }

    @app.get("/health")
    async def health() -> dict:
        current = await active_provider()
        healthy, detail = await current.health()
        if not healthy:
            raise HTTPException(status_code=503, detail=detail)
        return {
            "status": "ok",
            "provider": current.name,
            "model": current.model,
            "detail": detail,
        }

    @app.get("/agents")
    async def list_agents() -> dict:
        return {"agents": [agent.to_card() for agent in registry]}

    @app.post("/agents/{name}/run", response_model=RunResponse)
    async def run_agent_endpoint(name: str, request: RunRequest) -> RunResponse:
        agent = next((candidate for candidate in registry if candidate.name == name), None)
        if agent is None:
            raise HTTPException(status_code=404, detail=f"agent '{name}' not found")
        session_id = request.session_id or f"run_{uuid.uuid4().hex[:12]}"
        session = await sessions.get_session(agent.name, request.user_id, session_id)
        if session is None:
            other = await sessions.get_session_by_id(session_id)
            if other is not None:
                raise HTTPException(status_code=409, detail="session_id belongs to another user or agent")
            session = await sessions.create_session(agent.name, request.user_id, session_id)
        current = await active_provider()
        runner = Runner(
            agent=agent,
            session_service=sessions,
            memory_service=memories,
            config=app.state.run_config,
            provider=current,
            config_data=cfg,
        )
        result = await runner.run_async(agent, session, request.input)
        if result.error:
            raise HTTPException(status_code=502, detail=result.error)
        return RunResponse(
            session_id=session.id,
            output=result.final_output or _runner_last_output(result.events),
            events=[_serialize_event(event) for event in result.events],
        )

    @app.get("/sessions")
    async def list_sessions(
        app_name: str | None = Query(default=None),
        user_id: str | None = Query(default=None),
    ) -> dict:
        records = await sessions.list_sessions(app_name=app_name, user_id=user_id)
        return {
            "sessions": [
                {
                    "id": session.id,
                    "app_name": session.app_name,
                    "user_id": session.user_id,
                    "event_count": len(session.events),
                    "created_at": session.created_at.isoformat(),
                    "updated_at": session.updated_at.isoformat(),
                }
                for session in records
            ]
        }

    @app.get("/sessions/{session_id}")
    async def get_session(
        session_id: str,
        user_id: str | None = Query(default=None),
    ) -> dict:
        session = await sessions.get_session_by_id(session_id, user_id=user_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"session '{session_id}' not found")
        return {
            "id": session.id,
            "app_name": session.app_name,
            "user_id": session.user_id,
            "state": session.state.to_dict(),
            "events": [_serialize_event(event) for event in session.events],
        }

    return app


def serve(
    host: str = "127.0.0.1",
    port: int = 8002,
    log_level: str = "info",
    config: GoogleADKConfig | None = None,
) -> None:
    import uvicorn

    uvicorn.run(create_app(config=config), host=host, port=port, log_level=log_level)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(prog="mem20googlez-serve")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8002)
    args = parser.parse_args()
    serve(host=args.host, port=args.port)
