"""Narrative engine: seeded quest hooks, story beats, dialogue templates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .prng import DeterministicPRNG


@dataclass
class StoryBeat:
    """One narrative beat."""

    index: int
    kind: str  # hook | twist | climax | resolution
    text: str

    def to_dict(self) -> Dict:
        return {"index": self.index, "kind": self.kind, "text": self.text}


class NarrativeEngine:
    """Generates coherent story segments from seeded templates."""

    HOOKS = [
        "an ancient signal pulses from the {place}",
        "the {faction} has seized the {artifact}",
        "a stranger arrives bearing a {clue}",
    ]
    TWISTS = [
        "the ally was the {betrayer} all along",
        "the {artifact} was a decoy",
        "two factions secretly share the same {motive}",
    ]
    CLIMAXES = [
        "all routes converge at the {throne}",
        "the {gate} opens only at high {beacon}",
        "a final {choice} decides the {realm}",
    ]
    RESOLUTIONS = [
        "peace returns, but the {remnant} waits",
        "the {realm} finds a new {guardian}",
        "the {story} is retold for generations",
    ]

    def __init__(self, seed: int = 0):
        self.prng = DeterministicPRNG(seed)
        self.beats: List[StoryBeat] = []

    @staticmethod
    def _fill(template: str, tokens: Dict[str, str]) -> str:
        for key, value in tokens.items():
            template = template.replace("{" + key + "}", value)
        return template

    def tokens(self) -> Dict[str, str]:
        words = {
            "place": ["crypt", "highlands", "sunken city", "ash plains"],
            "faction": ["Order", "Cult", "Mercenary Guild", "Old Guard"],
            "artifact": ["Relic of Dawn", "Null Crown", "Echo Blade", "Argus Lens"],
            "betrayer": ["trusted captain", "childhood friend", "masked oracle"],
            "motive": ["hunger for power", "buried debt", "prophecy"],
            "throne": ["Glass Throne", "Thorn Court", "Ash Seat"],
            "gate": ["Sky Gate", "Root Door", "Bone Arch"],
            "beacon": ["moon", "neverlight", "beacon"],
            "choice": ["sacrifice", "alliance", "truce"],
            "realm": ["kingdom", "undervale", "empire"],
            "clue": ["cipher", "map fragment", "heirloom"],
            "remnant": ["shadow", "echo", "sealed hunger"],
            "guardian": ["keeper", "quiet sworn", "warden"],
            "story": ["tale", "legend", "song"],
        }
        return {k: self.prng.choice(v) for k, v in words.items()}

    def generate(self, segments: int = 12) -> List[StoryBeat]:
        self.beats = []
        kinds = ["hook"] + ["twist"] * (segments // 3) + ["climax"] + ["resolution"]
        for i in range(segments):
            kind = kinds[i] if i < len(kinds) else ("twist" if i % 3 else "hook")
            if kind == "hook":
                text = self._fill(self.prng.choice(self.HOOKS), self.tokens())
            elif kind == "twist":
                text = self._fill(self.prng.choice(self.TWISTS), self.tokens())
            elif kind == "climax":
                text = self._fill(self.prng.choice(self.CLIMAXES), self.tokens())
            else:
                text = self._fill(self.prng.choice(self.RESOLUTIONS), self.tokens())
            self.beats.append(StoryBeat(index=i, kind=kind, text=text))
        return self.beats

    def quest_hooks(self, count: int = 4) -> List[Dict]:
        out = []
        for i in range(count):
            text = self._fill(self.prng.choice(self.HOOKS), self.tokens())
            out.append({"id": f"quest_{i}", "title": text.title(), "kind": "primary" if i == 0 else "side"})
        return out

    def compile(self) -> Dict:
        return {"beats": [b.to_dict() for b in self.beats], "quests": self.quest_hooks()}