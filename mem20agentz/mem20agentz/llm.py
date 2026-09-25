"""mem20 agentz LLM layer: providers, fallback router, mixture-of-agents.

Design (2.8):
  * Provider  — one model endpoint (base_url + model + key resolution).
  * Router    — ordered fallback across providers; last resort is the
                substrate llm_chat seam when no providers are configured.
  * moa()     — mixture-of-agents: N proposals + one aggregator.

Credentials NEVER live here: the Router asks a KeyRing for each provider
and passes the token straight into the transport (never logged/printed).
"""

from __future__ import annotations

import dataclasses
import os
from typing import Any, Optional

import httpx

# Well-known OpenAI-compatible endpoints. Always overridable in config.
KNOWN_PROVIDERS: dict[str, dict[str, str]] = {
    "nvidia": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "model": "nvidia/nemotron-3-ultra-550b-a55b",
        "key_env": "NVIDIA_API_KEY",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "openrouter/auto",
        "key_env": "OPENROUTER_API_KEY",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "key_env": "GROQ_API_KEY",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "key_env": "DEEPSEEK_API_KEY",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.0-flash",
        "key_env": "GEMINI_API_KEY",
    },
    "together": {
        "base_url": "https://api.together.xyz/v1",
        "model": "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
        "key_env": "TOGETHER_API_KEY",
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "model": "mistral-large-latest",
        "key_env": "MISTRAL_API_KEY",
    },
    "sambanova": {
        "base_url": "https://api.sambanova.ai/v1",
        "model": "Meta-Llama-3.1-405B-Instruct",
        "key_env": "SAMBANOVA_API_KEY",
    },
}


@dataclasses.dataclass
class Provider:
    name: str
    base_url: str
    model: str
    key_env: Optional[str] = None      # conventional env var, if any
    api_key: Optional[str] = None      # direct value / "secret:<vault>" ref
    timeout_s: float = 120.0
    order: int = 0

    def describe(self) -> dict:
        return {
            "name": self.name,
            "base_url": self.base_url,
            "model": self.model,
            "key_env": self.key_env,
            "timeout_s": self.timeout_s,
            "order": self.order,
        }


def providers_from_config(config: Any) -> list[Provider]:
    """Providers from config `llm.providers` (or the single model provider).

    Config entry: {name: {base_url?, model?, api_key?, key_env?, timeout_s?}}.
    Empty/absent config -> []  (Router then falls back to the substrate seam).
    """
    cfg = (config.get("llm", {}).get("providers") or {}) if config else {}
    providers: list[Provider] = []
    for idx, (name, spec) in enumerate(cfg.items()):
        known = KNOWN_PROVIDERS.get(name, {})
        base = str(spec.get("base_url") or known.get("base_url") or "")
        if not base:
            base = os.environ.get("MEM20_LLM_BASE_URL", "").rstrip("/")
        model = spec.get("model") or known.get("model") or ""
        try:
            timeout = float(spec.get("timeout_s", 120))
        except (TypeError, ValueError):
            timeout = 120.0
        providers.append(Provider(
            name=str(name), base_url=base.rstrip("/"), model=str(model),
            key_env=str(spec.get("key_env") or known.get("key_env") or ""),
            api_key=spec.get("api_key"), timeout_s=timeout, order=idx))
    if providers:
        return providers
    legacy = config.model if config else {}
    name = str(legacy.get("provider", "nvidia") or "nvidia")
    known = KNOWN_PROVIDERS.get(name, {})
    base = os.environ.get("MEM20_LLM_BASE_URL",
                          known.get("base_url", "")).rstrip("/")
    if legacy.get("base_url"):
        base = str(legacy["base_url"]).rstrip("/")
    return [Provider(
        name=name, base_url=base, model=str(legacy.get("model") or
                                            known.get("model", "")),
        key_env=str(known.get("key_env", "")), order=0)]


