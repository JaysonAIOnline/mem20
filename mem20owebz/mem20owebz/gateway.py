"""Native model gateway — OpenAI-compatible /v1 proxy.

Replaces the LiteLLM docker service: reads model routes (42) from the
absorbed config as data, resolves keys from the mem20 secrets home, serves
/v1/models + /v1/chat/completions with router-group failover
(fast/balanced/strong + declared fallbacks).

No LiteLLM, no docker. Root-native so it can bind any host:port.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Optional

import httpx

from .config import (
    ENV_FILE,
    ModelConfig,
    Route,
    build_upstream_url,
    env,
    load_env_files,
    parse_config,
    upstream_base,
    upstream_model_name,
)

DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "bridge", "litellm_config.yaml",
)


class GatewayError(RuntimeError):
    """Honest upstream failure — never fabricate a completion."""


def _upstream_payload(route: Route, body: dict) -> dict:
    """Payload sent upstream. Handles observed provider quirks:
    google/gemini OpenAI-compat returns ~0 completion tokens with finish_reason
    'length' whenever max_tokens/max_completion_tokens is forwarded, so those
    are dropped for gemini routes (verified live 2026-09-10)."""
    payload = dict(body)
    payload["model"] = upstream_model_name(route)
    if route.provider in ("google", "gemini"):
        payload.pop("max_tokens", None)
        payload.pop("max_completion_tokens", None)
    return payload


class ModelGateway:
    """Holds the parsed route table and performs upstream proxy calls."""

    def __init__(self, cfg: ModelConfig, client: Optional[httpx.AsyncClient] = None):
        self.cfg = cfg
        self._client = client or httpx.AsyncClient(timeout=120.0)
        self.fail_counts: dict[str, int] = {}
        self.cooldown_until: dict[str, float] = {}

    # ---- routing ----------------------------------------------------------

    def _available(self, alias: str) -> list[Route]:
        """Member routes for an alias that have a real key, respecting cooldown."""
        group = self.cfg.group(alias)
        out = []
        now = time.time()
        for r in group:
            if not r.key():
                continue
            if self.cooldown_until.get(r.alias, 0) > now:
                continue
            out.append(r)
        return out

    def _pick(self, alias: str) -> list[Route]:
        """Candidate list (ordered) for an alias: its keyed members, then the
        keyed members of each declared group fallback."""
        candidates: list[Route] = list(self._available(alias))
        for fb in self.cfg.group_fallbacks(alias):
            for r in self._available(fb):
                if r not in candidates:
                    candidates.append(r)
        if not candidates and alias not in ("fast", "balanced", "strong"):
            r = self.cfg.route(alias)
            if r and r.key():
                candidates = [r]
        return candidates

    # ---- proxy ------------------------------------------------------------

    async def models(self) -> list[str]:
        load_env_files()
        names = []
        for r in self.cfg.keyed():
            if r.display_name() not in names:
                names.append(r.display_name())
        return names

    async def chat_completions(self, body: dict) -> dict:
        alias = str(body.get("model") or "").strip()
        if not alias:
            raise GatewayError("missing 'model' in request body")
        routes = self._pick(alias)
        if not routes:
            raise GatewayError(f"no configured/available route for model '{alias}' (no key or all cooled down)")
        failures: list[str] = []
        for r in routes:
            try:
                return await self._proxy(r, body)
            except (httpx.HTTPStatusError, httpx.HTTPError, GatewayError) as exc:
                failures.append(f"{r.display_name()} ({r.provider}): {exc}")
                self.fail_counts[r.alias] = self.fail_counts.get(r.alias, 0) + 1
                if self.fail_counts[r.alias] >= self.cfg.allowed_fails:
                    self.cooldown_until[r.alias] = time.time() + self.cfg.cooldown_time
        detail = "; ".join(failures)
        raise GatewayError(f"all routes failed for '{alias}': {detail}")

    async def _proxy(self, route: Route, body: dict) -> dict:
        key = route.key()
        base = upstream_base(route)
        url = build_upstream_url(base, route)
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        payload = _upstream_payload(route, body)
        response = await self._client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()


def build_app(cfg: Optional[ModelConfig] = None, config_path: Optional[str] = None,
              client: Optional[httpx.AsyncClient] = None):
    """Aiohttp application with /v1/models + /v1/chat/completions + /health."""
    import aiohttp.web

    if cfg is None:
        cfg = parse_config(config_path or DEFAULT_CONFIG_PATH)
    gw = ModelGateway(cfg, client=client)

    async def health(request):
        load_env_files()
        return aiohttp.web.json_response({
            "status": "ok",
            "routes": len(cfg.routes),
            "keyed": len(cfg.keyed()),
            "groups": sorted(cfg.router_groups),
            "secrets": os.path.exists(ENV_FILE),
        })

    async def models(request):
        return aiohttp.web.json_response(
            {"object": "list", "data": [{"id": n, "object": "model"} for n in await gw.models()]}
        )

    async def chat(request):
        body = await request.json()
        try:
            return aiohttp.web.json_response(await gw.chat_completions(body))
        except GatewayError as exc:
            return aiohttp.web.json_response(
                {"error": {"message": str(exc), "type": "gateway_error"}}, status=502)
        except Exception as exc:  # noqa: BLE001 - surface honestly
            return aiohttp.web.json_response(
                {"error": {"message": f"{exc!r}", "type": "internal"}}, status=500)

    app = aiohttp.web.Application()
    app.router.add_get("/health", health)
    app.router.add_get("/v1/models", models)
    app.router.add_post("/v1/chat/completions", chat)
    app.router.add_get("/", models)  # convenience
    app["gateway"] = gw
    return app


async def run_serve(config_path: str, host: str, port: int) -> None:
    from aiohttp import web

    app = build_app(config_path=config_path)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    print(f"mem20owebz gateway listening on http://{host}:{port}")
    await asyncio.Event().wait()