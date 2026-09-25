from __future__ import annotations
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json, time, base64, tempfile, os
from .runtime import MicroappRuntime

DASHBOARD='''<!doctype html><meta charset="utf-8"><title>RM-002 Microapp Desktop</title>
<style>body{font:14px system-ui;background:#0c111b;color:#e8eef8;margin:2rem;max-width:1100px}input,button,textarea{font:inherit;padding:.55rem;margin:.2rem}input,textarea{background:#151d2b;color:#fff;border:1px solid #40506a}pre{background:#080c12;padding:1rem;overflow:auto;border:1px solid #253147}.row{display:flex;gap:.5rem;flex-wrap:wrap}.grow{flex:1;min-width:260px}</style>
<h1>RM-002 · Zero-Install Microapp Runtime</h1><div class=row><input id=b class=grow placeholder="/path/to/app.fsmicro"><textarea id=p class=grow>{"name":"FreeStack"}</textarea><button onclick="launch()">Launch</button><button onclick="load()">Refresh</button></div><h2>Live jobs / event inspector</h2><pre id=o>loading...</pre>
<script>let seen={}; async function launch(){let r=await fetch('/v1/launch',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({bundle:b.value,payload:JSON.parse(p.value||'{}')})});o.textContent=JSON.stringify(await r.json(),null,2);load()} async function load(){let j=await(await fetch('/v1/jobs')).json();o.textContent=JSON.stringify(j,null,2)} setInterval(load,1000);load()</script>'''

class Handler(BaseHTTPRequestHandler):
    runtime: MicroappRuntime
    def _send(self,code,obj,ctype="application/json"):
        raw=obj if isinstance(obj,(bytes,bytearray)) else (obj.encode() if isinstance(obj,str) else json.dumps(obj,default=str).encode())
        self.send_response(code); self.send_header("Content-Type",ctype); self.send_header("Content-Length",str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def _body(self):
        n=int(self.headers.get("Content-Length","0")); return json.loads(self.rfile.read(n) or b"{}")
    def log_message(self,*a): pass
    def do_GET(self):
        u=urlparse(self.path); p=u.path; q=parse_qs(u.query)
        if p=="/": return self._send(200,DASHBOARD,"text/html; charset=utf-8")
        if p=="/health": return self._send(200,{"ok":True})
        if p=="/metrics": return self._send(200,self.runtime.metrics.prometheus(),"text/plain; version=0.0.4")
        if p=="/v1/jobs": return self._send(200,self.runtime.store.list_jobs())
        if p=="/v1/microapps": return self._send(200,self.runtime.store.list_microapps())
        if p=="/v1/events": return self._events("",q)
        if p.startswith("/v1/browser/"):
            parts=p.strip('/').split('/',3)
            if len(parts)<4: return self._send(404,{"error":"not_found"})
            try:
                data,ctype=self.runtime.browser_file(parts[2],parts[3]); return self._send(200,data,ctype)
            except Exception as e: return self._send(404,{"error":type(e).__name__,"detail":str(e)})
        parts=p.strip('/').split('/')
        if len(parts)>=3 and parts[:2]==["v1","jobs"]:
            job=parts[2]
            if len(parts)==4 and parts[3]=="events": return self._events(job,q)
            row=self.runtime.store.get_job(job); return self._send(200,row) if row else self._send(404,{"error":"not_found"})
        if len(parts)==4 and parts[:2]==["v1","microapps"]:
            row=self.runtime.store.get_microapp(parts[2],parts[3]); return self._send(200,row) if row else self._send(404,{"error":"not_found"})
        return self._send(404,{"error":"not_found"})
    def _events(self,job,q):
        after=int(q.get("after",["0"])[0]); stream=q.get("stream",["0"])[0]=="1"
        if not stream: return self._send(200,self.runtime.store.events(job,after))
        self.send_response(200); self.send_header("Content-Type","text/event-stream"); self.send_header("Cache-Control","no-cache"); self.end_headers()
        deadline=time.time()+30; seq=after
        while time.time()<deadline:
            events=self.runtime.store.events(job,seq)
            for e in events:
                seq=e["seq"]; self.wfile.write(f"id: {seq}\nevent: {e['event_type']}\ndata: {e['payload_json']}\n\n".encode()); self.wfile.flush()
            row=self.runtime.store.get_job(job) if job else None
            if row and row["status"] in {"succeeded","failed","cancelled","ready"}: break
            time.sleep(.2)
    def do_POST(self):
        p=urlparse(self.path).path
        try: body=self._body()
        except Exception as e: return self._send(400,{"error":"invalid_json","detail":str(e)})
        try:
            if p=="/v1/launch":
                result=self.runtime.launch(body["bundle"],body.get("payload",{}),preferred_mode=body.get("mode"),idempotency_key=body.get("idempotency_key"),async_run=True)
                return self._send(202,{"job_id":result})
            if p=="/v1/remote/execute":
                raw=base64.b64decode(body["bundle_b64"],validate=True)
                with tempfile.NamedTemporaryFile(prefix="rm002-remote-",suffix=".fsmicro",delete=False) as f:
                    f.write(raw); tmp=f.name
                try:
                    r=self.runtime.launch(tmp,body.get("payload",{}),preferred_mode="local",telemetry={"network_up":False})
                    return self._send(200,r.__dict__)
                finally:
                    try: os.unlink(tmp)
                    except OSError: pass
            if p=="/v1/microapps":
                m=self.runtime.register(body["bundle"]); return self._send(201,m.to_dict())
            if p.endswith("/cancel") and p.startswith("/v1/jobs/"):
                job=p.split("/")[3]; self.runtime.cancel(job); return self._send(202,{"job_id":job,"status":"cancelling"})
            if p=="/v1/feedback":
                correction=body.get("correction","")
                if isinstance(correction,dict): correction=json.dumps(correction,sort_keys=True)
                self.runtime.store.add_feedback(body["app_id"],float(body["outcome"]),correction); return self._send(201,{"ok":True})
        except Exception as e: return self._send(400,{"error":type(e).__name__,"detail":str(e)})
        return self._send(404,{"error":"not_found"})
    def do_DELETE(self):
        parts=urlparse(self.path).path.strip('/').split('/')
        if len(parts)==4 and parts[:2]==["v1","microapps"]:
            ok=self.runtime.unregister(parts[2],parts[3]); return self._send(200,{"deleted":ok})
        return self._send(404,{"error":"not_found"})

def serve(runtime: MicroappRuntime, host="127.0.0.1", port=8765):
    cls=type("RuntimeHandler",(Handler,),{"runtime":runtime}); ThreadingHTTPServer((host,port),cls).serve_forever()
