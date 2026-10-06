import tempfile,pathlib,unittest,threading,time
from mem20adaptiveinterfacecomposerz import *
from mem20adaptiveinterfacecomposerz.scheduler import Telemetry
class R(unittest.TestCase):
 def test_hybrid_failover(self):
  with tempfile.TemporaryDirectory() as d:
   r=InterfaceComposerRuntime(RuntimeConfig(db_path=str(pathlib.Path(d)/"x"),cloud_endpoint="http://127.0.0.1:1",timeout_s=.05,max_retries=0));r.register_capability(Capability("x","Search","search",("go",)))
   x=r.compose(UserIntent("search"),preferred_mode="hybrid",telemetry=Telemetry(local_latency_ms=1000,local_load=1.0,cloud_available=True,network_quality=.8));self.assertEqual(x["job"]["state"],"succeeded");self.assertEqual(x["job"]["mode"],"hybrid");self.assertGreater(r.metrics.counters["failover_total"],0);r.close()
 def test_load(self):
  with tempfile.TemporaryDirectory() as d:
   r=InterfaceComposerRuntime(RuntimeConfig(db_path=str(pathlib.Path(d)/"x"),max_concurrent=2,max_queue=20));r.register_capability(Capability("x","Search","search",("go",)))
   fs=[r.compose_async(UserIntent("search"),idempotency_key=f"k{i}") for i in range(10)];self.assertTrue(all(f.result(timeout=3)["job"]["state"]=="succeeded" for f in fs));r.close()
 def test_malformed(self):
  with tempfile.TemporaryDirectory() as d:
   r=InterfaceComposerRuntime(RuntimeConfig(db_path=str(pathlib.Path(d)/"x")))
   with self.assertRaises(ValueError):r.compose(UserIntent(""))
   r.close()
