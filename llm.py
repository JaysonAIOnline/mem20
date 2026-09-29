#!/usr/bin/env python3
"""
mem20 LLM client.

Thin OpenAI-compatible chat-completions wrapper used by the cognitive engine,
imagination, and theory-of-mind tools. Default target is Groq's
OpenAI-compatible endpoint (https://api.groq.com/openai/v1); NVIDIA's free
endpoint remains reachable via MEM20_LLM_BASE_URL / the fallback chain.

Configuration (environment variables):
  GROQ_API_KEY / MEM20_LLM_API_KEY / NVAPI_KEY / NVIDIA_API_KEY : bearer token
  MEM20_LLM_BASE_URL                              : default endpoint
  MEM20_LLM_MODEL                                 : default model name

Design rule: if no API key is configured, or the request fails, raise LLMError.
We NEVER fabricate a completion. Callers surface the error so behavior is honest.
"""

import os
import re

try:
    import httpx
except ImportError:  # some venvs install the fork as "httpx2"
    import httpx2 as httpx

# 2026-09-20: moved default off NVIDIA (too slow for interactive dreaming)
# to Groq gpt-oss-120b. Groq gpt-oss returns reasoning in message.reasoning,
# which _extract already handles.
DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "openai/gpt-oss-120b"

# Candidate .env files that may hold NVAPI_KEY / NVIDIA_API_KEY etc.
# 2026-09-07 key rule: the single permanent secrets home is
# /opt/mem20/secrets/.env — it must be read FIRST.
_ENV_CANDIDATES = [
    "/opt/mem20/secrets/.env",
    os.environ.get("MEM20_ENV_FILE"),
    "/home/jayson/Desktop/jayson-openwebui/.env",
    "/home/jayson/mem20/.env",
]


# Values read from the secrets file, private to this module.
#
# This used to be poured into ``os.environ`` at import time, and that was wrong
# on two counts. It leaked: every process that imports this module - the dream
# engine, the control plane, the cognitive engine, the game build harness - ended
# up holding *every* secret in the estate, including the control-plane admin
# password, the sudo password, database credentials and cloud keys that have
# nothing to do with calling a model. And it was sticky: because the loader
# snapshots once at import and ``_password()``-style lookups prefer the
# environment, a rotated secret in the file was silently ignored for the life of
# the process, which is exactly how the control plane ended up serving a stale
# admin password until someone restarted it.
#
# So the file is read into a private map and consulted only for LLM settings. The
# real environment still wins, which is what a deployment that injects secrets
# that way expects.
_FILE_VALUES: dict[str, str] = {}


def _load_dotenv() -> dict[str, str]:
    """Read LLM settings from the first candidate .env that provides a key.

    Best-effort, and deliberately *not* a mutation of the process environment.
    Returns the values it found so `_get` can consult them.
    """
    for path in _ENV_CANDIDATES:
        if not path or not os.path.exists(path):
            continue
        values: dict[str, str] = {}
        try:
            with open(path, "r") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key, val = key.strip(), val.strip().strip('"').strip("'")
                    if key:
                        values[key] = val
        except OSError:
            continue
        _FILE_VALUES.update(values)
        # Only need one successful load for the keys we care about.
        if _get("NVIDIA_API_KEY") or _get("NVAPI_KEY"):
            break
    return _FILE_VALUES


def _get(name: str, default: str = "") -> str:
    """Resolve one setting: the real environment first, then the secrets file."""
    value = os.environ.get(name, "")
    if value:
        return value.strip()
    value = _FILE_VALUES.get(name, "")
    return value.strip() if value else default


def env_value(name: str, default: str = "") -> str:
    """Resolve an LLM setting from the environment or the secrets file.

    Public because other modules legitimately need to know whether a provider is
    funded, and they used to answer that by reading ``os.environ`` directly. That
    only worked because this module used to publish the whole secrets file into
    the environment at import; once it stopped, the dream panel silently found no
    funded members at all. One resolver, so this cannot drift again.
    """
    return _get(name, default)


_load_dotenv()


class LLMError(RuntimeError):
    """Raised when the LLM cannot produce a real completion."""


