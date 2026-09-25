"""Generated from GraphLang lines. Do not edit by hand unless you mean it."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from urllib.parse import parse_qs, urlparse

GRAPH = json.loads('{\n  "nodes": [\n    {\n      "id": "auth_securejwt",\n      "label": "Auth",\n      "method": "jwt",\n      "level": "secure",\n      "requires_https": true,\n      "name": "SecureJWT",\n      "created_at": "2026-09-10T00:07:23.236015+00:00"\n    },\n    {\n      "id": "db_maindb",\n      "label": "Database",\n      "engine": "neo4j",\n      "name": "MainDB",\n      "created_at": "2026-09-10T00:07:23.235826+00:00"\n    },\n    {\n      "id": "inc_footer",\n      "label": "Include",\n      "name": "Footer",\n      "created_at": "2026-09-10T00:07:23.235962+00:00"\n    },\n    {\n      "id": "inc_header",\n      "label": "Include",\n      "name": "Header",\n      "created_at": "2026-09-10T00:07:23.235945+00:00"\n    },\n    {\n      "id": "page_dashboard",\n      "label": "Page",\n      "path": "/dashboard",\n      "name": "Dashboard",\n      "created_at": "2026-09-10T00:07:23.235914+00:00"\n    },\n    {\n      "id": "page_landing",\n      "label": "Page",\n      "path": "/",\n      "name": "Landing",\n      "created_at": "2026-09-10T00:07:23.235890+00:00"\n    },\n    {\n      "id": "page_settings",\n      "label": "Page",\n      "path": "/settings",\n      "name": "Settings",\n      "created_at": "2026-09-10T00:07:23.235928+00:00"\n    }\n  ],\n  "relationships": [\n    {\n      "from": "page_landing",\n      "from_name": "Landing",\n      "type": "CONNECTS_TO",\n      "to": "db_maindb",\n      "to_name": "MainDB",\n      "props": {\n        "secure": true,\n        "auth_method": "jwt",\n        "purpose": "Connect the db to the landing page with a secure auth.",\n        "created_at": "2026-09-10T00:07:23.235997+00:00"\n      }\n    },\n    {\n      "from": "page_landing",\n      "from_name": "Landing",\n      "type": "AUTHENTICATES_WITH",\n      "to": "auth_securejwt",\n      "to_name": "SecureJWT",\n      "props": {\n        "required": true,\n        "roles": [],\n        "created_at": "2026-09-10T00:07:23.236023+00:00"\n      }\n    }\n  ]\n}')

STORE = {}


def pages():
    return [n for n in GRAPH["nodes"] if n.get("label") == "Page"]


def node_by_id(nid):
    for n in GRAPH["nodes"]:
        if n.get("id") == nid:
            return n
    return None


def rels_from(page_id, typ):
    return [r for r in GRAPH["relationships"] if r.get("from") == page_id and r.get("type") == typ]


def open_page(name: str) -> dict:
    page = next((n for n in pages() if n.get("name") == name), None)
    if page is None:
        return {"ok": False, "status": 404, "reason": f"No page {name}"}
    includes = [r.get("to_name") for r in sorted(rels_from(page["id"], "INCLUDES"), key=lambda r: (r.get("props") or {}).get("order", 0))]
    connects = rels_from(page["id"], "CONNECTS_TO")
    auths = rels_from(page["id"], "AUTHENTICATES_WITH")
    if not connects:
        return {
            "ok": False,
            "status": 403,
            "page": name,
            "includes": includes,
            "reason": "No CONNECTS_TO line. Draw a handshake first.",
        }
    conn = connects[0]
    secure = bool((conn.get("props") or {}).get("secure"))
    if secure and not auths:
        return {
            "ok": False,
            "status": 401,
            "page": name,
            "includes": includes,
            "reason": "Secure connection requires AUTHENTICATES_WITH.",
        }
    return {
        "ok": True,
        "status": 200,
        "page": name,
        "path": page.get("path") or ("/" if name.lower() in {"landing", "home"} else f"/{name.lower()}"),
        "includes": includes,
        "database": conn.get("to_name"),
        "auth": auths[0].get("to_name") if auths else None,
        "secure": secure,
    }


def render(name: str) -> dict:
    opened = open_page(name)
    header = " | ".join(opened.get("includes") or [])
    body = f"{opened.get('page')} talking to {opened.get('database') or 'nowhere'}"
    if opened.get("auth"):
        body += f" via {opened['auth']}"
    opened["html"] = f"<header>{header}</header><main>{body}</main><footer>{header}</footer>"
    return opened


ROUTES = json.loads('{\n  "/": "Landing",\n  "/dashboard": "Dashboard",\n  "/settings": "Settings"\n}')


class Handler(BaseHTTPRequestHandler):
    def _send(self, payload: dict) -> None:
        body = json.dumps(payload, indent=2).encode()
        self.send_response(payload.get("status", 200 if payload.get("ok") else 400))
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path == "/__graph":
            self._send({"ok": True, "status": 200, "graph": GRAPH})
            return
        page = ROUTES.get(path)
        if not page:
            self._send({"ok": False, "status": 404, "reason": f"No route {path}"})
            return
        result = render(page)
        qs = parse_qs(parsed.query)
        if "key" in qs:
            if not result.get("ok"):
                self._send(result)
                return
            result["value"] = STORE.get(result["database"], {}).get(qs["key"][0])
        self._send(result)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        page = ROUTES.get(path)
        if not page:
            self._send({"ok": False, "status": 404, "reason": f"No route {path}"})
            return
        opened = open_page(page)
        if not opened.get("ok"):
            self._send(opened)
            return
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        db = opened["database"]
        STORE.setdefault(db, {}).update(payload)
        opened["written"] = payload
        self._send(opened)

    def log_message(self, fmt, *args):
        return


def main(host="127.0.0.1", port=8787):
    print("Generated GraphLang app")
    for path, page in ROUTES.items():
        print(f"  GET  {path}  -> {page}")
    print(f"http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
