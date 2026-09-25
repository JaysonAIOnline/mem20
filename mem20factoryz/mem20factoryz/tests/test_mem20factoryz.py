"""Hermetic tests for mem20factoryz."""

from __future__ import annotations

import unittest

from mem20factoryz.config import FactoryConfig
from mem20factoryz.prng import DeterministicPRNG, ValueNoise, grid
from mem20factoryz.generator import TerrainGenerator, BSPDungeonGenerator, LootGenerator
from mem20factoryz.assets import Palette, TextureSynthesizer, AudioSynthesizer, AssetSynthesizer
from mem20factoryz.level import LevelBuilder
from mem20factoryz.narrative import NarrativeEngine
from mem20factoryz.playtest import Playtester


def cfg(**kw):
    return FactoryConfig(**kw)


class TestConfig(unittest.TestCase):
    def test_defaults(self):
        c = cfg()
        self.assertEqual(c.seed, 20260910)
        self.assertEqual(c.width, 64)
        self.assertEqual(c.port, 8016)
        self.assertIn("http://127.0.0.1:4000", c.gateway_url)

    def test_yaml_roundtrip(self):
        import os
        import tempfile

        c = cfg(seed=42, width=32)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            c.save(f.name)
            f.flush()
            c2 = FactoryConfig.load(f.name)
        os.unlink(f.name)
        self.assertEqual(c2.seed, 42)
        self.assertEqual(c2.width, 32)


class TestPRNG(unittest.TestCase):
    def test_deterministic(self):
        a = DeterministicPRNG(99)
        b = DeterministicPRNG(99)
        self.assertEqual([a.float() for _ in range(10)], [b.float() for _ in range(10)])

    def test_float_range(self):
        r = DeterministicPRNG(1)
        for _ in range(100):
            v = r.float()
            self.assertTrue(0.0 <= v <= 1.0)

    def test_int_range(self):
        r = DeterministicPRNG(2)
        for _ in range(100):
            v = r.int(3, 7)
            self.assertIn(v, range(3, 8))

    def test_shuffle_stable(self):
        r1, r2 = DeterministicPRNG(5), DeterministicPRNG(5)
        self.assertEqual(r1.shuffle([1, 2, 3, 4]), r2.shuffle([1, 2, 3, 4]))

    def test_noise_range(self):
        n = ValueNoise(DeterministicPRNG(7))
        for _ in range(50):
            v = n.noise(_ * 0.37, _ * 0.11)
            self.assertGreaterEqual(v, 0.0)
            self.assertLessEqual(v, 1.0)

    def test_grid_shape(self):
        g = grid(12, 9, DeterministicPRNG(3))
        self.assertEqual(len(g), 9)
        self.assertEqual(len(g[0]), 12)


class TestGenerators(unittest.TestCase):
    def test_terrain(self):
        c = cfg(width=16, height=16)
        hmap = TerrainGenerator().generate(c)
        self.assertEqual(len(hmap), 16)
        self.assertEqual(len(hmap[0]), 16)
        tiles = TerrainGenerator().to_tiles(hmap, levels=4)
        self.assertEqual(max(max(r) for r in tiles), 3)
        self.assertEqual(min(min(r) for r in tiles), 0)

    def test_dungeon(self):
        c = cfg(width=32, height=32)
        result = BSPDungeonGenerator().generate(c)
        self.assertIn("tiles", result)
        self.assertIn("rooms", result)
        self.assertTrue(len(result["rooms"]) > 0)
        h, w = len(result["tiles"]), len(result["tiles"][0])
        self.assertEqual((w, h), (32, 32))
        self.assertIsInstance(result["spawn"], tuple)

    def test_dungeon_deterministic(self):
        c = cfg(seed=7, width=24, height=24)
        a = BSPDungeonGenerator().generate(c)
        b = BSPDungeonGenerator().generate(c)
        self.assertEqual(a["tiles"], b["tiles"])
        self.assertEqual(a["spawn"], b["spawn"])

    def test_loot(self):
        c = cfg(items_per_level=8)
        items = LootGenerator().generate(c)
        self.assertEqual(len(items), 8)
        for it in items:
            self.assertIn(it["rarity"], ["common", "uncommon", "rare", "epic"])
            self.assertIn("name", it)


