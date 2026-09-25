"""Hermetic tests for mem20unikitz."""

from __future__ import annotations

import unittest

from mem20unikitz.config import UniKitConfig, DEFAULT_CONFIG
from mem20unikitz.behavior_tree import (
    BehaviorTree, Blackboard, Sequence, Selector, Parallel,
    Inverter, Repeater, UntilSuccess, UntilFailure,
    ActionNode, ConditionNode, NodeStatus
)
from mem20unikitz.goap import GOAPPlanner, GOAPAgent, WorldState, Action, Plan
from mem20unikitz.utility import UtilityScorer, UtilityReasoner, create_consideration
from mem20unikitz.navigation import NavigationAgent, NavMesh, AStarPathfinder, Vector2


class TestConfig(unittest.TestCase):
    """Config tests."""

    def test_defaults(self):
        cfg = UniKitConfig()
        self.assertEqual(cfg.port, 8008)
        self.assertEqual(cfg.gateway_url, "http://127.0.0.1:4000")
        self.assertTrue(cfg.enable_bt)
        self.assertTrue(cfg.enable_goap)

    def test_load_from_yaml(self):
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("port: 9000\ngateway_url: \"http://localhost:4100\"\n")
            f.flush()
            cfg = UniKitConfig.load(f.name)
        import os
        os.unlink(f.name)
        self.assertEqual(cfg.port, 9000)
        self.assertEqual(cfg.gateway_url, "http://localhost:4100")


class TestBehaviorTree(unittest.TestCase):
    """Behavior tree tests."""

    def test_blackboard(self):
        bb = Blackboard()
        bb.set("key", "value")
        self.assertEqual(bb.get("key"), "value")
        self.assertTrue(bb.has("key"))
        bb.remove("key")
        self.assertFalse(bb.has("key"))

    def test_sequence(self):
        bb = Blackboard()
        call_order = []

        def action1(bb):
            call_order.append(1)
            return NodeStatus.SUCCESS
        def action2(bb):
            call_order.append(2)
            return NodeStatus.SUCCESS

        seq = Sequence(name="test", children=[
            ActionNode("a1", lambda bb: (call_order.append(1), NodeStatus.SUCCESS)[1]),
            ActionNode("a2", lambda bb: (call_order.append(2), NodeStatus.SUCCESS)[1]),
        ])
        bt = BehaviorTree(seq, Blackboard())
        result = bt.tick()
        self.assertEqual(result, NodeStatus.SUCCESS)
        self.assertEqual(call_order, [1, 2])

    def test_selector(self):
        sel = Selector(name="test", children=[
            ActionNode("fail", lambda bb: NodeStatus.FAILURE),
            ActionNode("success", lambda bb: NodeStatus.SUCCESS),
        ])
        bt = BehaviorTree(sel, Blackboard())
        result = bt.tick()
        self.assertEqual(result, NodeStatus.SUCCESS)

    def test_parallel(self):
        par = Parallel(name="test", children=[
            ActionNode("s1", lambda bb: NodeStatus.SUCCESS),
            ActionNode("s2", lambda bb: NodeStatus.SUCCESS),
        ], success_threshold=2)
        bt = BehaviorTree(par, Blackboard())
        result = bt.tick()
        self.assertEqual(result, NodeStatus.SUCCESS)

    def test_inverter(self):
        inv = Inverter(child=ActionNode("success", lambda bb: NodeStatus.SUCCESS))
        bt = BehaviorTree(inv, Blackboard())
        result = bt.tick()
        self.assertEqual(result, NodeStatus.FAILURE)

    def test_repeater(self):
        call_count = 0
        def action(bb):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                return NodeStatus.SUCCESS
            return NodeStatus.RUNNING

        rep = Repeater(child=ActionNode("repeat", action), count=3)
        bt = BehaviorTree(rep, Blackboard())
        # First tick
        result = bt.tick()
        self.assertEqual(result, NodeStatus.RUNNING)
        # Second tick
        result = bt.tick()
        self.assertEqual(result, NodeStatus.RUNNING)
        # Third tick
        result = bt.tick()
        self.assertEqual(result, NodeStatus.SUCCESS)

    def test_until_success(self):
        call_count = 0
        def action(bb):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                return NodeStatus.SUCCESS
            return NodeStatus.FAILURE

        us = UntilSuccess(child=ActionNode("until", action))
        bt = BehaviorTree(us, Blackboard())
        result = bt.tick()
        self.assertEqual(result, NodeStatus.RUNNING)
        result = bt.tick()
        self.assertEqual(result, NodeStatus.SUCCESS)

    def test_until_failure(self):
        call_count = 0
        def action(bb):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                return NodeStatus.FAILURE
            return NodeStatus.SUCCESS

        uf = UntilFailure(child=ActionNode("until_fail", action))
        bt = BehaviorTree(uf, Blackboard())
        result = bt.tick()
        self.assertEqual(result, NodeStatus.RUNNING)
        result = bt.tick()
        self.assertEqual(result, NodeStatus.FAILURE)


class TestGOAP(unittest.TestCase):
    """GOAP tests."""

    def test_world_state(self):
        ws = WorldState({"key": "value"})
        self.assertEqual(ws.get("key"), "value")
        self.assertTrue(ws.has("key"))

    def test_world_state_satisfies(self):
        start = WorldState({"a": 1, "b": 2})
        goal = WorldState({"a": 1})
        self.assertTrue(start.satisfies(goal))

    def test_action(self):
        act = Action("test", preconditions={"a": 1}, effects={"b": 2}, cost=1.0)
        state = WorldState({"a": 1})
        self.assertTrue(act.is_valid(state))
        new_state = act.apply(state)
        self.assertEqual(new_state.get("b"), 2)

    def test_planner(self):
        planner = GOAPPlanner()
        planner.add_action(Action("move", {"at_home": True}, {"at_work": True}, 1.0))
        planner.add_action(Action("work", {"at_work": True}, {"money": 100}, 2.0))

        start = WorldState({"at_home": True})
        goal = WorldState({"money": 100})

        plan = planner.plan(start, goal)
        self.assertIsNotNone(plan)
        self.assertIn("move", plan)
        self.assertIn("work", plan)

    def test_goap_agent(self):
        agent = GOAPAgent()
        agent.add_action(Action("move", {"at_home": True}, {"at_work": True}, 1.0))
        agent.add_action(Action("work", {"at_work": True}, {"money": 100}, 2.0))

        agent.current_state = WorldState({"at_home": True, "money": 0})
        agent.set_goal(WorldState({"money": 100}))

        action = agent.update()
        self.assertIsNotNone(action)
        self.assertEqual(action, "move")


class TestUtility(unittest.TestCase):
    """Utility AI tests."""

    def test_consideration(self):
        from mem20unikitz.utility import create_consideration
        c = create_consideration("test", lambda ctx: 0.8, weight=2.0, curve="linear")
        score = c.evaluate({})
        self.assertEqual(score, 1.6)

    def test_utility_scorer(self):
        scorer = UtilityScorer()
        from types import SimpleNamespace
        action = SimpleNamespace()
        action.name = "test"
        action.considerations = [
            SimpleNamespace(evaluate=lambda ctx: 0.8)
        ]
        action.evaluate = lambda ctx: 0.8
        action.is_on_cooldown = lambda t: False

        scorer.add_action(action)
        scores = scorer.score_all({})
        self.assertEqual(scores["test"], 0.8)

    def test_utility_reasoner(self):
        reasoner = UtilityReasoner()
        reasoner.add_action("attack", [
            ("enemy_close", lambda bb: 1.0 if bb.get("enemy_dist", 10) < 5 else 0.0, 1.0),
        ])
        reasoner.blackboard = {"enemy_dist": 3}
        best = reasoner.decide()
        self.assertEqual(best, "attack")


class TestNavigation(unittest.TestCase):
    """Navigation tests."""

    def test_vector2(self):
        v1 = Vector2(3, 4)
        self.assertAlmostEqual(v1.length(), 5.0)
        v2 = v1.normalized()
        self.assertAlmostEqual(v2.length(), 1.0)

    def test_nav_mesh(self):
        mesh = NavMesh()
        node = mesh.add_node(Vector2(0, 0), walkable=True)
        self.assertEqual(len(mesh.nodes), 1)

    def test_astar_pathfinder(self):
        mesh = NavMesh()
        start_node = mesh.add_node(Vector2(0, 0), walkable=True)
        goal_node = mesh.add_node(Vector2(1, 0), walkable=True)
        mesh.connect_nodes(start_node, mesh.nodes[0])  # simplified

        # Basic pathfinder creation
        finder = AStarPathfinder(mesh)
        # Note: Full pathfinding requires connected graph

    def test_navigation_agent(self):
        mesh = NavMesh()
        agent = NavigationAgent(mesh)
        agent.set_position(Vector2(0, 0))
        # New agent has no path, so reached_goal returns True (no goal to reach)
        self.assertTrue(agent.reached_goal())


class TestGOAPAgent(unittest.TestCase):
    """GOAP Agent tests."""

    def test_agent_creation(self):
        agent = GOAPAgent()
        agent.add_action(Action("test", {"a": 1}, {"b": 2}, 1.0))
        self.assertEqual(len(agent.planner.actions), 1)

    def test_replan(self):
        agent = GOAPAgent()
        agent.add_action(Action("move", {"at_home": True}, {"at_work": True}, 1.0))
        agent.current_state = WorldState({"at_home": True})
        agent.set_goal(WorldState({"at_work": True}))
        action = agent.update()
        self.assertEqual(action, "move")


if __name__ == "__main__":
    unittest.main()