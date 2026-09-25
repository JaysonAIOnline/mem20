from __future__ import annotations
import base64, json, urllib.request
from pathlib import Path

class RemoteAdapter:
    def __init__(self, endpoints: dict[str,str] | None=None):
        self.endpoints={k:v.rstrip('/') for k,v in (endpoints or {}).items() if v}
    def available(self, mode: str) -> bool:
        if mode == 'hybrid': return bool(self.endpoints)
        return mode in self.endpoints
    def execute(self, mode: str, bundle: Path, payload: dict, timeout: int):
        endpoint=self.endpoints.get(mode)
        if not endpoint and mode=='hybrid':
            endpoint=self.endpoints.get('edge') or self.endpoints.get('cloud')
        if not endpoint: raise ConnectionError(f'no {mode} endpoint configured')
        body=json.dumps({'bundle_b64':base64.b64encode(bundle.read_bytes()).decode(),'payload':payload}).encode()
        req=urllib.request.Request(endpoint+'/v1/remote/execute',data=body,headers={'content-type':'application/json'},method='POST')
        with urllib.request.urlopen(req,timeout=timeout+5) as r:
            return json.loads(r.read().decode())
