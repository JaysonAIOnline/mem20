import tempfile, pathlib, unittest
from mem20adaptiveinterfacecomposerz import *
from mem20adaptiveinterfacecomposerz.model import Job,JobState
from mem20adaptiveinterfacecomposerz.scheduler import Telemetry

class Core(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.rt=InterfaceComposerRuntime(RuntimeConfig(db_path=str(pathlib.Path(self.t.name)/"db.sqlite"),max_concurrent=2,max_queue=4,timeout_s=.3))
  self.rt.register_capability(Capability("search","Search Files","search local documents",("search","open"),("files","search"),risk="low"))
  self.rt.register_capability(Capability("delete","Delete Files","delete files permanently",("delete",),("files","danger"),risk="high"))
 def tearDown(self):self.rt.close();self.t.cleanup()
 def test_compose_semantic(self):
  x=self.rt.compose(UserIntent("search files"));self.assertEqual(x["plan"]["selected_capabilities"][0]["capability_id"],"search")
 def test_idempotency(self):
  a=self.rt.compose(UserIntent("search files"),idempotency_key="x");b=self.rt.compose(UserIntent("search files"),idempotency_key="x");self.assertTrue(b["idempotent_replay"]);self.assertEqual(a["job"]["job_id"],b["job"]["job_id"])
 def test_safety_block(self):
  x=self.rt.compose(UserIntent("delete files",max_risk="medium",auto_execute=True));ids=[c["capability_id"] for c in x["plan"]["selected_capabilities"]];self.assertNotIn("delete",ids)
 def test_high_risk_requires_confirmation(self):
  x=self.rt.compose(UserIntent("delete files",max_risk="high",auto_execute=True));self.assertTrue(x["plan"]["requires_confirmation"])
 def test_feedback_cannot_break_safety(self):
  self.rt.add_feedback("capability_weight",{"capability_id":"delete","delta":999});x=self.rt.compose(UserIntent("delete files",max_risk="medium"),idempotency_key="z");self.assertNotIn("delete",[c["capability_id"] for c in x["plan"]["selected_capabilities"]])
 def test_events(self):self.assertTrue(self.rt.subscribe(0))
 def test_rebuild_generation(self):
  x=self.rt.compose(UserIntent("search files"));self.assertGreaterEqual(x["plan"]["generation"],2);self.assertEqual(x["plan"]["job_state"],"succeeded")
 def test_restart_recovery(self):
  j=Job("pending","pending-key",UserIntent("search").to_dict(),JobState.RUNNING.value,"local");self.rt.state.create_job(j);self.assertIn("pending",self.rt.recover_pending())
 def test_local_scheduler_when_offline(self):
  x=self.rt.compose(UserIntent("search files"),idempotency_key="offline",telemetry=Telemetry(cloud_available=False,edge_available=False,network_quality=0));self.assertEqual(x["schedule"]["mode"],"local")
 def test_cancel_persisted_queued_job(self):
  j=Job("cancelme","cancel-key",UserIntent("search").to_dict(),JobState.QUEUED.value,"local");self.rt.state.create_job(j);self.assertTrue(self.rt.cancel("cancelme"));self.assertEqual(self.rt.state.get_job("cancelme").state,"cancelled")
 def test_backpressure_quota(self):
  self.rt.config.max_queue=0
  with self.assertRaises(RuntimeError):self.rt.compose(UserIntent("search files"),idempotency_key="bp")
