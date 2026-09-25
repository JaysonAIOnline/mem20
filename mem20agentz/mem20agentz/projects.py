"""Projects — named workspaces (sub-phase 2.4).

A project is a named folder under <runtime>/projects/<name>/ with a
project.yaml manifest (name, description, created, state). Projects give agent
runs a stable working directory. Archive moves a project out of the active
list instead of deleting it (no data loss).
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from typing import Optional

import yaml

from .config import config_dir

PROJECTS_DIR = "projects"
_MANIFEST = "project.yaml"
_CURRENT = "current_project"


@dataclass
class Project:
    name: str
    description: str = ""
    created: str = ""
    state: str = "active"
    root: Optional[str] = None

    def to_dict(self) -> dict:
        return {"name": self.name, "description": self.description,
                "created": self.created, "state": self.state,
                "root": self.root}


class Projects:
    def __init__(self, root: Optional[pathlib.Path] = None) -> None:
        self.root = root or config_dir() / PROJECTS_DIR

    # ------------------------------------------------------------ create
    def create(self, name: str, description: str = "") -> Project:
        project = Project(name=name, description=description,
                          created=_now())
        path = self._dir(project.name)
        path.mkdir(parents=True, exist_ok=True)
        project.root = str(path)
        self._write(project)
        return project

    def list(self, include_archived: bool = False) -> list[Project]:
        out = []
        if not self.root.exists():
            return out
        for d in sorted(self.root.iterdir()):
            mf = d / _MANIFEST
            if not mf.exists():
                continue
            data = yaml.safe_load(mf.read_text(encoding="utf-8")) or {}
            project = Project(**{k: v for k, v in data.items()
                                 if k in Project.__dataclass_fields__})
            if include_archived or project.state != "archived":
                out.append(project)
        return out

    def get(self, name: str) -> Optional[Project]:
        for project in self.list(include_archived=True):
            if project.name == name:
                return project
        return None

    def archive(self, name: str) -> Optional[Project]:
        project = self.get(name)
        if project is None:
            return None
        project.state = "archived"
        self._write(project)
        if self.current() == name:
            try:
                _current_path().unlink()
            except OSError:
                pass
        return project

    # ------------------------------------------------------------ current
    def current(self) -> str:
        try:
            return _current_path().read_text().strip() or "default"
        except OSError:
            return "default"

    def set_current(self, name: str) -> bool:
        if self.get(name) is None:
            return False
        _current_path().parent.mkdir(parents=True, exist_ok=True)
        _current_path().write_text(name)
        return True

    # ----------------------------------------------------------- helpers
    def _dir(self, name: str) -> pathlib.Path:
        return self.root / _safe(name)

    def _write(self, project: Project) -> None:
        d = self._dir(project.name)
        d.mkdir(parents=True, exist_ok=True)
        (d / _MANIFEST).write_text(
            yaml.safe_dump(project.to_dict(), sort_keys=False), encoding="utf-8")


def _now() -> str:
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "-" for c in name)


def _current_path() -> pathlib.Path:
    return config_dir() / "current_project"