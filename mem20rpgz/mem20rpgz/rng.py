"""Deterministic PRNG shared by mem20rpgz systems."""

from __future__ import annotations


class RpgRandom:
    """Seeded splitmix64 stream — reproducible dice rolls and drops."""

    def __init__(self, seed: int = 0):
        self._state = (int(seed) + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF

    def _next(self) -> int:
        self._state = (self._state + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = self._state
        z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9 & 0xFFFFFFFFFFFFFFFF
        z = (z ^ (z >> 27)) * 0x94D049BB133111EB & 0xFFFFFFFFFFFFFFFF
        return z ^ (z >> 31)

    def float(self) -> float:
        return self._next() / float(1 << 64)

    def int(self, lo: int, hi: int) -> int:
        if hi <= lo:
            return lo
        return lo + int(self.float() * (hi - lo + 1))

    def roll(self, sides: int, count: int = 1, bonus: int = 0) -> int:
        total = bonus
        for _ in range(count):
            total += self.int(1, sides)
        return total

    def chance(self, pct: float) -> bool:
        return self.float() < min(1.0, max(0.0, pct))

    def choice(self, seq):
        return seq[self.int(0, len(seq) - 1)]