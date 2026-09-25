from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from .graph import CapabilityGraph
from .models import Capability, CompositionRequest
from .planner import CompositionPlanner
from .runtime import CapabilityRuntime, RuntimePolicy
from .state import StateStore


def sample_capabilities() -> list[Capability]:
    return [
        Capability(id="text.input", name="Text Input", version="1.0.0", provider="core", outputs=["text/raw"], platforms=["local", "hybrid", "cloud"]),
        Capability(id="text.normalize", name="Normalize Text", version="1.0.0", provider="core", inputs=["text/raw"], outputs=["text/normalized"], platforms=["local", "hybrid", "cloud"], latency_ms=2),
        Capability(id="text.summary", name="Summarize", version="1.0.0", provider="core", inputs=["text/normalized"], outputs=["text/summary"], platforms=["local", "hybrid", "cloud"], latency_ms=3),
    ]


def run_scenarios() -> dict[str, Any]:
    results: dict[str, Any] = {}

    # success
    store = StateStore(":memory:")
    graph = CapabilityGraph(store)
    for c in sample_capabilities(): graph.register(c)
    planner = CompositionPlanner(graph)
    plan = planner.plan(CompositionRequest(required_outputs=["text/summary"], available_inputs=[]))
    runtime = CapabilityRuntime(graph, RuntimePolicy(max_retries=1, timeout_seconds=0.2))
    runtime.register_handler("text.input", lambda ctx: {"text/raw": ctx.get("source", "hello world")})
    runtime.register_handler("text.normalize", lambda ctx: {"text/normalized": ctx["text/raw"].strip().lower()})
    runtime.register_handler("text.summary", lambda ctx: {"text/summary": ctx["text/normalized"][:20]})
    results["success"] = runtime.execute(plan, {"source": "HELLO WORLD"}, "sim-success").to_dict()

    # malformed input
    try:
        Capability.from_dict({"id":"bad","name":"Bad","version":"x","provider":"sim","outputs":["x"]})
        results["malformed"] = "unexpected-pass"
    except Exception as e:
        results["malformed"] = f"blocked:{type(e).__name__}"

    # provider loss / disconnection
    runtime2 = CapabilityRuntime(graph, RuntimePolicy(max_retries=0, timeout_seconds=0.1))
    results["provider_loss"] = runtime2.execute(plan, {"source": "x"}, "sim-provider-loss").to_dict()

    # overload represented by payload sandbox rejection
    try:
        runtime.execute(plan, {"source": "x" * 1_100_000}, "sim-overload")
        results["overload"] = "unexpected-pass"
    except Exception as e:
        results["overload"] = f"blocked:{type(e).__name__}"

    # restart recovery / idempotency using persistent sqlite
    with tempfile.TemporaryDirectory() as d:
        db = str(Path(d) / "sim.sqlite")
        s1 = StateStore(db); g1 = CapabilityGraph(s1)
        for c in sample_capabilities(): g1.register(c)
        p1 = CompositionPlanner(g1).plan(CompositionRequest(required_outputs=["text/summary"]))
        r1 = CapabilityRuntime(g1)
        for cid, fn in {
            "text.input": lambda c: {"text/raw": c.get("source", "x")},
            "text.normalize": lambda c: {"text/normalized": c["text/raw"]},
            "text.summary": lambda c: {"text/summary": c["text/normalized"]},
        }.items(): r1.register_handler(cid, fn)
        first = r1.execute(p1, {"source":"restart"}, "same-key")
        s1.close()
        s2 = StateStore(db); g2 = CapabilityGraph(s2); r2 = CapabilityRuntime(g2)
        recovered = r2.execute(p1, {"source":"changed"}, "same-key")
        results["restart_recovery"] = {"same_job": first.id == recovered.id, "state": recovered.state.value}
        s2.close()

    # degraded network represented as high latency candidate influencing score
    slow = Capability(id="text.summary.slow", name="Slow Summary", version="1.0.0", provider="remote", inputs=["text/normalized"], outputs=["text/summary"], platforms=["cloud"], latency_ms=500)
    graph.register(slow)
    results["degraded_network"] = planner.plan(CompositionRequest(required_outputs=["text/summary"], platform="local")).to_dict()

    return results


if __name__ == "__main__":
    import json
    print(json.dumps(run_scenarios(), indent=2, default=str))
