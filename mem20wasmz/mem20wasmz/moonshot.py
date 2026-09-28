"""Moonshot experiment protocol for the mem30 Phase 4 incubation lane.

The rule this enforces, in one line: a moonshot may report a number only if it
measured it, and must otherwise say so.

This exists because RM-102 was found returning `estimated_speedup: 1.04` computed
as `round(1 + 4*min(1, ops/1e8), 2)` — arithmetic dressed as a benchmark, on a
box with a broken GPU driver, from a `webgpu_available` flag the caller supplied.
A moonshot lane built on that judge would manufacture convincing nonsense.

A verdict is one of:
  MEASURED    a real measurement ran, and the evidence is attached
  INFEASIBLE  the experiment was attempted and cannot be done on this host
  UNTESTED    the experiment was defined but not run
There is no fourth option. A result may not be asserted.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field

MEASURED = "MEASURED"
INFEASIBLE = "INFEASIBLE"
UNTESTED = "UNTESTED"

VALID_VERDICTS = (MEASURED, INFEASIBLE, UNTESTED)

# Fields that look like measurements but cannot be trusted unless a
# measurement backs them. This is the RM-102 lesson, encoded.
FABRICATED_METRIC_NAMES = (
    "estimated_speedup", "speedup", "expected_speedup", "projected_speedup",
    "accuracy_estimate", "estimated_accuracy", "theoretical_gain",
    "estimated_performance", "rough_benchmark",
)

_HONESTY_MARKERS = ("not_measured", "unverified", "infeasible", "unavailable")


class ProtocolViolation(RuntimeError):
    """Raised when a moonshot result asserts something it did not measure."""


@dataclass
class Evidence:
    kind: str
    detail: str
    value: object = None


@dataclass
class MoonshotResult:
    moonshot: str
    incubator: str
    verdict: str = UNTESTED
    reason: str = ""
    evidence: list[Evidence] = field(default_factory=list)
    claims: dict = field(default_factory=dict)
    started_at: float = 0.0
    duration_s: float = 0.0

    def as_dict(self) -> dict:
        payload = asdict(self)
        payload["evidence"] = [asdict(e) for e in self.evidence]
        return payload


def audit_claims(claims: dict) -> list[str]:
    """Return problems: fabricated metrics, and MEASURED with no evidence."""
    problems: list[str] = []

    for name in FABRICATED_METRIC_NAMES:
        if name not in claims:
            continue
        value = claims[name]
        if isinstance(value, str) and any(
                marker in value.lower() for marker in _HONESTY_MARKERS):
            continue
        problems.append(
            f"claim {name!r}={value!r} looks like a measurement but carries no "
            "measurement evidence; report it as 'not_measured' instead"
        )

    for name, value in claims.items():
        lowered = name.lower()
        if any(token in lowered for token in ("speedup", "benchmark", "accuracy",
                                              "throughput", "faster", "gain")):
            if isinstance(value, (int, float)) and not any(
                    token in lowered for token in ("measured_", "observed_")):
                problems.append(
                    f"numeric claim {name!r}={value!r} must be prefixed "
                    "measured_ or observed_ to show it was actually measured"
                )
    return problems


def validate(result: MoonshotResult) -> MoonshotResult:
    """Enforce the protocol. Raises ProtocolViolation on a dishonest result."""
    if result.verdict not in VALID_VERDICTS:
        raise ProtocolViolation(
            f"verdict must be one of {VALID_VERDICTS}, got {result.verdict!r}")

    problems = audit_claims(result.claims)
    if problems:
        raise ProtocolViolation("; ".join(problems))

    if result.verdict == MEASURED:
        if not result.evidence:
            raise ProtocolViolation(
                f"{result.moonshot}: verdict MEASURED requires at least one "
                "piece of evidence; measured nothing means INFEASIBLE or UNTESTED")
        if not result.reason:
            raise ProtocolViolation(
                f"{result.moonshot}: verdict MEASURED requires a reason "
                "stating what was measured")
    else:
        if result.verdict == INFEASIBLE and not result.reason:
            raise ProtocolViolation(
                f"{result.moonshot}: verdict INFEASIBLE requires a reason "
                "saying what blocked it")
    return result


def record(moonshot: str, incubator: str, verdict: str, reason: str = "",
           evidence: list[Evidence] | None = None,
           claims: dict | None = None) -> MoonshotResult:
    """Build and validate a result. Never returns an unvalidated result."""
    result = MoonshotResult(
        moonshot=moonshot, incubator=incubator, verdict=verdict, reason=reason,
        evidence=list(evidence or []), claims=dict(claims or {}),
        started_at=time.time(),
    )
    validate(result)
    result.duration_s = round(time.time() - result.started_at, 6)
    return result


def save(result: MoonshotResult, directory: str) -> str:
    os.makedirs(directory, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in result.moonshot)
    path = os.path.join(directory, f"{safe}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(result.as_dict(), fh, indent=2)
        fh.write("\n")
    return path


def load(path: str) -> MoonshotResult:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return MoonshotResult(
        moonshot=data["moonshot"], incubator=data["incubator"],
        verdict=data["verdict"], reason=data.get("reason", ""),
        evidence=[Evidence(**e) for e in data.get("evidence", [])],
        claims=data.get("claims", {}),
        started_at=data.get("started_at", 0.0),
        duration_s=data.get("duration_s", 0.0),
    )


__all__ = ["MEASURED", "INFEASIBLE", "UNTESTED", "VALID_VERDICTS",
           "Evidence", "MoonshotResult", "ProtocolViolation", "audit_claims",
           "validate", "record", "save", "load",
           "FABRICATED_METRIC_NAMES"]
