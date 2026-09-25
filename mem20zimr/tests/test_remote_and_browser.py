import json,tempfile,threading,unittest,urllib.request
from pathlib import Path
from http.server import ThreadingHTTPServer
from mem20zimr.builder import build
from mem20zimr.runtime import MicroappRuntime
from mem20zimr.api import Handler

class RemoteBrowserTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(); self.root=Path(self.t.name)
    def tearDown(self): self.t.cleanup()
    def _server(self,rt):
        cls=type('T',(Handler,),{'runtime':rt}); s=ThreadingHTTPServer(('127.0.0.1',0),cls); threading.Thread(target=s.serve_forever,daemon=True).start(); return s
    def test_cloud_peer_execution(self):
        src=self.root/'py'; src.mkdir(); (src/'main.py').write_text("import json,sys; print(json.dumps({'remote':True,'p':json.loads(sys.stdin.read() or '{}')}))")
        b=build(src,self.root/'p.fsmicro',app_id='p',version='1',kind='python',entrypoint='main.py',signer='t',secret='s',supported_modes=['local','cloud'])
        remote=MicroappRuntime(self.root/'remote.db',{'t':'s'}); srv=self._server(remote)
        local=MicroappRuntime(self.root/'local.db',{'t':'s'},{'cloud':f'http://127.0.0.1:{srv.server_address[1]}'})
        r=local.launch(b,{'x':7},preferred_mode='cloud'); self.assertEqual(r.status,'succeeded'); self.assertTrue(json.loads(r.stdout)['remote'])
        srv.shutdown(); srv.server_close()
    def test_browser_zero_install_serving(self):
        src=self.root/'web'; src.mkdir(); (src/'index.html').write_text('<h1>browser-ok</h1>')
        b=build(src,self.root/'w.fsmicro',app_id='w',version='1',kind='web',entrypoint='index.html',signer='t',secret='s',supported_modes=['browser'])
        rt=MicroappRuntime(self.root/'web.db',{'t':'s'}); r=rt.launch(b,preferred_mode='browser'); self.assertEqual(r.status,'ready')
        srv=self._server(rt)
        launch=json.loads(r.stdout)['launch_path']
        with urllib.request.urlopen(f'http://127.0.0.1:{srv.server_address[1]}{launch}',timeout=3) as resp:
            self.assertIn(b'browser-ok',resp.read())
        srv.shutdown(); srv.server_close()

if __name__=='__main__': unittest.main()
