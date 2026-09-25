"""Route/data layer for the native model gateway.

The absorbed `bridge/litellm_config.yaml` (42 model routes + router groups)
is consumed here as a DATA file — no LiteLLM dependency. Keys resolve ONLY
from the mem20 secrets home (/opt/mem20/secrets/.env, then .env.fallback
for numbered variants when a key is missing).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import yaml

SECRETS_HOME = "/opt/mem20/secrets"
ENV_FILE = os.path.join(SECRETS_HOME, ".env")
ENV_FALLBACK_FILE = os.path.join(SECRETS_HOME, ".env.fallback")


def load_env_files() -> None:
    """Load secrets home into os.environ unless already set (main first, then
    fallback — only the numbered *-N variants live there, loaded on demand)."""
    for path in (ENV_FILE, ENV_FALLBACK_FILE):
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key, val = key.strip(), val.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = val
        except OSError:
            pass


def env(key: str, max_variants: int = 9) -> str:
    """First non-empty os.environ value among KEY, KEY_2, KEY_3 ... KEY_N."""
    for i in range(1, max_variants + 1):
        name = key if i == 1 else f"{key}_{i}"
        v = os.environ.get(name, "").strip()
        if v:
            return v
    return ""


DEFAULT_BASES = {
    "groq": "https://api.groq.com/openai/v1",
    "google": "https://generativelanguage.googleapis.com/v1beta/openai",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "deepseek": "https://api.deepseek.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "mistral": "https://api.mistral.ai/v1",
    "together_ai": "https://api.together.xyz/v1",
    "openai": "https://api.openai.com/v1",
    "xai": "https://api.x.ai/v1",
    "nvidia_nim": "https://integrate.api.nvidia.com/v1",
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "sambanova": "https://api.sambanova.ai/v1",
    "cohere": "https://api.cohere.com/v1",
    "moonshot": "https://api.moonshot.cn/v1",
    "cerebras": "https://api.cerebras.ai/v1",
    "fireworks_ai": "https://api.fireworks.ai/v1",
    "huggingface": "https://api-inference.huggingface.co",
}


@dataclass
class Route:
    alias: str                       # user-facing model name (e.g. "fast", "deepseek/chat")
    upstream_model: str              # provider/model string to send upstream
    key_env: str = ""                # env var name holding the key ("" => inline key or none)
    inline_key: str = ""             # key hardcoded in the config (rare)
    api_base: str = ""               # explicit base URL (from config or env ref), may be ""
    api_version: str = ""            # azure-style api version, if any
    provider: str = ""               # first path segment of upstream model (e.g. "groq")
    router_group: str = ""           # set when alias is part of a router group

    def display_name(self) -> str:
        return self.alias

    def key(self) -> str:
        return env(self.key_env) if self.key_env else self.inline_key


@dataclass
class ModelConfig:
    routes: list[Route] = field(default_factory=list)
    router_groups: dict[str, list[Route]] = field(default_factory=dict)
    router_fallbacks: dict[str, list[str]] = field(default_factory=dict)
    allowed_fails: int = 3
    cooldown_time: int = 60

    def aliases(self) -> list[str]:
        seen: list[str] = []
        for r in self.routes:
            if r.alias not in seen:
                seen.append(r.alias)
        return seen

    def route(self, alias: str) -> Route | None:
        for r in self.routes:
            if r.alias == alias:
                return r
        return None

    def group(self, name: str) -> list[Route]:
        members = self.router_groups.get(name)
        if members is not None:
            return members
        r = self.route(name)
        return [r] if r else []

    def group_fallbacks(self, name: str) -> list[str]:
        return self.router_fallbacks.get(name, [])

    def keyed(self) -> list[Route]:
        """Routes whose upstream key is actually set (honest 'available' list)."""
        out = []
        for name in self.aliases():
            group = self.group(name)
            if not group:
                r = self.route(name)
                if r and r.key():
                    out.append(r)
                continue
            if any(r.key() for r in group):
                out.append(group[0])
        return out


def parse_config(path: str) -> ModelConfig:
    """Parse a litellm-style model config YAML into a ModelConfig (data only,
    no upstream calls). Keys stay symbolic (os.environ/KEY) until resolved."""
    with open(path, "r") as fh:
        raw = yaml.safe_load(fh) or {}

    cfg = ModelConfig()
    for entry in raw.get("model_list", []):
        alias = (entry.get("model_name") or "").strip()
        params = entry.get("litellm_params") or {}
        if not alias or not params:
            continue
        upstream = (params.get("model") or "").strip()
        if not upstream:
            continue
        api_base = _resolve_ref(params.get("api_base", ""))
        api_version = str(params.get("api_version", "") or "")
        provider = upstream.split("/", 1)[0]

        key_ref = params.get("api_key", "")
        key_env, inline_key = "", ""
        if isinstance(key_ref, str) and str(key_ref).startswith("os.environ/"):
            key_env = str(key_ref).split("/", 1)[1].strip()
        elif key_ref:
            inline_key = _resolve_ref(key_ref)

        cfg.routes.append(Route(
            alias=alias,
            upstream_model=upstream,
            key_env=key_env,
            inline_key=inline_key,
            api_base=api_base,
            api_version=api_version,
            provider=provider,
        ))

    # Router groups: aliases with more than one definition AND/OR named in
    # router_settings.fallbacks. Single-def aliases are plain routes.
    counts: dict[str, int] = {}
    for r in cfg.routes:
        counts[r.alias] = counts.get(r.alias, 0) + 1
    router_settings = raw.get("router_settings") or {}
    fb_raw = router_settings.get("fallbacks") or {}
    fallbacks: dict[str, list[str]] = {}
    if isinstance(fb_raw, dict):
        fallbacks = {k: list(v) for k, v in fb_raw.items()}
    elif isinstance(fb_raw, list):
        for item in fb_raw:
            if isinstance(item, dict):
                for k, v in item.items():
                    fallbacks[k] = list(v)
    group_names = {a for a, c in counts.items() if c > 1} | set(fallbacks)

    for r in cfg.routes:
        if r.alias in group_names:
            r.router_group = r.alias
            cfg.router_groups.setdefault(r.alias, []).append(r)

    cfg.router_fallbacks = fallbacks
    cfg.allowed_fails = int(router_settings.get("allowed_fails", 3))
    cfg.cooldown_time = int(router_settings.get("cooldown_time", 60))
    return cfg


def _resolve_ref(value):
    """Resolve an 'os.environ/KEY' literal against the secrets home; otherwise
    return the raw value unchanged."""
    if isinstance(value, str) and value.startswith("os.environ/"):
        return env(value[len("os.environ/"):].strip())
    return value or ""


def upstream_base(route: Route) -> str:
    """Resolved base URL for a route (explicit api_base wins over provider default)."""
    base = route.api_base or DEFAULT_BASES.get(route.provider, "")
    if not base:
        raise KeyError(
            f"no api_base for {route.alias} (provider '{route.provider}'); "
            "set api_base in the config or provide a default"
        )
    return base


def upstream_model_name(route: Route) -> str:
    """Model id sent upstream. The absorbed config stores every model as
    '<provider>/<real-id>'; the upstream API wants just the real id."""
    m = route.upstream_model
    if route.provider and m.startswith(route.provider + "/"):
        return m[len(route.provider) + 1:]
    return m


def build_upstream_url(base: str, route: Route, kind: str = "chat/completions") -> str:
    """Build the upstream endpoint URL for an OpenAI-compatible endpoint."""
    base = base.rstrip("/")
    model = upstream_model_name(route)
    if route.api_version:  # azure-style deployment URLs
        return f"{base}/openai/deployments/{model}/{kind}?api-version={route.api_version}"
    if route.provider == "huggingface":
        return f"{base}/models/{model}/{kind}"
    return f"{base}/{kind}"