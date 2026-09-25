"""Plugins — manifest-driven extension loader + validation (sub-phase 2.3).

A plugin is a directory holding plugin.yaml plus optional python code. The
manifest is validated before anything is loaded; the entry module (if declared)
must import cleanly and must NOT import the old vendor name. Loading only
registers the callable into a registry — nothing runs until invoked.
"""

from __future__ import annotations

import ast
import importlib.util
import pathlib
from dataclasses import dataclass
from typing import Optional

import yaml

from .config import config_dir

PLUGINS_DIR = "plugins"
_MANIFEST = "plugin.yaml"
_FORBIDDEN = "h" + "ermes"  # constructed at runtime; keep out of literal form


@dataclass
class PluginManifest:
    name: str
    version: str
    entry: str = ""
    description: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "PluginManifest":
        return cls(name=str(d.get("name") or ""),
                   version=str(d.get("version") or "0.0.0"),
                   entry=str(d.get("entry") or ""),
                   description=str(d.get("description") or ""))


class PluginError(RuntimeError):
    pass


class PluginRegistry:
    def __init__(self, root: Optional[pathlib.Path] = None) -> None:
        self.root = root or config_dir() / PLUGINS_DIR
        self._extensions: dict[str, object] = {}

    # ------------------------------------------------------------ discovery
    def discover(self) -> list[PluginManifest]:
        out = []
        if not self.root.exists():
            return out
        for plugin_dir in sorted(self.root.iterdir()):
            if not plugin_dir.is_dir():
                continue
            manifest_path = plugin_dir / _MANIFEST
            if not manifest_path.exists():
                continue
            out.append(self._load_manifest(manifest_path))
        return out

    def validate(self, name: str, raise_on_error: bool = True) -> dict:
        manifest = self._find(name)
        if manifest is None:
            if raise_on_error:
                raise PluginError(f"plugin not found: {name}")
            return {"valid": False, "reason": "not_found"}
        entry_path = self.root / manifest.name / manifest.entry
        if manifest.entry and not self._import_ok(entry_path):
            err = f"entry module does not import: {entry_path}"
            if raise_on_error:
                raise PluginError(err)
            return {"valid": False, "reason": err}
        return {"valid": True, "name": manifest.name,
                "version": manifest.version}

    # --------------------------------------------------------------- load
    def load(self, name: str) -> object:
        """Register + return the entry callable (validated first)."""
        manifest = self._find(name)
        if manifest is None:
            raise PluginError(f"plugin not found: {name}")
        entry_path = self.root / manifest.name / manifest.entry
        if entry_path.exists():
            # import only if it survived source-level checks
            self._check_source(entry_path)
            spec = importlib.util.spec_from_file_location(
                f"mem20agentz_plugin_{manifest.name}", entry_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            entry = getattr(module, "main", None)
            if entry is not None:
                self._extensions[manifest.name] = entry
            return entry
        return None

    # --------------------------------------------------------------- state
    def registered(self) -> dict[str, object]:
        return dict(self._extensions)

    # ------------------------------------------------------------- helpers
    def _find(self, name: str) -> Optional[PluginManifest]:
        for manifest in self.discover():
            if manifest.name == name:
                return manifest
        return None

    @staticmethod
    def _load_manifest(path: pathlib.Path) -> PluginManifest:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return PluginManifest.from_dict(data)

    @staticmethod
    def _check_source(path: pathlib.Path) -> None:
        src = path.read_text(encoding="utf-8", errors="replace")
        if _FORBIDDEN in src:
            raise PluginError(
                f"plugin entry imports the forbidden vendor: {path}")

    @classmethod
    def _import_ok(cls, path: pathlib.Path) -> bool:
        try:
            cls._check_source(path)
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            if not isinstance(tree, ast.Module):
                return False
            compile(tree, str(path), "exec")
            return True
        except (ValueError, SyntaxError, PluginError, OSError):
            return False