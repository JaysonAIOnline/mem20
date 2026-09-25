"""Procedural content generators: terrain, dungeons, treasure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from .prng import DeterministicPRNG, ValueNoise, grid, in_bounds


@dataclass(eq=False)
class Generator:
    """Base generator."""

    name: str = "generator"

    def generate(self, config) -> object:
        raise NotImplementedError


@dataclass(eq=False)
class TerrainGenerator(Generator):
    """Heightmap / biome terrain from value-noise octaves."""

    name: str = "terrain"

    def generate(self, config) -> List[List[float]]:
        prng = DeterministicPRNG(config.seed)
        return grid(config.width, config.height, prng, octaves=4)

    def to_tiles(self, heightmap: List[List[float]], levels: int = 8) -> List[List[int]]:
        w, h = len(heightmap[0]), len(heightmap)
        return [[min(levels - 1, int(v * levels)) for v in row] for row in heightmap]


@dataclass(eq=False)
class BSPDungeonGenerator(Generator):
    """BSP (binary space partition) dungeon: rooms + corridors."""

    name: str = "dungeon"

    def generate(self, config) -> Dict:
        prng = DeterministicPRNG(config.seed + 7)
        w, h = config.width, config.height
        tile = [[0] * w for _ in range(h)]  # 0 = wall
        rooms = self._carve_rooms(prng, tile)
        self._connect_rooms(prng, tile, rooms)
        spawn = center(rooms[0]) if rooms else (0, 0)
        return {"tiles": tile, "rooms": rooms, "spawn": spawn}

    def _split(self, prng, minx, miny, maxx, maxy, depth):
        regions = []
        self._split_rec(prng, minx, miny, maxx, maxy, depth, regions)
        return regions

    def _split_rec(self, prng, minx, miny, maxx, maxy, depth, out):
        w = maxx - minx
        h = maxy - miny
        if depth <= 0 or w < 8 or h < 8:
            out.append((minx, miny, maxx, maxy))
            return
        horizontal = w < h
        if horizontal:
            split = prng.int(miny + 4, maxy - 4)
            self._split_rec(prng, minx, miny, maxx, split, depth - 1, out)
            self._split_rec(prng, minx, split, maxx, maxy, depth - 1, out)
        else:
            split = prng.int(minx + 4, maxx - 4)
            self._split_rec(prng, minx, miny, split, maxy, depth - 1, out)
            self._split_rec(prng, split, miny, maxx, maxy, depth - 1, out)

    def _carve_rooms(self, prng, tile) -> List[Tuple[int, int, int, int]]:
        w, h = len(tile[0]), len(tile)
        rooms = []
        for _ in range(32):
            rw = prng.int(4, 9)
            rh = prng.int(4, 9)
            x = prng.int(1, w - rw - 2)
            y = prng.int(1, h - rh - 2)
            for yy in range(y, y + rh):
                for xx in range(x, x + rw):
                    tile[yy][xx] = 1
            rooms.append((x, y, x + rw, y + rh))
        return rooms

    def _connect_rooms(self, prng, tile, rooms) -> None:
        for (prev, room) in in_pairs(rooms):
            x1, y1 = center(prev)
            x2, y2 = center(room)
            if x1 == x2 and y1 == y2:
                continue
            if prng.float() < 0.5:
                self._carve_h(tile, y1, min(x1, x2), max(x1, x2))
                self._carve_v(tile, x2, min(y1, y2), max(y1, y2))
            else:
                self._carve_v(tile, x1, min(y1, y2), max(y1, y2))
                self._carve_h(tile, y2, min(x1, x2), max(x1, x2))

    def _carve_h(self, tile, y, x0, x1):
        for x in range(x0, x1 + 1):
            if in_bounds(x, y, len(tile[0]), len(tile)):
                tile[y][x] = 1

    def _carve_v(self, tile, x, y0, y1):
        for y in range(y0, y1 + 1):
            if in_bounds(x, y, len(tile[0]), len(tile)):
                tile[y][x] = 1


@dataclass(eq=False)
class LootGenerator(Generator):
    """Spawn weighted loot tables."""

    name: str = "loot"

    def generate(self, config) -> List[Dict]:
        prng = DeterministicPRNG(config.seed + 3)
        items = []
        names = ["sword", "shield", "potion", "gem", "armor", "scroll", "key", "relic"]
        for i in range(config.items_per_level):
            items.append({
                "id": i,
                "name": prng.choice(names),
                "rarity": prng.choice(["common", "uncommon", "rare", "epic"]),
                "tier": prng.int(1, 5),
            })
        return items


def center(room: Tuple[int, int, int, int]) -> Tuple[int, int]:
    x0, y0, x1, y1 = room
    return (x0 + x1) // 2, (y0 + y1) // 2


def in_pairs(seq: List) -> List[Tuple]:
    return [(seq[i], seq[i + 1]) for i in range(len(seq) - 1)]