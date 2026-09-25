import json, tempfile, unittest
from pathlib import Path
from mem20zimr.builder import build
from mem20zimr.runtime import MicroappRuntime

class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(); root=Path(self.t.name); src=root/"app"; src.mkdir(); (src/"main.py").write_text("import json,sys; print(json.dumps({'ok':True,'in':json.loads(sys.stdin.read() or '{}')}))")
        self.bundle=build(src,root/"a.fsmicro",app_id="t",version="1",kind="python",entrypoint="main.py",signer="test",secret="secret",supported_modes=["local","hybrid","cloud"])
        self.rt=MicroappRuntime(root/"state.db",{"test":"secret"})
    def tearDown(self): self.t.cleanup()
    def test_signed_launch(self):
        r=self.rt.launch(self.bundle,{"x":1}); self.assertEqual(r.status,"succeeded"); self.assertEqual(json.loads(r.stdout)["in"]["x"],1)
    def test_idempotency(self):
        a=self.rt.launch(self.bundle,{},idempotency_key="same"); b=self.rt.launch(self.bundle,{},idempotency_key="same"); self.assertEqual(a.job_id,b.job_id)
    def test_offline_scheduler(self):
        d=self.rt.scheduler.choose(["local","cloud"],{"network_up":False}); self.assertEqual(d.chosen,"local")
    def test_hybrid_fallback(self):
        r=self.rt.launch(self.bundle,{},preferred_mode="hybrid",telemetry={"network_up":True}); self.assertEqual(r.status,"succeeded")

if __name__=="__main__": unittest.main()
