"""GOAP Planner — native absorption of UniKit GOAP."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from collections import deque
import heapq
import uuid


@dataclass
class WorldState:
    """World state for GOAP."""
    variables: Dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        self.variables[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.variables.get(key, default)

    def has(self, key: str) -> bool:
        return key in self.variables

    def satisfies(self, other: "WorldState") -> bool:
        """Check if this state satisfies another state's requirements."""
        for key, value in other.variables.items():
            if key not in self.variables or self.variables[key] != value:
                return False
        return True

    def clone(self) -> "WorldState":
        ws = WorldState()
        ws.variables = self.variables.copy()
        return ws

    def apply_effects(self, effects: Dict[str, Any]) -> "WorldState":
        new = self.clone()
        new.variables.update(effects)
        return new

    def __eq__(self, other):
        if not isinstance(other, WorldState):
            return False
        return self.variables == other.variables

    def __hash__(self):
        return hash(tuple(sorted(self.variables.items())))


@dataclass
class Action:
    """GOAP action."""
    name: str
    preconditions: Dict[str, Any] = field(default_factory=dict)
    effects: Dict[str, Any] = field(default_factory=dict)
    cost: float = 1.0
    callback: Optional[callable] = None

    def is_valid(self, state: WorldState) -> bool:
        for key, value in self.preconditions.items():
            if state.get(key) != value:
                return False
        return True

    def apply(self, state: WorldState) -> WorldState:
        new_state = state.clone()
        new_state.variables.update(self.effects)
        return new_state


@dataclass
class Plan:
    """GOAP plan - sequence of actions."""
    actions: List["Action"] = field(default_factory=list)
    total_cost: float = 0.0

    def add_action(self, action: "Action"):
        self.actions.append(action)
        self.total_cost += action.cost


class GOAPPlanner:
    """GOAP planner using A* search."""

    def __init__(self):
        self.actions: Dict[str, Action] = {}

    def add_action(self, action: Action) -> None:
        self.actions[action.name] = action

    def plan(
        self,
        start_state: WorldState,
        goal_state: WorldState,
        max_iterations: int = 1000,
    ) -> Optional[List[str]]:
        """Find plan from start to goal using A*."""
        if start_state.satisfies(goal_state):
            return []

        # Priority queue: (f_cost, g_cost, state, plan)
        open_set = []
        closed_set: Set[WorldState] = set()

        start_plan = []
        start_g = 0.0
        start_h = self._heuristic(start_state, goal_state)
        heapq.heappush(open_set, (start_g + start_h, start_g, start_state, []))

        iterations = 0
        while open_set and iterations < max_iterations:
            iterations += 1
            f_cost, g_cost, current_state, plan = heapq.heappop(open_set)

            if current_state in closed_set:
                continue

            if current_state.satisfies(goal_state):
                return [action.name for action in plan]

            closed_set.add(current_state)

            # Try each action
            for action in self.actions.values():
                if action.is_valid(current_state):
                    new_state = action.apply(current_state)
                    if new_state in closed_set:
                        continue

                    new_g = g_cost + action.cost
                    new_h = self._heuristic(new_state, goal_state)
                    new_plan = plan + [action]
                    heapq.heappush(open_set, (new_g + new_h, new_g, new_state, new_plan))

        return None  # No plan found

    def _heuristic(self, state: WorldState, goal: WorldState) -> float:
        """Heuristic: number of unsatisfied goal conditions."""
        unsatisfied = 0
        for key, value in goal.variables.items():
            if state.get(key) != value:
                unsatisfied += 1
        return float(unsatisfied)


class GOAPAgent:
    """GOAP-enabled agent."""

    def __init__(self):
        self.planner = GOAPPlanner()
        self.current_state = WorldState()
        self.goal_state = WorldState()
        self.current_plan: List[str] = []
        self.current_plan_index = 0

    def add_action(self, action: Action) -> None:
        self.planner.add_action(action)

    def set_goal(self, goal: WorldState) -> None:
        self.goal_state = goal
        self.current_plan = []
        self.current_plan_index = 0

    def update(self) -> Optional[str]:
        """Get next action to execute."""
        if not self.current_plan:
            # Replan
            plan = self.planner.plan(self.current_state, self.goal_state)
            if plan:
                self.current_plan = plan
                self.current_plan_index = 0
            else:
                return None  # No plan possible

        if self.current_plan_index < len(self.current_plan):
            action_name = self.current_plan[self.current_plan_index]
            return action_name
        return None

    def execute_action(self, action_name: str, world_state: WorldState) -> WorldState:
        """Execute action and update world state."""
        action = self.actions.get(action_name)
        if action and action.is_valid(self.current_state):
            self.current_state = action.apply(self.current_state)
            if action.callback:
                action.callback()
            self.current_plan_index += 1
        return self.current_state