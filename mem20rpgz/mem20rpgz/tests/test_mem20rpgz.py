"""Hermetic tests for mem20rpgz."""

from __future__ import annotations

import unittest

from mem20rpgz.config import RPGConfig
from mem20rpgz.rng import RpgRandom
from mem20rpgz.character import Character, StatBlock, Skill, create_party
from mem20rpgz.inventory import Inventory, Item, Equipment, EQUIPMENT_SLOTS
from mem20rpgz.combat import CombatEngine, Combatant, CombatAction
from mem20rpgz.quest import Quest, QuestLog, QuestObjective
from mem20rpgz.world import Faction, NPC, Scene, World
from mem20rpgz.agents import (
    RPGStudio, NarrativeAgent, SceneAgent, GameplayAgent, AestheticsAgent,
    AgentOutput, ELEMENTAL_TETRAD, BaseStudioAgent,
)


def cfg(**kw):
    return RPGConfig(**kw)


class TestConfig(unittest.TestCase):
    def test_defaults(self):
        c = cfg()
        self.assertEqual(c.seed, 20260917)
        self.assertEqual(c.party_size, 4)
        self.assertEqual(c.port, 8017)

    def test_yaml_roundtrip(self):
        import os
        import tempfile

        c = cfg(seed=5, party_size=2)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            c.save(f.name)
            f.flush()
            c2 = RPGConfig.load(f.name)
        os.unlink(f.name)
        self.assertEqual(c2.seed, 5)
        self.assertEqual(c2.party_size, 2)


class TestRng(unittest.TestCase):
    def test_deterministic(self):
        a, b = RpgRandom(42), RpgRandom(42)
        self.assertEqual([a.float() for _ in range(10)], [b.float() for _ in range(10)])

    def test_roll_range(self):
        r = RpgRandom(3)
        for _ in range(100):
            v = r.roll(20)
            self.assertTrue(1 <= v <= 20)


class TestCharacter(unittest.TestCase):
    def test_defaults(self):
        c = Character("Ari", "warrior")
        self.assertEqual(c.level, 1)
        self.assertEqual(c.hp, c.max_hp())
        self.assertTrue(c.alive)

    def test_stat_modifier(self):
        s = StatBlock(strength=18)
        self.assertEqual(s.modifier("strength"), 4)

    def test_xp_levels(self):
        c = Character("Test", "adventurer")
        gained = c.gain_xp(400)
        self.assertEqual(c.level, 3)
        self.assertGreaterEqual(gained, 2)

    def test_level_curve_grows(self):
        c = Character("Curve", "adventurer")
        self.assertGreater(c.xp_for_level(6), c.xp_for_level(3))

    def test_skills(self):
        c = Character("Skill", "mage")
        c.add_skill(Skill("fireball", 2))
        self.assertTrue(c.has_skill("fireball"))
        c.add_skill(Skill("fireball", 4))
        self.assertEqual(next(s for s in c.skills if s.name == "fireball").level, 4)

    def test_damage_heal(self):
        c = Character("Tank", "warrior")
        c.take_damage(30)
        self.assertLess(c.hp, c.max_hp())
        c.heal(50)
        self.assertEqual(c.hp, c.max_hp())

    def test_to_dict_roundtrip(self):
        c = Character("R", "ranger")
        c.gain_xp(150)
        c.add_skill(Skill("aim", 3))
        c2 = Character.from_dict(c.to_dict())
        self.assertEqual(c2.name, "R")
        self.assertEqual(c2.level, c.level)
        self.assertTrue(c2.has_skill("aim"))

    def test_create_party(self):
        party = create_party(["A", "B", "C", "D"], seed=7)
        self.assertEqual(len(party), 4)
        for m in party:
            self.assertTrue(1 <= m.level)


