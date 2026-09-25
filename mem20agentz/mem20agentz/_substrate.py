"""mem20 agentz substrate facade.

Same discipline as phase 01: lazy, swappable seams over mem20 natives so the
cleanroom imports fast and tests stay hermetic. MEM20AGENTZ_BACKEND=fake seals
every seam — any call without an injected hook raises BackendSealed.

Hooks (add per module as needed):
  remember, recall, namespace_ensure, namespace_grant,
  self_model_get, self_model_create, session_add, session_list,
  session_update, session_delete
"""

from __future__ import annotations

import importlib
import os
import pathlib
import sys
from typing import Any, Callable, Optional

_BACKEND = os.environ.get("MEM20AGENTZ_BACKEND", "native")
_DEFAULT: Optional["Backend"] = None


def _load(name: str):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name != name:
            raise
        # mem20agentz lives inside the mem20 tree; make the substrate root
        # (which holds memory/llm/cog) importable regardless of cwd/PYTHONPATH.
        root = pathlib.Path(__file__).resolve().parents[2]  # /opt/mem20
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        return importlib.import_module(name)


def get_backend():
    """Shared backend; tests replace this once with a sealed+stubbed instance."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = Backend()
    return _DEFAULT


def set_backend(backend: Optional["Backend"]) -> None:
    """Test seam: install a sealed/stubbed instance (restore with None)."""
    import mem20agentz._substrate as _self
    _self._DEFAULT = backend


class Backend:
    def __init__(self, use_substrate: Optional[bool] = None) -> None:
        self.use_substrate = _BACKEND != "fake" if use_substrate is None \
            else use_substrate
        self.hooks: dict[str, Callable[..., Any]] = {}
        self._mem = None

    def _guard(self, name: str) -> None:
        if not self.use_substrate and name not in self.hooks:
            raise BackendSealed(
                f"seam '{name}' is sealed (MEM20AGENTZ_BACKEND=fake); "
                "inject a hook to use it")

    def _call(self, name: str, *args, **kwargs) -> Any:
        if name in self.hooks:
            return self.hooks[name](*args, **kwargs)
        self._guard(name)
        return getattr(self.mem, name)(*args, **kwargs)

    @property
    def mem(self):
        if self._mem is None:
            self._mem = _load("memory")
        return self._mem

    # ------------------------------------------------------------ memory
    def remember(self, topic: str, content: str, tags: Optional[list] = None,
                 actor: str = "agent", epistemic_status: str = "observed",
                 source: str = "mem20agentz") -> dict:
        if "remember" in self.hooks:
            return self.hooks["remember"](topic, content, tags, actor,
                                          epistemic_status)
        self._guard("remember")
        return self.mem.remember(topic=topic, content=content, tags=tags,
                                 actor=actor, epistemic_status=epistemic_status,
                                 source=source, scrub_secrets=True)

    def recall(self, topic: Optional[str] = None, tags: Optional[list] = None,
               k: int = 10) -> list[dict]:
        if "recall" in self.hooks:
            return self.hooks["recall"](topic, tags, k)
        self._guard("recall")
        return self.mem.recall(topic=topic, tags=tags, k=k,
                               include_simulated=False)

    # ----------------------------------------------------------------- llm
    def llm_chat(self, messages: list, model: Optional[str] = None,
                 temperature: float = 0.7, max_tokens: int = 1200,
                 timeout: Optional[float] = None) -> str:
        if "llm_chat" in self.hooks:
            return self.hooks["llm_chat"](messages, model, temperature,
                                          max_tokens, timeout)
        self._guard("llm_chat")
        return _load("llm").chat(messages=messages, model=model,
                                 temperature=temperature,
                                 max_tokens=max_tokens, timeout=timeout)

    # ------------------------------------------------------------ procedural
    def procedural_list(self, category: Optional[str] = None) -> list[dict]:
        if "procedural_list" in self.hooks:
            return self.hooks["procedural_list"](category)
        self._guard("procedural_list")
        return self.mem.procedural_list_skills(category=category)

    def procedural_register(self, name: str, description: str, steps: list,
                            preconditions: Optional[dict] = None,
                            effects: Optional[dict] = None,
                            category: str = "general") -> dict:
        if "procedural_register" in self.hooks:
            return self.hooks["procedural_register"](
                name, description, steps, preconditions, effects, category)
        self._guard("procedural_register")
        return self.mem.procedural_add_skill(
            name, description, steps, preconditions or {},
            effects or {}, category)

    def procedural_execute(self, name: str,
                           context: Optional[dict] = None) -> dict:
        if "procedural_execute" in self.hooks:
            return self.hooks["procedural_execute"](name, context)
        self._guard("procedural_execute")
        return self.mem.procedural_execute_skill(name, context=context)

    # ----------------------------------------------------------- namespaces
    def namespace_ensure(self, namespace: str) -> dict:
        if "namespace_ensure" in self.hooks:
            return self.hooks["namespace_ensure"](namespace)
        self._guard("namespace_ensure")
        create = getattr(self.mem, "namespace_create", None)
        if create is None:
            return {"namespace": namespace, "exists": True}
        return create(namespace=namespace, owner="mem20agentz")

    def namespace_grant(self, namespace: str, agent: str,
                        permission: str = "read_write") -> dict:
        if "namespace_grant" in self.hooks:
            return self.hooks["namespace_grant"](namespace, agent, permission)
        self._guard("namespace_grant")
        create = getattr(self.mem, "namespace_create", None)
        if create is None:
            return {"namespace": namespace, "granted": True}
        return create(namespace=namespace, owner="mem20agentz",
                      acl={agent: permission})

    # ------------------------------------------------------------ self-model
    def self_model_get(self, profile: str) -> Optional[dict]:
        if "self_model_get" in self.hooks:
            return self.hooks["self_model_get"](profile)
        self._guard("self_model_get")
        found = self.mem.recall(
            topic=f"self-model:{profile}", tags=["mem20agentz", "self_model"],
            k=1, include_simulated=False)
        return found[0] if found else None

    def self_model_create(self, profile: str, capabilities: list[str],
                          values: list[str], identity: str) -> dict:
        if "self_model_create" in self.hooks:
            return self.hooks["self_model_create"](profile, capabilities,
                                                   values, identity)
        self._guard("self_model_create")
        return self.mem.remember(
            topic=f"self-model:{profile}",
            content=f"self-model {profile}: identity={identity!r} "
                    f"capabilities={capabilities!r} values={values!r}",
            tags=["mem20agentz", "self_model", profile], actor=profile,
            epistemic_status="agent_generated", source="mem20agentz")

    # ------------------------------------------------------------- sessions
    def session_add(self, profile: str, session_id: str, title: str,
                    meta: Optional[dict] = None) -> dict:
        payload = {"profile": profile, "title": title, "meta": meta or {}}
        content = (f"session {session_id} ({profile}): {title}")
        if "session_add" in self.hooks:
            return self.hooks["session_add"](profile, session_id, title, meta)
        self._guard("session_add")
        return self.mem.remember(
            topic=f"session:{profile}:{session_id}", content=content,
            tags=["mem20agentz", "session", profile], actor=profile,
            epistemic_status="observed", source="mem20agentz")

    def session_list(self, profile: str) -> list[dict]:
        if "session_list" in self.hooks:
            return self.hooks["session_list"](profile)
        self._guard("session_list")
        return self.mem.recall(topic=f"session:{profile}",
                               tags=["mem20agentz", "session", profile], k=50)

    def session_update(self, profile: str, session_id: str,
                       title: Optional[str] = None,
                       meta: Optional[dict] = None) -> dict:
        if "session_update" in self.hooks:
            return self.hooks["session_update"](profile, session_id, title, meta)
        self._guard("session_update")
        return self.mem.remember(
            topic=f"session:{profile}:{session_id}",
            content=f"session {session_id} ({profile}) updated",
            tags=["mem20agentz", "session", profile, "updated"],
            actor=profile, epistemic_status="observed", source="mem20agentz")

    # ------------------------------------------------- session transcript
    def session_append(self, profile: str, session_id: str, role: str,
                       text: str) -> dict:
        if "session_append" in self.hooks:
            return self.hooks["session_append"](profile, session_id, role, text)
        self._guard("session_append")
        return self.mem.remember(
            topic=f"message:{profile}:{session_id}", content=text,
            tags=["mem20agentz", "message", profile, session_id], actor=profile,
            epistemic_status="observed", source="mem20agentz")

    def session_messages(self, profile: str, session_id: str,
                         k: int = 20) -> list[dict]:
        if "session_messages" in self.hooks:
            return self.hooks["session_messages"](profile, session_id, k)
        self._guard("session_messages")
        return self.mem.recall(topic=f"message:{profile}:{session_id}",
                               tags=["mem20agentz", "message", profile,
                                     session_id], k=k)


class BackendSealed(Exception):
    """A substrate seam was called while sealed (no hook injected)."""