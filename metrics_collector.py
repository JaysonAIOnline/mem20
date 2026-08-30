#!/usr/bin/env python3
"""mem20 install-metrics collector (stdlib only, no external deps).

Deploy this once on a host you control. Point every mem20 install at it by
setting, on each installed machine:

    export MEM20_INSTALL_WEBHOOK="http://<collector-host>:<port>/ingest"

It receives install pings (POST /ingest), stores them, and serves
aggregated metrics + a simple dashboard.

Endpoints:
  POST /ingest              record one event (body = install_tracker JSON)
  GET  /metrics             aggregated metrics (JSON)
  GET  /recent?n=20         recent raw events (JSON)
  GET  /export              download the raw installs.jsonl
  GET  /                    HTML dashboard

Optional auth: set MEM20_COLLECTOR_TOKEN; then requests must pass
?token=... or header X-Token.
"""
import os
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from collections import Counter
from datetime import datetime, timezone, timedelta

STORE = os.environ.get("MEM20_COLLECTOR_STORE") or os.path.expanduser(
    "~/.local/share/mem20-collector/store"
)
TOKEN = os.environ.get("MEM20_COLLECTOR_TOKEN")
PORT = int(os.environ.get("MEM20_COLLECTOR_PORT", "9090"))
HOST = os.environ.get("MEM20_COLLECTOR_HOST", "0.0.0.0")

os.makedirs(STORE, exist_ok=True)
EVENTS = os.path.join(STORE, "installs.jsonl")


def _auth_ok(headers, qs):
    if not TOKEN:
        return True
    if headers.get("X-Token") == TOKEN:
        return True
    return qs.get("token", [""])[0] == TOKEN


def _append(event):
    try:
        with open(EVENTS, "a") as f:
            f.write(json.dumps(event) + "\n")
    except Exception:
        pass


def _load_events():
    out = []
    if os.path.exists(EVENTS):
        with open(EVENTS) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    return out


def compute_metrics(events):
    by_channel = Counter(e.get("channel", "?") for e in events)
    by_platform = Counter(e.get("platform", "?") for e in events)
    by_version = Counter(e.get("version", "?") for e in events)
    installs = set(e.get("install_id") for e in events if e.get("install_id"))
    times = sorted(t for t in (e.get("timestamp") for e in events) if t)
    last_24h = 0
    if times:
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            last_24h = sum(
                1 for t in times if _parse_ts(t) and _parse_ts(t) >= cutoff
            )
        except Exception:
            pass
    return {
        "total_events": len(events),
        "unique_installs": len(installs),
        "by_channel": dict(by_channel),
        "by_platform": dict(by_platform),
        "by_version": dict(by_version),
        "first_seen": times[0] if times else None,
        "last_seen": times[-1] if times else None,
        "last_24h": last_24h,
    }


def _parse_ts(s):
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _dashboard_html(metrics, recent):
    rows = "".join(
        f"<tr><td>{e.get('timestamp','')}</td><td>{e.get('channel','')}</td>"
        f"<td>{e.get('event','')}</td><td>{e.get('version','')}</td>"
        f"<td>{e.get('platform','')}</td><td>{str(e.get('install_id',''))[:8]}</td></tr>"
        for e in recent
    )
    return f"""<!doctype html><html><head><meta charset=utf-8>
<title>mem20 install metrics</title>
<style>body{{font-family:system-ui,sans-serif;margin:2rem;background:#0f1115;color:#e6e6e6}}
h1{{font-weight:600}}table{{border-collapse:collapse;width:100%;margin-top:1rem}}
th,td{{border:1px solid #333;padding:.4rem .6rem;text-align:left;font-size:.85rem}}
.kpis{{display:flex;gap:1rem;flex-wrap:wrap}} .kpi{{background:#1a1d24;border:1px solid #333;
border-radius:8px;padding:1rem 1.2rem;min-width:120px}} .kpi b{{display:block;font-size:1.6rem}}
code{{color:#9fd}}</style></head><body>
<h1>mem20 — install metrics</h1>
<div class=kpis>
<div class=kpi><b>{metrics['unique_installs']}</b>unique installs</div>
<div class=kpi><b>{metrics['total_events']}</b>total events</div>
<div class=kpi><b>{metrics['last_24h']}</b>last 24h</div>
<div class=kpi><b>{metrics['first_seen'] or '-'}</b>first seen</div>
<div class=kpi><b>{metrics['last_seen'] or '-'}</b>last seen</div>
</div>
<h3>By channel</h3><p><code>{metrics['by_channel']}</code></p>
<h3>By platform</h3><p><code>{metrics['by_platform']}</code></p>
<h3>By version</h3><p><code>{metrics['by_version']}</code></p>
<h3>Recent events</h3>
<table><tr><th>time</th><th>channel</th><th>event</th><th>version</th><th>platform</th><th>id</th></tr>
{rows}</table>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body)
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        if not _auth_ok(self.headers, qs):
            self._send(401, {"error": "unauthorized"})
            return
        if u.path in ("/", "/dashboard"):
            metrics = compute_metrics(_load_events())
            n = int(qs.get("n", ["20"])[0])
            recent = _load_events()[-n:]
            self._send(200, _dashboard_html(metrics, recent), "text/html")
        elif u.path == "/metrics":
            self._send(200, compute_metrics(_load_events()))
        elif u.path == "/recent":
            n = int(qs.get("n", ["20"])[0])
            self._send(200, _load_events()[-n:])
        elif u.path == "/export":
            if os.path.exists(EVENTS):
                with open(EVENTS, "rb") as f:
                    self._send(200, f.read(), "application/octet-stream")
            else:
                self._send(404, {"error": "no data"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        if not _auth_ok(self.headers, qs):
            self._send(401, {"error": "unauthorized"})
            return
        if u.path == "/ingest":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length else b"{}"
                event = json.loads(raw or b"{}")
                if isinstance(event, dict) and event.get("install_id"):
                    _append(event)
                    self._send(200, {"ok": True})
                else:
                    self._send(400, {"error": "bad payload"})
            except Exception as e:
                self._send(400, {"error": str(e)})
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, *a):
        pass


def main():
    print(f"mem20 metrics collector on http://{HOST}:{PORT}  (store: {STORE})")
    if TOKEN:
        print("auth: enabled (MEM20_COLLECTOR_TOKEN)")
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("stopped")


if __name__ == "__main__":
    main()
