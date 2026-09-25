"""ucg_client — HTTP boundary to the Universal Capability Graph (RM-001).

Typed-ish client for the live mem20ucgz service. No private cross-runtime
imports: this is an independent HTTP client that speaks the same JSON contract
as /health, /graph, /capabilities, /query and /compose. The base URL comes
from MEM20_UCG_URL and defaults to the estate's UCG endpoint.
"""
from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

UCG_BASE = os.environ.get("MEM20_UCG_URL", "http://127.0.0.1:8781").rstrip("/")


class UCGUnavailable(RuntimeError):
    pass


class UCGClient:
    """Minimal JSON/HTTP client for the mem20ucgz service."""

    def __init__(self, base_url: str = UCG_BASE, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, method: str, path: str, body: Any = None) -> Any:
        data = None if body is None else json.dumps(body).encode()
        req = Request(self.base_url + path, data=data, method=method,
                      headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=self.timeout) as r:
                raw = r.read()
                if r.headers.get_content_type() == "application/json":
                    return json.loads(raw or b"null")
                return raw.decode()
        except HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode()
            except Exception:
                pass
            raise UCGUnavailable(f"UCG error {e.code} from {self.base_url}{path}: {detail}") from e
        except URLError as e:
            raise UCGUnavailable(f"UCG unreachable at {self.base_url}: {e.reason}") from e
        except TimeoutError as e:
            raise UCGUnavailable(f"UCG timeout at {self.base_url}: {e}") from e

    # --- capability graph (RM-001) --------------------------------------
    def register(self, capability: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/capabilities", capability)

    def get(self, capability_id: str) -> dict[str, Any]:
        return self._request("GET", f"/capabilities/{capability_id}")

    def update(self, capability_id: str, capability: dict[str, Any]) -> dict[str, Any]:
        return self._request("PUT", f"/capabilities/{capability_id}", capability)

    def delete(self, capability_id: str) -> bool:
        return self._request("DELETE", f"/capabilities/{capability_id}")

    def query(self, text: str = "", **extra: Any) -> list[dict[str, Any]]:
        body: dict[str, Any] = {"text": text}
        body.update(extra)
        return self._request("POST", "/query", body)

    def compose(self, **request: Any) -> Any:
        return self._request("POST", "/compose", request)

    def events(self, since: int = 0) -> list[dict[str, Any]]:
        return self._request("GET", "/events?" + urlencode({"since": since}))

    def graph(self) -> dict[str, Any]:
        return self._request("GET", "/graph")

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")


def default_client() -> UCGClient:
    return UCGClient()


def ucg_ok(client: UCGClient | None = None) -> bool:
    try:
        (client or default_client()).health()
        return True
    except Exception:
        return False