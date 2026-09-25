"""Asset synthesis: textures, sprites, palettes, audio."""

from __future__ import annotations

import math
import struct
import wave
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .prng import DeterministicPRNG, ValueNoise


def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


@dataclass
class Palette:
    """Color palette."""

    colors: List[Tuple[int, int, int]] = None  # noqa: RUF012 (mutable default handled in post_init)

    def __post_init__(self):
        if self.colors is None:
            self.colors = [(r, g, b) for r, g, b in [(0x1B, 0x1B, 0x2F), (0xB4, 0x3A, 0x3A), (0x7C, 0x6B, 0x2E), (0x3A, 0x6E, 0x4B), (0x2E, 0x4B, 0x7C)]]

    @classmethod
    def from_seed(cls, seed: int) -> "Palette":
        prng = DeterministicPRNG(seed)
        cols = []
        for _ in range(5):
            cols.append((prng.int(0, 255), prng.int(0, 255), prng.int(0, 255)))
        return cls(colors=cols)

    def index(self, v: float) -> Tuple[int, int, int]:
        i = int(clamp(v) * (len(self.colors) - 1))
        return self.colors[i]


class TextureSynthesizer:
    """Procedural texture generation (value-noise tile maps)."""

    def __init__(self, resolution: int = 32, seed: int = 0):
        self.resolution = resolution
        self.prng = DeterministicPRNG(seed)
        self.noise = ValueNoise(self.prng)

    def generate(self, palette: Palette, octaves: int = 4, scale: float = 3.0) -> List[List[Tuple[int, int, int]]]:
        n = self.resolution
        out = []
        for y in range(n):
            row = []
            for x in range(n):
                v = self.noise.octaves(x / n * scale, y / n * scale, octaves=octaves)
                row.append(palette.index(v))
            out.append(row)
        return out

    def export_ppm(self, pixels: List[List[Tuple[int, int, int]]], path: str) -> str:
        n = len(pixels)
        with open(path, "w") as f:
            f.write(f"P3\n{n} {n}\n255\n")
            for row in pixels:
                for r, g, b in row:
                    f.write(f"{r} {g} {b}\n")
        return path


class AudioSynthesizer:
    """Procedural audio synthesis (square/sine/noise at 22050 Hz)."""

    RATE = 22050

    def __init__(self, seed: int = 0):
        self.prng = DeterministicPRNG(seed)

    def tone(self, freq: float, duration: float, volume: float = 0.3, kind: str = "sine") -> bytes:
        n = int(self.RATE * duration)
        if kind == "square":
            samples = [0.5 if math.sin(2 * math.pi * freq * i / self.RATE) >= 0 else -0.5 for i in range(n)]
        elif kind == "saw":
            samples = [2 * ((freq * i / self.RATE) % 1) - 1 for i in range(n)]
        elif kind == "noise":
            samples = [self.prng.float() * 2 - 1 for _ in range(n)]
        else:
            samples = [math.sin(2 * math.pi * freq * i / self.RATE) for i in range(n)]
        return self._encode([s * volume for s in samples])

    def _encode(self, samples: List[float]) -> bytes:
        frames = bytearray()
        for s in samples:
            v = max(-1.0, min(1.0, s))
            frames += struct.pack("<h", int(v * 32767))
        return bytes(frames)

    def export_wav(self, data: bytes, path: str) -> str:
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.RATE)
            w.writeframes(data)
        return path


class AssetSynthesizer:
    """Top-level asset factory wrapping texture + audio synthesis."""

    def __init__(self, config):
        self.config = config
        self.textures = TextureSynthesizer(config.asset_resolution, config.seed)
        self.audio = AudioSynthesizer(config.seed)

    def synthesise_texture(self, palette: Palette = None, octaves: int = 4) -> List[List[Tuple[int, int, int]]]:
        if palette is None:
            palette = Palette.from_seed(self.config.seed)
        return self.textures.generate(palette, octaves=octaves)

    def synthesise_sfx(self) -> bytes:
        return self.audio.tone(440, 0.1, kind="square") + self.audio.tone(880, 0.1, kind="square")

    def manifest(self) -> Dict:
        return {
            "texture": self.synthesise_texture(),
            "pixel_size": self.config.asset_resolution,
            "audio": self.synthesise_sfx(),
        }