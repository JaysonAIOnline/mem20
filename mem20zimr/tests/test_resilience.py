import json,tempfile,time,unittest,zipfile
from pathlib import Path
from mem20zimr.builder import build
from mem20zimr.runtime import MicroappRuntime

class ResilienceTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(); self.root=Path(self.t.name)
    def tearDown(self): self.t.cleanup()
    def bundle(self,code,modes=['local'],app='r'):
        src=self.root/(app+'src'); src.mkdir(exist_ok=True); (src/'main.py').write_text(code)
        return build(src,self.root/(app+'.fsmicro'),app_id=app,version='1',kind='python',entrypoint='main.py',signer='t',secret='s',supported_modes=modes)
    def test_privacy_environment_isolation(self):
        import os; os.environ['SHOULD_NOT_LEAK']='secret'
        b=self.bundle("import os; print(os.environ.get('SHOULD_NOT_LEAK','blocked'))",app='privacy')
        r=MicroappRuntime(self.root/'p.db',{'t':'s'}).launch(b); self.assertEqual(r.stdout.strip(),'blocked')
    def test_misuse_entrypoint_escape_blocked(self):
        src=self.root/'badsrc'; src.mkdir(); (src/'main.py').write_text('print(1)')
        b=build(src,self.root/'bad.fsmicro',app_id='bad',version='1',kind='python',entrypoint='../main.py',signer='t',secret='s',supported_modes=['local'])
        r=MicroappRuntime(self.root/'bad.db',{'t':'s'}).launch(b); self.assertEqual(r.status,'failed'); self.assertIn('invalid entrypoint',r.stderr)
    def test_degraded_network_hybrid_falls_back(self):
        b=self.bundle("print('fallback-ok')",modes=['hybrid','local'],app='hyb')
        rt=MicroappRuntime(self.root/'h.db',{'t':'s'},{'cloud':'http://127.0.0.1:1'})
        r=rt.launch(b,preferred_mode='hybrid',telemetry={'network_up':True}); self.assertEqual(r.status,'succeeded'); self.assertIn('fallback-ok',r.stdout)
    def test_feedback_changes_tunable_mode_score(self):
        b=self.bundle("print('ok')",modes=['local','cloud'],app='fb'); rt=MicroappRuntime(self.root/'f.db',{'t':'s'})
        rt.store.add_feedback('fb',1.0,json.dumps({'prefer_mode':'cloud','weight':1.0}))
        d=rt.scheduler.choose(['local','cloud'],{'network_up':True,'network_latency_ms':20,'local_load':.7,'cost_weight':0,'mode_biases':rt.store.mode_biases('fb')})
        self.assertIn('cloud',d.explanation['mode_biases'])
    def test_bounded_load(self):
        b=self.bundle("import json,sys,time; time.sleep(.05); print('ok')",app='load'); rt=MicroappRuntime(self.root/'l.db',{'t':'s'},max_concurrent=2)
        ids=[rt.launch(b,{},idempotency_key=f'k{i}',async_run=True) for i in range(8)]
        deadline=time.time()+15
        while time.time()<deadline:
            rows=[rt.store.get_job(j) for j in ids]
            if all(r and r['status'] in {'succeeded','failed','cancelled'} for r in rows): break
            time.sleep(.05)
        self.assertTrue(all(rt.store.get_job(j)['status']=='succeeded' for j in ids))
    def test_restart_recovery_replays_persisted_job(self):
        b=self.bundle("print('recovered')",app='recover'); rt=MicroappRuntime(self.root/'rr.db',{'t':'s'})
        m=rt.inspect(b); rt.store.register_microapp(m.app_id,m.version,str(b),m.to_dict())
        rt.store.create_job({'job_id':'recover-job','app_id':m.app_id,'version':m.version,'status':'queued','mode':'local','attempt':0,'idempotency_key':'recover-key','request':{}})
        resumed=rt.resume_incomplete(lambda a,v: b); self.assertIn('recover-job',resumed)
        deadline=time.time()+5
        while time.time()<deadline and rt.store.get_job('recover-job')['status']!='succeeded': time.sleep(.05)
        self.assertEqual(rt.store.get_job('recover-job')['status'],'succeeded')

if __name__=='__main__': unittest.main()
