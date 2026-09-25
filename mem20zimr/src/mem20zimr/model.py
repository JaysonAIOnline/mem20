from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Literal
import json

Mode = Literal["local", "hybrid", "cloud", "browser", "edge"]
Kind = Literal["python", "web"]

@dataclass(frozen=True)
class ResourceLimits:
    timeout_seconds: int = 15
    memory_mb: int = 512
    cpu_seconds: int = 10
    output_kb: int = 256
    max_retries: int = 2

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "ResourceLimits":
        d = d or {}
        return cls(**{k: d[k] for k in d if k in cls.__annotations__})

@dataclass(frozen=True)
class MicroappManifest:
    schema_version: str
    app_id: str
    version: str
    kind: Kind
    entrypoint: str
    capabilities: tuple[str, ...]
    supported_modes: tuple[Mode, ...]
    signer: str
    signature: str
    digest: str
    limits: ResourceLimits

    @classmethod
    def from_json(cls, raw: str) -> "MicroappManifest":
        d = json.loads(raw)
        required = {"schema_version","app_id","version","kind","entrypoint","capabilities","supported_modes","signer","signature","digest"}
        missing = sorted(required - d.keys())
        if missing:
            raise ValueError(f"manifest missing fields: {', '.join(missing)}")
        if d["schema_version"] != "1":
            raise ValueError("unsupported schema_version")
        if d["kind"] not in {"python", "web"}:
            raise ValueError("unsupported kind")
        return cls(
            schema_version=d["schema_version"], app_id=d["app_id"], version=d["version"], kind=d["kind"],
            entrypoint=d["entrypoint"], capabilities=tuple(d.get("capabilities", [])),
            supported_modes=tuple(d.get("supported_modes", ["local"])), signer=d["signer"],
            signature=d["signature"], digest=d["digest"], limits=ResourceLimits.from_dict(d.get("limits"))
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["capabilities"] = list(self.capabilities)
        d["supported_modes"] = list(self.supported_modes)
        return d

@dataclass
class JobResult:
    job_id: str
    app_id: str
    status: str
    mode: str
    attempt: int
    exit_code: int | None
    stdout: str
    stderr: str
    started_at: float
    finished_at: float | None
    explanation: dict[str, Any]
