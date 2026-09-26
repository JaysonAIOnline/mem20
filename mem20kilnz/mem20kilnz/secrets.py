"""The single sanctioned place KilNZ reads credentials from.

The mem20 estate keeps every key in one file: /opt/mem20/secrets/.env. This
module reads that file and nothing else. It never invents a key, never prompts
for one, and reports clearly when the file is absent rather than pretending a
credential exists.
"""
from __future__ import annotations

import os
from pathlib import Path

SECRETS_PATH = Path(os.environ.get("KILNZ_SECRETS", "/opt/mem20/secrets/.env"))

#: OpenAI-compatible providers, in the estate's resolution order. Groq is the
#: primary and NVIDIA the fallback, per the standing mem20 provider policy.
PROVIDERS: tuple[tuple[str, str, str, str], ...] = (
    ("groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1", "openai/gpt-oss-120b"),
    ("nvidia", "NVIDIA_API_KEY", "https://integrate.api.nvidia.com/v1",
     "meta/llama-3.3-70b-instruct"),
    ("together", "TOGETHER_API_KEY", "https://api.together.xyz/v1",
     "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
    ("deepseek", "DEEPSEEK_API_KEY", "https://api.deepseek.com/v1", "deepseek-chat"),
    ("mistral", "MISTRAL_API_KEY", "https://api.mistral.ai/v1", "mistral-large-latest"),
    ("sambanova", "SAMBANOVA_API_KEY", "https://api.sambanova.ai/v1",
     "Meta-Llama-3.3-70B-Instruct"),
    ("siliconflow", "SILICONFLOW_API_KEY", "https://api.siliconflow.cn/v1",
     "Qwen/Qwen2.5-72B-Instruct"),
    ("openrouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1",
     "meta-llama/llama-3.3-70b-instruct"),
    ("cerebras", "CEREBRAS_API_KEY", "https://api.cerebras.ai/v1",
     "llama-3.3-70b"),
    ("fireworks", "FIREWORKS_API_KEY", "https://api.fireworks.ai/inference/v1",
     "accounts/fireworks/models/llama-v3p3-70b-instruct"),
)

#: Providers the estate does not use.
DISALLOWED = frozenset({"xai"})

_cache: dict[str, str] | None = None


def secrets_available() -> bool:
    return SECRETS_PATH.is_file()


def load(force: bool = False) -> dict[str, str]:
    """Parse the secrets file. Missing file is an empty mapping, not an error."""
    global _cache
    if _cache is not None and not force:
        return _cache
    out: dict[str, str] = {}
    if secrets_available():
        for raw in SECRETS_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.lower().startswith("export "):
                line = line[7:].strip()
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                val = val[1:-1]
            if key:
                out[key] = val
    _cache = out
    return out


def get(name: str, default: str | None = None) -> str | None:
    """Environment wins over the secrets file, so a caller can override inline."""
    env = os.environ.get(name)
    if env:
        return env
    return load().get(name, default)


def llm_config() -> dict[str, str]:
    """Resolve an OpenAI-compatible endpoint for the engine's agent.

    The engine speaks the OpenAI `/chat/completions` shape, so any compatible
    provider works. Resolution order is the estate's standing provider policy
    (Groq primary, NVIDIA fallback, xAI disallowed) rather than a hope that
    `OPENAI_API_KEY` happens to exist. Only keys that are actually present are
    returned, so the caller can name the missing credential instead of sending
    an empty one.
    """
    explicit_key = get("KILNZ_API_KEY") or get("OPENAI_API_KEY")  # noqa: E501
    explicit_base = get("KILNZ_API_BASE") or get("OPENAI_API_BASE") or get("OPENAI_BASE_URL")
    if explicit_key:
        cfg = {"KILN_API_KEY": explicit_key, "_provider": "explicit"}
        if explicit_base:
            cfg["KILN_API_BASE"] = explicit_base.rstrip("/")
        model = get("KILNZ_MODEL")
        if model:
            cfg["KILN_MODEL"] = model
        return cfg

    loaded = load()
    for name, env_key, base, model in PROVIDERS:
        if name in DISALLOWED:
            continue
        key = loaded.get(env_key)
        if not key:
            continue
        cfg = {"KILN_API_KEY": key, "KILN_API_BASE": base, "KILN_MODEL": model}
        override = get("KILNZ_MODEL")
        if override:
            cfg["KILN_MODEL"] = override
        cfg["_provider"] = name
        return cfg
    return {}


def engine_env() -> dict[str, str]:
    """Exactly the environment the engine should receive.

    `llm_config()` also carries an internal `_provider` marker for reporting;
    that must never reach the subprocess as a stray environment variable.
    """
    return {k: v for k, v in llm_config().items() if not k.startswith("_")}


def provider_candidates() -> list[dict]:
    """What is available right now, in resolution order, without exposing values."""
    loaded = load()
    out = []
    for name, env_key, base, model in PROVIDERS:
        if name in DISALLOWED:
            continue
        out.append(
            {
                "provider": name,
                "key_name": env_key,
                "configured": bool(loaded.get(env_key)),
                "base": base,
                "model": model,
            }
        )
    return out


def status() -> dict[str, object]:
    cfg = llm_config()
    return {
        "path": str(SECRETS_PATH),
        "exists": secrets_available(),
        "keys_loaded": len(load()),
        "llm_configured": bool(cfg),
        "llm_env_keys": sorted(k for k in cfg if not k.startswith("_")),
        "llm_provider": cfg.get("_provider", ""),
        "llm_base": cfg.get("KILN_API_BASE", ""),
        "llm_model": cfg.get("KILN_MODEL", ""),
        "providers_available": [p["provider"] for p in provider_candidates() if p["configured"]],
    }
