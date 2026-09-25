"""Characters, stats, skills, progression."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class StatBlock:
    """Core attributes."""

    strength: int = 10
    dexterity: int = 10
    constitution: int = 10
    intelligence: int = 10
    wisdom: int = 10
    charisma: int = 10

    def modifier(self, stat: str) -> int:
        value = getattr(self, stat)
        return (value - 10) // 2

    def to_dict(self) -> Dict:
        return {k: getattr(self, k) for k in ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")}

    @classmethod
    def from_dict(cls, d: Dict) -> "StatBlock":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Skill:
    """A defined skill/ability."""

    name: str
    level: int = 1
    kind: str = "combat"  # combat | magic | craft | social
    description: str = ""

    def to_dict(self) -> Dict:
        return {"name": self.name, "level": self.level, "kind": self.kind, "description": self.description}


class Character:
    """An RPG character with stats, XP, level progression."""

    XP_CURVE = [0, 100, 250, 500, 900, 1500, 2300, 3400, 4800, 6500]

    def __init__(self, name: str, archetype: str = "adventurer", stats: Optional[StatBlock] = None):
        self.name = name
        self.archetype = archetype
        self.stats = stats or StatBlock()
        self.level = 1
        self.xp = 0
        self.hp = self.max_hp()
        self.mp = self.max_mp()
        self.skills: List[Skill] = []
        self.alive = True

    def max_hp(self) -> int:
        return 20 + self.stats.modifier("constitution") * 5 + (self.level - 1) * 8

    def max_mp(self) -> int:
        return max(5, 5 + self.stats.modifier("intelligence") * 3 + (self.level - 1) * 3)

    def gain_xp(self, amount: int) -> int:
        """Returns number of levels gained."""
        self.xp += amount
        gained = 0
        while self.level < len(self.XP_CURVE) and self.xp >= self.xp_for_level(self.level + 1):
            self.level += 1
            gained += 1
        self.hp = self.max_hp()
        self.mp = self.max_mp()
        return gained

    def xp_for_level(self, level: int) -> int:
        if level - 1 < len(self.XP_CURVE):
            return self.XP_CURVE[level - 1]
        prev = self.XP_CURVE[-1]
        for lv in range(len(self.XP_CURVE) + 1, level + 1):
            prev = prev + prev // 3
        return prev

    def add_skill(self, skill: Skill) -> None:
        existing = next((s for s in self.skills if s.name == skill.name), None)
        if existing:
            existing.level = max(existing.level, skill.level)
        else:
            self.skills.append(skill)

    def has_skill(self, name: str) -> bool:
        return any(s.name == name for s in self.skills)

    def take_damage(self, dmg: int) -> int:
        self.hp = max(0, self.hp - dmg)
        if self.hp == 0:
            self.alive = False
        return self.hp

    def heal(self, amount: int) -> int:
        self.hp = min(self.max_hp(), self.hp + amount)
        self.alive = self.hp > 0
        return self.hp

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "archetype": self.archetype,
            "level": self.level,
            "xp": self.xp,
            "hp": self.hp,
            "mp": self.mp,
            "stats": self.stats.to_dict(),
            "skills": [s.to_dict() for s in self.skills],
            "alive": self.alive,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "Character":
        c = cls(d["name"], d.get("archetype", "adventurer"), StatBlock.from_dict(d.get("stats", {})))
        c.level = d.get("level", 1)
        c.xp = d.get("xp", 0)
        c.hp = d.get("hp", c.max_hp())
        c.mp = d.get("mp", d.get("hp", c.max_mp()))
        c.alive = d.get("alive", True)
        for s in d.get("skills", []):
            c.add_skill(Skill(**s))
        return c


def create_party(names: List[str], archetype: str = None, seed: int = 0) -> List[Character]:
    from .rng import RpgRandom

    rng = RpgRandom(seed)
    archetypes = ["warrior", "rogue", "mage", "cleric", "ranger"]
    party = []
    for name in names:
        arch = archetype or rng.choice(archetypes)
        stats = StatBlock(
            strength=rng.int(6, 18),
            dexterity=rng.int(6, 18),
            constitution=rng.int(6, 18),
            intelligence=rng.int(6, 18),
            wisdom=rng.int(6, 18),
            charisma=rng.int(6, 18),
        )
        party.append(Character(name, arch, stats))
    return party