from __future__ import annotations
import json, urllib.request
from typing import Any

class RemoteError(RuntimeError): pass

class RemotePeer:
    def __init__(self,base_url:str,timeout:float=2.0):self.base_url=base_url.rstrip('/');self.timeout=timeout
    def compose(self,payload:dict[str,Any])->dict[str,Any]:
        req=urllib.request.Request(self.base_url+"/v1/remote/compose",data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"},method="POST")
        try:
            with urllib.request.urlopen(req,timeout=self.timeout) as r:return json.loads(r.read())
        except Exception as e:raise RemoteError(str(e)) from e
    def health(self)->bool:
        try:
            with urllib.request.urlopen(self.base_url+"/health",timeout=self.timeout) as r:return r.status==200
        except Exception:return False