def parse_prompt(value: str) -> list[dict]:
    return [{"role": "user", "content": value}]


def request_chat(messages: list, provider: Provider, api_key: Optional[str],
                 model: Optional[str] = None, temperature: float = 0.7,
                 max_tokens: int = 1200, timeout: Optional[float] = None,
                 client: Optional[httpx.Client] = None) -> str:
    """POST an OpenAI-compatible chat completion. Returns the content string."""
    if not provider.base_url:
        raise ProviderMisconfigured(f"{provider.name}: no base_url")
    payload: dict[str, Any] = {
        "model": model or provider.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    url = f"{provider.base_url}/chat/completions"
    close_client = False
    if client is None:
        client = httpx.Client(timeout=timeout or provider.timeout_s)
        close_client = True
    try:
        resp = client.post(url, json=payload, headers=headers)
        if resp.status_code == 401:
            raise ProviderKeyRejected(f"{provider.name}: 401 (bad/rotated key)")
        resp.raise_for_status()
        data = resp.json()
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                f"{provider.name}: malformed completion payload: {exc}") from exc
    finally:
        if close_client:
            client.close()


class ProviderError(Exception):
    """Transport failure for one provider (fallback candidate)."""


class ProviderMisconfigured(ProviderError):
    """Provider lacks required configuration (skipped in fallback)."""


class ProviderKeyRejected(ProviderError):
    """Provider rejected the key (auth pool will rotate)."""


class AllProvidersFailed(Exception):
    """Every configured provider failed; underlying errors attached."""

    def __init__(self, errors: list[dict]) -> None:
        super().__init__("all providers failed")
        self.errors = errors


class Router:
    """Ordered fallback across providers, keying via a KeyRing."""

    def __init__(self, providers: Optional[list[Provider]] = None,
                 keyring: Any = None, client: Optional[httpx.Client] = None,
                 substrate: Optional[Any] = None) -> None:
        self.providers = providers or []
        self.keyring = keyring
        self.client = client
        self.substrate = substrate
        self.attempts: list[dict] = []

    def complete(self, messages: list, model: Optional[str] = None,
                 temperature: float = 0.7, max_tokens: int = 1200,
                 timeout: Optional[float] = None) -> dict:
        """Try providers in order; on failure try the next. Never fabricates."""
        self.attempts = []
        if not self.providers and self.substrate is not None:
            text = self.substrate.llm_chat(messages, model, temperature,
                                           max_tokens, timeout)
            return {"text": text, "provider": "substrate", "model": model,
                    "attempts": [{"provider": "substrate", "ok": True}]}
        for idx, provider in enumerate(self.providers[:]):
            retried = False
            while True:
                api_key, source = None, None
                if self.keyring is not None:
                    api_key, source = self.keyring.get(provider.name,
                                                       provider.api_key)
                    if api_key is None:
                        # auth-managed mode: never send an unauthenticated
                        # request to a paywalled endpoint.
                        self.attempts.append({"provider": provider.name,
                                              "ok": False,
                                              "error": "no api key"})
                        break
                try:
                    text = request_chat(
                        messages, provider, api_key, model=model,
                        temperature=temperature, max_tokens=max_tokens,
                        timeout=timeout, client=self.client)
                except ProviderMisconfigured as exc:
                    self.attempts.append({"provider": provider.name,
                                          "ok": False,
                                          "error": str(exc).split(
                                              ": ", 1)[-1]})
                    break
                except ProviderKeyRejected as exc:
                    rotated = None
                    if self.keyring is not None:
                        rotated = self.keyring.rotate(provider.name)
                    if rotated and not retried:
                        retried = True  # one retry with the rotated key
                        continue
                    self.attempts.append({
                        "provider": provider.name, "ok": False, "status": 401,
                        "error": str(exc),
                        "rotated": bool(rotated)})
                    break
                except (httpx.HTTPError, ProviderError, OSError) as exc:
                    self.attempts.append({"provider": provider.name,
                                          "ok": False,
                                          "error": exc.__class__.__name__})
                    break
                self.attempts.append({"provider": provider.name, "ok": True,
                                      "key_source": source})
                return {"text": text, "provider": provider.name,
                        "model": model or provider.model,
                        "attempts": list(self.attempts)}
        errors = [a for a in self.attempts if not a["ok"]]
        raise AllProvidersFailed(errors)

    def text(self, messages: list, model: Optional[str] = None,
             temperature: float = 0.7, max_tokens: int = 1200,
             timeout: Optional[float] = None) -> str:
        return self.complete(messages, model=model, temperature=temperature,
                             max_tokens=max_tokens, timeout=timeout)["text"]


