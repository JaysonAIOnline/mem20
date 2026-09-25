"""Egress firewall (iron-proxy credential injection).

Agents must never leak a credential to the wrong destination. Every outbound
call is governed by two rules enforced by :class:`EgressPolicy`:

  1. fail-closed host policy — the target host must be allow-listed
     (config ``egress.allow``, else ``$MEM20AGENTZ_EGRESS_ALLOW``, else
     deny-all), not deny-listed, and the URL must not smuggle ``userinfo@``;
  2. credential binding — a secret is injected into a request ONLY when a
     binding matches the target host::

        egress.bindings:
          api.example.com:
            api_key: "Authorization: Bearer {key}"

A missing required credential or a policy violation raises :class:`EgressBlocked`
(before any socket I/O, for the 403 proxy path we still answer 403).

:class:`EgressProxy` is a loopback forward proxy that applies the exact same
policy + injection on real HTTP traffic (absolute-URI requests), so an agent's
``httpx`` client can be pointed at ``http://127.0.0.1:<port>`` and every egress
goes through the iron gate.
"""

from __future__ import annotations

import http.client
import http.server
import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

_HEADER_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


class EgressBlocked(ConnectionError):
    pass


def _host_matches(rule: str, host: str) -> bool:
    rule = rule.strip().lower().lstrip(".")
    host = host.strip().lower().rstrip(".")
    if not rule:
        return False
    if rule.startswith("*."):
        return host.endswith("." + rule[2:]) or host == rule[2:]
    return host == rule or host.endswith("." + rule)


class EgressPolicy:
    def __init__(self, allow: Optional[list] = None,
                 deny: Optional[list] = None,
                 bindings: Optional[dict] = None) -> None:
        self.allow = [r for r in (allow or []) if r]
        self.deny = [r for r in (deny or []) if r]
        self.bindings = {str(k): dict(v)
                         for k, v in (bindings or {}).items() if isinstance(v, dict)}

    # ----------------------------------------------------------- policy
    def allowed(self, url: str) -> bool:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        if parsed.username or parsed.password:
            return False
        host = (parsed.hostname or "").lower()
        if any(_host_matches(r, host) for r in self.deny):
            return False
        if not self.allow:
            return False  # fail-closed: no allowlist configured
        return any(_host_matches(r, host) for r in self.allow)

    def check(self, url: str) -> dict:
        if urllib.parse.urlparse(url).scheme not in ("http", "https"):
            return {"allow": False, "reason": "scheme not http(s)"}
        parsed = urllib.parse.urlparse(url)
        if parsed.username or parsed.password:
            return {"allow": False,
                    "reason": "credential smuggling in URL userinfo"}
        host = (parsed.hostname or "").lower()
        for rule in self.deny:
            if _host_matches(rule, host):
                return {"allow": False, "reason": f"host deny-listed ({rule})"}
        if not self.allow:
            return {"allow": False,
                    "reason": "fail-closed: egress.allow is empty (set config "
                              "egress.allow or MEM20AGENTZ_EGRESS_ALLOW)"}
        for rule in self.allow:
            if _host_matches(rule, host):
                return {"allow": True, "reason": f"host allow-listed ({rule})"}
        return {"allow": False,
                "reason": f"host '{host}' not in egress allowlist"}

    # --------------------------------------------------------- injection
    def bindings_for(self, url: str) -> list[tuple[str, str]]:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
        out = []
        for rule, creds in self.bindings.items():
            if _host_matches(rule, host):
                for key, spec in creds.items():
                    out.append((str(key), str(spec)))
        return out

    def inject(self, url: str, headers, get_secret) -> dict:
        """Apply bindings; ``get_secret`` is any ``key -> str|None`` callable."""
        if not self.allowed(url):
            raise EgressBlocked(self.check(url)["reason"])
        result = dict(headers or {})
        for key, spec in self.bindings_for(url):
            value = get_secret(key)
            if value is None:
                raise EgressBlocked(
                    f"binding requires credential '{key}' for '{url}' "
                    f"but it is missing")
            name, _, template = spec.partition(":")
            name = name.strip()
            if not _HEADER_NAME.match(name):
                raise EgressBlocked(f"invalid header name in binding: {name!r}")
            rendered = template.format(key=value).strip()
            result[name] = rendered
        return result


