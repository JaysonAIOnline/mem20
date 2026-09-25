from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class GoogleADKConfig:
    host: str = "127.0.0.1"
    port: int = 8002
    gateway_url: str = "http://127.0.0.1:4000"
    ollama_url: str = "http://127.0.0.1:11434"
    secrets_home: str = "/opt/mem20/secrets"
    default_model: str = "qwen2.5-coder:0.5b"
    gateway_model: str = "fast"
    provider: str = "auto"
    request_timeout: float = 120.0
    enable_sessions: bool = True
    enable_memory: bool = True
    session_db_path: str = "/opt/mem20/mem20googlez/state/sessions.db"
    memory_dir: str = "/opt/mem20/mem20googlez/state/memory"

    @classmethod
    def load(cls, path: str | None = None) -> GoogleADKConfig:
        config = cls()
        config_path = path or os.getenv("MEM20GOOGLEZ_CONFIG")
        if config_path and Path(config_path).is_file():
            with open(config_path, "r", encoding="utf-8") as stream:
                data: dict[str, Any] = yaml.safe_load(stream) or {}
            for key, value in data.items():
                if hasattr(config, key):
                    setattr(config, key, value)
        env_values = {
            "host": os.getenv("MEM20GOOGLEZ_HOST"),
            "port": os.getenv("MEM20GOOGLEZ_PORT"),
            "gateway_url": os.getenv("MEM20GOOGLEZ_GATEWAY_URL"),
            "ollama_url": os.getenv("MEM20GOOGLEZ_OLLAMA_URL"),
            "default_model": os.getenv("MEM20GOOGLEZ_DEFAULT_MODEL"),
            "gateway_model": os.getenv("MEM20GOOGLEZ_GATEWAY_MODEL"),
            "provider": os.getenv("MEM20GOOGLEZ_PROVIDER"),
            "request_timeout": os.getenv("MEM20GOOGLEZ_REQUEST_TIMEOUT"),
            "session_db_path": os.getenv("MEM20GOOGLEZ_SESSION_DB"),
            "memory_dir": os.getenv("MEM20GOOGLEZ_MEMORY_DIR"),
        }
        for key, value in env_values.items():
            if value is None:
                continue
            if key == "port":
                value = int(value)
            elif key in {"request_timeout"}:
                value = float(value)
            setattr(config, key, value)
        return config

    def save(self, path: str) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8") as stream:
            yaml.safe_dump(self.__dict__, stream, sort_keys=False)


DEFAULT_CONFIG = GoogleADKConfig()
