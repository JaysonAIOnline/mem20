"""Skills registry — the "tools" of the cleanroom.

Bridges mem20 procedural skills (persisted, executable skill library) and plain
python callables through one inventory so the tool-callback loop sees a uniform
surface. Procedural skills are the durable tool layer; callables are for
function-specific tools supplied at build/run time.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ._substrate import backend as sub


@dataclass
class Skill:
    name: str
    kind: str = "procedural"  # procedural | callable
    description: str = ""
    fn: Optional[Callable[[str], str]] = field(default=None, repr=False)
    args: str = "string argument"


def _render_result(value: Any) -> str:
    if isinstance(value, dict):
        # procedural skill execution returns {ok, output} style dicts.
        return value.get("output") or value.get("result") or value.get("message") \
            or json.dumps(value, default=str)
    if isinstance(value, (list, tuple)):
        return json.dumps(value, default=str)
    return str(value)


class Skills:
    """Tool inventory + executor for one crew run."""

    def __init__(self, seed: Optional[list[Skill]] = None) -> None:
        self._skills: dict[str, Skill] = {}
        for s in seed or []:
            self._skills[s.name] = s

    # ------------------------------------------------------------ collection
    def add_callable(self, name: str, fn: Callable[[str], Any],
                     description: str = "", args: str = "string argument") -> "Skills":
        self._skills[name] = Skill(name=name, kind="callable",
                                   description=description, fn=fn, args=args)
        return self

    def add_procedural(self, name: str) -> "Skills":
        """Register an existing mem20 procedural skill by name."""
        self._skills[name] = Skill(name=name, kind="procedural", description="")
        return self

    def load_procedural_inventory(self, category: Optional[str] = None) -> "Skills":
        """Auto-register every procedural skill listed in mem20."""
        for s in sub.procedural_list(category=category):
            name = s.get("name") or s.get("skill") or ""
            if name and name not in self._skills:
                self._skills[name] = Skill(name=name, kind="procedural",
                                           description=s.get("description", ""))
        return self

    def names(self) -> list[str]:
        return sorted(self._skills)

    def has(self, name: str) -> bool:
        return name in self._skills

    def inventory(self) -> str:
        """Human-readable tool manifest used by the brain's action contract."""
        lines = []
        for name in sorted(self._skills):
            s = self._skills[name]
            lines.append(f"- {name} ({s.kind}) — {s.description or 'no description'}")
        return "\n".join(lines) or "(no tools registered)"

    # -------------------------------------------------------------- execute
    def execute(self, name: str, arg: Any = "") -> dict:
        """Run one tool. Returns {"ok": bool, "output": str, "tool": name}.

        Procedural skills call the mem20 skill library; callables are invoked
        directly. Errors surface in the result (never thrown) so the loop can
        feed the failure back to the brain as an observation.
        """
        s = self._skills.get(name)
        if not s:
            out = self._try_fresh_procedural(name, arg)
            if out is not None:
                return out
            return {"ok": False, "output": f"unknown tool: {name}",
                    "tool": name, "error": "not_registered"}
        try:
            if s.kind == "callable":
                if s.fn is None:
                    raise TypeError(f"callable tool '{name}' has no fn")
                out = s.fn(str(arg))
            else:
                result = sub.procedural_execute(name, context={"arg": str(arg)})
                out = result.get("output") or result.get("result") \
                    or result.get("message") \
                    or ("[skill %s ok]" % name)
                if not result.get("ok", True):
                    return {"ok": False, "output": out, "tool": name}
            return {"ok": True, "output": _render_result(out), "tool": name}
        except Exception as exc:  # surface, never crash the loop
            return {"ok": False, "output": f"{type(exc).__name__}: {exc}",
                    "tool": name, "error": str(exc)}

    def _try_fresh_procedural(self, name: str, arg: Any) -> Optional[dict]:
        """Late-bind a procedural skill that was not in the preloaded inventory."""
        try:
            desc = sub.procedural_get(name)
        except Exception:
            return None
        if not desc:
            return None
        self.add_procedural(name)
        return self.execute(name, arg)

    def __len__(self) -> int:
        return len(self._skills)