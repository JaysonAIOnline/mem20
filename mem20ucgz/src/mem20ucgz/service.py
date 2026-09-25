from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import Any

from .graph import CapabilityGraph
from .mesh import MeshScheduler
from .metrics import Metrics
from .models import Capability, CapabilityQuery, CompositionRequest
from .planner import CompositionPlanner
from .runtime import CapabilityRuntime
from .state import StateStore


class UCGService:
    def __init__(self, db_path: str = ":memory:") -> None:
        key = os.environ.get("FREESTACK_UCG_SIGNING_KEY")
        enforce = os.environ.get("FREESTACK_UCG_ENFORCE_SIGNATURES", "0") == "1"
        self.store = StateStore(db_path)
        self.graph = CapabilityGraph(self.store, signing_key=key, enforce_signatures=enforce)
        self.planner = CompositionPlanner(self.graph)
        self.runtime = CapabilityRuntime(self.graph)
        self.mesh = MeshScheduler()
        self.metrics = Metrics()

    def register(self, body: dict[str, Any]) -> dict[str, Any]:
        cap = self.graph.register(Capability.from_dict(body))
        self.metrics.inc("capability_upserts_total")
        self.metrics.gauge("capabilities", len(self.store.all_capabilities()))
        return cap.to_dict()

    def query(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        q = CapabilityQuery(**body)
        result = [c.to_dict() for c in self.graph.query(q)]
        self.metrics.inc("queries_total")
        return result

    def compose(self, body: dict[str, Any]) -> dict[str, Any]:
        plan = self.planner.plan(CompositionRequest(**body))
        self.metrics.inc("plans_total")
        if not plan.unresolved_outputs and not plan.bottlenecks:
            self.metrics.inc("plans_resolved_total")
        return plan.to_dict()
