from __future__ import annotations
import re
from typing import Any

SENSITIVE_KEYS = {"password", "passwd", "secret", "token", "api_key", "apikey", "authorization", "cookie"}
SECRET_PATTERNS = [
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
]
RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

class UnsafeAutomaticAction(PermissionError):
    pass


def redact(value: Any, key: str | None = None) -> Any:
    if key and key.lower() in SENSITIVE_KEYS:
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact(v) for v in value)
    if isinstance(value, str):
        out = value
        for p in SECRET_PATTERNS:
            out = p.sub(lambda m: (m.group(1) if m.lastindex else "") + "[REDACTED]", out)
        return out
    return value


def permits_risk(capability_risk: str, max_risk: str) -> bool:
    return RISK_ORDER[capability_risk] <= RISK_ORDER[max_risk]


def automatic_action_allowed(risk: str) -> bool:
    # Hard safety boundary: feedback/tuning may never override this.
    return risk in {"low", "medium"}
