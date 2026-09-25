"""Lazy substrate adapters.

mem20crewz runs on mem20 natives (memory, cog, llm) loaded lazily so the
cleanroom itself imports fast and deterministic tests stay hermetic. Every
adapter is a callable seam that can be overridden per-test so real tests never
touch the real ledger / LLM / peers.

Default backend is "native" (real mem20). Set MEM20CREWZ_BACKEND=fake to make
all seams fail loudly unless explicitly injected (used by tests).
"""

from __future__ import annotations

import importlib
import os
from typing import Any, Callable, Optional

_BACKEND = os.environ.get("MEM20CREWZ_BACKEND", "native")


def _load(name: str):
    return importlib.import_module(name)


class Backend:
    """Facade over the mem20 substrate with swappable seams.

    To stub a behavior for tests set ``hooks[name]`` to a callable with the
    same signature as the real function.

    hooks keys: recall, remember, procedural_list, procedural_get,
    procedural_execute, plan_guard, veto, quarantine, cog_plan, human_review.
    ``human_review`` is the human-in-the-loop seam: hooks["human_review"](task_name)
    is called when a Task is marked human_input=True. Raise to refuse, return to
    approve.

    ``use_substrate=False`` (MEM20CREWZ_BACKEND=fake) seals every seam: any call
    without an injected hook raises BackendSealed instead of touching the real
    ledger / cog / LLM. Tests run sealed so they cannot silently hit mem20.
    """

    def __init__(self, use_substrate: Optional[bool] = None) -> None:
        self.use_substrate = _BACKEND != "fake" if use_substrate is None \
            else use_substrate
        self.hooks: dict[str, Callable[..., Any]] = {}
        self._mem: Optional[Any] = None
        self._cog: Optional[Any] = None
        self._llm: Optional[Any] = None

    def _guard(self, name: str) -> None:
        if not self.use_substrate and name not in self.hooks:
            raise BackendSealed(
                f"seam '{name}' is sealed (MEM20CREWZ_BACKEND=fake); "
                "inject a hook to use it")

    # ------------------------------------------------------------------ mem
    @property
    def mem(self):
        if self._mem is None:
            self._mem = _load("memory")
        return self._mem

    @property
    def cog(self):
        if self._cog is None:
            self._cog = _load("cog.cognitive_engine")
        return self._cog

    @property
    def llm(self):
        if self._llm is None:
            self._llm = _load("llm")
        return self._llm

    # ----------------------------------------------------------------- tools
    def recall(self, topic: Optional[str] = None, tags: Optional[list] = None,
               k: int = 5) -> list[dict]:
        if "recall" in self.hooks:
            return self.hooks["recall"](topic, tags, k)
        self._guard("recall")
        return self.mem.recall(topic=topic, tags=tags, k=k, include_simulated=False)

    def remember(self, topic: str, content: str, tags: Optional[list] = None,
                 actor: str = "agent", epistemic_status: str = "observed",
                 source: str = "mem20crewz") -> dict:
        if "remember" in self.hooks:
            return self.hooks["remember"](topic, content, tags, actor)
        self._guard("remember")
        return self.mem.remember(topic=topic, content=content, tags=tags,
                                 actor=actor, epistemic_status=epistemic_status,
                                 source=source, scrub_secrets=True)

    # ------------------------------------------------------------ procedural
    def procedural_list(self, category: Optional[str] = None) -> list[dict]:
        if "procedural_list" in self.hooks:
            return self.hooks["procedural_list"](category)
        self._guard("procedural_list")
        return self.mem.procedural_list_skills(category=category)

    def procedural_get(self, name: str) -> dict:
        if "procedural_get" in self.hooks:
            return self.hooks["procedural_get"](name)
        self._guard("procedural_get")
        return self.mem.procedural_get_skill(name)

    def procedural_execute(self, name: str, context: Optional[dict] = None) -> dict:
        if "procedural_execute" in self.hooks:
            return self.hooks["procedural_execute"](name, context)
        self._guard("procedural_execute")
        return self.mem.procedural_execute_skill(name, context=context)

    # ----------------------------------------------------------- guardrails
    def plan_guard(self, fact_ids: Optional[list] = None, actor: str = "agent") -> dict:
        if "plan_guard" in self.hooks:
            return self.hooks["plan_guard"](fact_ids or [], actor)
        self._guard("plan_guard")
        return self.mem.run_plan_execution_guard(fact_ids or [], actor=actor)

    def veto(self, fact_ids: list, actor: str = "agent") -> dict:
        if "veto" in self.hooks:
            return self.hooks["veto"](fact_ids, actor)
        self._guard("veto")
        return self.mem.epistemic_veto(fact_ids, actor=actor)

    def quarantine(self, actor: str = "agent") -> dict:
        if "quarantine" in self.hooks:
            return self.hooks["quarantine"](actor)
        self._guard("quarantine")
        return self.mem.quarantine_expired_simulated(actor=actor)

    def human_review(self, task_name: str) -> None:
        """Human-in-the-loop gate. A Task with human_input=True calls this
        before execution; the hook approves by returning (default) or refuses
        by raising. With no hook the review is refused so we never pretend a
        human signed off."""
        if "human_review" in self.hooks:
            return self.hooks["human_review"](task_name)
        raise BackendSealed(
            f"human_review seam is sealed (no hook injected); "
            f"task '{task_name}' requires human input")


class BackendSealed(Exception):
    """A substrate seam was called while sealed (no hook injected)."""


backend = Backend()