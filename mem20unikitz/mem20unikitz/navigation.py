"""Navigation — native absorption of UniKit navigation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
from collections import deque
import heapq
import math


@dataclass
class Vector2:
    """2D vector."""
    x: float = 0.0
    y: float = 0.0

    def __add__(self, other: "Vector2") -> "Vector2":
        return Vector2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Vector2") -> "Vector2":
        return Vector2(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> "Vector2":
        return Vector2(self.x * scalar, self.y * scalar)

    def length(self) -> float:
        return math.hypot(self.x, self.y)

    def normalized(self) -> "Vector2":
        l = self.length()
        return Vector2(self.x / l, self.y / l) if l > 0 else Vector2(0, 0)

    def distance_to(self, other: "Vector2") -> float:
        return (self - other).length()

    def to_tuple(self) -> Tuple[float, float]:
        return (self.x, self.y)


@dataclass
class NavNode:
    """Navigation graph node."""
    position: Vector2
    neighbors: List["NavNode"] = field(default_factory=list)
    cost: float = 1.0
    walkable: bool = True
    metadata: Dict = field(default_factory=dict)


class NavMesh:
    """Simple navigation mesh."""

    def __init__(self):
        self.nodes: List[NavNode] = []
        self.grid: Dict[Tuple[int, int], NavNode] = {}
        self.cell_size = 1.0

    def add_node(self, position: Vector2, walkable: bool = True, cost: float = 1.0) -> NavNode:
        node = NavNode(position=position, walkable=walkable, cost=cost)
        self.nodes.append(node)
        grid_key = (int(position.x / self.cell_size), int(position.y / self.cell_size))
        self.grid[grid_key] = node
        return node

    def get_node_at(self, position: Vector2) -> Optional[NavNode]:
        grid_key = (int(position.x / self.cell_size), int(position.y / self.cell_size))
        return self.grid.get(grid_key)

    def connect_nodes(self, a: NavNode, b: NavNode, bidirectional: bool = True):
        if b not in a.neighbors:
            a.neighbors.append(b)
        if bidirectional and a not in b.neighbors:
            b.neighbors.append(a)

    def build_from_grid(self, width: int, height: int, walkable_fn: Callable[[int, int], bool]):
        """Build nav mesh from grid."""
        self.nodes.clear()
        self.grid.clear()
        for x in range(width):
            for y in range(height):
                walkable = walkable_fn(x, y)
                node = self.add_node(Vector2(x, y), walkable)
                # Connect to neighbors
                for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < width and 0 <= ny < height:
                        neighbor = self.grid.get((nx, ny))
                        if neighbor and neighbor.walkable and node.walkable:
                            self.connect_nodes(node, neighbor)


class AStarPathfinder:
    """A* pathfinding."""

    def __init__(self, nav_mesh: NavMesh):
        self.nav_mesh = nav_mesh

    def find_path(self, start: Vector2, goal: Vector2) -> List[Vector2]:
        start_node = self.nav_mesh.get_node_at(start)
        goal_node = self.nav_mesh.get_node_at(goal)

        if not start_node or not goal_node:
            return []

        if not start_node.walkable or not goal_node.walkable:
            return []

        open_set = []
        closed_set = set()
        came_from: Dict = {}
        g_score = {start_node: 0}
        f_score = {start_node: self._heuristic(start_node, goal_node)}

        open_set = [(self._heuristic(start_node, goal_node), start_node)]

        while open_set:
            _, current = heapq.heappop(open_set)

            if current == goal_node:
                return self._reconstruct_path(came_from, current)

            for neighbor in current.neighbors:
                if not neighbor.walkable:
                    continue

                tentative_g = g_score[current] + current.cost
                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score = tentative_g + self._heuristic(neighbor, goal_node)
                    heapq.heappush(open_set, (f_score, neighbor))

        return []  # No path found

    def _heuristic(self, a: "NavNode", b: "NavNode") -> float:
        return a.position.distance_to(b.position)

    def _reconstruct_path(self, came_from: Dict, current: "NavNode") -> List[Vector2]:
        path = [current.position]
        while current in came_from:
            current = came_from[current]
            path.append(current.position)
        return list(reversed(path))


class NavigationAgent:
    """Agent with navigation capabilities."""

    def __init__(self, nav_mesh: NavMesh):
        self.nav_mesh = nav_mesh
        self.pathfinder = AStarPathfinder(nav_mesh)
        self.current_path: List[Vector2] = []
        self.current_target_index = 0
        self.position = Vector2(0, 0)
        self.speed = 1.0

    def set_position(self, position: Vector2):
        self.position = position

    def set_goal(self, goal: Vector2) -> bool:
        path = self.nav_mesh.find_path(self.position, goal)
        if path:
            self.current_path = path
            self.current_target_index = 1  # Skip current position
            return True
        return False

    def update(self, dt: float) -> bool:
        """Update agent position along path. Returns True if reached goal."""
        if not self.current_path or self.current_target_index >= len(self.current_path):
            return False

        target = self.current_path[self.current_target_index]
        direction = target - self.position
        distance = direction.length()

        if distance < 0.1:  # Close enough to waypoint
            self.current_target_index += 1
            if self.current_target_index >= len(self.current_path):
                return True  # Reached final goal
            return False

        # Move towards target
        move = direction.normalized() * self.speed * dt
        self.position += move
        return False

    def reached_goal(self) -> bool:
        return not self.current_path or self.current_target_index >= len(self.current_path)


class NavAgentManager:
    """Manages multiple navigation agents."""

    def __init__(self, nav_mesh: NavMesh):
        self.nav_mesh = nav_mesh
        self.agents: Dict[str, NavigationAgent] = {}

    def create_agent(self, agent_id: str, start_pos: Vector2, speed: float = 1.0) -> NavigationAgent:
        agent = NavigationAgent(self.nav_mesh)
        agent.set_position(start_pos)
        agent.speed = 1.0
        self.agents[agent_id] = agent
        return agent

    def remove_agent(self, agent_id: str) -> bool:
        if agent_id in self.agents:
            del self.agents[agent_id]
            return True
        return False

    def update_all(self, dt: float) -> Dict[str, bool]:
        results = {}
        for agent_id, agent in self.agents.items():
            results[agent_id] = agent.update(dt)
        return results