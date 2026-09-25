"""Resolve bridge keys from the single secrets home (/opt/mem20/secrets/.env)."""

from __future__ import annotations

import os
from pathlib import Path

SECRETS_ENV = Path("/opt/mem20/secrets/.env")


def load_secrets() -> dict[str, str]:
    secrets: dict[str, str] = {}
    try:
        for raw in SECRETS_ENV.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):].lstrip()
            key, _, value = line.partition("=")
            secrets[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return secrets


def bridge_key() -> str:
    return os.environ.get("LITELLM_MASTER_KEY") or load_secrets().get("LITELLM_MASTER_KEY", "")