from __future__ import annotations
import json, urllib.request
from typing import Any

class InterfaceComposerClient:
    def __init__(self,base_url:str):self.base_url=base_url.rstrip('/')
    def _request(self,path:str,method:str="GET",payload:dict[str,Any]|None=None):
        data=json.dumps(payload).encode() if payload is not None else None
        req=urllib.request.Request(self.base_url+path,data=data,headers={"Content-Type":"application/json"},method=method)
        with urllib.request.urlopen(req,timeout=10) as r:
            raw=r.read();return json.loads(raw) if raw else None
    def capabilities(self):return self._request("/v1/capabilities")
    def register(self,capability:dict[str,Any]):return self._request("/v1/capabilities","POST",capability)
    def compose(self,intent:dict[str,Any],idempotency_key:str|None=None,preferred_mode:str|None=None):return self._request("/v1/compose","POST",{"intent":intent,"idempotency_key":idempotency_key,"preferred_mode":preferred_mode})
    def jobs(self):return self._request("/v1/jobs")
    def events(self,after:int=0):return self._request(f"/v1/events?after={after}")
    def feedback(self,kind:str,payload:dict[str,Any]):return self._request("/v1/feedback","POST",{"kind":kind,"payload":payload})
    def cancel(self,job_id:str):return self._request(f"/v1/jobs/{job_id}/cancel","POST",{})
