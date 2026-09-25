"""Profiles — isolated agent instances.

Each profile is a mem20 namespace plus a persistent self-model (capabilities,
values, identity). Profiles inherit from the mem20 base profile ("mem20") so a
profile without an explicit self-model still reports the base one.
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from ._substrate import Backend, get_backend

BASE_PROFILE = "mem20"


@dataclasses.dataclass
class Profile:
    name: str
    namespace: str
    identity: str = ""
    capabilities: list[str] = dataclasses.field(default_factory=list)
    values: list[str] = dataclasses.field(default_factory=list)

    @property
    def self_model(self) -> dict:
        return {
            "identity": self.identity,
            "capabilities": self.capabilities,
            "values": self.values,
        }


def namespace_for(name: str) -> str:
    return f"mem20agentz:{name.replace(' ', '-')}"


class Profiles:
    def __init__(self, backend: Optional[Backend] = None) -> None:
        self._b = backend or get_backend()

    def ensure(self, name: str) -> Profile:
        ns = namespace_for(name)
        self._b.namespace_ensure(ns)
        self._b.namespace_grant(ns, name)
        model = self._b.self_model_get(name)
        if model is None and name != BASE_PROFILE:
            base = self._b.self_model_get(BASE_PROFILE)
            model = base
        if model is None:
            return Profile(name=name, namespace=ns)
        caps, vals = _parse_model(model)
        return Profile(name=name, namespace=ns,
                       identity=_parse_identity(model),
                       capabilities=caps, values=vals)

    def create(self, name: str, identity: str = "",
               capabilities: Optional[list[str]] = None,
               values: Optional[list[str]] = None) -> Profile:
        ns = namespace_for(name)
        self._b.namespace_ensure(ns)
        self._b.namespace_grant(ns, name)
        if identity or capabilities or values:
            self._b.self_model_create(name, capabilities or [],
                                      values or [], identity or name)
        return Profile(name=name, namespace=ns, identity=identity or name,
                       capabilities=capabilities or [],
                       values=values or [])

    def list(self) -> list[str]:
        """Known profiles = every self-model stored on the substrate."""
        hits = self._b.recall(topic="self-model", tags=["mem20agentz",
                                                        "self_model"], k=200)
        names = set()
        for h in hits:
            t = h.get("topic", "") or ""
            if t.startswith("self-model:"):
                names.add(t[len("self-model:"):])
        return sorted(names)


def _parse_identity(model: dict) -> str:
    content = model.get("content", "") if isinstance(model, dict) else ""
    identity = model.get("identity")
    if identity:
        return identity
    for marker in ("identity=",):
        idx = content.find(marker)
        if idx >= 0:
            rest = content[idx + len(marker):]
            return rest.split(" ")[0].strip("'\"")
    return ""


def _parse_model(model: dict) -> tuple[list[str], list[str]]:
    content = model.get("content", "") if isinstance(model, dict) else ""
    if isinstance(model, dict):
        caps = model.get("capabilities") or model.get("self_model", {}).get("capabilities")
        vals = model.get("values") or model.get("self_model", {}).get("values")
        if caps or vals:
            return list(caps or []), list(vals or [])
    import ast
    caps, vals = [], []
    for key in ("capabilities=", "values="):
        idx = content.find(key)
        if idx < 0:
            continue
        raw = content[idx + len(key):]
        end = raw.find("]")
        if end >= 0:
            raw = raw[: end + 1]
        try:
            parsed = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            parsed = []
        if key.startswith("capabilities"):
            caps = parsed
        else:
            vals = parsed
    return ([str(c) for c in caps], [str(v) for v in vals])