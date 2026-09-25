"""Blender operator catalog: real index over 2 498 `bpy.ops` from Blender 5.2 LTS.

The data is the genuine `bpy.ops` surface captured from Blender itself, so
`exists()` is a fact about Blender, not an assumption.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "data", "blender_ops.json")

OP_PREFIX = "bpy.ops."


class CatalogError(RuntimeError):
    pass


@dataclass(frozen=True)
class Op:
    name: str
    module: str
    function: str

    def as_dict(self) -> dict:
        return {"name": self.name, "module": self.module,
                "function": self.function}


class Catalog:
    """Indexed, read-only view over the captured Blender operator surface."""

    def __init__(self, ops: list[str], modules: dict[str, int],
                 blender_version: str):
        self._ops: dict[str, Op] = {}
        for name in ops:
            self._ops[name] = _parse(name)
        self._modules = dict(modules)
        self.blender_version = blender_version

    # ---------------------------------------------------------- properties
    @property
    def count(self) -> int:
        return len(self._ops)

    @property
    def modules(self) -> dict[str, int]:
        return dict(sorted(self._modules.items(), key=lambda kv: (-kv[1], kv[0])))

    def names(self) -> list[str]:
        return sorted(self._ops)

    # ------------------------------------------------------------- queries
    def exists(self, op_name: str) -> bool:
        return op_name in self._ops

    def get(self, op_name: str) -> Op | None:
        return self._ops.get(op_name)

    def require(self, op_name: str) -> Op:
        op = self._ops.get(op_name)
        if op is None:
            raise CatalogError(f"unknown Blender op: {op_name}")
        return op

    def in_module(self, module: str) -> list[str]:
        prefix = f"{OP_PREFIX}{module}."
        return [n for n in self.names() if n.startswith(prefix)]

    def search(self, term: str, limit: int = 50) -> list[str]:
        needle = term.strip().lower()
        if not needle:
            return []
        return [n for n in self.names() if needle in n.lower()][:limit]

    def stats(self) -> dict:
        return {
            "blender_version": self.blender_version,
            "operators": self.count,
            "modules": len(self._modules),
        }


def _parse(name: str) -> Op:
    body = name[len(OP_PREFIX):] if name.startswith(OP_PREFIX) else name
    module, _, function = body.partition(".")
    return Op(name=name, module=module, function=function or body)


@lru_cache(maxsize=4)
def load(path: str | None = None) -> Catalog:
    target = path or DATA_FILE
    if not os.path.exists(target):
        raise CatalogError(f"catalog data not found: {target}")
    with open(target, encoding="utf-8") as fh:
        raw = json.load(fh)
    for required in ("all_ops_flat", "ops_by_module", "blender_version"):
        if required not in raw:
            raise CatalogError(f"catalog missing {required!r}")
    return Catalog(list(raw["all_ops_flat"]), dict(raw["ops_by_module"]),
                   str(raw["blender_version"]))
