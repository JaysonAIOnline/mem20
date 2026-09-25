from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import exp
from typing import Iterable

from .graph import CapabilityGraph
from .models import Capability, CompositionRequest, Plan


@dataclass(slots=True)
class Candidate:
    ids: list[str]
    resolved: set[str]
    unresolved: set[str]
    score: float
    bottlenecks: list[str]
    metrics: dict[str, float]


class CompositionPlanner:
    """Constraint-aware set-cover planner for automatic app assembly."""

    def __init__(self, graph: CapabilityGraph) -> None:
        self.graph = graph

    def _candidate_score(self, caps: list[Capability], req: CompositionRequest) -> Candidate:
        available = set(req.available_inputs)
        provided: set[str] = set()
        bottlenecks: list[str] = []
        ids = {c.id for c in caps}

        for cap in caps:
            if req.platform not in cap.platforms and "any" not in cap.platforms:
                bottlenecks.append(f"{cap.id}:platform:{req.platform}")
            missing_deps = [d for d in cap.requires if d not in ids]
            for dep in missing_deps:
                bottlenecks.append(f"{cap.id}:missing-required-capability:{dep}")
            conflicts = [x for x in cap.conflicts if x in ids]
            for conflict in conflicts:
                bottlenecks.append(f"{cap.id}:conflict:{conflict}")
            available |= set(cap.outputs)
            provided |= set(cap.outputs)

        # Input satisfiability is evaluated after all selected outputs are known.
        for cap in caps:
            missing_inputs = set(cap.inputs) - available
            for item in sorted(missing_inputs):
                bottlenecks.append(f"{cap.id}:missing-input:{item}")

        required = set(req.required_outputs)
        resolved = required & provided
        unresolved = required - provided
        latency = sum(c.latency_ms for c in caps)
        cost = sum(c.cost_units for c in caps)
        energy = sum(c.energy_units for c in caps)
        signed_ratio = (sum(1 for c in caps if c.signed) / len(caps)) if caps else 0.0

        if req.max_cost_units is not None and cost > req.max_cost_units:
            bottlenecks.append("budget:cost")
        if req.max_latency_ms is not None and latency > req.max_latency_ms:
            bottlenecks.append("budget:latency")
        if req.max_energy_units is not None and energy > req.max_energy_units:
            bottlenecks.append("budget:energy")

        coverage = len(resolved) / max(1, len(required))
        penalty = 0.09 * len(caps) + 0.015 * latency + 0.03 * cost + 0.02 * energy + 0.12 * len(bottlenecks)
        signature_bonus = 0.08 * signed_ratio if req.prefer_signed else 0.0
        feedback = self.graph.store.feedback_weight() * 0.03
        score = (coverage * 1.3) + signature_bonus + feedback - penalty
        return Candidate(
            ids=[c.id for c in caps],
            resolved=resolved,
            unresolved=unresolved,
            score=score,
            bottlenecks=sorted(set(bottlenecks)),
            metrics={"latency_ms": latency, "cost_units": cost, "energy_units": energy, "signed_ratio": signed_ratio},
        )

    def plan(self, request: CompositionRequest) -> Plan:
        request.validate()
        caps = [c for c in self.graph.store.all_capabilities() if request.platform in c.platforms or "any" in c.platforms]
        if not caps:
            return Plan.new(
                capabilities=[], required_outputs=request.required_outputs, resolved_outputs=[],
                unresolved_outputs=request.required_outputs, score=-1.0, confidence=0.0,
                alternatives=[], bottlenecks=[f"no active capabilities for platform:{request.platform}"],
                explanation={"reason": "no candidates"},
            )

        # Prune to capabilities that can contribute directly or transitively through inputs/outputs.
        relevant_types = set(request.required_outputs)
        changed = True
        while changed:
            changed = False
            for c in caps:
                if relevant_types & set(c.outputs):
                    before = len(relevant_types)
                    relevant_types |= set(c.inputs)
                    changed |= len(relevant_types) != before
        pruned = [c for c in caps if set(c.outputs) & relevant_types]
        pruned = pruned[:24]  # deterministic bound against combinatorial explosion

        if not pruned:
            return Plan.new(
                capabilities=[], required_outputs=request.required_outputs, resolved_outputs=[],
                unresolved_outputs=request.required_outputs, score=-1.0, confidence=0.0,
                alternatives=[], bottlenecks=["no capability can provide the requested output types"],
                explanation={"algorithm": "bounded constraint-aware set-cover search", "candidate_count": 0, "safety_limits_mutated": False},
            )

        candidates: list[Candidate] = []
        max_n = min(request.max_capabilities, len(pruned))
        for n in range(1, max_n + 1):
            for combo in combinations(pruned, n):
                cand = self._candidate_score(list(combo), request)
                candidates.append(cand)
            # Stop growing once we have several full, valid compositions.
            full = [c for c in candidates if not c.unresolved and not c.bottlenecks]
            if len(full) >= 6:
                break

        candidates.sort(key=lambda c: (not bool(c.unresolved), -len(c.bottlenecks), c.score), reverse=True)
        best = candidates[0]
        valid = not best.unresolved and not best.bottlenecks
        confidence = 1.0 / (1.0 + exp(-3.0 * best.score)) if valid else max(0.0, min(0.49, 0.2 + best.score / 5.0))
        alternatives = [c.ids for c in candidates[1:4] if c.ids != best.ids]
        return Plan.new(
            capabilities=best.ids,
            required_outputs=request.required_outputs,
            resolved_outputs=sorted(best.resolved),
            unresolved_outputs=sorted(best.unresolved),
            score=round(best.score, 6),
            confidence=round(confidence, 6),
            alternatives=alternatives,
            bottlenecks=best.bottlenecks,
            explanation={
                "algorithm": "bounded constraint-aware set-cover search",
                "metrics": best.metrics,
                "candidate_count": len(candidates),
                "safety_limits_mutated": False,
            },
        )
