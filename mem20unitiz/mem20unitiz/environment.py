"""Concrete trainable environments and behavior specifications."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np


class ObservationType(str, Enum):
    VECTOR = "vector"
    VISUAL = "visual"


@dataclass
class ObservationSpec:
    shape: tuple[int, ...]
    observation_type: ObservationType = ObservationType.VECTOR
    name: str = ""

    def __post_init__(self) -> None:
        self.shape = tuple(int(value) for value in self.shape)
        if not self.shape or any(value < 1 for value in self.shape):
            raise ValueError("observation shape must contain positive dimensions")


@dataclass
class ActionSpec:
    continuous_size: int = 0
    discrete_size: int = 0
    discrete_branches: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.continuous_size = int(self.continuous_size)
        self.discrete_size = int(self.discrete_size)
        self.discrete_branches = [int(value) for value in self.discrete_branches]
        if self.continuous_size < 0 or self.discrete_size < 0:
            raise ValueError("action sizes must be non-negative")
        if self.continuous_size and (self.discrete_size or self.discrete_branches):
            raise ValueError("continuous and discrete action specifications are exclusive")
        if any(value < 1 for value in self.discrete_branches):
            raise ValueError("discrete branch sizes must be positive")
        if self.discrete_branches and self.discrete_size:
            raise ValueError("use discrete_size or discrete_branches, not both")

    @property
    def num_branches(self) -> int:
        if self.discrete_branches:
            return len(self.discrete_branches)
        return 1 if self.discrete_size > 0 else 0

    @property
    def total_discrete(self) -> int:
        return sum(self.discrete_branches) if self.discrete_branches else self.discrete_size


@dataclass
class BehaviorSpec:
    behavior_name: str
    observation_specs: list[ObservationSpec]
    action_spec: ActionSpec
    is_action_continuous: bool = False
    is_action_discrete: bool = False

    def __post_init__(self) -> None:
        if not self.behavior_name:
            raise ValueError("behavior_name must not be empty")
        if not self.observation_specs:
            raise ValueError("a behavior requires at least one observation specification")
        self.is_action_continuous = self.action_spec.continuous_size > 0
        self.is_action_discrete = self.action_spec.total_discrete > 0
        if not self.is_action_continuous and not self.is_action_discrete:
            raise ValueError("a behavior requires a continuous or discrete action")

    @property
    def observation_shapes(self) -> list[tuple[int, ...]]:
        return [spec.shape for spec in self.observation_specs]

    @property
    def observation_dim(self) -> int:
        return int(np.prod(self.observation_shapes[0]))


@dataclass
class AgentInfo:
    observations: list[np.ndarray]
    reward: float = 0.0
    done: bool = False
    max_step_reached: bool = False
    action_mask: np.ndarray | None = None
    agent_id: str = ""


@dataclass
class StepOutput:
    agent_info: dict[str, AgentInfo]
    action_taken: dict[str, np.ndarray]
    policy_outputs: dict[str, object] = field(default_factory=dict)


class Environment:
    """Base interface for environments with explicit reset and step methods."""

    def __init__(self, behavior_specs: dict[str, BehaviorSpec]) -> None:
        if not behavior_specs:
            raise ValueError("an environment requires at least one behavior")
        self.behavior_specs = behavior_specs
        self._step_count = 0

    def reset(self) -> dict[str, AgentInfo]:
        raise NotImplementedError

    def step(self, actions: dict[str, np.ndarray]) -> StepOutput:
        raise NotImplementedError

    def close(self) -> None:
        return None

    @property
    def step_count(self) -> int:
        return self._step_count


def _action_value(action: np.ndarray) -> float:
    values = np.asarray(action, dtype=np.float64).reshape(-1)
    if values.size == 0:
        raise ValueError("action must contain at least one value")
    return float(values[0])


class SimpleEnvironment(Environment):
    """A one-dimensional corridor whose action controls forward movement."""

    def __init__(
        self,
        behavior_specs: dict[str, BehaviorSpec],
        episode_length: int = 20,
        step_reward: float = 0.05,
        goal_reward: float = 1.0,
    ) -> None:
        super().__init__(behavior_specs)
        if int(episode_length) < 2:
            raise ValueError("episode_length must be at least two")
        self.episode_length = int(episode_length)
        self.step_reward = float(step_reward)
        self.goal_reward = float(goal_reward)
        self._positions = {name: 0.0 for name in behavior_specs}
        self._done = False

    def _observation(self, name: str) -> np.ndarray:
        shape = self.behavior_specs[name].observation_shapes[0]
        value = self._positions[name] / (self.episode_length - 1)
        observation = np.zeros(shape, dtype=np.float32)
        observation.reshape(-1)[0] = value
        return observation

    def reset(self) -> dict[str, AgentInfo]:
        self._step_count = 0
        self._done = False
        self._positions = {name: 0.0 for name in self.behavior_specs}
        return {
            name: AgentInfo([self._observation(name)], 0.0, False, False, agent_id=name)
            for name in self.behavior_specs
        }

    def step(self, actions: dict[str, np.ndarray]) -> StepOutput:
        if self._done:
            infos = {
                name: AgentInfo([self._observation(name)], 0.0, True, False, agent_id=name)
                for name in self.behavior_specs
            }
            return StepOutput(infos, actions)
        self._step_count += 1
        infos: dict[str, AgentInfo] = {}
        for name, spec in self.behavior_specs.items():
            if name not in actions:
                raise KeyError(f"missing action for behavior {name}")
            raw_action = np.asarray(actions[name])
            if spec.is_action_continuous:
                command = _action_value(raw_action)
                if abs(command) < 1e-8:
                    command = 1.0
            else:
                branch = int(np.asarray(raw_action).reshape(-1)[0])
                command = 1.0 if branch == 0 else -1.0
            previous = self._positions[name]
            self._positions[name] = float(np.clip(previous + command, 0.0, self.episode_length - 1))
            reached = self._positions[name] >= self.episode_length - 1
            blocked = abs(self._positions[name] - previous) < 1e-8 and not reached
            reward = self.step_reward + (self.goal_reward if reached else 0.0)
            if blocked:
                reward -= 0.1
            done = reached or self._step_count >= self.episode_length
            infos[name] = AgentInfo(
                [self._observation(name)],
                float(reward),
                bool(done),
                bool(self._step_count >= self.episode_length and not reached),
                agent_id=name,
            )
        self._done = all(info.done for info in infos.values())
        return StepOutput(infos, actions)


class GridWorld(Environment):
    """A deterministic or continuous grid-navigation task with dense shaping."""

    def __init__(
        self,
        behavior_name: str = "grid",
        grid_size: int = 5,
        discrete: bool = True,
        max_steps: int = 32,
        seed: int | None = None,
        goal_reward: float = 1.0,
        step_penalty: float = 0.01,
        wall_penalty: float = 0.1,
        shaping_scale: float = 0.5,
        goal: tuple[int, int] | None = None,
    ) -> None:
        if int(grid_size) < 2:
            raise ValueError("grid_size must be at least two")
        self.grid_size = int(grid_size)
        self.discrete = bool(discrete)
        self.max_steps = int(max_steps)
        self.goal = tuple(goal or (self.grid_size - 1, self.grid_size - 1))
        if len(self.goal) != 2 or any(value < 0 or value >= self.grid_size for value in self.goal):
            raise ValueError("goal must be inside the grid")
        obs_spec = ObservationSpec((2,), name="position")
        action_spec = ActionSpec(discrete_branches=[4]) if self.discrete else ActionSpec(continuous_size=2)
        spec = BehaviorSpec(behavior_name, [obs_spec], action_spec)
        super().__init__({behavior_name: spec})
        self.behavior_name = behavior_name
        self.goal_reward = float(goal_reward)
        self.step_penalty = float(step_penalty)
        self.wall_penalty = float(wall_penalty)
        self.shaping_scale = float(shaping_scale)
        self._rng = np.random.default_rng(seed)
        self._max_distance = max(1.0, float(np.hypot(*self.goal)))
        self._position = np.zeros(2, dtype=np.float64)
        self._done = False

    @property
    def position(self) -> tuple[int, int]:
        return round(float(self._position[0])), round(float(self._position[1]))

    def _observation(self) -> np.ndarray:
        scale = max(1.0, self.grid_size - 1.0)
        return np.asarray(self._position / scale, dtype=np.float32)

    def _potential(self, position: np.ndarray) -> float:
        distance = float(np.linalg.norm(position - np.asarray(self.goal, dtype=np.float64)))
        return -self.shaping_scale * distance / self._max_distance

    def reset(self) -> dict[str, AgentInfo]:
        self._step_count = 0
        self._done = False
        if self.discrete:
            self._position = np.zeros(2, dtype=np.float64)
        else:
            self._position = self._rng.uniform(0.0, 0.5, size=2)
        return {
            self.behavior_name: AgentInfo(
                [self._observation()], 0.0, False, False, agent_id=self.behavior_name
            )
        }

    def step(self, actions: dict[str, np.ndarray]) -> StepOutput:
        if self._done:
            info = AgentInfo([self._observation()], 0.0, True, False, agent_id=self.behavior_name)
            return StepOutput({self.behavior_name: info}, actions)
        self._step_count += 1
        if self.behavior_name not in actions:
            raise KeyError(f"missing action for behavior {self.behavior_name}")
        previous = self._position.copy()
        previous_potential = self._potential(previous)
        wall_bump = False
        if self.discrete:
            action = int(np.asarray(actions[self.behavior_name]).reshape(-1)[0])
            moves = ((0, 1), (0, -1), (-1, 0), (1, 0))
            dx, dy = moves[action % 4]
            nx, ny = int(previous[0] + dx), int(previous[1] + dy)
            if not (0 <= nx < self.grid_size and 0 <= ny < self.grid_size):
                nx, ny = int(previous[0]), int(previous[1])
                wall_bump = True
            self._position = np.asarray([nx, ny], dtype=np.float64)
        else:
            action = np.asarray(actions[self.behavior_name], dtype=np.float64).reshape(-1)
            if action.size < 2:
                raise ValueError("continuous GridWorld actions require two values")
            self._position = np.clip(self._position + np.clip(action[:2], -1.0, 1.0) * 0.8, 0.0, self.grid_size - 1.0)
        current_potential = self._potential(self._position)
        reached = self.position == self.goal
        done = reached or self._step_count >= self.max_steps
        reward = -self.step_penalty + (self.goal_reward if reached else 0.0)
        reward += current_potential - previous_potential
        if wall_bump:
            reward -= self.wall_penalty
        info = AgentInfo(
            [self._observation()],
            float(reward),
            bool(done),
            bool(self._step_count >= self.max_steps and not reached),
            agent_id=self.behavior_name,
        )
        self._done = bool(done)
        return StepOutput({self.behavior_name: info}, actions)


class CooperativeGridWorld(Environment):
    """A two-agent cooperative grid task with a shared team reward."""

    def __init__(
        self,
        behavior_names: list[str] | None = None,
        grid_size: int = 5,
        max_steps: int = 48,
        seed: int | None = None,
        goal_reward: float = 1.0,
        step_penalty: float = 0.01,
        wall_penalty: float = 0.1,
        shaping_scale: float = 0.5,
    ) -> None:
        names = list(behavior_names or ["agent_0", "agent_1"])
        if len(names) != 2 or len(set(names)) != 2:
            raise ValueError("CooperativeGridWorld requires exactly two unique behavior names")
        if int(grid_size) < 2:
            raise ValueError("grid_size must be at least two")
        self.behavior_names = names
        self.grid_size = int(grid_size)
        self.max_steps = int(max_steps)
        self.goal_reward = float(goal_reward)
        self.step_penalty = float(step_penalty)
        self.wall_penalty = float(wall_penalty)
        self.shaping_scale = float(shaping_scale)
        self.starts = ((0, 0), (0, self.grid_size - 1))
        self.goals = ((self.grid_size - 1, self.grid_size - 1), (self.grid_size - 1, 0))
        specs = {
            name: BehaviorSpec(
                name,
                [ObservationSpec((2,), name="position")],
                ActionSpec(discrete_branches=[4]),
            )
            for name in names
        }
        super().__init__(specs)
        self._rng = np.random.default_rng(seed)
        self._positions = {name: np.asarray(start, dtype=np.float64) for name, start in zip(names, self.starts)}
        self._reached = {name: False for name in names}
        self._done = False

    def _observation(self, name: str) -> np.ndarray:
        scale = max(1.0, self.grid_size - 1.0)
        return np.asarray(self._positions[name] / scale, dtype=np.float32)

    def reset(self) -> dict[str, AgentInfo]:
        self._step_count = 0
        self._done = False
        self._positions = {name: np.asarray(start, dtype=np.float64) for name, start in zip(self.behavior_names, self.starts)}
        self._reached = {name: False for name in self.behavior_names}
        return {
            name: AgentInfo([self._observation(name)], 0.0, False, False, agent_id=name)
            for name in self.behavior_names
        }

    def step(self, actions: dict[str, np.ndarray]) -> StepOutput:
        if self._done:
            infos = {
                name: AgentInfo([self._observation(name)], 0.0, True, False, agent_id=name)
                for name in self.behavior_names
            }
            return StepOutput(infos, actions)
        self._step_count += 1
        moves = ((0, 1), (0, -1), (-1, 0), (1, 0))
        team_reward = 0.0
        for index, name in enumerate(self.behavior_names):
            if name not in actions:
                raise KeyError(f"missing action for behavior {name}")
            previous = self._positions[name].copy()
            action = int(np.asarray(actions[name]).reshape(-1)[0])
            dx, dy = moves[action % 4]
            nx, ny = int(previous[0] + dx), int(previous[1] + dy)
            wall_bump = not (0 <= nx < self.grid_size and 0 <= ny < self.grid_size)
            if wall_bump:
                nx, ny = int(previous[0]), int(previous[1])
            self._positions[name] = np.asarray([nx, ny], dtype=np.float64)
            goal = np.asarray(self.goals[index], dtype=np.float64)
            previous_potential = -self.shaping_scale * float(np.linalg.norm(previous - goal)) / max(1.0, self.grid_size - 1.0)
            current_potential = -self.shaping_scale * float(np.linalg.norm(self._positions[name] - goal)) / max(1.0, self.grid_size - 1.0)
            reached = (int(nx), int(ny)) == self.goals[index]
            self._reached[name] = self._reached[name] or reached
            reward = -self.step_penalty + (self.goal_reward if reached else 0.0)
            reward += current_potential - previous_potential
            if wall_bump:
                reward -= self.wall_penalty
            team_reward += reward
        all_done = all(self._reached.values())
        done = all_done or self._step_count >= self.max_steps
        infos = {
            name: AgentInfo(
                [self._observation(name)],
                float(team_reward),
                bool(done),
                bool(self._step_count >= self.max_steps and not all_done),
                agent_id=name,
            )
            for name in self.behavior_names
        }
        self._done = bool(done)
        return StepOutput(infos, actions)