def _config():
    base = _get("MEM20_LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    # Key must match the provider the base URL points at. Previously NVAPI_KEY
    # was always preferred, so a Groq base URL paired with NVAPI_KEY sent the
    # NVIDIA key to Groq and failed with HTTP 401 "Invalid API Key".
    if "groq" in base.lower():
        key = (
            _get("GROQ_API_KEY")
            or _get("GROQ_API_KEYS")
            or _get("MEM20_LLM_API_KEY")
            or _get("NVAPI_KEY")
            or _get("NVIDIA_API_KEY")
            or ""
        )
    else:
        key = (
            _get("NVAPI_KEY")
            or _get("NVIDIA_API_KEY")
            or _get("MEM20_LLM_API_KEY")
            or ""
        )
    key = key.strip()
    model = _get("MEM20_LLM_MODEL", DEFAULT_MODEL)
    return base, key, model


def _headers(key: str) -> dict:
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _payload(messages, model, temperature, max_tokens):
    return {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }


def _extract(content: dict) -> str:
    msg = content["choices"][0]["message"]
    text = msg.get("content") or ""
    if isinstance(text, list):
        text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
    if not text:
        # Reasoning models differ: Groq gpt-oss uses message.reasoning,
        # NVIDIA / others use message.reasoning_content.
        text = msg.get("reasoning") or msg.get("reasoning_content") or ""
    return _strip_thinking(text).strip()


_OPEN  = r"\n\s*<think(?:ing)?>\s*\n?"
_CLOSE = r"\n\s*</think(?:ing)?>\s*\n?"
_RESP  = r"\n\s*response\s*\n?"


def _strip_thinking(text: str) -> str:
    """Drop the model's reasoning preamble up to the answer marker.

    Delimiters vary per provider/model: plain ` thinking ... /thinking`,
    `<thinking> ... </thinking>`, and Groq qwen3.x which emits
    ` thinking ... response` or `<thinking> ... response` (no close tag).
    """
    pairs = [
        (_OPEN, _CLOSE),
        (_OPEN, _RESP),
        (r"\n\s*thinking\s*\n", _RESP),
        (r"\n\s*thinking\s*\n", r"\n\s*/thinking\s*\n?"),
        (r"\n\s*thinking\s*\n", _CLOSE),
        (r"<thinking>\s*", r"</thinking>"),
    ]
    for start, end in pairs:
        m = re.search(start + r".*?" + end, text, flags=re.S | re.I)
        if m:
            return re.sub(start + r".*?" + end, "\n", text, flags=re.S | re.I)
    return text


def _env(name: str, default: str = "") -> str:
    """Resolve an env var plus its numbered *_N variants, first present wins."""
    for i in range(10):
        key = name if i == 0 else f"{name}_{i}"
        val = _get(key)
        if val:
            return val.strip()
    return default


def _provider_key(name: str) -> str:
    """API key for a fallback provider name (openrouter -> OPENROUTER_API_KEY)."""
    stem = name.upper().replace("-", "_")
    return _env(f"{stem}_API_KEY") or _env(f"{stem}_API_KEYS") or ""


def _fallback_chain() -> list[dict]:
    """Ordered fallback provider candidates for chat()/achat().

    Built from the explicit ``MEM20_LLM_FALLBACK_BASE_URL`` endpoint plus every
    provider listed in ``MEM20_LLM_FALLBACK_PROVIDERS`` that actually has a key
    configured. Providers without a key are skipped — we never retry a provider
    anonymously or fabricate a completion.
    """
    chain: list[dict] = []
    fb_base = _get("MEM20_LLM_FALLBACK_BASE_URL").strip().rstrip("/")
    if fb_base:
        fb_key = _get("MEM20_LLM_FALLBACK_API_KEY").strip()
        if fb_key:
            chain.append({
                "name": "fallback",
                "base": fb_base,
                "key": fb_key,
                "model": _get("MEM20_LLM_FALLBACK_MODEL"),
            })
    for name in _get("MEM20_LLM_FALLBACK_PROVIDERS").split(","):
        name = name.strip()
        if not name:
            continue
        key = _provider_key(name)
        if not key:
            continue
        stem = name.upper().replace("-", "_")
        chain.append({
            "name": name,
            "base": _env(f"{stem}_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
            "key": key,
            "model": _env(f"{stem}_MODEL", DEFAULT_MODEL),
        })
    return chain


def _aggregate_error(primary: str, failures: list[dict]) -> LLMError:
    lines = [f"LLM primary provider failed: {primary}"]
    if failures:
        lines.extend(f"  fallback {f['name']}: {f['error']}" for f in failures)
    else:
        lines.append("  no fallback providers configured")
    return LLMError("\n".join(lines))


def _post_sync(client, base, key, messages, model, temperature, max_tokens):
    resp = client.post(
        f"{base}/chat/completions",
        headers=_headers(key),
        json=_payload(messages, model, temperature, max_tokens),
    )
    resp.raise_for_status()
    return _extract(resp.json())


def chat(
    messages: list,
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = 1500,
    base_url: str = None,
    api_key: str = None,
    timeout: float = 180.0,
) -> str:
    """Synchronous chat completion with fallback chain.

    Tries the primary provider first; on an HTTP/transport failure, tries each
    configured fallback provider in order and returns the first success. If
    every provider fails, raises an honest, aggregated LLMError.
    """
    base, key, def_model = _config()
    base = (base_url or base).rstrip("/")
    key = api_key if api_key is not None else key
    model = model or def_model

    if not key:
        raise LLMError(
            "No LLM API key configured. Set NVAPI_KEY / NVIDIA_API_KEY / "
            "MEM20_LLM_API_KEY. Refusing to fabricate reasoning output."
        )

    primary_err = None
    try:
        with httpx.Client(timeout=timeout) as client:
            return _post_sync(client, base, key, messages, model, temperature, max_tokens)
    except httpx.HTTPStatusError as exc:
        primary_err = f"HTTP {exc.response.status_code}: {exc.response.text[:400]}"
    except httpx.HTTPError as exc:
        primary_err = f"request failed: {exc}"
    except (KeyError, IndexError, ValueError) as exc:
        raise LLMError(f"LLM response malformed: {exc}")

    failures: list[dict] = []
    for fb in _fallback_chain():
        if not fb.get("base") or not fb.get("key"):
            continue
        try:
            with httpx.Client(timeout=timeout) as client:
                return _post_sync(client, fb["base"], fb["key"], messages,
                                  fb["model"] or model, temperature, max_tokens)
        except httpx.HTTPStatusError as exc:
            failures.append({"name": fb["name"],
                             "error": f"HTTP {exc.response.status_code}: {exc.response.text[:400]}"})
        except httpx.HTTPError as exc:
            failures.append({"name": fb["name"], "error": f"request failed: {exc}"})
        except (KeyError, IndexError, ValueError) as exc:
            failures.append({"name": fb["name"], "error": f"malformed response: {exc}"})

    raise _aggregate_error(primary_err, failures)


async def achat(
    messages: list,
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = 1500,
    base_url: str = None,
    api_key: str = None,
    timeout: float = 180.0,
    max_retries: int = 2,
) -> str:
    """Async chat completion with retries. Raises LLMError on missing key / failure."""
    base, key, def_model = _config()
    base = (base_url or base).rstrip("/")
    key = api_key if api_key is not None else key
    model = model or def_model

    if not key:
        raise LLMError(
            "No LLM API key configured. Set NVAPI_KEY / NVIDIA_API_KEY / "
            "MEM20_LLM_API_KEY. Refusing to fabricate reasoning output."
        )

    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{base}/chat/completions",
                    headers=_headers(key),
                    json=_payload(messages, model, temperature, max_tokens),
                )
                resp.raise_for_status()
                return _extract(resp.json())
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code >= 500 and attempt < max_retries:
                last_exc = exc
                import asyncio
                await asyncio.sleep(2 ** attempt)
                continue
            last_exc = exc
            break
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt < max_retries:
                import asyncio
                await asyncio.sleep(2 ** attempt)
                continue
            break
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"LLM response malformed: {exc}")

    import asyncio

    failures: list[dict] = []
    for fb in _fallback_chain():
        if not fb.get("base") or not fb.get("key"):
            continue
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{fb['base']}/chat/completions",
                    headers=_headers(fb["key"]),
                    json=_payload(messages, fb["model"] or model, temperature, max_tokens),
                )
                resp.raise_for_status()
                return _extract(resp.json())
        except httpx.HTTPStatusError as exc:
            failures.append({"name": fb["name"],
                             "error": f"HTTP {exc.response.status_code}: {exc.response.text[:400]}"})
        except httpx.HTTPError as exc:
            failures.append({"name": fb["name"], "error": f"request failed: {exc}"})
        except (KeyError, IndexError, ValueError) as exc:
            failures.append({"name": fb["name"], "error": f"malformed response: {exc}"})

    if isinstance(last_exc, httpx.HTTPStatusError):
        primary = f"HTTP {last_exc.response.status_code}: {last_exc.response.text[:400]}"
    else:
        primary = f"request failed: {last_exc}"
    raise _aggregate_error(primary, failures)
