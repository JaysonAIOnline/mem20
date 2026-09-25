"""Deterministic procedural primitives: PRNG and value noise.

Hermetic — no external deps. SplitMix64 PRNG for seeding, xorshift stream,
and 1D/2D fractal value noise for terrain/tile generation.
"""

from __future__ import annotations

import math
import random
from typing import List, Tuple


class DeterministicPRNG:
    """Seeded PRNG (splitmix64 stream) for reproducible generation."""

    def __init__(self, seed: int = 0):
        self.seed = int(seed)
        self._state = self._splitmix64(self.seed)

    @staticmethod
    def _splitmix64(seed: int) -> int:
        z = (seed + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9 & 0xFFFFFFFFFFFFFFFF
        z = (z ^ (z >> 27)) * 0x94D049BB133111EB & 0xFFFFFFFFFFFFFFFF
        return z ^ (z >> 31)

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

    def choice(self, seq: List) -> object:
        if not seq:
            raise IndexError("choice from empty sequence")
        return seq[self.int(0, len(seq) - 1)]

    def shuffle(self, seq: List) -> List:
        out = list(seq)
        for i in range(len(out) - 1, 0, -1):
            j = self.int(0, i)
            out[i], out[j] = out[j], out[i]
        return out

    def sample(self, seq: List, k: int) -> List:
        if k >= len(seq):
            return self.shuffle(seq)
        return self.shuffle(seq)[:k]

    def seed_rng(self) -> random.Random:
        return random.Random(self._next() & 0xFFFFFFFF)


class ValueNoise:
    """Grid-based value noise with smoothstep interpolation."""

    def __init__(self, prng: DeterministicPRNG):
        self._cells: dict = {}
        self._prng = prng

    def _cell(self, x: int, y: int) -> float:
        key = (x, y)
        if key not in self._cells:
            v = DeterministicPRNG((x * 374761393 + y * 668265263 + self._prng.seed) & 0xFFFFFFFF)
            self._cells[key] = v.float()
        return self._cells[key]

    @staticmethod
    def _fade(t: float) -> float:
        return t * t * (3 - 2 * t)

    def noise(self, x: float, y: float = 0.0) -> float:
        x0, y0 = math.floor(x), math.floor(y)
        fx, fy = x - x0, y - y0
        ux, uy = self._fade(fx), self._fade(fy)
        if y is None or (hasattr(y, "__float__") is False):
            pass
        a = self._cell(x0, y0)
        b = self._cell(x0 + 1, y0)
        c = self._cell(x0, y0 + 1)
        d = self._cell(x0 + 1, y0 + 1)
        top = a + (b - a) * ux
        bottom = c + (d - c) * ux
        return top + (bottom - top) * uy

    def octaves(self, x: float, y: float, octaves: int = 4, persistence: float = 0.5, lacunarity: float = 2.0) -> float:
        total, amp, freq, norm = 0.0, 1.0, 1.0, 0.0
        for _ in range(octaves):
            total += self.noise(x * freq, y * freq) * amp
            norm += amp
            amp *= persistence
            freq *= lacunarity
        return total / norm if norm else 0.0


def grid(w: int, h: int, prng: DeterministicPRNG, octaves: int = 3) -> List[List[float]]:
    noise = ValueNoise(prng)
    return [[noise.octaves(x / max(w, 1) * 6, y / max(h, 1) * 6, octaves=octaves) for x in range(w)] for y in range(h)]


def in_bounds(x: int, y: int, w: int, h: int) -> bool:
    return 0 <= x < w and 0 <= y < h