import tempfile
import unittest
from pathlib import Path

from mem20ucgz.graph import CapabilityGraph
from mem20ucgz.mesh import MeshScheduler, Node
from mem20ucgz.models import Capability, CapabilityQuery, CompositionRequest, JobState
from mem20ucgz.planner import CompositionPlanner
from mem20ucgz.runtime import CapabilityRuntime, RuntimePolicy
from mem20ucgz.signing import sign_manifest
from mem20ucgz.state import StateStore


def caps():
    return [
        Capability(id="a", name="A", version="1.0.0", provider="p", outputs=["x"], platforms=["local", "cloud"]),
        Capability(id="b", name="B", version="1.0.0", provider="p", inputs=["x"], outputs=["y"], platforms=["local", "cloud"]),
        Capability(id="c", name="C", version="1.0.0", provider="p", inputs=["y"], outputs=["z"], platforms=["local", "cloud"]),
    ]


class TestUCG(unittest.TestCase):
    def setUp(self):
        self.store = StateStore(":memory:")
        self.graph = CapabilityGraph(self.store)
        for c in caps(): self.graph.register(c)

    def test_graph_edges(self):
        relations = {(e["src"],e["dst"],e["relation"]) for e in self.store.edges()}
        self.assertIn(("a","b","feeds"), relations)
        self.assertIn(("b","c","feeds"), relations)

    def test_query(self):
        self.assertEqual([c.id for c in self.graph.query(CapabilityQuery(provides=["y"]))], ["b"])

    def test_crud(self):
        a = self.graph.get("a"); a.tags.append("updated"); self.graph.update(a)
        self.assertIn("updated", self.graph.get("a").tags)
        self.assertTrue(self.graph.delete("a")); self.assertIsNone(self.graph.get("a"))

    def test_composition(self):
        p = CompositionPlanner(self.graph).plan(CompositionRequest(required_outputs=["z"]))
        self.assertFalse(p.unresolved_outputs); self.assertFalse(p.bottlenecks)
        self.assertEqual(set(p.capabilities), {"a","b","c"})

    def test_idempotency(self):
        p = CompositionPlanner(self.graph).plan(CompositionRequest(required_outputs=["z"]))
        r = CapabilityRuntime(self.graph)
        r.register_handler("a", lambda c:{"x":1}); r.register_handler("b", lambda c:{"y":c["x"]+1}); r.register_handler("c", lambda c:{"z":c["y"]+1})
        j1 = r.execute(p, {}, "key"); j2 = r.execute(p, {"ignored":True}, "key")
        self.assertEqual(j1.id, j2.id); self.assertEqual(j1.state, JobState.SUCCEEDED)

    def test_bounded_retry(self):
        p = CompositionPlanner(self.graph).plan(CompositionRequest(required_outputs=["z"]))
        r = CapabilityRuntime(self.graph, RuntimePolicy(max_retries=1, timeout_seconds=0.2))
        count = {"a":0}
        def flaky(c):
            count["a"] += 1
            if count["a"] == 1: raise RuntimeError("first")
            return {"x":1}
        r.register_handler("a", flaky); r.register_handler("b", lambda c:{"y":2}); r.register_handler("c", lambda c:{"z":3})
        j = r.execute(p, {}, "retry"); self.assertEqual(j.state, JobState.SUCCEEDED); self.assertGreaterEqual(j.attempts, 4)

    def test_persistent_restart(self):
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d)/"x.sqlite")
            s = StateStore(path); g = CapabilityGraph(s); g.register(caps()[0]); s.close()
            s2 = StateStore(path); self.assertEqual(s2.get_capability("a").name, "A"); s2.close()

    def test_signature_policy(self):
        key = "secret"
        s = StateStore(":memory:"); g = CapabilityGraph(s, signing_key=key, enforce_signatures=True)
        c = Capability(id="signed", name="Signed", version="1.0.0", provider="p", outputs=["o"])
        d = c.to_dict(); d["signed"] = True; d["signature"] = sign_manifest(d, key)
        g.register(Capability.from_dict(d)); self.assertIsNotNone(g.get("signed"))

    def test_mesh_scheduler_and_failover(self):
        m = MeshScheduler()
        m.advertise(Node("local", ["local"], ["a"], 2, 100, 100, 1, 0, 0))
        m.advertise(Node("cloud", ["cloud"], ["a"], 20, 1000, 100, 2, 1, 1))
        self.assertEqual(m.choose(["a"])["node"], "local")
        m.mark_unavailable("local")
        self.assertEqual(m.choose(["a"])["node"], "cloud")

    def test_event_history(self):
        events = self.store.events_since(0)
        self.assertGreaterEqual(len(events), 5)

    def test_unresolved_plan_explained(self):
        p = CompositionPlanner(self.graph).plan(CompositionRequest(required_outputs=["not-here"]))
        self.assertIn("not-here", p.unresolved_outputs)
        self.assertLess(p.confidence, 0.5)


if __name__ == "__main__": unittest.main()