def install_hook(backend: Any, router: Optional[Router] = None) -> Router:
    """Wire the Router into the shared backend llm_chat seam (5-arg hook)."""
    if router is None:
        router = Router(keyring=getattr(backend, "_keyring", None),
                        substrate=backend)
    backend.hooks["llm_chat"] = \
        lambda messages, model=None, temperature=0.7, max_tokens=1200, \
            timeout=None: router.text(messages, model=model,
                                      temperature=temperature,
                                      max_tokens=max_tokens, timeout=timeout)
    return router


# ----------------------------------------------------------------- MoA
_AGGREGATOR_RULES = (
    "You are the aggregator in a mixture-of-agents setup. Several models "
    "answered the user's request below. Produce ONE final answer that is the "
    "best synthesis of their proposals: correct, concise, and faithful to "
    "the user's intent. Do not mention the other models. Do not fabricate."
)

_PROMPT_TEMPLATE = (
    "Answer the user's request. Return only the answer, no preamble.\n\n"
    "USER REQUEST:\n{question}"
)


def _proposals_prompt(question: str, proposals: list[dict]) -> str:
    parts = [_AGGREGATOR_RULES,
             f"\nUSER REQUEST:\n{question}\n",
             "PROPOSALS FROM OTHER MODELS:"]
    for i, p in enumerate(proposals, 1):
        parts.append(f"  [{i}] ({p.get('provider', '?')})\n{p['text'].strip()}\n")
    return "\n".join(parts)


def moa(question: str, router: Router, proposers: int = 3,
        temperature: float = 0.3, max_tokens: int = 1200) -> dict:
    """Single-layer mixture-of-agents: N proposals, one aggregator pass."""
    if proposers < 1:
        raise ValueError("proposers must be >= 1")
    pool = router.providers or []
    proposals: list[dict] = []
    for i in range(proposers):
        completor = router
        provider_name = "router"
        if pool:
            # one proposal per provider (rotating), each on its own model,
            # so fallback per proposal is a single, honest provider attempt.
            provider = pool[i % len(pool)]
            provider_name = provider.name
            completor = Router([provider], keyring=router.keyring,
                               substrate=router.substrate)
        try:
            result = completor.complete(
                parse_prompt(_PROMPT_TEMPLATE.format(question=question)),
                temperature=temperature, max_tokens=max_tokens)
        except AllProvidersFailed as exc:
            result = {"text": "", "provider": provider_name,
                      "attempts": exc.errors,
                      "error": "all providers failed"}
        proposals.append({"provider": result.get("provider"),
                          "text": result.get("text", ""),
                          "attempts": result.get("attempts")})
    live = [p for p in proposals if p["text"].strip()]
    if not live:
        raise AllProvidersFailed(
            [{"provider": "moa", "ok": False, "error": "no live proposals"}])
    agg = router.complete(
        parse_prompt(_proposals_prompt(question, live)),
        temperature=temperature, max_tokens=max_tokens)
    return {"text": agg.get("text"), "provider": agg.get("provider"),
            "model": agg.get("model"),
            "proposals": [{"provider": p["provider"], "text": p["text"]}
                          for p in proposals]}