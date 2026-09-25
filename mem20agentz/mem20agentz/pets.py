"""Pets — petdex companions persisted in the mem20 ledger (sub-phase 2.3).

A pet is a named companion with species + stats (happiness, energy). Care
actions adjust stats; pets persist through remember/recall so they survive
restarts. No deletion: the store keeps the record forever, new states are
written on top.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ._substrate import Backend, get_backend

TOPIC = "petdex"


@dataclass
class Pet:
    name: str
    species: str
    stats: dict = field(default_factory=lambda: {"happiness": 50, "energy": 50})

    def clamp(self) -> "Pet":
        self.stats = {k: max(0, min(100, int(v)))
                      for k, v in self.stats.items()}
        return self


class Petdex:
    def __init__(self, backend: Optional[Backend] = None) -> None:
        self._b = backend or get_backend()

    def adopt(self, name: str, species: str) -> Pet:
        pet = Pet(name=name, species=species).clamp()
        self._b.remember(topic=TOPIC, content=_encode(pet),
                         tags=["mem20agentz", "pet", name], actor="mem20agentz")
        return pet

    def list(self) -> list[Pet]:
        out = []
        for hit in self._b.recall(topic=TOPIC, tags=["mem20agentz", "pet"],
                                  k=50):
            pet = _decode(hit)
            if pet:
                out.append(pet)
        # dedupe by name, keep the newest record per pet
        merged: dict[str, Pet] = {}
        for pet in out:
            merged[pet.name] = pet
        return list(merged.values())

    def get(self, name: str) -> Optional[Pet]:
        for pet in self.list():
            if pet.name == name:
                return pet
        return None

    def care(self, name: str, act: str) -> Optional[Pet]:
        pet = self.get(name)
        if pet is None:
            return None
        if act == "feed":
            pet.stats["energy"] += 10
            pet.stats["happiness"] += 5
        elif act == "play":
            pet.stats["happiness"] += 15
            pet.stats["energy"] -= 5
        elif act == "rest":
            pet.stats["energy"] += 20
        pet.clamp()
        self._b.remember(topic=TOPIC, content=_encode(pet),
                         tags=["mem20agentz", "pet", name], actor="mem20agentz")
        return pet


def _encode(pet: Pet) -> str:
    return (f"pet {pet.name} | species={pet.species} | "
            f"happiness={pet.stats['happiness']} | energy={pet.stats['energy']}")


def _decode(hit: dict) -> Optional[Pet]:
    if not isinstance(hit, dict):
        return None
    content = hit.get("content") or ""
    if not content.startswith("pet "):
        return None
    try:
        head, _, rest = content.partition(" | ")
        name = head.split(" ", 1)[1]
        species = _val(rest, "species")
        happiness = int(_val(rest, "happiness"))
        energy = int(_val(rest, "energy"))
    except (IndexError, ValueError):
        return None
    return Pet(name=name, species=species,
               stats={"happiness": happiness, "energy": energy})


def _val(text: str, key: str) -> str:
    for part in text.split(" | "):
        k, _, v = part.partition("=")
        if k == key:
            return v
    return ""