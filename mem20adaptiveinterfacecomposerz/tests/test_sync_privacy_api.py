import tempfile,pathlib,unittest,threading,urllib.request,json,time
from mem20adaptiveinterfacecomposerz import *
from mem20adaptiveinterfacecomposerz.api import make_server
from mem20adaptiveinterfacecomposerz.scheduler import Telemetry

class More(unittest.TestCase):
 def mk(self,origin="a"):
  d=tempfile.TemporaryDirectory();r=InterfaceComposerRuntime(RuntimeConfig(db_path=str(pathlib.Path(d.name)/"d.sqlite"),origin=origin));return d,r
 def test_conflict_safe_sync(self):
  d1,a=self.mk("a");d2,b=self.mk("b")
  try:
   a.register_capability(Capability("x","A","one",("go",)));b.register_capability(Capability("x","B","two",("go",)))
   out=a.sync_from(b.sync_export());self.assertEqual(out["conflicts"],1);self.assertIn(a.state.get_capability("x")["capability"].title,{"A","B"})
  finally:a.close();b.close();d1.cleanup();d2.cleanup()
 def test_privacy_redaction(self):
  d,r=self.mk()
  try:
   r.register_capability(Capability("x","Search","search",("go",)));r.compose(UserIntent("search",context={"api_key":"sk-abcdefghijkl"}));dump=json.dumps(r.subscribe(0));self.assertNotIn("sk-abcdefghijkl",dump)
  finally:r.close();d.cleanup()
 def test_api_and_remote_peer(self):
  d1,a=self.mk();d2,b=self.mk()
  s=make_server(b);th=threading.Thread(target=s.serve_forever,daemon=True);th.start();base=f"http://127.0.0.1:{s.server_address[1]}"
  try:
   a.register_capability(Capability("x","Search","search",("go",)));a.config.cloud_endpoint=base
   with urllib.request.urlopen(base+"/health") as q:self.assertEqual(q.status,200)
   x=a.compose(UserIntent("search"),idempotency_key="cloud",preferred_mode="cloud",telemetry=Telemetry(local_latency_ms=1000,local_load=1.0,cloud_available=True,network_quality=1.0));self.assertEqual(x["job"]["state"],"succeeded");self.assertEqual(x["job"]["mode"],"cloud")
  finally:s.shutdown();s.server_close();a.close();b.close();d1.cleanup();d2.cleanup()
