"""Real PPO, DQN, SAC, and cooperative PPO trainers."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

import numpy as np

from .buffer import Buffer, Trajectory
from .environment import BehaviorSpec
from .model_saver import ModelSaver
from .policy import QNetwork, SACPolicy, create_policy
from .settings import (
    DQNSettings,
    POCASettings,
    PPOSettings,
    SACSettings,
    TrainerSettings,
    TrainerType,
    get_default_settings,
)
from .torch_policy import (
    TorchQNetwork,
    TorchSACPolicy,
    create_q_network,
    create_sac_policy,
)


@dataclass
class TrainingMetrics:
    step: int = 0
    episodes: int = 0
    mean_reward: float = 0.0
    mean_episode_length: float = 0.0
    policy_loss: float = 0.0
    value_loss: float = 0.0
    entropy: float = 0.0
    learning_rate: float = 0.0
    total_reward: float = 0.0
    updates: int = 0


class Trainer(ABC):
    """Common collection, checkpoint, and metrics behavior for RL trainers."""

    trainer_type = "base"

    def __init__(
        self,
        behavior_name: str,
        behavior_spec: BehaviorSpec,
        settings: TrainerSettings,
        policy: Any,
        buffer: Buffer | None,
        seed: int | None = None,
    ) -> None:
        self.behavior_name = behavior_name
        self.behavior_spec = behavior_spec
        self.settings = settings
        self.policy = policy
        if buffer is None:
            action_shape = self._action_shape(behavior_spec)
            buffer = Buffer(
                buffer_size=settings.buffer_size,
                observation_shape=behavior_spec.observation_shapes[0],
                action_shape=action_shape,
                seed=seed,
            )
        self.buffer = buffer
        self.metrics = TrainingMetrics(learning_rate=settings.learning_rate)
        self._rng = np.random.default_rng(seed)
        self._loss_history: list[float] = []
        self._episode_rewards: list[float] = []
        self._trajectory_history: list[Trajectory] = []

    @staticmethod
    def _action_shape(behavior_spec: BehaviorSpec) -> tuple[int, ...]:
        if behavior_spec.is_action_continuous:
            return (behavior_spec.action_spec.continuous_size,)
        if behavior_spec.action_spec.discrete_branches:
            return (len(behavior_spec.action_spec.discrete_branches),)
        return (1,)

    @property
    def loss_history(self) -> list[float]:
        return list(self._loss_history)

    def _record_episode(self, trajectory: Trajectory) -> None:
        reward = float(np.sum(trajectory.rewards))
        self._episode_rewards.append(reward)
        self.metrics.mean_reward = float(np.mean(self._episode_rewards[-100:]))
        self.metrics.mean_episode_length = float(
            np.mean([len(trajectory) for trajectory in self._recent_trajectories[-100:]])
        )

    @property
    def _recent_trajectories(self) -> list[Trajectory]:
        if not hasattr(self, "_trajectory_history"):
            self._trajectory_history: list[Trajectory] = []
        return self._trajectory_history

    def collect_trajectory(
        self,
        environment: Any,
        policy: Any = None,
        max_steps: int | None = None,
        deterministic: bool = False,
    ) -> Trajectory:
        """Run one complete real environment episode and record next states."""
        actor = self.policy if policy is None else policy
        infos = environment.reset()
        if self.behavior_name not in infos:
            raise KeyError(f"environment has no behavior {self.behavior_name}")
        trajectory = Trajectory(self.behavior_name)
        limit = int(max_steps or getattr(environment, "max_steps", 256))
        for _ in range(limit):
            observation = np.asarray(infos[self.behavior_name].observations[0], dtype=np.float32)
            output = actor.act(observation, deterministic=deterministic)
            step_output = environment.step({self.behavior_name: output.action})
            info = step_output.agent_info[self.behavior_name]
            next_observation = np.asarray(info.observations[0], dtype=np.float32)
            trajectory.add_step(
                observation,
                output.action,
                info.reward,
                output.log_prob,
                output.value,
                info.done,
                info={"max_step_reached": info.max_step_reached},
                next_observation=next_observation,
            )
            infos = {self.behavior_name: info}
            if info.done:
                break
        if trajectory.length() and not trajectory.dones[-1] and hasattr(actor, "value"):
            trajectory.bootstrap_values[-1] = float(actor.value(trajectory.next_observations[-1]))
        self._trajectory_history.append(trajectory)
        self._record_episode(trajectory)
        self.metrics.mean_episode_length = float(
            np.mean([len(item) for item in self._recent_trajectories[-100:]])
        )
        return trajectory

    @abstractmethod
    def update(self) -> dict[str, float]:
        raise NotImplementedError

    @abstractmethod
    def process_experiences(self, trajectories: list[Trajectory]) -> None:
        raise NotImplementedError

    def fit(
        self,
        environment: Any,
        total_steps: int,
        rollout_size: int | None = None,
        deterministic: bool = False,
    ) -> list[dict[str, float]]:
        """Collect real transitions and apply updates until the step budget ends."""
        updates: list[dict[str, float]] = []
        target = int(total_steps)
        if target < 1:
            raise ValueError("total_steps must be positive")
        budget = max(1, int(rollout_size or max(self.settings.time_horizon, self.settings.batch_size)))
        while self.metrics.step < target:
            trajectory = self.collect_trajectory(environment, max_steps=budget, deterministic=deterministic)
            self.process_experiences([trajectory])
            if self.buffer.size >= self.settings.batch_size:
                losses = self.update()
                if losses:
                    updates.append(losses)
        return updates

    def save(self, path: str) -> str:
        """Save the complete policy parameters."""
        return ModelSaver(path).save(
            self.policy,
            step=self.metrics.step,
            metrics=self.metrics.__dict__,
            trainer_type=self.trainer_type,
        )

    def load(self, path: str) -> dict[str, Any]:
        return ModelSaver(path).load(path, policy=self.policy)


class PPOTrainer(Trainer):
    """Clipped-surrogate PPO with GAE and value-function updates."""

    trainer_type = "ppo"

    def __init__(
        self,
        behavior_name: str,
        behavior_spec: BehaviorSpec,
        settings: PPOSettings,
        policy: Any = None,
        buffer: Buffer | None = None,
        seed: int | None = None,
    ) -> None:
        if policy is None:
            policy = create_policy(
                behavior_spec.observation_shapes[0],
                behavior_spec.action_spec,
                {
                    "hidden_units": settings.network_settings.hidden_units,
                    "num_layers": settings.network_settings.num_layers,
                    "learning_rate": settings.learning_rate,
                },
                continuous=behavior_spec.is_action_continuous,
                seed=seed,
            )
        if not hasattr(policy, "ppo_update"):
            raise TypeError("PPO requires a policy with a real ppo_update method")
        super().__init__(behavior_name, behavior_spec, settings, policy, buffer, seed)
        self.ppo_settings = settings
        self.metrics.learning_rate = settings.learning_rate

    def process_experiences(self, trajectories: list[Trajectory]) -> None:
        for trajectory in trajectories:
            returns = trajectory.compute_returns(self.settings.gamma)
            advantages = trajectory.compute_advantages(
                self.settings.gamma,
                self.settings.gae_lambda,
            )
            for index in range(trajectory.length()):
                self.buffer.add(
                    {
                        "observation": trajectory.observations[index],
                        "action": trajectory.actions[index],
                        "reward": trajectory.rewards[index],
                        "next_observation": trajectory.next_observations[index],
                        "done": trajectory.dones[index],
                        "log_prob": trajectory.log_probs[index],
                        "value": trajectory.values[index],
                        "advantage": float(advantages[index]),
                        "return_": float(returns[index]),
                    }
                )
            self.metrics.episodes += 1
            self.metrics.step += trajectory.length()
            self.metrics.total_reward += float(np.sum(trajectory.rewards))

    def update(self) -> dict[str, float]:
        if self.buffer.size < self.settings.batch_size:
            return {}
        size = self.buffer.size
        observations = self.buffer.observations[:size]
        actions = self.buffer.actions[:size]
        old_log_probs = self.buffer.log_probs[:size]
        advantages = self.buffer.advantages[:size]
        returns = self.buffer.returns[:size]
        losses = self.policy.ppo_update(
            observations,
            actions,
            old_log_probs,
            advantages,
            returns,
            clip_epsilon=self.ppo_settings.clip_epsilon,
            epochs=self.settings.num_epochs,
            batch_size=self.settings.batch_size,
            learning_rate=self.settings.learning_rate,
            value_coefficient=self.ppo_settings.value_coefficient,
            entropy_coefficient=self.ppo_settings.beta,
        )
        self._loss_history.append(float(losses["total_loss"]))
        self.metrics.policy_loss = float(losses["policy_loss"])
        self.metrics.value_loss = float(losses["value_loss"])
        self.metrics.entropy = float(losses["entropy"])
        self.metrics.updates += 1
        if self.ppo_settings.clear_after_update:
            self.buffer.clear()
        return losses


class DQNTrainer(Trainer):
    """Deep Q-learning with a target network and prioritized replay."""

    trainer_type = "dqn"

    def __init__(
        self,
        behavior_name: str,
        behavior_spec: BehaviorSpec,
        settings: DQNSettings,
        policy: Any = None,
        buffer: Buffer | None = None,
        seed: int | None = None,
    ) -> None:
        if behavior_spec.is_action_continuous:
            raise ValueError("DQN requires discrete actions")
        if behavior_spec.action_spec.discrete_branches:
            if len(behavior_spec.action_spec.discrete_branches) != 1:
                raise ValueError("DQN supports one flat discrete action branch")
            action_size = behavior_spec.action_spec.discrete_branches[0]
        else:
            action_size = behavior_spec.action_spec.discrete_size
        if action_size < 1:
            raise ValueError("DQN requires a positive discrete action size")
        if policy is None:
            policy = create_q_network(
                behavior_spec.observation_shapes[0],
                action_size,
                settings.network_settings.hidden_units,
                settings.network_settings.num_layers,
                settings.learning_rate,
                seed,
            )
        if not isinstance(policy, (QNetwork, TorchQNetwork)):
            raise TypeError("DQN requires a QNetwork or TorchQNetwork")
        super().__init__(behavior_name, behavior_spec, settings, policy, buffer, seed)
        self.dqn_settings = settings
        self.target = type(policy)(
            behavior_spec.observation_shapes[0],
            action_size,
            settings.network_settings.hidden_units,
            settings.network_settings.num_layers,
            settings.learning_rate,
            (seed or 0) + 1000,
        )
        self.target.load_state_dict(policy.state_dict())
        self.epsilon = float(settings.epsilon_init)
        self._target_updates = 0

    def act(self, observation: np.ndarray, deterministic: bool = False) -> int:
        if deterministic or self._rng.random() >= self.epsilon:
            return int(np.argmax(self.policy.q_values(np.asarray(observation, dtype=np.float32))))
        return int(self._rng.integers(self.policy.action_size))

    def process_experiences(self, trajectories: list[Trajectory]) -> None:
        for trajectory in trajectories:
            for index in range(trajectory.length()):
                self.buffer.add(
                    {
                        "observation": trajectory.observations[index],
                        "action": trajectory.actions[index],
                        "reward": trajectory.rewards[index],
                        "next_observation": trajectory.next_observations[index],
                        "done": trajectory.dones[index],
                    }
                )
            self.metrics.episodes += 1
            self.metrics.step += trajectory.length()
            self.metrics.total_reward += float(np.sum(trajectory.rewards))

    def update(self) -> dict[str, float]:
        if self.buffer.size < self.settings.batch_size:
            return {}
        if self.dqn_settings.prioritized:
            batch, indices, weights = self.buffer.sample_prioritized(
                self.settings.batch_size,
                self.dqn_settings.buffer_alpha,
                self.dqn_settings.buffer_beta,
            )
        else:
            batch = self.buffer.get_batch(self.settings.batch_size)
            indices = np.arange(batch["observations"].shape[0], dtype=np.int64)
            weights = None
        observations = batch["observations"]
        actions = batch["actions"].reshape(-1).astype(np.int64)
        rewards = batch["rewards"].astype(np.float64)
        next_observations = batch["next_observations"]
        dones = batch["dones"].astype(np.float64)
        next_values = np.max(self.target.q_values(next_observations), axis=1)
        targets = rewards + self.settings.gamma * (1.0 - dones) * next_values
        before = self.policy.q_values(observations)[np.arange(len(actions)), actions]
        loss = self.policy.update(observations, actions, targets, weights)
        td_errors = targets - before
        if self.dqn_settings.prioritized:
            self.buffer.update_priorities(indices, td_errors)
        self.epsilon = max(
            self.dqn_settings.epsilon_min,
            self.epsilon * self.dqn_settings.epsilon_decay,
        )
        self._target_updates += 1
        if self.dqn_settings.tau >= 1.0:
            if self._target_updates % max(1, self.dqn_settings.target_update_freq) == 0:
                self.target.load_state_dict(self.policy.state_dict())
        else:
            target_state = self.target.state_dict()
            source_state = self.policy.state_dict()
            self.target.load_state_dict(
                {key: self.dqn_settings.tau * source_state[key] + (1.0 - self.dqn_settings.tau) * target_state[key] for key in target_state}
            )
        losses = {
            "q_loss": float(loss),
            "mean_q": float(np.mean(before)),
            "mean_td_error": float(np.mean(np.abs(td_errors))),
            "epsilon": float(self.epsilon),
        }
        self._loss_history.append(float(loss))
        self.metrics.policy_loss = float(loss)
        self.metrics.value_loss = float(loss)
        self.metrics.updates += 1
        return losses

    def collect_trajectory(self, environment: Any, policy: Any = None, max_steps: int | None = None, deterministic: bool = False) -> Trajectory:
        """Collect using the trainer's epsilon-greedy action method."""
        if policy is not None:
            return super().collect_trajectory(environment, policy, max_steps, deterministic)
        infos = environment.reset()
        trajectory = Trajectory(self.behavior_name)
        limit = int(max_steps or getattr(environment, "max_steps", 256))
        for _ in range(limit):
            observation = np.asarray(infos[self.behavior_name].observations[0], dtype=np.float32)
            action = self.act(observation, deterministic)
            value = 0.0
            step_output = environment.step({self.behavior_name: np.asarray([action], dtype=np.float32)})
            info = step_output.agent_info[self.behavior_name]
            next_observation = np.asarray(info.observations[0], dtype=np.float32)
            trajectory.add_step(
                observation,
                np.asarray([action], dtype=np.float32),
                info.reward,
                0.0,
                value,
                info.done,
                next_observation=next_observation,
            )
            infos = {self.behavior_name: info}
            if info.done:
                break
        self._trajectory_history.append(trajectory)
        self._record_episode(trajectory)
        return trajectory


