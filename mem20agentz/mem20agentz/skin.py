"""Skins — named display themes for the CLI (sub-phase 2.3).

A skin is a small dict (banner + colors as ANSI codes) persisted as YAML under
<runtime>/skins/<name>.yaml. The active skin is stored in <runtime>/active_skin.
Rendering is a pure function of the skin so anything can theme without side
effects.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from typing import Optional

import yaml

from .config import config_dir

SKINS_DIR = "skins"
ACTIVE_FILE = "active_skin"

DEFAULT_SKIN = {
    "name": "mem20",
    "banner": "mem20 agentz",
    "primary": "\033[36m",     # cyan
    "muted": "\033[90m",       # bright black
    "reset": "\033[0m",
}


@dataclass
class Skin:
    name: str = "mem20"
    banner: str = "mem20 agentz"
    colors: dict = field(default_factory=lambda: dict(DEFAULT_SKIN))

    def render(self, text: str, part: str = "primary") -> str:
        code = self.colors.get(part, "") or ""
        return f"{code}{text}{self.colors.get('reset', '')}"


class Skins:
    def __init__(self, root: Optional[pathlib.Path] = None) -> None:
        self.root = root or config_dir() / SKINS_DIR

    def list(self) -> list[str]:
        if not self.root.exists():
            return [DEFAULT_SKIN["name"]]
        names = [p.stem for p in sorted(self.root.glob("*.yaml"))]
        if DEFAULT_SKIN["name"] not in names:
            names.insert(0, DEFAULT_SKIN["name"])
        return names

    def create(self, name: str, banner: Optional[str] = None,
               colors: Optional[dict] = None) -> Skin:
        data = dict(DEFAULT_SKIN, name=name)
        if banner:
            data["banner"] = banner
        if colors:
            data.update({k: v for k, v in colors.items() if v})
        path = self.root / f"{_safe(name)}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data, sort_keys=False),
                        encoding="utf-8")
        return Skin(name=name, banner=data["banner"], colors=data)

    def get(self, name: str) -> Optional[Skin]:
        if name == DEFAULT_SKIN["name"]:
            return Skin()
        path = self.root / f"{_safe(name)}.yaml"
        if not path.exists():
            return None
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return Skin(name=name, banner=str(data.get("banner") or name),
                    colors=data)

    def apply(self, name: str) -> bool:
        if self.get(name) is None:
            return False
        active = config_dir() / ACTIVE_FILE
        active.parent.mkdir(parents=True, exist_ok=True)
        active.write_text(name)
        self._current = name
        return True

    def active(self) -> str:
        if hasattr(self, "_current"):
            return self._current
        try:
            return (config_dir() / ACTIVE_FILE).read_text().strip() or "mem20"
        except OSError:
            return "mem20"


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "-" for c in name)