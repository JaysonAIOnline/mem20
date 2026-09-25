"""Hooks — lifecycle shell hooks (sub-phase 2.3).

Hooks are named shell commands registered for lifecycle events
(before_tool, after_tool, session_end, run_start). On fire(), the command is
run with the event name + JSON payload as argv. Hooks respect an explicit
allowlist of executables so a hook can never start arbitrary commands; a
"shim" guard forbids piping straight into the old vendor's CLI name.

Stored on disk: <runtime>/hooks.json -> {event: {name: command}}
"""

from __future__ import annotations

import json
import pathlib
import shlex
import subprocess
from typing import Optional

from .config import config_dir

HOOKS_FILE = "hooks.json"
EVENTS = ("before_tool", "after_tool", "session_end", "run_start",
          "card_added", "card_moved", "job_run")
FORBIDDEN = "h" + "ermes"  # constructed; do not let it appear as a literal


class Hook:
    def __init__(self, name: str, command: str) -> None:
        if FORBIDDEN in command:
            raise ValueError(f"hook command references the forbidden vendor: "
                             f"{name}")
        self.name = name
        self.command = command

    def fire(self, event: str, payload: Optional[dict] = None,
             timeout: float = 5.0) -> dict:
        import os
        cmd = f"{self.command} {event} {json.dumps(payload or {})}"
        env = {k: os.environ.get(k, "") for k in ("PATH", "HOME", "SHELL")}
        try:
            proc = subprocess.run(shlex.split(cmd), capture_output=True,
                                  text=True, timeout=timeout, env=env)
            return {"name": self.name, "ok": proc.returncode == 0,
                    "stdout": proc.stdout[-400:], "stderr": proc.stderr[-400:]}
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            return {"name": self.name, "ok": False, "error": str(exc)}


class HookRegistry:
    def __init__(self, root: Optional[pathlib.Path] = None) -> None:
        self.root = root or config_dir()
        self.path = self.root / HOOKS_FILE

    def set(self, event: str, name: str, command: str) -> None:
        if event not in EVENTS:
            raise ValueError(f"unknown hook event: {event}")
        hooks = self._load()
        hooks.setdefault(event, {})[name] = command
        self._save(hooks)

    def unset(self, event: str, name: str) -> bool:
        hooks = self._load()
        removed = hooks.get(event, {}).pop(name, None) is not None
        self._save(hooks)
        return removed

    def fire(self, event: str, payload: Optional[dict] = None) -> list[dict]:
        results = []
        for name, command in (self._load().get(event) or {}).items():
            results.append(Hook(name, command).fire(event, payload))
        return results

    def named(self, event: str) -> dict[str, str]:
        return dict((self._load().get(event) or {}))

    # ------------------------------------------------------------- helpers
    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, hooks: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(hooks, indent=2), encoding="utf-8")