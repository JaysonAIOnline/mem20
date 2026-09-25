from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Iterable

@dataclass
class Decision:
    chosen: str
    confidence: float
    alternatives: list[dict]
    bottlenecks: list[str]
    explanation: dict

class ModeScheduler:
    """Small deterministic cost-aware scheduler suitable for local/offline-first use."""
    def choose(self, supported: Iterable[str], telemetry: dict | None = None, preferred: str | None = None) -> Decision:
        telemetry = telemetry or {}
        supported = list(supported)
        if preferred and preferred in supported:
            return Decision(preferred, 0.99, [], [], {"reason":"explicit_preference"})
        network_up = bool(telemetry.get("network_up", False))
        latency = float(telemetry.get("network_latency_ms", 9999))
        local_load = float(telemetry.get("local_load", 0.2))
        cost_weight = float(telemetry.get("cost_weight", 1.0))
        mode_biases = telemetry.get("mode_biases", {}) or {}
        scores = {}
        for mode in supported:
            if mode in {"cloud", "edge", "hybrid"} and not network_up:
                scores[mode] = -999
                continue
            score = 1.0
            if mode == "local": score += 2.0 - local_load * 2
            if mode == "browser": score += 1.5
            if mode == "edge": score += 1.4 - latency/1000 - 0.2*cost_weight
            if mode == "hybrid": score += 1.2 - latency/1200 - 0.3*cost_weight
            if mode == "cloud": score += 1.0 - latency/900 - 0.7*cost_weight
            score += float(mode_biases.get(mode,0.0))
            scores[mode] = score
        if not scores:
            raise ValueError("no supported execution modes")
        chosen = max(scores, key=scores.get)
        ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        finite = [s for _,s in ordered if s > -900]
        confidence = 1.0 if len(finite) == 1 else min(0.99, max(0.5, 0.5 + (finite[0]-finite[1])/4))
        bottlenecks = []
        if not network_up: bottlenecks.append("network_unavailable")
        if local_load > 0.8: bottlenecks.append("local_load_high")
        return Decision(chosen, round(confidence,3), [{"mode":m,"score":round(s,3)} for m,s in ordered[1:]], bottlenecks,
                        {"scores":scores,"network_up":network_up,"latency_ms":latency,"local_load":local_load,"cost_weight":cost_weight,"mode_biases":mode_biases})
