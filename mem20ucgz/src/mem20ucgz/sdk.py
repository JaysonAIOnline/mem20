from __future__ import annotations

import json
from urllib.request import Request, urlopen
from urllib.parse import urlencode


class UCGClient:
    """Typed-ish HTTP client boundary; no private cross-runtime imports required."""

    def __init__(self, base_url: str = "http://127.0.0.1:8781") -> None:
        self.base_url = base_url.rstrip("/")

    def _request(self, method: str, path: str, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = Request(self.base_url + path, data=data, method=method, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=20) as r:
            raw = r.read()
            if r.headers.get_content_type() == "application/json":
                return json.loads(raw or b"null")
            return raw.decode()

    def register(self, capability: dict):
        return self._request("POST", "/capabilities", capability)

    def get(self, capability_id: str):
        return self._request("GET", f"/capabilities/{capability_id}")

    def update(self, capability_id: str, capability: dict):
        return self._request("PUT", f"/capabilities/{capability_id}", capability)

    def delete(self, capability_id: str):
        return self._request("DELETE", f"/capabilities/{capability_id}")

    def query(self, **query):
        return self._request("POST", "/query", query)

    def compose(self, **request):
        return self._request("POST", "/compose", request)

    def events(self, since: int = 0):
        return self._request("GET", "/events?" + urlencode({"since": since}))

    def graph(self):
        return self._request("GET", "/graph")
