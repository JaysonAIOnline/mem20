import json, tempfile, unittest, zipfile
from pathlib import Path
from mem20zimr.builder import build
from mem20zimr.runtime import MicroappRuntime

class SecurityAndRegistryTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(); root=Path(self.t.name); src=root/'app'; src.mkdir(); (src/'main.py').write_text("print('ok')")
        self.bundle=build(src,root/'a.fsmicro',app_id='reg.app',version='1.0.0',kind='python',entrypoint='main.py',signer='test',secret='secret',supported_modes=['local'])
        self.rt=MicroappRuntime(root/'state.db',{'test':'secret'})
    def tearDown(self): self.t.cleanup()
    def test_registry_crud(self):
        m=self.rt.register(self.bundle); self.assertEqual(m.app_id,'reg.app')
        self.assertEqual(len(self.rt.store.list_microapps()),1)
        self.assertTrue(self.rt.unregister('reg.app','1.0.0'))
        self.assertEqual(self.rt.store.list_microapps(),[])
    def test_tamper_blocked(self):
        with zipfile.ZipFile(self.bundle,'a',zipfile.ZIP_DEFLATED) as z: z.writestr('evil.txt','tamper')
        with self.assertRaises(ValueError): self.rt.inspect(self.bundle)
    def test_global_subscription_event(self):
        self.rt.register(self.bundle); events=self.rt.store.events('',0)
        self.assertTrue(any(e['event_type']=='microapp_registered' for e in events))

if __name__=='__main__': unittest.main()
