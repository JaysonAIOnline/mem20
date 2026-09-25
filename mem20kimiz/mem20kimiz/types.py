"""Shared type contracts for mem20kimiz (port of kimi-code's sessionSwarm.ts)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Protocol, TypeVar, Union

T = TypeVar("T")

SpanKind = Literal["spawn", "resume"]
"""Local varient names mirror kimi-code's Tuple `kind: 'spawn' | 'resume'`."""

MLifecycleState = Literal["queued", "running", "suspended", "completed", "failed", "aborted", "not_started"]
"""Lifecycle state vocabulary exposed on runs (queued/running/suspended/...)."""


@dataclass
class SessionSwarmTaskBase:
    data: Any = None
    profileName: str = "subagent"
    parentToolCallId: str = ""
    parentToolCallUuid: Optional[str] = None
    prompt: str = ""
    description: str = ""
    swarmIndex: Optional[int] = None
    swarmItem: Optional[str] = None
    runInBackground: bool = False
    timeout: Optional[float] = None
    signal: Any = None


@dataclass
class SessionSwarmSpawnTask(SessionSwarmTaskBase):
    kind: Literal["spawn"] = "spawn"
    plan: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionSwarmResumeTask(SessionSwarmTaskBase):
    kind: Literal["resume"] = "resume"
    resumeAgentId: str = ""


SessionSwarmTask = Union[SessionSwarmSpawnTask, SessionSwarmResumeTask]


@dataclass
class SessionSwarmRunResult:
    task: Optional[SessionSwarmTask] = None
    agentId: Optional[str] = None
    status: Literal["completed", "failed", "aborted"] = "failed"
    state: Optional[Literal["started", "not_started"]] = None
    result: Optional[str] = None
    usage: Optional[Any] = None
    stopReason: Optional[str] = None
    error: Optional[str] = None


@dataclass
class SessionSwarmRunArgs:
    callerAgentId: str = ""
    tasks: list[SessionSwarmTask] = field(default_factory=list)


class ISessionSwarmService(Protocol):
    def getSwarmItem(self, agentId: str) -> Optional[str]:
        ...

    def run(self, args: SessionSwarmRunArgs) -> list[SessionSwarmRunResult]:
        ...

    def cancel(self, callerAgentId: str) -> None:
        ...


def escape_xml(value: Any) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )