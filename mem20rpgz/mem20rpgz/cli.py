"""CLI for mem20rpgz."""

from __future__ import annotations

import argparse
import json

from .agents import RPGStudio
from .character import Character, StatBlock, create_party
from .combat import CombatEngine, Combatant
from .config import RPGConfig
from .inventory import Inventory, Item
from .quest import Quest, QuestLog, QuestObjective
from .world import Faction, NPC, Scene, World


def _cmd_character(args) -> int:
    c = Character(args.name, args.archetype)
    for skill, lvl in [("slash", 1), ("shout", 2)]:
        c.add_skill(SkillStub(skill, lvl))
    c.gain_xp(260)
    print(json.dumps(c.to_dict(), indent=2))
    return 0


class SkillStub:
    def __init__(self, name, level):
        from .character import Skill

        self._s = Skill(name, level)

    def to_dict(self):
        return self._s.to_dict()


def _cmd_party(args) -> int:
    names = args.names.split(",") if args.names else ["Ari", "Bran", "Cora", "Dune"]
    party = create_party(names, seed=args.seed)
    out = [c.to_dict() for c in party]
    for m in out:
        m.pop("skills", None)
    print(json.dumps(out, indent=2))
    return 0


def _cmd_combat(args) -> int:
    a = Character("Hero", "warrior")
    a.gain_xp(5)
    b = Character("Goblin King", "adventurer")
    b.hp = 30
    engine = CombatEngine(args.seed)
    result = engine.battle(Combatant.from_character(a, True), Combatant.from_character(b, False))
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Winner: {result['winner']} in {result['turns']} turns")
        for step in result["log"][-3:]:
            print(f"  {step['actor']} -> {step['target']} hit={step['hit']} dmg={step['damage']} crit={step['critical']}")
    return 0


def _cmd_inventory(args) -> int:
    inv = Inventory(capacity=args.capacity)
    inv.add(Item("Bronze Sword", "weapon", 15))
    inv.add(Item("Health Potion", "potion", 5, count=3))
    inv.add(Item("Health Potion", "potion", 5, count=2))
    print(json.dumps(inv.to_dict(), indent=2))
    return 0


def _cmd_quest(args) -> int:
    log = QuestLog()
    log.accept(Quest("First Blood", [QuestObjective("kill", "goblin", 3), QuestObjective("collect", "relic", 1)], {"gold": 50, "xp": 120, "items": ["Iron Key"]}, "Mayor"))
    quest = log.by_title("First Blood")
    quest.progress("kill", "goblin", 2)
    quest.progress("kill", "goblin", 1)
    quest.progress("collect", "relic", 1)
    print(json.dumps({"quest": quest.to_dict(), "rewards": log.grant_rewards(quest)}, indent=2))
    return 0


def _cmd_world(args) -> int:
    w = World("Aethel")
    w.add_faction(Faction("Order", 40))
    w.add_faction(Faction("Cult", -80))
    w.add_scene(Scene("Grimroot", "A hollow village.", npcs=[NPC("Sable", "innkeeper", "Order")], exits=["Forest", "Crypt"]))
    w.add_scene(Scene("Crypt", "Bone-lined passages.", hazards=["wolves"], treasure=["Bronze Sword"]))
    print(json.dumps({"faction_stances": {k: f.stance for k, f in w.factions.items()}, "scenes": list(w.scenes.keys())}, indent=2))
    return 0


def _cmd_story(args) -> int:
    studio = RPGStudio(seed=args.seed, live_mode=args.live)
    if args.live:
        import asyncio

        result = asyncio.run(studio.produce_async(args.outline))
    else:
        result = studio.produce(args.outline)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        acts = result["story"]["acts"]
        print(f"Logline: {result['story']['logline']}")
        print(f"Setting: {result['story']['setting']}")
        print(f"Acts: {len(acts)} | Scenes: {len(result['scenes']['scenes'])} | Mechanics: {len(result['gameplay']['mechanics'])} | Tetrad: {result['tetrad']}")
    return 0


def _cmd_test(args) -> int:
    c = Character("Test", "mage")
    assert c.gain_xp(400) >= 1
    inv = Inventory(capacity=10)
    assert inv.add(Item("Potion", "potion", count=5))
    engine = CombatEngine(args.seed)
    result = engine.battle(Combatant.from_character(Character("A", "warrior")), Combatant.from_character(Character("B", "rogue")))
    assert result["winner"]
    log = QuestLog()
    assert log.accept(Quest("T", [QuestObjective("kill", "rat", 1)], {"gold": 1}, "M"))
    studio = RPGStudio(args.seed)
    design = studio.produce("lost heirloom")
    assert design["story"]["logline"] == "lost heirloom"
    assert len(design["gameplay"]["mechanics"]) > 0
    print("mem20rpgz test: ALL OK")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="mem20rpgz", description="Native mem20 RPGAgent")
    p.add_argument("--seed", type=int, default=20260917)
    sub = p.add_subparsers(dest="cmd", required=True)

    ch = sub.add_parser("character", help="Create a character")
    ch.add_argument("--name", default="Hero")
    ch.add_argument("--archetype", default="warrior")
    ch.set_defaults(func=_cmd_character)

    pa = sub.add_parser("party", help="Generate a party")
    pa.add_argument("--names", default="")
    pa.set_defaults(func=_cmd_party)

    cb = sub.add_parser("combat", help="Simulate a battle")
    cb.add_argument("--json", action="store_true")
    cb.set_defaults(func=_cmd_combat)

    iv = sub.add_parser("inventory", help="Inventory demo")
    iv.add_argument("--capacity", type=int, default=24)
    iv.set_defaults(func=_cmd_inventory)

    qs = sub.add_parser("quest", help="Quest demo")
    qs.set_defaults(func=_cmd_quest)

    wd = sub.add_parser("world", help="World demo")
    wd.set_defaults(func=_cmd_world)

    st = sub.add_parser("story", help="Run the story-to-play studio")
    st.add_argument("--outline", default="")
    st.add_argument("--live", action="store_true")
    st.add_argument("--json", action="store_true")
    st.set_defaults(func=_cmd_story)

    sub.add_parser("test", help="Smoke test").set_defaults(func=_cmd_test)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())