from mem20ucgz.graph import CapabilityGraph
from mem20ucgz.models import Capability, CompositionRequest
from mem20ucgz.planner import CompositionPlanner
from mem20ucgz.runtime import CapabilityRuntime
from mem20ucgz.state import StateStore

store = StateStore(":memory:")
graph = CapabilityGraph(store)
for cap in [
    Capability(id="demo.source", name="Source", version="1.0.0", provider="demo", outputs=["text/raw"]),
    Capability(id="demo.upper", name="Uppercase", version="1.0.0", provider="demo", inputs=["text/raw"], outputs=["text/upper"]),
]:
    graph.register(cap)
plan = CompositionPlanner(graph).plan(CompositionRequest(required_outputs=["text/upper"]))
print("assembled plan:", plan.to_dict())
runtime = CapabilityRuntime(graph)
runtime.register_handler("demo.source", lambda c: {"text/raw": c.get("source", "hello")})
runtime.register_handler("demo.upper", lambda c: {"text/upper": c["text/raw"].upper()})
print("job:", runtime.execute(plan, {"source":"FreeStack"}, "demo-run").to_dict())