class TestAssets(unittest.TestCase):
    def test_palette(self):
        p = Palette()
        self.assertEqual(len(p.colors), 5)
        self.assertEqual(len(p.index(0.0)), 3)

    def test_texture_synth(self):
        c = cfg(seed=1, asset_resolution=16)
        synth = AssetSynthesizer(c)
        pixels = synth.synthesise_texture()
        self.assertEqual(len(pixels), 16)
        self.assertEqual(len(pixels[0]), 16)
        self.assertEqual(len(pixels[0][0]), 3)

    def test_texture_deterministic(self):
        c = cfg(seed=2, asset_resolution=8)
        a = AssetSynthesizer(c).synthesise_texture()
        b = AssetSynthesizer(c).synthesise_texture()
        self.assertEqual(a, b)

    def test_audio_synth(self):
        c = cfg(seed=3)
        synth = AssetSynthesizer(c)
        sfx = synth.synthesise_sfx()
        self.assertTrue(len(sfx) > 0)

    def test_ppm_export(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.ppm")
            c = cfg(seed=4, asset_resolution=4)
            synth = AssetSynthesizer(c)
            synth.textures.export_ppm(synth.synthesise_texture(), path)
            self.assertTrue(os.path.exists(path))
            with open(path) as f:
                head = f.readline().strip()
            self.assertEqual(head, "P3")


class TestLevel(unittest.TestCase):
    def test_build(self):
        c = cfg(width=32, height=32, objectives=3, enemies_per_level=6, items_per_level=8)
        level = LevelBuilder(c).build()
        self.assertEqual(level.width, 32)
        self.assertEqual(level.height, 32)
        self.assertEqual(len(level.objectives), 3)
        self.assertEqual(sum(1 for e in level.entities if e["type"] == "enemy"), 6)
        self.assertEqual(sum(1 for e in level.entities if e["type"] == "item"), 8)
        self.assertIn("seed", level.metadata)

    def test_json(self):
        import json

        c = cfg(width=16, height=16)
        level = LevelBuilder(c).build()
        data = json.loads(level.json())
        self.assertEqual(data["width"], 16)

    def test_loot_table(self):
        c = cfg()
        self.assertEqual(len(LevelBuilder(c).loot_table()), c.items_per_level)


class TestNarrative(unittest.TestCase):
    def test_generation(self):
        eng = NarrativeEngine(seed=1)
        beats = eng.generate(segments=12)
        self.assertEqual(len(beats), 12)
        for b in beats:
            self.assertIn(b.kind, ["hook", "twist", "climax", "resolution"])

    def test_fill_no_unresolved_tokens(self):
        eng = NarrativeEngine(seed=2)
        beats = eng.generate(segments=30)
        for b in beats:
            self.assertNotIn("{", b.text)
            self.assertNotIn("}", b.text)

    def test_quest_hooks(self):
        eng = NarrativeEngine(seed=3)
        quests = eng.quest_hooks(count=4)
        self.assertEqual(len(quests), 4)
        self.assertEqual(quests[0]["kind"], "primary")

    def test_compile(self):
        eng = NarrativeEngine(seed=4)
        eng.generate(segments=6)
        out = eng.compile()
        self.assertEqual(len(out["beats"]), 6)
        self.assertTrue(len(out["quests"]) >= 1)


class TestPlaytest(unittest.TestCase):
    def test_playtest(self):
        c = cfg(seed=5, max_playtest_steps=100)
        level = LevelBuilder(c).build()
        tester = Playtester(c)
        results = tester.run(level, runs=3, seeds=[5, 6, 7])
        self.assertEqual(len(results), 3)
        for r in results:
            self.assertLessEqual(r.steps, 100)
            self.assertIsInstance(r.completed, bool)
            self.assertGreaterEqual(r.loot_collected, 0)

    def test_aggregate(self):
        c = cfg(seed=5)
        level = LevelBuilder(c).build()
        tester = Playtester(c)
        results = tester.run(level, runs=4)
        agg = tester.aggregate(results)
        self.assertEqual(agg["runs"], 4)
        self.assertGreaterEqual(agg["completion_rate"], 0.0)
        self.assertLessEqual(agg["completion_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()