"""Inventory, items, equipment."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Item:
    """A portable item."""

    name: str
    kind: str = "misc"  # weapon | armor | potion | key | quest | misc
    value: int = 0
    weight: float = 1.0
    effect: Dict = field(default_factory=dict)
    count: int = 1

    def to_dict(self) -> Dict:
        return {"name": self.name, "kind": self.kind, "value": self.value, "weight": self.weight, "effect": self.effect, "count": self.count}

    @classmethod
    def from_dict(cls, d: Dict) -> "Item":
        return cls(**d)


@dataclass
class Inventory:
    """Bounded inventory with item stacking."""

    capacity: int = 24
    items: List[Item] = field(default_factory=list)

    def __len__(self) -> int:
        return sum(i.count for i in self.items)

    def is_full(self) -> bool:
        return len(self) >= self.capacity

    def add(self, item: Item) -> bool:
        if item.count <= 0:
            return True
        for existing in self.items:
            if existing.name == item.name and existing.kind == item.kind:
                existing.count += item.count
                return True
        if self.is_full():
            return False
        self.items.append(item)
        return True

    def remove(self, name: str, count: int = 1) -> bool:
        for existing in self.items:
            if existing.name == name:
                if existing.count <= count:
                    self.items.remove(existing)
                else:
                    existing.count -= count
                return True
        return False

    def count_of(self, name: str) -> int:
        for existing in self.items:
            if existing.name == name:
                return existing.count
        return 0

    def all_of_kind(self, kind: str) -> List[Item]:
        return [i for i in self.items if i.kind == kind]

    def total_weight(self) -> float:
        return sum(i.weight * i.count for i in self.items)

    def to_dict(self) -> Dict:
        return {"capacity": self.capacity, "items": [i.to_dict() for i in self.items]}

    @classmethod
    def from_dict(cls, d: Dict) -> "Inventory":
        return cls(d.get("capacity", 24), [Item.from_dict(i) for i in d.get("items", [])])


EQUIPMENT_SLOTS = {"weapon", "armor", "shield", "head", "feet", "ring", "amulet"}


@dataclass
class Equipment:
    """Equippable slots per character."""

    slots: Dict[str, Optional[Item]] = field(default_factory=dict)

    def __post_init__(self):
        if not self.slots:
            self.slots = {slot: None for slot in EQUIPMENT_SLOTS}

    def equip(self, slot: str, item: Item) -> Optional[Item]:
        if slot not in EQUIPMENT_SLOTS or item.kind != "equip":
            return None
        old = self.slots.get(slot)
        self.slots[slot] = item
        return old

    def unequip(self, slot: str) -> Optional[Item]:
        item = self.slots.get(slot)
        self.slots[slot] = None
        return item

    def equipped(self) -> List[Item]:
        return [i for i in self.slots.values() if i is not None]

    def bonus(self, stat: str) -> int:
        total = 0
        for item in self.equipped():
            total += item.effect.get(stat, 0)
        return total

    def to_dict(self) -> Dict:
        return {slot: (item.to_dict() if item else None) for slot, item in self.slots.items()}

    @classmethod
    def from_dict(cls, d: Dict) -> "Equipment":
        eq = cls()
        eq.slots = {s: (Item.from_dict(i) if i else None) for s, i in d.items()}
        return eq