class SACTrainer(Trainer):
    """Off-policy soft actor-critic with twin critics and target smoothing."""

    trainer_type = "sac"

    def __init__(
        self,
        behavior_name: str,
        behavior_spec: BehaviorSpec,
        settings: SACSettings,
        policy: Any = None,
        buffer: Buffer | None = None,
        seed: int | None = None,
    ) -> None:
        if not behavior_spec.is_action_continuous:
            raise ValueError("SAC requires continuous actions")
        if policy is None:
            policy = create_sac_policy(
                behavior_spec.observation_shapes[0],
                behavior_spec.action_spec.continuous_size,
                settings.network_settings.hidden_units,
                settings.learning_rate,
                settings.target_entropy,
                seed,
            )
        if not isinstance(policy, (SACPolicy, TorchSACPolicy)):
            raise TypeError("SAC requires a SACPolicy or TorchSACPolicy")
        super().__init__(behavior_name, behavior_spec, settings, policy, buffer, seed)
        self.sac_settings = settings
        self.policy.set_log_alpha(math.log(max(settings.init_entcoef, 1e-8)))

    def process_experiences(self, trajectories: list[Trajectory]) -> None:
        for trajectory in trajectories:
            for index in range(trajectory.length()):
                self.buffer.add(
                    {
                        "observation": trajectory.observations[index],
                        "action": trajectory.actions[index],
                        "reward": trajectory.rewards[index],
                        "next_observation": trajectory.next_observations[index],
                        "done": trajectory.dones[index],
                        "log_prob": trajectory.log_probs[index],
                    }
                )
            self.metrics.episodes += 1
            self.metrics.step += trajectory.length()
            self.metrics.total_reward += float(np.sum(trajectory.rewards))

    def update(self) -> dict[str, float]:
        if self.buffer.size < self.settings.batch_size:
            return {}
        batch = self.buffer.get_batch(self.settings.batch_size)
        observations = batch["observations"]
        actions = batch["actions"]
        rewards = batch["rewards"].astype(np.float64)
        next_observations = batch["next_observations"]
        dones = batch["dones"].astype(np.float64)
        alpha = self.policy.alpha()
        next_actions, next_log_probs = self.policy.sample(next_observations)
        target_q1, target_q2 = self.policy.critic_values(next_observations, next_actions, target=True)
        targets = rewards + self.settings.gamma * (1.0 - dones) * (
            np.minimum(target_q1, target_q2) - alpha * next_log_probs
        )
        q1_loss, q2_loss = self.policy.update_critics(observations, actions, targets)
        actor_loss = self.policy.update_actor(observations, alpha)
        with_log_prob = self.policy.sample(observations)[1]
        alpha_loss = self.policy.update_alpha(with_log_prob)
        self.policy.soft_update(self.sac_settings.tau)
        losses = {
            "actor_loss": float(actor_loss),
            "critic_loss": float((q1_loss + q2_loss) / 2.0),
            "alpha_loss": float(alpha_loss),
            "alpha": alpha,
            "target_q": float(np.mean(targets)),
        }
        self._loss_history.append(float(losses["critic_loss"]))
        self.metrics.policy_loss = float(actor_loss)
        self.metrics.value_loss = float(losses["critic_loss"])
        self.metrics.updates += 1
        return losses


