"""mem20 agentz configuration.

Single YAML config file (mem20-native schema). Path resolution order:
  1. $MEM20AGENTZ_CONFIG
  2. <runtime_root>/config.yaml      (default: ~/.mem20agentz/config.yaml)
If no file exists, sane defaults are returned and the file is written so the
user always has an editable source of truth somewhere.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
from typing import Any, Optional

import yaml

DEFAULT_RUNTIME = pathlib.Path(os.environ.get("MEM20AGENTZ_RUNTIME",
                                              "~/.mem20agentz")).expanduser()
CONFIG_ENV = "MEM20AGENTZ_CONFIG"

DEFAULTS: dict[str, Any] = {
    "default_profile": "mem20",
    "model": {
        "provider": "nvidia",
        "model": "nvidia/nemotron-3-ultra-550b-a55b",
        "timeout_s": 900,
    },
    "approvals": "auto",
    "logging": {"file": "runtime/mem20agentz.log", "level": "info"},
}


@dataclasses.dataclass
class Config:
    path: pathlib.Path
    data: dict[str, Any]

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    @property
    def default_profile(self) -> str:
        return self.data.get("default_profile", DEFAULTS["default_profile"])

    @property
    def model(self) -> dict[str, Any]:
        return self.data.get("model", DEFAULTS["model"])

    @property
    def runtime_root(self) -> pathlib.Path:
        return self.path.parent

    def update_file(self, data: dict[str, Any]) -> None:
        merged = dict(self.data)
        merged.update(data)
        self.data = merged
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            yaml.safe_dump(self.data, sort_keys=False), encoding="utf-8"
        )


def default_path() -> pathlib.Path:
    return DEFAULT_RUNTIME / "config.yaml"


def config_dir() -> pathlib.Path:
    """Runtime root for state that lives next to config (plugins, bundles, ...)."""
    return DEFAULT_RUNTIME


def resolve_path(path: Optional[str]) -> pathlib.Path:
    if path:
        return pathlib.Path(path).expanduser()
    if CONFIG_ENV in os.environ:
        return pathlib.Path(os.environ[CONFIG_ENV]).expanduser()
    return default_path()


def load_config(path: Optional[str] = None) -> Config:
    cfg_path = resolve_path(path)
    data: dict[str, Any] = {}
    if cfg_path.exists():
        loaded = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded
    data = _deep_merge(dict(DEFAULTS), data)
    cfg = Config(path=cfg_path, data=data)
    if not cfg_path.exists() and os.environ.get("MEM20AGENTZ_WRITE_DEFAULT", "1") == "1":
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            cfg_path.write_text(
                yaml.safe_dump(cfg.data, sort_keys=False), encoding="utf-8"
            )
        except OSError:
            pass  # read-only runtime: still return defaults
    return cfg


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out