from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any
import json
import time

SCHEMA_VERSION = "1.0"

class ExecutionMode(str, Enum):
    LOCAL = "local"
    HYBRID = "hybrid"
    CLOUD = "cloud"

class JobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass(frozen=True)
class Capability:
    capability_id: str
    title: str
    description: str
    actions: tuple[str, ...]
    tags: tuple[str, ...] = ()
    version: str = "1.0.0"
    input_schema: dict[str, Any] = field(default_factory=dict)
    risk: str = "low"
    cost: float = 0.0
    latency_ms: float = 1.0
    execution_modes: tuple[str, ...] = ("local", "hybrid", "cloud")
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def validate(self) -> None:
        if not self.capability_id or len(self.capability_id) > 128:
            raise ValueError("capability_id must be 1..128 characters")
        if not self.title or len(self.title) > 200:
            raise ValueError("title must be 1..200 characters")
        if self.risk not in {"low", "medium", "high", "critical"}:
            raise ValueError("risk must be low|medium|high|critical")
        if not self.actions or any(not isinstance(a, str) or not a for a in self.actions):
            raise ValueError("actions must contain non-empty strings")
        if self.cost < 0 or self.latency_ms < 0:
            raise ValueError("cost and latency_ms must be non-negative")
        for mode in self.execution_modes:
            ExecutionMode(mode)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["actions"] = list(self.actions)
        d["tags"] = list(self.tags)
        d["execution_modes"] = list(self.execution_modes)
        return d

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Capability":
        obj = cls(
            capability_id=str(raw["capability_id"]),
            title=str(raw["title"]),
            description=str(raw.get("description", "")),
            actions=tuple(raw.get("actions", ())),
            tags=tuple(raw.get("tags", ())),
            version=str(raw.get("version", "1.0.0")),
            input_schema=dict(raw.get("input_schema", {})),
            risk=str(raw.get("risk", "low")),
            cost=float(raw.get("cost", 0.0)),
            latency_ms=float(raw.get("latency_ms", 1.0)),
            execution_modes=tuple(raw.get("execution_modes", ("local", "hybrid", "cloud"))),
            metadata=dict(raw.get("metadata", {})),
            schema_version=str(raw.get("schema_version", SCHEMA_VERSION)),
        )
        obj.validate()
        return obj

@dataclass(frozen=True)
class UserIntent:
    task: str
    goals: tuple[str, ...] = ()
    required_tags: tuple[str, ...] = ()
    preferred_actions: tuple[str, ...] = ()
    prohibited_capabilities: tuple[str, ...] = ()
    max_risk: str = "medium"
    auto_execute: bool = False
    context: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def validate(self) -> None:
        if not self.task or len(self.task) > 4096:
            raise ValueError("task must be 1..4096 characters")
        if self.max_risk not in {"low", "medium", "high", "critical"}:
            raise ValueError("invalid max_risk")
        if len(self.goals) > 64 or len(self.required_tags) > 64:
            raise ValueError("too many goals/tags")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k in ("goals", "required_tags", "preferred_actions", "prohibited_capabilities"):
            d[k] = list(d[k])
        return d

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "UserIntent":
        obj = cls(
            task=str(raw["task"]), goals=tuple(raw.get("goals", ())),
            required_tags=tuple(raw.get("required_tags", ())),
            preferred_actions=tuple(raw.get("preferred_actions", ())),
            prohibited_capabilities=tuple(raw.get("prohibited_capabilities", ())),
            max_risk=str(raw.get("max_risk", "medium")),
            auto_execute=bool(raw.get("auto_execute", False)),
            context=dict(raw.get("context", {})),
            schema_version=str(raw.get("schema_version", SCHEMA_VERSION)),
        )
        obj.validate()
        return obj

@dataclass
class InterfacePlan:
    plan_id: str
    job_id: str
    task: str
    selected_capabilities: list[dict[str, Any]]
    sections: list[dict[str, Any]]
    commands: list[dict[str, Any]]
    confidence: float
    alternatives: list[dict[str, Any]]
    bottlenecks: list[str]
    explanation: dict[str, Any]
    requires_confirmation: bool
    execution_mode: str
    generation: int = 1
    job_state: str = JobState.QUEUED.value
    created_at: float = field(default_factory=time.time)
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "InterfacePlan":
        return cls(**raw)

@dataclass
class Job:
    job_id: str
    idempotency_key: str
    intent: dict[str, Any]
    state: str
    mode: str
    attempts: int = 0
    error: str | None = None
    plan_id: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