class POCATrainer:
    """Cooperative PPO with independent actors and a shared team critic."""

    trainer_type = "poca"

    def __init__(
        self,
        behavior_specs: dict[str, BehaviorSpec],
        settings: POCASettings,
        policy_factory: Any = None,
        buffer_size: int = 4096,
        batch_size: int = 64,
        num_epochs: int = 2,
        seed: int | None = None,
    ) -> None:
        if len(behavior_specs) < 1:
            raise ValueError("POCA requires at least one behavior")
        self.behavior_specs = behavior_specs
        self.settings = settings
        self.batch_size = int(batch_size)
        self.num_epochs = int(num_epochs)
        self._rng = np.random.default_rng(seed)
        self.metrics = TrainingMetrics(learning_rate=settings.learning_rate)
        self._loss_history: list[float] = []
        self._trajectory_history: list[Trajectory] = []
        self._episode_rewards: list[float] = []
        self.policies: dict[str, Any] = {}
        self.buffers: dict[str, Buffer] = {}
        for name, spec in behavior_specs.items():
            if policy_factory is not None:
                policy = policy_factory(name, spec)
            else:
                policy = create_policy(
                    spec.observation_shapes[0],
                    spec.action_spec,
                    {
                        "hidden_units": settings.hidden_units,
                        "num_layers": settings.network_settings.num_layers,
                        "learning_rate": settings.learning_rate,
                    },
                    continuous=spec.is_action_continuous,
                    seed=None if seed is None else seed + len(self.policies),
                )
            if not hasattr(policy, "ppo_update"):
                raise TypeError("POCA policy factory must return a trainable policy")
            self.policies[name] = policy
            action_shape = (spec.action_spec.continuous_size,) if spec.is_action_continuous else (1,)
            self.buffers[name] = Buffer(
                buffer_size=buffer_size,
                observation_shape=spec.observation_shapes[0],
                action_shape=action_shape,
                team_observation_shape=(sum(item.observation_dim for item in behavior_specs.values()),),
                seed=None if seed is None else seed + 100 + len(self.buffers),
            )
        self.team_dim = sum(spec.observation_dim for spec in behavior_specs.values())
        self.critic = create_q_network(
            (self.team_dim,),
            1,
            settings.hidden_units,
            settings.network_settings.num_layers,
            settings.learning_rate,
            None if seed is None else seed + 200,
        )

    @property
    def loss_history(self) -> list[float]:
        return list(self._loss_history)

    @property
    def behavior_name(self) -> str:
        return ",".join(self.behavior_specs)

    @property
    def policy(self) -> dict[str, Any]:
        return self.policies

    @property
    def buffer(self) -> Buffer:
        return self.buffers[next(iter(self.buffers))]

    @property
    def behavior_spec(self) -> BehaviorSpec:
        return next(iter(self.behavior_specs.values()))

    def process_experiences(self, trajectories: list[Trajectory]) -> None:
        grouped = {trajectory.agent_id: trajectory for trajectory in trajectories}
        if set(grouped) != set(self.behavior_specs):
            raise ValueError("POCA requires one trajectory for every behavior")
        names = list(self.behavior_specs)
        length = min(grouped[name].length() for name in names)
        for index in range(length):
            team_observation = np.concatenate(
                [np.asarray(grouped[name].observations[index], dtype=np.float32).reshape(-1) for name in names]
            )
            for name in names:
                trajectory = grouped[name]
                self.buffers[name].add(
                    {
                        "observation": trajectory.observations[index],
                        "team_observation": team_observation,
                        "action": trajectory.actions[index],
                        "reward": trajectory.rewards[index],
                        "next_observation": trajectory.next_observations[index],
                        "done": trajectory.dones[index],
                        "log_prob": trajectory.log_probs[index],
                    }
                )
        team_reward = float(np.mean([sum(grouped[name].rewards[:length]) for name in names]))
        self._episode_rewards.append(team_reward)
        self.metrics.episodes += 1
        self.metrics.step += length
        self.metrics.total_reward += team_reward
        self.metrics.mean_reward = float(np.mean(self._episode_rewards[-100:]))
        self.metrics.mean_episode_length = float(length)

    def update(self) -> dict[str, float]:
        if any(item.size < self.batch_size for item in self.buffers.values()):
            return {}
        critic_losses: list[float] = []
        actor_losses: list[float] = []
        for name, buffer in self.buffers.items():
            size = buffer.size
            team_observations = buffer.team_observations[:size]
            values = self.critic.q_values(team_observations).reshape(-1)
            buffer.values[:size] = values
            buffer.compute_advantages(self.settings.gamma, self.settings.gae_lambda)
            critic_loss = self.critic.update(
                team_observations,
                np.zeros(size, dtype=np.int64),
                buffer.returns[:size],
            )
            critic_losses.append(critic_loss)
            policy = self.policies[name]
            losses = policy.ppo_update(
                buffer.observations[:size],
                buffer.actions[:size],
                buffer.log_probs[:size],
                buffer.advantages[:size],
                buffer.returns[:size],
                clip_epsilon=self.settings.clip_epsilon,
                epochs=self.num_epochs,
                batch_size=self.batch_size,
                learning_rate=self.settings.learning_rate,
                value_coefficient=self.settings.value_coefficient,
                entropy_coefficient=self.settings.beta,
            )
            actor_losses.append(float(losses["policy_loss"]))
        mean_critic = float(np.mean(critic_losses))
        mean_actor = float(np.mean(actor_losses))
        self._loss_history.append(mean_actor)
        self.metrics.policy_loss = mean_actor
        self.metrics.value_loss = mean_critic
        self.metrics.updates += 1
        if self.settings.clear_after_update:
            for buffer in self.buffers.values():
                buffer.clear()
        return {"critic_loss": mean_critic, "policy_loss": mean_actor}

    def fit(self, environment: Any, total_steps: int, rollout_size: int = 64) -> list[dict[str, float]]:
        updates: list[dict[str, float]] = []
        target = int(total_steps)
        if target < 1:
            raise ValueError("total_steps must be positive")
        while self.metrics.step < target:
            infos = environment.reset()
            trajectories = {name: Trajectory(name) for name in self.behavior_specs}
            for _ in range(min(int(rollout_size), target - self.metrics.step)):
                actions: dict[str, np.ndarray] = {}
                outputs = {}
                for name in self.behavior_specs:
                    observation = infos[name].observations[0]
                    output = self.policies[name].act(observation)
                    outputs[name] = output
                    actions[name] = output.action
                step_output = environment.step(actions)
                next_infos = step_output.agent_info
                for name in self.behavior_specs:
                    info = next_infos[name]
                    observation = infos[name].observations[0]
                    output = outputs[name]
                    trajectories[name].add_step(
                        observation,
                        output.action,
                        info.reward,
                        output.log_prob,
                        output.value,
                        info.done,
                        next_observation=info.observations[0],
                    )
                infos = next_infos
                if any(info.done for info in next_infos.values()):
                    break
            self.process_experiences(list(trajectories.values()))
            if all(buffer.size >= self.batch_size for buffer in self.buffers.values()):
                losses = self.update()
                if losses:
                    updates.append(losses)
        return updates

    def save(self, path: str) -> list[str]:
        root = Path(path)
        saved = []
        for name, policy in self.policies.items():
            actor_saver = ModelSaver(str(root / name))
            saved.append(
                actor_saver.save(
                    policy,
                    step=self.metrics.step,
                    trainer_type="poca-actor",
                    settings={"behavior": name},
                )
            )
        critic_saver = ModelSaver(str(root / "critic"))
        saved.append(critic_saver.save(self.critic, step=self.metrics.step, trainer_type="poca-critic"))
        return saved


