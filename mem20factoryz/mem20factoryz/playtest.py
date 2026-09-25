"""Playtester: simulate playthroughs against a generated level, collect metrics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .level import Level
from .prng import DeterministicPRNG


@dataclass
class PlaytestResult:
    """Outcome of one simulated playthrough."""

    seed: int
    completed: bool
    steps: int
    deaths: int
    loot_collected: int
    damage_taken: float = 0.0
    damage_dealt: float = 0.0

    def summary(self) -> Dict:
        return {
            "seed": self.seed,
            "completed": self.completed,
            "steps": self.steps,
            "deaths": self.deaths,
            "loot_collected": self.loot_collected,
            "damage_taken": round(self.damage_taken, 2),
            "damage_dealt": round(self.damage_dealt, 2),
        }


class Playtester:
    """Runs N seeded playthroughs (mock agent) to evaluate a level."""

    def __init__(self, config):
        self.config = config

    def run(self, level: Level, runs: int = 1, seeds: List[int] = None) -> List[PlaytestResult]:
        cfg = self.config
        results = []
        use_seeds = seeds or [cfg.seed + i for i in range(runs)]
        for seed in use_seeds:
            results.append(self._single(level, seed))
        return results

    def _single(self, level: Level, seed: int) -> PlaytestResult:
        prng = DeterministicPRNG(seed)
        cfg = self.config
        steps = 0
        deaths = 0
        loot = 0
        dmg_taken, dmg_dealt = 0.0, 0.0
        enemies_left = sum(1 for e in level.entities if e["type"] == "enemy")
        objectives = max(1, len(level.objectives))
        complete_need = objectives  # one objective per ~supported target

        while steps < cfg.max_playtest_steps:
            steps += 1
            event = prng.float()
            if event < 0.25 and enemies_left > 0:
                dmg_dealt += prng.float() * 10 + 5
                if prng.float() < 0.5:
                    enemies_left -= 1
                else:
                    deaths += 1
                    dmg_taken += prng.float() * 8 + 2
            elif event < 0.4:
                loot += 1
            if enemies_left == 0 and loot >= complete_need:
                return PlaytestResult(seed, True, steps, deaths, loot, dmg_taken, dmg_dealt)

        return PlaytestResult(seed, False, steps, deaths, loot, dmg_taken, dmg_dealt)

    def aggregate(self, results: List[PlaytestResult]) -> Dict:
        if not results:
            return {}
        completion = sum(1 for r in results if r.completed) / len(results)
        return {
            "runs": len(results),
            "completion_rate": round(completion, 3),
            "avg_steps": round(sum(r.steps for r in results) / len(results), 2),
            "avg_deaths": round(sum(r.deaths for r in results) / len(results), 2),
            "avg_loot": round(sum(r.loot_collected for r in results) / len(results), 2),
        }