#!/usr/bin/env python3
"""Procedural memory tools for mem20.

Canonical home for the procedural-skill API (skills, procedures, how-to
knowledge): add, get, find, execute, learn, list. Backed by the mem20
procedural store (``procedural_memory.json``) whose schema is::

    {"skills": {name: {...}}, "execution_history": [...]}

This module is loaded as the ``memory`` procedural seam by the agent
substrates (mem20agentz, mem20crewz), so the public function names and
signatures match what those seams expect.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

STORE_DIR = Path(os.environ.get("MEM20_STORE_PATH") or Path(__file__).resolve().parent)
PROCEDURAL_FILE = Path(
    os.environ.get("MEM20_PROCEDURAL_STORE") or (STORE_DIR / "procedural_memory.json")
)

_lock = threading.RLock()
_cache: "ProceduralMemory | None" = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> dict:
    if not PROCEDURAL_FILE.exists():
        return {"skills": {}, "execution_history": []}
    try:
        with open(PROCEDURAL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {"skills": {}, "execution_history": []}
    if not isinstance(data, dict):
        return {"skills": {}, "execution_history": []}
    data.setdefault("skills", {})
    data.setdefault("execution_history", [])
    return data


def _save(data: dict) -> None:
    PROCEDURAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = PROCEDURAL_FILE.with_suffix(PROCEDURAL_FILE.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PROCEDURAL_FILE)


class ProceduralMemory:
    """Procedural memory for skills, procedures, and how-to knowledge."""

    def __init__(self) -> None:
        self.skills: dict = {}
        self.execution_history: list = []

    def add_skill(self, name, description, steps, preconditions=None,
                  effects=None, category="general") -> None:
        self.skills[name] = {
            "description": description,
            "steps": list(steps or []),
            "preconditions": preconditions or {},
            "effects": effects or {},
            "category": category,
            "created_ts": _now(),
            "execution_count": 0,
            "success_rate": 1.0,
        }

    def get_skill(self, name):
        return self.skills.get(name)

    def find_skills(self, category=None, matching_preconditions=None) -> list:
        results = []
        for name, skill in self.skills.items():
            if category and skill.get("category") != category:
                continue
            if matching_preconditions:
                if not all(skill.get("preconditions", {}).get(k) == v
                           for k, v in matching_preconditions.items()):
                    continue
            results.append({"name": name, **skill})
        return results

    def execute_skill(self, name, context=None) -> dict:
        skill = self.skills.get(name)
        if not skill:
            return {"error": f"Skill '{name}' not found"}
        preconditions = skill.get("preconditions", {})
        if preconditions and context:
            for k, v in preconditions.items():
                if context.get(k) != v:
                    return {"error": f"Precondition failed: {k}={v} "
                                     f"(got {context.get(k)})"}
        success = True
        result = {"executed_steps": skill.get("steps", []), "context": context or {}}
        for effect_key, effect_val in skill.get("effects", {}).items():
            result[effect_key] = effect_val
        n = skill.get("execution_count", 0) + 1
        rate = skill.get("success_rate", 1.0)
        skill["success_rate"] = (rate * (n - 1) + 1) / n if success \
            else (rate * (n - 1)) / n
        skill["execution_count"] = n
        self.execution_history.append({
            "skill": name, "ts": _now(), "context": context or {},
            "success": success, "result": result,
        })
        return result

    def learn_from_execution(self, name, success, modified_steps=None,
                             new_preconditions=None, new_effects=None) -> dict:
        skill = self.skills.get(name)
        if not skill:
            return {"error": f"Skill '{name}' not found"}
        if modified_steps is not None:
            skill["steps"] = list(modified_steps)
        if new_preconditions is not None:
            skill.setdefault("preconditions", {}).update(new_preconditions)
        if new_effects is not None:
            skill.setdefault("effects", {}).update(new_effects)
        return {"skill": name, "updated": True}

    def to_dict(self) -> dict:
        return {
            "skills": self.skills,
            "execution_history": self.execution_history[-1000:],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProceduralMemory":
        pm = cls()
        pm.skills = data.get("skills", {}) or {}
        pm.execution_history = data.get("execution_history", []) or []
        return pm


def _get_procedural() -> ProceduralMemory:
    global _cache
    if _cache is None:
        _cache = ProceduralMemory.from_dict(_load())
    return _cache


def _persist(pm: ProceduralMemory) -> None:
    _save(pm.to_dict())


def procedural_add_skill(name, description, steps, preconditions=None,
                         effects=None, category="general", actor="agent") -> dict:
    with _lock:
        pm = _get_procedural()
        pm.add_skill(name, description, steps, preconditions, effects, category)
        _persist(pm)
    return {"skill": name, "description": description, "steps": steps}


def procedural_get_skill(name, actor="agent") -> dict:
    with _lock:
        skill = _get_procedural().get_skill(name)
    if not skill:
        return {"error": f"Skill '{name}' not found"}
    return {"name": name, **skill}


def procedural_find_skills(category=None, preconditions=None, actor="agent") -> list:
    with _lock:
        return _get_procedural().find_skills(category, preconditions)


def procedural_execute_skill(name, context=None, actor="agent") -> dict:
    with _lock:
        pm = _get_procedural()
        result = pm.execute_skill(name, context)
        _persist(pm)
    return result


def procedural_learn(name, success, modified_steps=None, new_preconditions=None,
                     new_effects=None, actor="agent") -> dict:
    with _lock:
        pm = _get_procedural()
        result = pm.learn_from_execution(name, success, modified_steps,
                                         new_preconditions, new_effects)
        _persist(pm)
    return result


def procedural_list_skills(category=None, actor="agent") -> list:
    with _lock:
        return _get_procedural().find_skills(category, None)


__all__ = [
    "ProceduralMemory",
    "procedural_add_skill",
    "procedural_get_skill",
    "procedural_find_skills",
    "procedural_execute_skill",
    "procedural_learn",
    "procedural_list_skills",
]
