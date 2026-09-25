"""Native chat backend + web front-end over the mem20 model gateway.

Single aiohttp app: serves the mem20 chat UI at / and proxies the gateway
(/v1/models, /v1/chat/completions) alongside simple /api/* chat helpers.
No docker, no Open WebUI process — this is the mem20 user-facing chat.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Optional

import httpx

from .config import ModelConfig, parse_config, load_env_files
from .gateway import DEFAULT_CONFIG_PATH, GatewayError, ModelGateway

_INDEX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "index.html")


def _chat_payload(user_message: str, model: str, system: str = "") -> dict:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user_message})
    return {"model": model, "messages": messages}


def build_app(cfg: Optional[ModelConfig] = None, config_path: Optional[str] = None,
              client: Optional[httpx.AsyncClient] = None):
    import aiohttp.web

    if cfg is None:
        cfg = parse_config(config_path or DEFAULT_CONFIG_PATH)
    gw = ModelGateway(cfg, client=client)

    async def index(request):
        try:
            with open(_INDEX, "r") as fh:
                return aiohttp.web.Response(text=fh.read(), content_type="text/html")
        except OSError:
            return aiohttp.web.Response(text="mem20 chat UI not found", status=404)

    async def api_models(request):
        names = await gw.models()
        return aiohttp.web.json_response({"models": names})

    async def api_chat(request):
        load_env_files()
        body = await request.json()
        alias = str(body.get("model") or "").strip()
        if not alias:
            names = await gw.models()
            if not names:
                return aiohttp.web.json_response({"error": "no available models (no keys?)"}, status=503)
            alias = names[0] if "fast" not in names else "fast"
        try:
            result = await gw.chat_completions(
                _chat_payload(
                    str(body.get("message") or ""),
                    alias,
                    system=str(body.get("system") or ""),
                )
            )
        except GatewayError as exc:
            return aiohttp.web.json_response({"error": str(exc)}, status=502)
        content = (result.get("choices") or [{}])[0].get("message", {}).get("content", "")
        return aiohttp.web.json_response({"reply": content})

    async def api_models_v1(request):
        names = await gw.models()
        return aiohttp.web.json_response(
            {"object": "list", "data": [{"id": n, "object": "model"} for n in names]})

    app = aiohttp.web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/api/models", api_models)
    app.router.add_post("/api/chat", api_chat)
    app.router.add_get("/v1/models", api_models_v1)
    app["gateway"] = gw
    return app


async def run_serve(config_path: str, host: str, port: int) -> None:
    from aiohttp import web

    app = build_app(config_path=config_path)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    print(f"mem20 chat at http://{host}:{port}")
    await asyncio.Event().wait()