class TestInventory(unittest.TestCase):
    def test_add_stack(self):
        inv = Inventory(capacity=24)
        self.assertTrue(inv.add(Item("Potion", "potion", count=3)))
        self.assertTrue(inv.add(Item("Potion", "potion", count=2)))
        self.assertEqual(inv.count_of("Potion"), 5)
        self.assertEqual(len(inv.items), 1)

    def test_capacity(self):
        inv = Inventory(capacity=2)
        inv.add(Item("A", "misc"))
        inv.add(Item("B", "misc"))
        self.assertTrue(inv.is_full())
        self.assertFalse(inv.add(Item("C", "misc")))

    def test_remove(self):
        inv = Inventory()
        inv.add(Item("Sword", "weapon"), ) if False else inv.add(Item("Sword", "weapon"))
        self.assertTrue(inv.remove("Sword"))
        self.assertEqual(inv.count_of("Sword"), 0)

    def test_all_of_kind(self):
        inv = Inventory()
        inv.add(Item("Sword", "weapon"))
        inv.add(Item("Shield", "armor"))
        self.assertEqual(len(inv.all_of_kind("weapon")), 1)

    def test_total_weight(self):
        inv = Inventory()
        inv.add(Item("Sword", "weapon", weight=3))
        self.assertAlmostEqual(inv.total_weight(), 3.0)

    def test_roundtrip(self):
        inv = Inventory(capacity=12)
        inv.add(Item("Gold", "misc", count=9))
        inv2 = Inventory.from_dict(inv.to_dict())
        self.assertEqual(inv2.count_of("Gold"), 9)


class TestEquipment(unittest.TestCase):
    def test_slots(self):
        eq = Equipment()
        self.assertEqual(set(eq.slots.keys()), EQUIPMENT_SLOTS)

    def test_equip_unequip(self):
        eq = Equipment()
        sword = Item("Greatsword", "equip", effect={"strength": +3})
        old = eq.equip("weapon", sword)
        self.assertIsNone(old)
        self.assertEqual(eq.bonus("strength"), 3)
        removed = eq.unequip("weapon")
        self.assertEqual(removed.name, "Greatsword")
        self.assertEqual(eq.bonus("strength"), 0)

    def test_invalid_slot(self):
        eq = Equipment()
        self.assertIsNone(eq.equip("chest", Item("X", "equip")))


class TestCombat(unittest.TestCase):
    def test_battle_has_winner(self):
        engine = CombatEngine(seed=1)
        a = Combatant.from_character(Character("A", "warrior"))
        b = Combatant.from_character(Character("B", "rogue"))
        result = engine.battle(a, b)
        self.assertIn(result["winner"], ("A", "B"))
        self.assertGreater(len(result["log"]), 0)

    def test_damage_never_negative(self):
        engine = CombatEngine(seed=2)
        a = Combatant.from_character(Character("A", "warrior"))
        b = Combatant.from_character(Character("B", "cleric"))
        engine.resolve_attack(a, b)
        self.assertGreaterEqual(b.hp, 0)

    def test_deterministic(self):
        ra, rb = CombatEngine(3), CombatEngine(3)
        la, lb = Combatant.from_character(Character("A", "warrior")), Combatant.from_character(Character("B", "warrior"))
        ca, cb = Combatant.from_character(Character("A", "warrior")), Combatant.from_character(Character("B", "warrior"))
        result_a = ra.battle(la, lb)
        result_b = rb.battle(ca, cb)
        self.assertEqual(result_a["log"], result_b["log"])


