"""Combat resolution — deterministic, seeded turn-based combat."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .character import Character
from .rng import RpgRandom


@dataclass
class Combatant:
    """Combat wrapper exposing stats used by resolution formulas."""

    name: str
    hp: int
    max_hp: int
    attack: int = 10
    defense: int = 10
    speed: int = 10
    is_player: bool = True
    alive: bool = True

    @classmethod
    def from_character(cls, c: Character, is_player: bool = True) -> "Combatant":
        atk = c.stats.strength + c.stats.modifier("strength")
        return cls(
            name=c.name,
            hp=c.hp,
            max_hp=c.max_hp(),
            attack=atk + c.stats.modifier("dexterity"),
            defense=10 + c.stats.modifier("dexterity") + c.stats.modifier("constitution"),
            speed=10 + c.stats.modifier("dexterity"),
            is_player=is_player,
            alive=c.alive,
        )

    def to_dict(self) -> Dict:
        return {"name": self.name, "hp": self.hp, "max_hp": self.max_hp, "attack": self.attack, "defense": self.defense, "speed": self.speed, "is_player": self.is_player, "alive": self.alive}


@dataclass
class CombatAction:
    """One resolved combat step."""

    actor: str
    target: str
    action: str  # attack | skill | flee
    hit: bool = False
    damage: int = 0
    critical: bool = False

    def to_dict(self) -> Dict:
        return {"actor": self.actor, "target": self.target, "action": self.action, "hit": self.hit, "damage": self.damage, "critical": self.critical}


class CombatEngine:
    """Seeded, reproducible combat between two combatants."""

    def __init__(self, seed: int = 0):
        self.rng = RpgRandom(seed)
        self.log: List[CombatAction] = []

    def resolve_attack(self, attacker: Combatant, defender: Combatant) -> CombatAction:
        atk_bonus = max(1, (attacker.attack - defender.defense) // 2 + 1)
        hit_chance = min(0.95, 0.4 + atk_bonus / 10.0)
        hit = self.rng.chance(hit_chance)
        critical = False
        damage = 0
        if hit:
            critical = self.rng.chance(0.1)
            base = self.rng.roll(6, count=2, bonus=max(0, attacker.attack // 4))
            damage = base * 2 if critical else base
            defender.hp = max(0, defender.hp - damage)
            if defender.hp == 0:
                defender.alive = False
        action = CombatAction(attacker.name, defender.name, "attack", hit, damage, critical)
        self.log.append(action)
        return action

    def battle(self, a: Combatant, b: Combatant) -> Dict:
        """Fight to the death. Returns outcome summary."""
        while a.alive and b.alive:
            first, second = (a, b) if a.speed >= b.speed else (b, a)
            if first.alive:
                self.resolve_attack(first, second if second is not a else b)
            if second.alive:
                self.resolve_attack(second, first if first is not b else a)
        winner = a if a.alive else b
        return {
            "winner": winner.name,
            "a": a.to_dict(),
            "b": b.to_dict(),
            "turns": len(self.log),
            "log": [x.to_dict() for x in self.log],
        }

    def clear(self) -> None:
        self.log = []