# ===================================================================== proxy
def default_policy(config: Optional[dict] = None,
                   env: Optional[dict] = None) -> EgressPolicy:
    """Build the fail-closed policy from config ``egress`` + env override."""
    env = env if env is not None else os.environ
    cfg = (config or {}).get("egress") or {}
    allow = list(cfg.get("allow") or [])
    if env.get("MEM20AGENTZ_EGRESS_ALLOW"):
        allow += [h.strip() for h in
                  env["MEM20AGENTZ_EGRESS_ALLOW"].split(",") if h.strip()]
    return EgressPolicy(allow=allow,
                        deny=list(cfg.get("deny") or []),
                        bindings=dict(cfg.get("bindings") or {}))


class _ProxyHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _forward(self, method: str) -> None:
        server: EgressProxy = self.server.server_side  # type: ignore[attr-defined]
        url = self.path
        if not urllib.parse.urlparse(url).scheme:
            url = f"http://{self.path}"
        verdict = server.policy.check(url)
        if not verdict["allow"]:
            body = json.dumps({"proxy": "egress", "allow": False,
                              "reason": verdict["reason"]}).encode()
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        try:
            headers = self._read_headers()
            injected = server.policy.inject(url, headers, server.get_secret)
            request = urllib.request.Request(url, method=method,
                                             headers=injected)
            body = b""
            if method in ("POST", "PUT", "PATCH"):
                length = int(self.headers.get("Content-Length") or 0)
                if length:
                    body = self.rfile.read(length)
            with urllib.request.urlopen(request, data=body or None,
                                        timeout=server.timeout) as resp:
                payload = resp.read()
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() in ("content-length", "transfer-encoding",
                                     "connection"):
                        continue
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
        except EgressBlocked as exc:
            body = json.dumps({"proxy": "egress", "allow": False,
                               "reason": str(exc)}).encode()
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            self.send_response(exc.code)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except Exception as exc:  # noqa: BLE001
            body = json.dumps({"proxy": "egress", "error": str(exc)}).encode()
            if not self.wfile.closed:
                try:
                    self.send_response(502)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

    def _read_headers(self) -> dict:
        out = {}
        for key, value in self.headers.items():
            if key.lower() not in ("host", "connection", "proxy-connection",
                                   "content-length", "accept-encoding"):
                out[key] = value
        return out

    def do_GET(self):  # noqa: N802
        self._forward("GET")

    def do_POST(self):  # noqa: N802
        self._forward("POST")

    def do_PUT(self):  # noqa: N802
        self._forward("PUT")

    def do_PATCH(self):  # noqa: N802
        self._forward("PATCH")

    def log_message(self, *args):  # silence default logging
        pass


class EgressProxy:
    """Loopback forward proxy enforcing exclusive credential injection."""

    def __init__(self, policy: EgressPolicy, get_secret,
                 timeout: float = 30.0) -> None:
        self.policy = policy
        self.get_secret = get_secret
        self.timeout = timeout
        self._httpd: Optional[http.server.ThreadingHTTPServer] = None

    def serve(self, port: int = 0, host: str = "127.0.0.1") -> str:
        self._httpd = http.server.ThreadingHTTPServer((host, port), _ProxyHandler)
        self._httpd.server_side = self  # type: ignore[attr-defined]
        actual = self._httpd.server_address[1]
        threading.Thread(target=self._httpd.serve_forever,
                         daemon=True).start()
        return f"http://{host}:{actual}"

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    def fetch(self, method: str, url: str,
              headers: Optional[dict] = None) -> dict:
        """Policy + injection + real request in one call (no proxy server)."""
        verdict = self.policy.check(url)
        if not verdict["allow"]:
            raise EgressBlocked(verdict["reason"])
        injected = self.policy.inject(url, headers or {}, self.get_secret)
        request = urllib.request.Request(url, method=method, headers=injected)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                return {"status": resp.status,
                        "headers": dict(resp.headers.items()),
                        "body": resp.read().decode("utf-8", "replace")}
        except urllib.error.HTTPError as exc:
            return {"status": exc.code,
                    "headers": dict(exc.headers.items()),
                    "body": exc.read().decode("utf-8", "replace")}