class TestQuest(unittest.TestCase):
    def test_progress_completes_quest(self):
        q = Quest("Kill rats", [QuestObjective("kill", "rat", 3)], {"gold": 10, "xp": 50}, "Mayor")
        self.assertFalse(q.progress("kill", "rat", 2))
        self.assertTrue(q.progress("kill", "rat", 1))
        self.assertTrue(q.completed)
        self.assertFalse(q.active)

    def test_wrong_targets_dont_advance(self):
        q = Quest("Kill rats", [QuestObjective("kill", "rat", 1)], {"gold": 1})
        q.progress("kill", "goblin")
        self.assertEqual(q.objectives[0].current, 0)

    def test_progress_pct(self):
        q = Quest("Kill rats", [QuestObjective("kill", "rat", 4)])
        q.progress("kill", "rat", 2)
        self.assertEqual(q.progress_pct, 0.5)

    def test_log(self):
        log = QuestLog()
        self.assertTrue(log.accept(Quest("A", [QuestObjective("reach", "town", 1)])))
        self.assertTrue(log.accept(Quest("B", [QuestObjective("talk", "sage", 1)])))
        self.assertEqual(len(log.active_quests()), 2)
        self.assertEqual(log.by_title("A").title, "A")

    def test_rewards(self):
        log = QuestLog()
        q = Quest("Reward", [QuestObjective("reach", "town", 1)], {"gold": 100, "xp": 50, "items": ["Key"]})
        rewards = log.grant_rewards(q)
        self.assertEqual(rewards["gold"], 100)
        self.assertEqual(rewards["xp"], 50)
        self.assertEqual(len(rewards["items"]), 1)

    def test_roundtrip(self):
        log = QuestLog()
        log.accept(Quest("P", [QuestObjective("kill", "rat", 1)], {"gold": 1}))
        clone = QuestLog.from_dict(log.to_dict())
        self.assertEqual(len(clone.active_quests()), 1)


class TestWorld(unittest.TestCase):
    def test_faction_disposition(self):
        f = Faction("Order", 40)
        f.shift(-10)
        self.assertEqual(f.disposition, 30)
        f.shift(-100)
        self.assertEqual(f.stance, "hostile")

    def test_scene_npc_registration(self):
        w = World("Test")
        w.add_scene(Scene("Village", npcs=[], exits=["Forest"]))
        self.assertTrue(w.register_npc(NPC("Sable", "innkeeper"), "Village"))
        self.assertEqual(len(w.scene("Village").npcs), 1)

    def test_world_serialization(self):
        w = World("Aethel")
        w.add_faction(Faction("Cult", -80))
        data = w.to_dict()
        self.assertEqual(data["factions"][0]["disposition"], -80)


class TestAgents(unittest.TestCase):
    def test_tetrad_tuple(self):
        self.assertEqual(len(ELEMENTAL_TETRAD), 4)

    def test_narrative(self):
        agent = NarrativeAgent(seed=1)
        story = agent.run({"outline": "lost heirloom"})
        self.assertEqual(story["logline"], "lost heirloom")
        self.assertEqual(len(story["acts"]), 3)

    def test_scene(self):
        agent = SceneAgent(seed=1)
        scenes = agent.run({"story": {"acts": [{"act": 1, "summary": "hook -- setting"}]}})
        self.assertEqual(len(scenes["scenes"]), 1)
        self.assertEqual(scenes["scenes"][0]["act"], 1)

    def test_gameplay(self):
        agent = GameplayAgent(seed=1)
        mech = agent.run({"scenes": [{"name": "S1"}, {"name": "S2"}]})
        self.assertEqual(len(mech["mechanics"]), 2)
        self.assertTrue(mech["tetrad_check"])

    def test_aesthetics(self):
        agent = AestheticsAgent(seed=1)
        out = agent.run({})
        self.assertIn("palette", out)
        self.assertIn("tone", out)

    def test_studio_pipeline(self):
        studio = RPGStudio(seed=1)
        design = studio.produce("lost heirloom")
        self.assertEqual(design["story"]["logline"], "lost heirloom")
        self.assertEqual(len(design["scenes"]["scenes"]), 3)
        self.assertEqual(len(design["gameplay"]["mechanics"]), 3)
        self.assertEqual(len(studio.history), 4)
        for h in studio.history:
            self.assertIsInstance(h, AgentOutput)

    def test_studio_deterministic(self):
        a = RPGStudio(seed=5).produce("zombie apocalypse")
        b = RPGStudio(seed=5).produce("zombie apocalypse")
        self.assertEqual(a, b)

    def test_base_agent_requires_run(self):
        with self.assertRaises(NotImplementedError):
            BaseStudioAgent().run({})


if __name__ == "__main__":
    unittest.main()