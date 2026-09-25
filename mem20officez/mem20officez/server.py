"""mem20officez native server — serves 3D office frontend + API over mem20 gateway."""

from __future__ import annotations

import asyncio
import json
import mimetypes
import os
from pathlib import Path
from typing import Optional

import httpx
from aiohttp import web

from .config import DEFAULT_CONFIG, OfficeConfig

# Ensure mimetypes for JS/CSS/WASM
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("text/css", ".css")


class OfficeServer:
    """Aiohttp server for the native mem20 office."""

    def __init__(self, cfg: OfficeConfig, client: Optional[httpx.AsyncClient] = None):
        self.cfg = cfg
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self.app = web.Application()
        self._setup_routes()

    def _setup_routes(self) -> None:
        self.app.router.add_get("/health", self.health)
        self.app.router.add_get("/api/office", self.office_state)
        self.app.router.add_get("/api/gateway/models", self.gateway_models)
        self.app.router.add_post("/api/gateway/chat", self.gateway_chat)
        self.app.router.add_get("/wellness", self.wellness)
        self.app.router.add_get("/wellness/demo", self.wellness_demo)
        self.app.router.add_get("/wellness/embed", self.wellness_embed)
        self.app.router.add_get("/dashboard", self.dashboard)
        # Static file serving (Next.js build + public assets)
        self._add_static_routes()

    def _add_static_routes(self) -> None:
        # Public assets
        public_dir = self.cfg.harvest_root / "public"
        if public_dir.exists():
            self.app.router.add_static("/public", public_dir, show_index=False)
        # Next.js static export (from build_dir)
        build_static = self.cfg.build_dir / ".next" / "static"
        if build_static.exists():
            self.app.router.add_static("/_next/static", build_static, show_index=False)
        # Next.js server pages (static HTML)
        server_pages = self.cfg.build_dir / ".next" / "server" / "app"
        if server_pages.exists():
            # Serve static HTML files directly for known routes
            for html_file in server_pages.rglob("*.html"):
                route = "/" + html_file.relative_to(server_pages).with_suffix("").as_posix()
                if route == "/index":
                    route = "/"
                self.app.router.add_get(route, self._make_file_handler(html_file))
        # Fallback: SPA handler
        self.app.router.add_get("/{tail:.*}", self.spa_fallback)

    def _make_file_handler(self, file_path: Path):
        async def handler(request: web.Request) -> web.Response:
            return web.FileResponse(file_path)
        return handler

    async def health(self, request: web.Request) -> web.Response:
        return web.json_response({
            "status": "ok",
            "service": "mem20officez",
            "version": "0.1.0",
            "gateway": self.cfg.gateway_url,
            "phaser": self.cfg.enable_phaser,
            "wellness": self.cfg.enable_wellness,
            "dashboard": self.cfg.enable_dashboard,
        })

    async def office_state(self, request: web.Request) -> web.Response:
        """Office state API — aggregates gateway + local state."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                gw = await client.get(f"{self.cfg.gateway_url}/health")
                gw_data = gw.json() if gw.status_code == 200 else {"status": "unreachable"}
        except Exception as e:
            gw_data = {"status": "error", "error": str(e)}
        return web.json_response({
            "service": "mem20officez",
            "gateway": gw_data,
            "features": {
                "phaser": self.cfg.enable_phaser,
                "wellness": self.cfg.enable_wellness,
                "dashboard": self.cfg.enable_dashboard,
            },
        })

    async def gateway_models(self, request: web.Request) -> web.Response:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self.cfg.gateway_url}/v1/models")
                return web.json_response(resp.json(), status=resp.status_code)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=502)

    async def gateway_chat(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(f"{self.cfg.gateway_url}/v1/chat/completions", json=body)
                return web.json_response(resp.json(), status=resp.status_code)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=502)

    async def wellness(self, request: web.Request) -> web.Response:
        path = self.cfg.harvest_root / "wellness-checkin.html"
        if path.exists():
            return web.FileResponse(path)
        return web.Response(text="Wellness checkin not found", status=404)

    async def wellness_demo(self, request: web.Request) -> web.Response:
        path = self.cfg.harvest_root / "wellness-checkin-demo.html"
        if path.exists():
            return web.FileResponse(path)
        return web.Response(text="Wellness demo not found", status=404)

    async def wellness_embed(self, request: web.Request) -> web.Response:
        path = self.cfg.harvest_root / "wellness-checkin-embed.js"
        if path.exists():
            return web.FileResponse(path, headers={"Content-Type": "application/javascript"})
        return web.Response(text="Wellness embed not found", status=404)

    async def dashboard(self, request: web.Request) -> web.Response:
        path = self.cfg.harvest_root / "mem20-dashboard.html"
        if path.exists():
            return web.FileResponse(path)
        return web.Response(text="Dashboard not found", status=404)

    async def spa_fallback(self, request: web.Request) -> web.Response:
        """SPA fallback — serve index.html for client-side routes."""
        # Try to serve from Next.js build first
        build_index = self.cfg.build_dir / ".next" / "server" / "app" / "index.html"
        if build_index.exists():
            return web.FileResponse(build_index)
        # Fallback: try to find any index.html in harvest
        harvest_index = self.cfg.harvest_root / "src" / "app" / "page.tsx"
        # For dev, we can't serve TSX directly. Return a helpful message.
        return web.Response(
            text="mem20officez: Next.js build not found. Run `npm run build` in src_harvest/ first.",
            status=503,
            content_type="text/plain"
        )


async def run_server(cfg: Optional[OfficeConfig] = None, host: Optional[str] = None,
                     port: Optional[int] = None) -> None:
    cfg = cfg or DEFAULT_CONFIG
    if host:
        cfg.host = host
    if port:
        cfg.port = port
    server = OfficeServer(cfg)
    runner = web.AppRunner(server.app)
    await runner.setup()
    site = web.TCPSite(runner, cfg.host, cfg.port)
    await site.start()
    print(f"mem20officez serving at http://{cfg.host}:{cfg.port}")
    print(f"  Gateway: {cfg.gateway_url}")
    print(f"  Wellness: /wellness, /wellness/demo")
    print(f"  Dashboard: /dashboard")
    print(f"  Office API: /api/office")
    await asyncio.Event().wait()