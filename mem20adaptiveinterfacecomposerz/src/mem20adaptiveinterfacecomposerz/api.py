from __future__ import annotations
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json, time
from typing import Any
from .runtime import InterfaceComposerRuntime
from .model import Capability, UserIntent

DASHBOARD='''<!doctype html><html><head><meta charset="utf-8"><title>RM-003 Adaptive Interface Composer</title><style>body{font:15px system-ui;margin:2rem;max-width:1100px}input,button,textarea{font:inherit;padding:.65rem;margin:.25rem}textarea{width:90%;height:80px}.card{border:1px solid #9994;border-radius:12px;padding:1rem;margin:1rem 0}pre{white-space:pre-wrap}.palette{display:flex;gap:.5rem}.cmd{border:1px solid #9996;border-radius:8px;padding:.45rem}</style></head><body><h1>Adaptive Interface Composer</h1><div class="card"><b>Command Palette</b><div class="palette"><input id="task" size="70" placeholder="Describe the job…"><button onclick="compose()">Compose Interface</button></div></div><div id="ui" class="card">The interface will rebuild around the current job.</div><div class="card"><b>Event Stream Inspector</b><pre id="events"></pre></div><script>let after=0;async function compose(){let task=document.getElementById('task').value;let r=await fetch('/v1/compose',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({intent:{task}})});let x=await r.json();render(x.plan)}function render(p){let h='<h2>'+p.task+'</h2><p>state: '+p.job_state+' · generation '+p.generation+' · confidence '+p.confidence+'</p>';for(let s of p.sections){h+='<h3>'+s.title+'</h3>';if(s.controls)for(let c of s.controls)h+='<button class="cmd">'+c.label+'</button>';}document.getElementById('ui').innerHTML=h}async function poll(){let r=await fetch('/v1/events?after='+after);let x=await r.json();for(let e of x.events){after=e.seq;document.getElementById('events').textContent+=JSON.stringify(e)+'\\n'}setTimeout(poll,500)}poll()</script></body></html>'''

class Handler(BaseHTTPRequestHandler):
    runtime: InterfaceComposerRuntime
    def log_message(self,*args):pass
    def _json(self,status:int,obj:Any):
        data=json.dumps(obj).encode();self.send_response(status);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(data)));self.end_headers();self.wfile.write(data)
    def _body(self):
        n=int(self.headers.get("Content-Length","0"));
        if n>1024*1024:raise ValueError("payload too large")
        return json.loads(self.rfile.read(n) or b"{}")
    def do_GET(self):
        u=urlparse(self.path)
        if u.path=="/":
            d=DASHBOARD.encode();self.send_response(200);self.send_header("Content-Type","text/html;charset=utf-8");self.send_header("Content-Length",str(len(d)));self.end_headers();self.wfile.write(d);return
        if u.path=="/health":return self._json(200,{"ok":True,"capability":"RM-003 Adaptive Interface Composer","discovery":self.runtime.discovery()})
        if u.path=="/metrics":
            d=self.runtime.metrics.prometheus().encode();self.send_response(200);self.send_header("Content-Type","text/plain");self.end_headers();self.wfile.write(d);return
        if u.path=="/v1/capabilities":return self._json(200,{"capabilities":self.runtime.query_capabilities()})
        if u.path=="/v1/jobs":return self._json(200,{"jobs":[j.to_dict() for j in self.runtime.state.list_jobs()]})
        if u.path=="/v1/events":
            after=int(parse_qs(u.query).get("after",["0"])[0]);return self._json(200,{"events":self.runtime.subscribe(after)})
        if u.path=="/v1/events/stream":
            after=int(parse_qs(u.query).get("after",["0"])[0]);self.send_response(200);self.send_header("Content-Type","text/event-stream");self.send_header("Cache-Control","no-cache");self.end_headers()
            deadline=time.time()+2
            while time.time()<deadline:
                events=self.runtime.subscribe(after)
                for e in events:
                    after=e["seq"];self.wfile.write(("data: "+json.dumps(e)+"\n\n").encode());self.wfile.flush()
                time.sleep(.1)
            return
        if u.path.startswith("/v1/plans/"):
            p=self.runtime.state.get_plan(u.path.rsplit('/',1)[1]);return self._json(200,p.to_dict()) if p else self._json(404,{"error":"not found"})
        return self._json(404,{"error":"not found"})
    def do_POST(self):
        try:
            u=urlparse(self.path);b=self._body()
            if u.path=="/v1/capabilities":return self._json(201,{"revision":self.runtime.register_capability(Capability.from_dict(b))})
            if u.path=="/v1/compose":
                out=self.runtime.compose(UserIntent.from_dict(b["intent"]),idempotency_key=b.get("idempotency_key"),preferred_mode=b.get("preferred_mode"));return self._json(200,out)
            if u.path=="/v1/feedback":self.runtime.add_feedback(str(b["kind"]),dict(b.get("payload",{})));return self._json(200,{"ok":True})
            if u.path.startswith("/v1/jobs/") and u.path.endswith("/cancel"):
                jid=u.path.split('/')[3];return self._json(200,{"cancelled":self.runtime.cancel(jid)})
            if u.path=="/v1/remote/compose":
                p=self.runtime.remote_compose(UserIntent.from_dict(b["intent"]),[Capability.from_dict(x) for x in b.get("capabilities",[])]);return self._json(200,{"plan":p.to_dict()})
            if u.path=="/v1/sync":return self._json(200,self.runtime.sync_from(list(b.get("capabilities",[]))))
            return self._json(404,{"error":"not found"})
        except Exception as e:return self._json(400,{"error":str(e)})

def make_server(runtime:InterfaceComposerRuntime,host="127.0.0.1",port=0):
    cls=type("BoundHandler",(Handler,),{"runtime":runtime});return ThreadingHTTPServer((host,port),cls)
