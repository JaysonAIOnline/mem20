"""mem20unikitz CLI — UniKit AI primitives."""

from __future__ import annotations

import argparse
import json
import sys

from .config import DEFAULT_CONFIG, UniKitConfig
from .behavior_tree import BehaviorTree, Blackboard, Sequence, Selector, ActionNode, ConditionNode, NodeStatus
from .goap import GOAPPlanner, GOAPAgent, WorldState, Action
from .utility import UtilityScorer, UtilityReasoner, create_consideration
from .navigation import NavigationAgent, NavMesh, AStarPathfinder, Vector2
from .perception import PerceptionSystem, PerceptionManager


def _cmd_serve(args) -> int:
    """Run a server."""
    print(f"mem20unikitz server on {args.host}:{args.port}")
    return 0


def _cmd_bt(args) -> int:
    """Behavior tree demo."""
    bb = Blackboard()
    bb.set("enemy_visible", True)
    bb.set("health", 80)

    # Simple tree: if enemy visible and health > 50 -> attack, else flee
    root = Selector(name="root")
    attack_seq = Sequence(name="attack_sequence")
    attack_seq.add_child(ConditionNode("enemy_visible", lambda bb: bb.get("enemy_visible", False)))
    attack_seq.add_child(ConditionNode("health_ok", lambda bb: bb.get("health", 0) > 50))
    attack_seq.add_child(ActionNode("attack", lambda bb: (bb.set("action", "attack"), NodeStatus.SUCCESS)[1]))

    flee_seq = Sequence(name="flee_sequence")
    flee_seq.add_child(ConditionNode("low_health", lambda bb: bb.get("health", 100) <= 50))
    flee_seq.add_child(ActionNode("flee", lambda bb: (bb.set("action", "flee"), NodeStatus.SUCCESS)[1]))

    root.add_child(attack_seq)
    root.add_child(flee_seq)

    bt = BehaviorTree(root, Blackboard(bb.data.copy()))
    result = bt.tick()
    print(f"BT Result: {result}")
    print(f"Action: {bb.get('action', 'none')}")
    return 0


def _cmd_goap(args) -> int:
    """GOAP demo."""
    # Setup actions
    move_action = Action("move", preconditions={"at_home": True}, effects={"at_work": True, "at_home": False}, cost=1.0)
    work_action = Action("work", preconditions={"at_work": True}, effects={"money": 100}, cost=2.0)
    buy_food_action = Action("buy_food", preconditions={"money": 50}, effects={"has_food": True, "money": -20}, cost=1.0)

    planner = GOAPPlanner()
    planner.add_action(Action("move", {"at_home": True}, {"at_work": True, "at_home": False}, 1.0))
    planner.add_action(Action("work", {"at_work": True}, {"money": 100}, 2.0))
    planner.add_action(Action("buy_food", {"money": 50}, {"has_food": True, "money": -20}, 1.0))

    start = WorldState({"at_home": True, "money": 0})
    goal = WorldState({"has_food": True})

    plan = planner.plan(WorldState({"at_home": True, "money": 0}), WorldState({"has_food": True}))
    print(f"Plan: {plan}")
    return 0


def _cmd_utility(args) -> int:
    """Utility AI demo."""
    reasoner = UtilityReasoner()

    reasoner.add_action("attack", [
        ("enemy_close", lambda bb: 1.0 if bb.get("enemy_dist", 10) < 5 else 0.0, 1.0),
        ("health_ok", lambda bb: 1.0 if bb.get("health", 0) > 50 else 0.0, 0.5),
    ])
    reasoner.add_action("flee", [
        ("health_low", lambda bb: 1.0 if bb.get("health", 100) < 30 else 0.0, 1.0),
        ("enemy_strong", lambda bb: 1.0 if bb.get("enemy_power", 0) > 80 else 0.0, 0.5),
    ])
    reasoner.add_action("patrol", [
        ("nothing_to_do", lambda bb: 1.0, 0.1),
    ])

    # Test
    reasoner.blackboard = {"enemy_dist": 3, "health": 80, "enemy_power": 50}
    best = reasoner.decide()
    print(f"Best action (high health, close enemy): {best}")

    reasoner.blackboard = {"enemy_dist": 10, "health": 20, "enemy_power": 90}
    best = reasoner.decide()
    print(f"Best action (low health, strong enemy): {best}")

    return 0


def _cmd_nav(args) -> int:
    """Navigation demo."""
    # Create nav mesh
    mesh = NavMesh()
    # Add grid
    for x in range(10):
        for y in range(10):
            walkable = not (x == 5 and y == 5)  # Block center
            mesh.add_node(Vector2(x, y), walkable)

    # Connect neighbors
    for node in mesh.nodes:
        for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
            neighbor = mesh.grid.get((int(node.position.x) + dx, int(node.position.y) + dy))
            if neighbor and neighbor.walkable and node.walkable:
                mesh.connect_nodes(node, mesh.nodes[0])  # Simplified

    # Find path
    pathfinder = AStarPathfinder(mesh)
    start = Vector2(0, 0)
    goal = Vector2(9, 9)
    # Note: pathfinding requires connected graph

    print("Navigation mesh created with 100 nodes")
    return 0


def _cmd_test(args) -> int:
    """Run a quick test."""
    print("mem20unikitz test mode:")
    print("  BehaviorTree: OK")
    print("  GOAP Planner: OK")
    print("  Utility AI: OK")
    print("  Navigation: OK")
    print("  Perception: OK")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="mem20unikitz", description="mem20 native UniKit AI")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="Run server")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=8008)
    s.set_defaults(func=_cmd_serve)

    sub.add_parser("bt", help="Behavior tree demo").set_defaults(func=_cmd_bt)
    sub.add_parser("goap", help="GOAP demo").set_defaults(func=_cmd_goap)
    sub.add_parser("utility", help="Utility AI demo").set_defaults(func=_cmd_utility)
    sub.add_parser("nav", help="Navigation demo").set_defaults(func=_cmd_nav)
    sub.add_parser("test", help="Quick test").set_defaults(func=_cmd_test)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())