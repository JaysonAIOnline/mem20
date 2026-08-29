#!/usr/bin/env python3
"""
mem20 LLM client.

Thin OpenAI-compatible chat-completions wrapper used by the cognitive engine,
imagination, and theory-of-mind tools. Default target is NVIDIA's free
OpenAI-compatible endpoint (https://integrate.api.nvidia.com/v1).

Configuration (environment variables):
  NVAPI_KEY / NVIDIA_API_KEY / MEM20_LLM_API_KEY  : bearer token (required)
  MEM20_LLM_BASE_URL                              : default NVIDIA endpoint
  MEM20_LLM_MODEL                                 : default model name

Design rule: if no API key is configured, or the request fails, raise LLMError.
We NEVER fabricate a completion. Callers surface the error so behavior is honest.
"""

import os

try:
    import httpx
except ImportError:  # some venvs install the fork as "httpx2"
    import httpx2 as httpx

DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL = "google/gemma-4-31b-it"

# Candidate .env files that may hold NVAPI_KEY / NVIDIA_API_KEY etc.
_ENV_CANDIDATES = [
    os.environ.get("MEM20_ENV_FILE"),
    "/home/jayson/Desktop/jayson-openwebui/.env",
    "/home/jayson/mem20/.env",
]


def _load_dotenv():
    """Best-effort load of API keys from a .env file if not already in os.environ."""
    for path in _ENV_CANDIDATES:
        if not path or not os.path.exists(path):
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
        # Only need one successful load for the keys we care about.
        if os.environ.get("NVIDIA_API_KEY") or os.environ.get("NVAPI_KEY"):
            break


_load_dotenv()


class LLMError(RuntimeError):
    """Raised when the LLM cannot produce a real completion."""


def _config():
    base = os.environ.get("MEM20_LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    key = (
        os.environ.get("NVAPI_KEY")
        or os.environ.get("NVIDIA_API_KEY")
        or os.environ.get("MEM20_LLM_API_KEY")
        or ""
    ).strip()
    model = os.environ.get("MEM20_LLM_MODEL", DEFAULT_MODEL)
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
    return content["choices"][0]["message"]["content"]


def chat(
    messages: list,
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = 1500,
    base_url: str = None,
    api_key: str = None,
    timeout: float = 180.0,
) -> str:
    """Synchronous chat completion. Raises LLMError on missing key / failure."""
    base, key, def_model = _config()
    base = (base_url or base).rstrip("/")
    key = api_key if api_key is not None else key
    model = model or def_model

    if not key:
        raise LLMError(
            "No LLM API key configured. Set NVAPI_KEY / NVIDIA_API_KEY / "
            "MEM20_LLM_API_KEY. Refusing to fabricate reasoning output."
        )

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                f"{base}/chat/completions",
                headers=_headers(key),
                json=_payload(messages, model, temperature, max_tokens),
            )
            resp.raise_for_status()
            return _extract(resp.json())
    except httpx.HTTPStatusError as exc:
        raise LLMError(f"LLM HTTP {exc.response.status_code}: {exc.response.text[:400]}")
    except httpx.HTTPError as exc:
        raise LLMError(f"LLM request failed: {exc}")
    except (KeyError, IndexError, ValueError) as exc:
        raise LLMError(f"LLM response malformed: {exc}")


async def achat(
    messages: list,
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = 1500,
    base_url: str = None,
    api_key: str = None,
    timeout: float = 180.0,
) -> str:
    """Async chat completion. Raises LLMError on missing key / failure."""
    base, key, def_model = _config()
    base = (base_url or base).rstrip("/")
    key = api_key if api_key is not None else key
    model = model or def_model

    if not key:
        raise LLMError(
            "No LLM API key configured. Set NVAPI_KEY / NVIDIA_API_KEY / "
            "MEM20_LLM_API_KEY. Refusing to fabricate reasoning output."
        )

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
        raise LLMError(f"LLM HTTP {exc.response.status_code}: {exc.response.text[:400]}")
    except httpx.HTTPError as exc:
        raise LLMError(f"LLM request failed: {exc}")
    except (KeyError, IndexError, ValueError) as exc:
        raise LLMError(f"LLM response malformed: {exc}")
