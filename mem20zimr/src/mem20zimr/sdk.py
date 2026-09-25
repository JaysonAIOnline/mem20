from __future__ import annotations
import json, urllib.request

class ZeroInstallClient:
    def __init__(self, base_url: str="http://127.0.0.1:8765"):
        self.base=base_url.rstrip("/")
    def _json(self, method: str, path: str, body=None):
        data=None if body is None else json.dumps(body).encode()
        req=urllib.request.Request(self.base+path,data=data,method=method,headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req,timeout=30) as r: return json.loads(r.read().decode())
    def launch(self,bundle: str,payload=None,mode=None,idempotency_key=None):
        return self._json("POST","/v1/launch",{"bundle":bundle,"payload":payload or {},"mode":mode,"idempotency_key":idempotency_key})
    def job(self,job_id: str): return self._json("GET",f"/v1/jobs/{job_id}")
    def cancel(self,job_id: str): return self._json("POST",f"/v1/jobs/{job_id}/cancel",{})
    def jobs(self): return self._json("GET","/v1/jobs")
    def register(self,bundle: str): return self._json("POST","/v1/microapps",{"bundle":bundle})
    def microapps(self): return self._json("GET","/v1/microapps")
    def events(self,job_id: str,after: int=0): return self._json("GET",f"/v1/jobs/{job_id}/events?after={after}")
    def feedback(self,app_id: str,outcome: float,correction: str=""): return self._json("POST","/v1/feedback",{"app_id":app_id,"outcome":outcome,"correction":correction})
