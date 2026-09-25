from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any
import re
import time
import uuid

SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:[-+][0-9A-Za-z.-]+)?$")


class CapabilityState(StrEnum):
    ACTIVE = "active"
    DEGRADED = "degraded"
    DISABLED = "disabled"


class JobState(StrEnum):
    PENDING = "pending"
    PLANNING = "planning"
    RUNNING = "running"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class Capability:
    id: str
    name: str
    version: str
    provider: str
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    platforms: list[str] = field(default_factory=lambda: ["local"])
    endpoint: str | None = None
    invocation: str | None = None
    signed: bool = False
    signature: str | None = None
    state: CapabilityState = CapabilityState.ACTIVE
    latency_ms: float = 1.0
    cost_units: float = 0.0
    energy_units: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def validate(self) -> None:
        if not self.id.strip():
            raise ValueError("capability.id is required")
        if not self.name.strip():
            raise ValueError("capability.name is required")
        if not self.provider.strip():
            raise ValueError("capability.provider is required")
        if not SEMVER_RE.match(self.version):
            raise ValueError(f"invalid semantic version: {self.version}")
        if not self.outputs:
            raise ValueError("capability.outputs must contain at least one typed output")
        if self.latency_ms < 0 or self.cost_units < 0 or self.energy_units < 0:
            raise ValueError("latency/cost/energy values cannot be negative")
        self.inputs = sorted(set(self.inputs))
        self.outputs = sorted(set(self.outputs))
        self.tags = sorted(set(self.tags))
        self.requires = sorted(set(self.requires))
        self.conflicts = sorted(set(self.conflicts))
        self.platforms = sorted(set(self.platforms))
        self.updated_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Capability":
        d = dict(data)
        if "state" in d and not isinstance(d["state"], CapabilityState):
            d["state"] = CapabilityState(d["state"])
        cap = cls(**d)
        cap.validate()
        return cap


@dataclass(slots=True)
class CapabilityQuery:
    text: str | None = None
    provides: list[str] = field(default_factory=list)
    requires_platform: str | None = None
    tags: list[str] = field(default_factory=list)
    active_only: bool = True
    signed_only: bool = False


@dataclass(slots=True)
class CompositionRequest:
    required_outputs: list[str]
    available_inputs: list[str] = field(default_factory=list)
    platform: str = "local"
    prefer_signed: bool = True
    max_capabilities: int = 8
    max_cost_units: float | None = None
    max_latency_ms: float | None = None
    max_energy_units: float | None = None

    def validate(self) -> None:
        if not self.required_outputs:
            raise ValueError("required_outputs cannot be empty")
        if self.max_capabilities < 1:
            raise ValueError("max_capabilities must be >= 1")


@dataclass(slots=True)
class Plan:
    id: str
    capabilities: list[str]
    required_outputs: list[str]
    resolved_outputs: list[str]
    unresolved_outputs: list[str]
    score: float
    confidence: float
    alternatives: list[list[str]]
    bottlenecks: list[str]
    explanation: dict[str, Any]

    @classmethod
    def new(cls, **kwargs: Any) -> "Plan":
        return cls(id=str(uuid.uuid4()), **kwargs)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Job:
    id: str
    idempotency_key: str
    plan_id: str
    state: JobState = JobState.PENDING
    attempts: int = 0
    result: Any = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value
        return d
