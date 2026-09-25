"""mem20 gateway LLM client used by live-mode studio agents."""

from __future__ import annotations


async def chat_completion(gateway_url: str, prompt: str, seed: int = 0) -> str:
    """POST /v1/chat/completions to the mem20 gateway, return assistant text."""
    import aiohttp

    url = f"{gateway_url.rstrip('/')}/v1/chat/completions"
    payload = {
        "model": "fast",
        "messages": [
            {"role": "system", "content": "You are a game design assistant. Reply concisely."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 512,
        "temperature": 0.7,
        "seed": seed,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"gateway {resp.status}: {body[:200]}")
            data = await resp.json()
            content = data["choices"][0]["message"]["content"]
            return content