def _typed_settings(settings: TrainerSettings | str | TrainerType, trainer_type: str) -> TrainerSettings:
    if isinstance(settings, str):
        return get_default_settings(settings)
    if isinstance(settings, TrainerType):
        return get_default_settings(settings)
    classes = {
        "ppo": PPOSettings,
        "dqn": DQNSettings,
        "sac": SACSettings,
        "poca": POCASettings,
    }
    target_type = classes[trainer_type]
    if isinstance(settings, target_type):
        return settings
    typed = target_type()
    for field in fields(TrainerSettings):
        if hasattr(settings, field.name):
            setattr(typed, field.name, getattr(settings, field.name))
    typed.trainer_type = TrainerType(trainer_type)
    return typed


def create_trainer(
    behavior_name: str,
    behavior_spec: BehaviorSpec,
    settings: TrainerSettings | str | TrainerType,
    policy: Any = None,
    buffer: Buffer | None = None,
    team: dict[str, BehaviorSpec] | None = None,
    seed: int | None = None,
) -> Trainer | POCATrainer:
    """Create one implemented trainer from its explicit settings type."""
    requested = settings.value if isinstance(settings, TrainerType) else str(settings) if isinstance(settings, str) else settings.trainer_type.value
    trainer_type = requested.value if isinstance(requested, TrainerType) else str(requested)
    typed = _typed_settings(settings, trainer_type)
    if trainer_type == "ppo":
        return PPOTrainer(behavior_name, behavior_spec, typed, policy, buffer, seed)
    if trainer_type == "dqn":
        return DQNTrainer(behavior_name, behavior_spec, typed, policy, buffer, seed)
    if trainer_type == "sac":
        return SACTrainer(behavior_name, behavior_spec, typed, policy, buffer, seed)
    if trainer_type == "poca":
        return POCATrainer(team or {behavior_name: behavior_spec}, typed, seed=seed)
    raise ValueError(f"unknown trainer type: {trainer_type}")
