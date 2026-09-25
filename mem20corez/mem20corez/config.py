"""Configuration for mem20corez."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any

import yaml


@dataclass
class CoreAIConfig:
    """Native CoreAI configuration."""
    host: str = "127.0.0.1"
    port: int = 8006
    gateway_url: str = "http://127.0.0.1:4000"
    secrets_home: str = "/opt/mem20/secrets"
    ollama_url: str = "http://127.0.0.1:11434"
    default_llm_model: str = "qwen2.5-coder:0.5b"
    model_cache_dir: str = "/opt/mem20/corez/models"
    max_batch_size: int = 8
    batch_timeout_ms: int = 10
    enable_quantization: bool = True
    enable_distillation: bool = True
    enable_evaluation: bool = True
    default_quantization: str = "int8"  # int8, int4, fp16
    default_distillation_temp: float = 2.0
    tensor_context_len: int = 8
    tensor_hidden: int = 48
    tensor_train_iterations: int = 400

    @classmethod
    def load(cls, path: Optional[str] = None) -> "CoreAIConfig":
        cfg = cls()
        if path and Path(path).exists():
            with open(path, "r") as f:
                data = yaml.safe_load(f) or {}
            for k, v in data.items():
                if hasattr(cfg, k):
                    setattr(cfg, k, v)
        return cfg

    def save(self, path: str) -> None:
        with open(path, "w") as f:
            yaml.safe_dump(self.__dict__, f)


DEFAULT_CONFIG = CoreAIConfig()