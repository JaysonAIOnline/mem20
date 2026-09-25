"""Single-agent and interleaved multi-agent reinforcement-learning loops."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy

import numpy as np
import torch

from .agent import AgentConfig, AgentType, GameAgent, create_agent
from .curriculum import Curriculum, CurriculumConfig, CurriculumType, create_curriculum
from .environment import EnvConfig, Environment, StepResult, create_environment, decode_grid_obs
from .replay_buffer import Experience
from .reward_shaper import RewardConfig, RewardShaper, create_shaper

_STEP_BASED = (AgentType.DQN, AgentType.SAC)


def normalize_grid_size(difficulty: float, grid_range: tuple[int, int]) -> int:
    """Map normalized difficulty onto discrete inclusive grid sizes."""
    lower, upper = grid_range
    if lower < 2 or upper < lower:
        raise ValueError("grid_range must satisfy 2 <= lower <= upper")
    if upper == lower:
        return lower
    normalized = float(np.clip(difficulty, 0.0, 1.0))
    return min(upper, lower + int(np.floor(normalized * (upper - lower + 1))))


def _buffer_size(agent: GameAgent) -> int:
    replay = getattr(agent, "buffer", None)
    return len(replay) if replay is not None else 0


def _remember_transition(
    agent: GameAgent,
    observation: np.ndarray,
    result: StepResult,
    action: int,
    shaper: RewardShaper | None,
) -> None:
    terminated = bool(result.terminated)
    truncated = bool(result.truncated)
    reward = float(result.reward)
    if shaper is not None:
        reward = shaper.shape(
            reward=result.reward,
            state=observation,
            action=action,
            next_state=result.observation,
            done=terminated,
            info=result.info,
        )
    agent.remember(
        Experience(
            state=np.asarray(observation, dtype=np.float32),
            action=int(action),
            reward=float(reward),
            next_state=np.asarray(result.observation, dtype=np.float32),
            done=terminated,
            info=dict(result.info),
            truncated=truncated,
        )
    )


def _environment_progress(env: Environment, result: StepResult) -> float:
    position = result.info.get("pos")
    grid_size = result.info.get("grid_size", getattr(env.config, "grid_size", None))
    if position is None or grid_size is None:
        return 0.0
    initial_distance = 2 * (max(int(grid_size), 2) - 1)
    final_row, final_col = int(position[0]), int(position[1])
    final_distance = abs(int(grid_size) - 1 - final_row) + abs(int(grid_size) - 1 - final_col)
    return float(np.clip((initial_distance - final_distance) / initial_distance, 0.0, 1.0))


def _episode_metrics(rewards: list[float], steps: list[int], successes: list[bool]) -> dict[str, float]:
    return {
        "mean_reward": float(np.mean(rewards)),
        "std_reward": float(np.std(rewards)),
        "median_reward": float(np.median(rewards)),
        "mean_steps": float(np.mean(steps)),
        "success_rate": float(np.mean(successes)),
    }


class DQNTrainer:
    """Train one agent while integrating reward shaping and curriculum control."""

    def __init__(
        self,
        env_config: EnvConfig | None = None,
        agent_config: AgentConfig | None = None,
        reward_shaper: RewardShaper | None = None,
        curriculum: Curriculum | None = None,
        seed: int = 0,
    ):
        self.env_config = deepcopy(env_config or EnvConfig())
        self.agent_config = deepcopy(agent_config or AgentConfig())
        self.seed = int(seed)
        torch.manual_seed(self.seed)
        np.random.seed(self.seed)
        probe = create_environment(self.env_config)
        self.agent_config.obs_shape = probe.obs_shape
        self.agent_config.action_size = probe.action_size
        probe.close()
        self.agent: GameAgent = create_agent(self.agent_config)
        self.agent_type = self.agent_config.agent_type
        self.reward_shaper = reward_shaper
        self.curriculum = curriculum
        self.history: list[dict[str, float]] = []
        self.grid_range = (2, int(self.env_config.max_grid_size))

    def _make_env(self) -> Environment:
        config = deepcopy(self.env_config)
        if self.curriculum is not None:
            config.grid_size = normalize_grid_size(self.curriculum.get_difficulty(), self.grid_range)
        return create_environment(config)

    def train(self, episodes: int, update_every: int = 4, log_every: int = 10) -> list[dict[str, float]]:
        """Run a real training loop and return one metrics record per episode."""
        if episodes <= 0:
            raise ValueError("episodes must be positive")
        if update_every <= 0:
            raise ValueError("update_every must be positive")
        if log_every < 0:
            raise ValueError("log_every must be non-negative")
        self.history = []
        step_based = self.agent_type in _STEP_BASED
        recent_rewards: list[float] = []

        for episode in range(episodes):
            env = self._make_env()
            shaper = deepcopy(self.reward_shaper) if self.reward_shaper is not None else None
            if shaper is not None:
                shaper.reset()
            observation, _ = env.reset(seed=self.seed + episode)
            total_reward = 0.0
            steps = 0
            losses: list[float] = []
            updates = 0
            episode_performance = 0.0
            last_terminated = False
            transitions: list[tuple[np.ndarray, int, StepResult]] = []

            try:
                while True:
                    action = self.agent.act(observation, training=True)
                    result = env.step(action)
                    total_reward += float(result.reward)
                    episode_performance = _environment_progress(env, result)
                    last_terminated = bool(result.terminated)
                    finished = bool(result.terminated or result.truncated)

                    if step_based:
                        _remember_transition(self.agent, observation, result, action, shaper)
                        if (
                            steps % update_every == 0
                            and _buffer_size(self.agent) >= self.agent_config.batch_size
                        ):
                            metrics = self.agent.replay()
                            if metrics is not None:
                                losses.append(float(metrics.get("loss", metrics.get("q1_loss", 0.0))))
                                updates += 1
                    else:
                        transitions.append((observation, action, result))

                    observation = result.observation
                    steps += 1
                    if finished:
                        break

                if not step_based:
                    for transition_observation, transition_action, transition_result in transitions:
                        _remember_transition(
                            self.agent,
                            transition_observation,
                            transition_result,
                            transition_action,
                            shaper,
                        )
                    metrics = self.agent.learn()
                    if metrics:
                        losses.append(float(metrics.get("policy_loss", metrics.get("loss", 0.0))))
                        updates = 1

                self.agent.end_episode()
                if self.curriculum is not None:
                    self.curriculum.update(episode_performance)

                entry: dict[str, float] = {
                    "episode": float(episode),
                    "reward": float(total_reward),
                    "steps": float(steps),
                    "loss": float(np.mean(losses)) if losses else 0.0,
                    "updates": float(updates),
                    "epsilon": float(getattr(self.agent, "epsilon", 0.0)),
                    "difficulty": float(self.curriculum.get_difficulty()) if self.curriculum is not None else 0.0,
                    "buffer": float(_buffer_size(self.agent)),
                    "success": float(last_terminated),
                    "performance": float(episode_performance),
                }
                self.history.append(entry)
                recent_rewards.append(total_reward)
                if log_every and (episode + 1) % log_every == 0:
                    window = recent_rewards[-log_every:]
                    print(
                        f"  ep {episode + 1:>4}/{episodes}  reward {np.mean(window):8.3f}  "
                        f"loss {entry['loss']:8.4f}  eps {entry['epsilon']:5.3f}  "
                        f"diff {entry['difficulty']:.2f}"
                    )
            finally:
                env.close()
        return self.history

    def evaluate(self, episodes: int = 20, seed: int | None = None) -> dict[str, float]:
        """Evaluate the current greedy policy without learning or exploration."""
        if episodes <= 0:
            raise ValueError("episodes must be positive")
        env = self._make_env()
        rewards: list[float] = []
        steps: list[int] = []
        successes: list[bool] = []
        evaluation_seed = self.seed + 1000 if seed is None else int(seed)
        try:
            for episode in range(episodes):
                observation, _ = env.reset(seed=evaluation_seed + episode)
                total_reward = 0.0
                episode_steps = 0
                terminated = False
                last_terminated = False
                while not terminated:
                    action = self.agent.act(observation, training=False)
                    result = env.step(action)
                    total_reward += float(result.reward)
                    episode_steps += 1
                    last_terminated = bool(result.terminated)
                    terminated = bool(result.terminated or result.truncated)
                    observation = result.observation
                rewards.append(total_reward)
                steps.append(episode_steps)
                successes.append(last_terminated)
        finally:
            env.close()
        metrics = _episode_metrics(rewards, steps, successes)
        metrics["episodes"] = float(episodes)
        return metrics


class MultiAgentTrainer:
    """Interleave independent DQN or SAC agents across their own environments."""

    def __init__(
        self,
        n_agents: int,
        env_config: EnvConfig | None = None,
        agent_config: AgentConfig | None = None,
        reward_shaper_factory: Callable[[int], RewardShaper | None] | None = None,
        curriculum_factory: Callable[[int], Curriculum | None] | None = None,
        seed: int = 0,
    ):
        if n_agents < 1:
            raise ValueError("n_agents must be >= 1")
        self.n_agents = int(n_agents)
        self.seed = int(seed)
        self.env_config = deepcopy(env_config or EnvConfig())
        base_config = deepcopy(agent_config or AgentConfig())
        if base_config.agent_type not in _STEP_BASED:
            raise ValueError("multi-agent training requires DQN or SAC agents")
        probe = create_environment(self.env_config)
        base_config.obs_shape = probe.obs_shape
        base_config.action_size = probe.action_size
        probe.close()
        self.grid_range = (2, int(self.env_config.max_grid_size))
        self.agents: list[GameAgent] = []
        self.envs: list[Environment] = []
        self.shapers: list[RewardShaper | None] = []
        self.curricula: list[Curriculum | None] = []
        for index in range(self.n_agents):
            config = deepcopy(base_config)
            config.seed = self.seed + index
            self.agents.append(create_agent(config))
            self.envs.append(create_environment(deepcopy(self.env_config)))
            self.shapers.append(
                reward_shaper_factory(index) if reward_shaper_factory is not None else None
            )
            self.curricula.append(
                curriculum_factory(index) if curriculum_factory is not None else None
            )

    def _prepare_episode(self, index: int, episode: int) -> tuple[np.ndarray, float, int, list[float], int]:
        env = self.envs[index]
        curriculum = self.curricula[index]
        if curriculum is not None:
            env.config.grid_size = normalize_grid_size(curriculum.get_difficulty(), self.grid_range)
        shaper = self.shapers[index]
        if shaper is not None:
            shaper.reset()
        observation, _ = env.reset(seed=self.seed + episode * self.n_agents + index)
        return observation, 0.0, 0, [], 0

    def train(self, episodes: int, update_every: int = 4) -> dict[str, list[dict[str, float]]]:
        """Interleave every agent and perform an independent value update per experience."""
        if episodes <= 0:
            raise ValueError("episodes must be positive")
        if update_every <= 0:
            raise ValueError("update_every must be positive")
        histories: dict[str, list[dict[str, float]]] = {
            f"agent_{index}": [] for index in range(self.n_agents)
        }
        completed = [0] * self.n_agents
        active_observations: list[np.ndarray | None] = [None] * self.n_agents
        returns = [0.0] * self.n_agents
        step_counts = [0] * self.n_agents
        losses: list[list[float]] = [[] for _ in range(self.n_agents)]
        updates = [0] * self.n_agents

        for index in range(self.n_agents):
            active_observations[index], returns[index], step_counts[index], losses[index], updates[index] = (
                self._prepare_episode(index, 0)
            )

        while any(completed[index] < episodes for index in range(self.n_agents)):
            for index, (agent, env) in enumerate(zip(self.agents, self.envs)):
                if completed[index] >= episodes:
                    continue
                observation = active_observations[index]
                if observation is None:
                    raise RuntimeError("active agent is missing its current observation")
                action = agent.act(observation, training=True)
                result = env.step(action)
                _remember_transition(agent, observation, result, action, self.shapers[index])
                returns[index] += float(result.reward)
                transition_index = step_counts[index]
                step_counts[index] += 1
                if transition_index % update_every == 0 and _buffer_size(agent) >= agent.config.batch_size:
                    metrics = agent.replay()
                    if metrics is not None:
                        losses[index].append(float(metrics.get("loss", metrics.get("q1_loss", 0.0))))
                        updates[index] += 1
                active_observations[index] = result.observation
                if result.terminated or result.truncated:
                    performance = _environment_progress(env, result)
                    curriculum = self.curricula[index]
                    if curriculum is not None:
                        curriculum.update(performance)
                    histories[f"agent_{index}"].append(
                        {
                            "episode": float(completed[index]),
                            "reward": float(returns[index]),
                            "steps": float(step_counts[index]),
                            "loss": float(np.mean(losses[index])) if losses[index] else 0.0,
                            "updates": float(updates[index]),
                            "epsilon": float(getattr(agent, "epsilon", 0.0)),
                            "difficulty": float(curriculum.get_difficulty()) if curriculum is not None else 0.0,
                            "buffer": float(_buffer_size(agent)),
                            "success": float(bool(result.terminated)),
                            "performance": float(performance),
                        }
                    )
                    completed[index] += 1
                    losses[index] = []
                    if completed[index] < episodes:
                        active_observations[index], returns[index], step_counts[index], losses[index], updates[index] = (
                            self._prepare_episode(index, completed[index])
                        )
        return histories

    def evaluate(self, episodes: int = 20, seed: int | None = None) -> dict[str, dict[str, float]]:
        """Evaluate every greedy policy in its own environment."""
        if episodes <= 0:
            raise ValueError("episodes must be positive")
        results: dict[str, dict[str, float]] = {}
        evaluation_seed = self.seed + 1000 if seed is None else int(seed)
        for index, (agent, env) in enumerate(zip(self.agents, self.envs)):
            curriculum = self.curricula[index]
            if curriculum is not None:
                env.config.grid_size = normalize_grid_size(curriculum.get_difficulty(), self.grid_range)
            rewards: list[float] = []
            steps: list[int] = []
            successes: list[bool] = []
            for episode in range(episodes):
                observation, _ = env.reset(seed=evaluation_seed + episode * self.n_agents + index)
                total_reward = 0.0
                episode_steps = 0
                terminated = False
                last_terminated = False
                while not terminated:
                    action = agent.act(observation, training=False)
                    result = env.step(action)
                    total_reward += float(result.reward)
                    episode_steps += 1
                    last_terminated = bool(result.terminated)
                    terminated = bool(result.terminated or result.truncated)
                    observation = result.observation
                rewards.append(total_reward)
                steps.append(episode_steps)
                successes.append(last_terminated)
            metrics = _episode_metrics(rewards, steps, successes)
            metrics["episodes"] = float(episodes)
            results[f"agent_{index}"] = metrics
        return results

    def close(self) -> None:
        for env in self.envs:
            env.close()


def default_reward_shaper(gamma: float = 0.99) -> RewardShaper:
    """Create potential-based progress shaping aligned with the trainer discount."""
    def potential(state: np.ndarray) -> float:
        decoded = decode_grid_obs(state)
        if decoded is None:
            return 0.0
        row, col, _canvas, grid = decoded
        return float(-(abs(grid - 1 - row) + abs(grid - 1 - col)))

    return create_shaper(
        RewardConfig(shaping_type="potential", gamma=gamma),
        potential_fn=potential,
    )


def default_adaptive_curriculum(seed: int = 0) -> Curriculum:
    return create_curriculum(
        CurriculumConfig(
            curriculum_type=CurriculumType.ADAPTIVE,
            start_difficulty=0.0,
            end_difficulty=1.0,
            step_size=0.25,
            threshold=0.6,
            regress_threshold=0.1,
            window_size=10,
            seed=seed,
        )
    )
