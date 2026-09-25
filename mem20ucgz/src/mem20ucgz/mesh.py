from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import StrEnum
from typing import Iterable
import time


class ExecutionMode(StrEnum):
    LOCAL = "local"
    HYBRID = "hybrid"
    CLOUD = "cloud"


@dataclass(slots=True)
class Node:
    id: str
    modes: list[str]
    capabilities: list[str]
    latency_ms: float
    throughput: float
    memory_mb: float
    energy_units: float
    network_mb: float
    cost_units: float
    healthy: bool = True
    updated_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.updated_at:
            self.updated_at = time.time()


class MeshScheduler:
    """Measured-constraint execution mode chooser with graceful peer loss."""

    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}

    def advertise(self, node: Node) -> None:
        self.nodes[node.id] = node

    def mark_unavailable(self, node_id: str) -> None:
        if node_id in self.nodes:
            self.nodes[node_id].healthy = False
            self.nodes[node_id].updated_at = time.time()

    def discover(self, capability_ids: Iterable[str]) -> list[Node]:
        required = set(capability_ids)
        return [n for n in self.nodes.values() if n.healthy and required.issubset(set(n.capabilities))]

    def choose(self, capability_ids: Iterable[str]) -> dict[str, object]:
        candidates = self.discover(capability_ids)
        if not candidates:
            return {"mode": None, "node": None, "reason": "no healthy peer satisfies requested capabilities"}
        def score(n: Node) -> float:
            # Lower is better. Throughput is a benefit, but is deliberately normalized
            # so a high-throughput remote node cannot overwhelm latency/network/cost.
            return (n.latency_ms * 0.03) + (n.memory_mb * 0.0005) + (n.energy_units * 0.2) + (n.network_mb * 0.05) + (n.cost_units * 0.5) - (n.throughput * 0.001)
        best = min(candidates, key=score)
        available_modes = [ExecutionMode(m) for m in best.modes if m in {e.value for e in ExecutionMode}]
        mode = ExecutionMode.LOCAL if ExecutionMode.LOCAL in available_modes else available_modes[0]
        return {"mode": mode.value, "node": best.id, "score": round(score(best), 6), "metrics": asdict(best)}
