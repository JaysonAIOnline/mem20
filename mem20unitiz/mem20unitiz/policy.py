"""Real Torch and NumPy reinforcement-learning policies and network primitives."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import numpy as np

try:
    import torch

    TORCH_AVAILABLE = True
except ImportError:
    torch = None
    TORCH_AVAILABLE = False


@dataclass
class PolicyOutput:
    """One sampled action and its associated distribution statistics."""

    action: Any
    log_prob: float
    value: float
    entropy: float = 0.0
    hidden_state: np.ndarray | None = None


class Policy(ABC):
    """Interface shared by stochastic policies."""

    @abstractmethod
    def act(self, obs: np.ndarray, deterministic: bool = False) -> PolicyOutput:
        raise NotImplementedError

    @abstractmethod
    def evaluate(self, obs: np.ndarray, action: np.ndarray) -> tuple[float, float, float]:
        raise NotImplementedError


def _batch(obs: np.ndarray, obs_dim: int) -> np.ndarray:
    value = np.asarray(obs, dtype=np.float64)
    if value.ndim == 1:
        value = value.reshape(1, -1)
    if value.ndim != 2 or value.shape[1] != obs_dim:
        raise ValueError(f"observation shape {value.shape} does not match ({obs_dim},)")
    return value


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits, axis=-1, keepdims=True)
    exp = np.exp(shifted)
    return exp / np.sum(exp, axis=-1, keepdims=True)


def _tanh_backward(values: np.ndarray) -> np.ndarray:
    return 1.0 - values * values


if TORCH_AVAILABLE:
    import torch.nn.functional as F
    from torch import nn
    from torch.distributions import Categorical, Independent, Normal

    class _TorchBranchDistribution:
        def __init__(self, logits: list[torch.Tensor]) -> None:
            self.distributions = [Categorical(logits=item) for item in logits]

        def sample(self) -> torch.Tensor:
            return torch.cat([item.sample().unsqueeze(-1) for item in self.distributions], dim=-1)

        @property
        def mode(self) -> torch.Tensor:
            return torch.cat([item.mode.unsqueeze(-1) for item in self.distributions], dim=-1)

        def log_prob(self, action: torch.Tensor) -> torch.Tensor:
            result = torch.zeros(action.shape[0], dtype=action.dtype, device=action.device)
            for index, distribution in enumerate(self.distributions):
                result = result + distribution.log_prob(action[:, index])
            return result

        def entropy(self) -> torch.Tensor:
            result = torch.zeros((), dtype=torch.get_default_dtype(), device=self.distributions[0].logits.device)
            for distribution in self.distributions:
                result = result + distribution.entropy()
            return result

    class TorchPolicy(nn.Module, Policy):
        """Real Torch actor-critic used automatically when Torch is installed."""

        def __init__(
            self,
            obs_shape: tuple[int, ...],
            action_spec: Any,
            continuous: bool | None = None,
            hidden_units: int = 16,
            num_layers: int = 1,
            learning_rate: float = 0.01,
            seed: int | None = None,
        ) -> None:
            super().__init__()
            if seed is not None:
                torch.manual_seed(int(seed))
            self.obs_shape = tuple(obs_shape)
            self.obs_dim = int(np.prod(self.obs_shape))
            self.action_spec = action_spec
            self.continuous = bool(action_spec.continuous_size > 0 if continuous is None else continuous)
            if self.continuous:
                self.action_size = int(action_spec.continuous_size)
                self.discrete_branches = None
            elif action_spec.discrete_branches:
                self.discrete_branches = [int(value) for value in action_spec.discrete_branches]
                self.action_size = sum(self.discrete_branches)
            else:
                self.discrete_branches = None
                self.action_size = int(action_spec.discrete_size)
            if self.action_size < 1:
                raise ValueError("policy requires a positive action dimension")
            self.hidden_units = max(1, int(hidden_units))
            self.num_layers = max(1, int(num_layers))
            self.actor = self._network(self.action_size)
            self.critic = self._network(1)
            if self.continuous:
                self.log_std = nn.Parameter(torch.full((self.action_size,), -0.5))
            self.optimizer = torch.optim.Adam(self.parameters(), lr=float(learning_rate))

        def _network(self, output_size: int) -> nn.Sequential:
            layers: list[nn.Module] = []
            width = self.obs_dim
            for _ in range(self.num_layers):
                layers.extend((nn.Linear(width, self.hidden_units), nn.Tanh()))
                width = self.hidden_units
            layers.append(nn.Linear(width, output_size))
            return nn.Sequential(*layers)

        def _distribution(self, observations: torch.Tensor) -> tuple[Any, torch.Tensor]:
            observations = observations.float()
            if observations.ndim == 1:
                observations = observations.unsqueeze(0)
            value = self.critic(observations).squeeze(-1)
            logits = self.actor(observations)
            if self.continuous:
                std = torch.exp(torch.clamp(self.log_std, -8.0, 2.0)).expand_as(logits)
                return Independent(Normal(logits, std), 1), value
            if self.discrete_branches:
                parts = []
                offset = 0
                for size in self.discrete_branches:
                    parts.append(logits[:, offset : offset + size])
                    offset += size
                return _TorchBranchDistribution(parts), value
            return Categorical(logits=logits), value

        def _values(self, distribution: Any, actions: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
            if self.continuous:
                return distribution.log_prob(actions), distribution.entropy()
            if self.discrete_branches:
                return distribution.log_prob(actions), distribution.entropy()
            return distribution.log_prob(actions), distribution.entropy()

        def act(self, obs: np.ndarray, deterministic: bool = False) -> PolicyOutput:
            with torch.no_grad():
                distribution, value = self._distribution(torch.as_tensor(obs, dtype=torch.float32))
                action = distribution.mean if self.continuous and deterministic else distribution.mode if deterministic else distribution.sample()
                log_prob, entropy = self._values(distribution, action)
                if self.continuous:
                    output_action: Any = action[0].cpu().numpy().astype(np.float32)
                elif self.discrete_branches:
                    output_action = action[0].cpu().numpy().astype(np.int64)
                else:
                    output_action = int(action[0].item())
                return PolicyOutput(output_action, float(log_prob[0].item()), float(value[0].item()), float(entropy.mean().item()))

        def _canonical_actions(self, actions: np.ndarray, count: int) -> torch.Tensor:
            tensor = torch.as_tensor(actions)
            if self.continuous:
                return tensor.float().reshape(count, self.action_size)
            if self.discrete_branches:
                result = tensor.long().reshape(count, len(self.discrete_branches))
                limits = torch.as_tensor(self.discrete_branches, dtype=torch.long)
                if torch.any(result < 0) or torch.any(result >= limits):
                    raise ValueError("action is outside its discrete branch")
                return result
            result = tensor.long().reshape(count)
            if torch.any(result < 0) or torch.any(result >= self.action_size):
                raise ValueError("discrete action is outside its action range")
            return result

        def evaluate_batch(self, observations: np.ndarray, actions: np.ndarray) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
            distribution, value = self._distribution(torch.as_tensor(observations, dtype=torch.float32))
            count = value.shape[0]
            action_tensor = self._canonical_actions(actions, count)
            log_prob, entropy = self._values(distribution, action_tensor)
            return log_prob, entropy, value

        def evaluate_actions(self, observations: np.ndarray, actions: np.ndarray) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
            return self.evaluate_batch(observations, actions)

        def evaluate(self, obs: np.ndarray, action: np.ndarray) -> tuple[float, float, float]:
            log_prob, entropy, value = self.evaluate_batch(np.asarray(obs), np.asarray(action))
            return float(log_prob[0].item()), float(entropy[0].item()), float(value[0].item())

        def value(self, obs: np.ndarray) -> float:
            with torch.no_grad():
                _, value = self._distribution(torch.as_tensor(obs, dtype=torch.float32))
            return float(value[0].item())

        def parameter_norm(self) -> float:
            return math.sqrt(sum(float(torch.sum(parameter * parameter).item()) for parameter in self.parameters()))

        def ppo_update(
            self,
            observations: np.ndarray,
            actions: np.ndarray,
            old_log_probs: np.ndarray,
            advantages: np.ndarray,
            returns: np.ndarray,
            clip_epsilon: float = 0.2,
            epochs: int = 2,
            batch_size: int = 64,
            learning_rate: float | None = None,
            value_coefficient: float = 0.5,
            entropy_coefficient: float = 0.01,
        ) -> dict[str, float]:
            observations_t = torch.as_tensor(observations, dtype=torch.float32)
            if observations_t.ndim == 1:
                observations_t = observations_t.unsqueeze(0)
            old_t = torch.as_tensor(old_log_probs, dtype=torch.float32).detach().reshape(-1)
            advantages_t = torch.as_tensor(advantages, dtype=torch.float32).detach().reshape(-1)
            returns_t = torch.as_tensor(returns, dtype=torch.float32).detach().reshape(-1)
            if observations_t.shape[0] == 0:
                raise ValueError("cannot update a policy with an empty batch")
            if float(torch.std(advantages_t)) > 1e-8:
                advantages_t = (advantages_t - torch.mean(advantages_t)) / (torch.std(advantages_t) + 1e-8)
            if learning_rate is not None:
                for group in self.optimizer.param_groups:
                    group["lr"] = float(learning_rate)
            totals = {"policy_loss": 0.0, "value_loss": 0.0, "entropy": 0.0, "total_loss": 0.0}
            batches = 0
            for _ in range(max(1, int(epochs))):
                order = torch.randperm(observations_t.shape[0])
                for start in range(0, observations_t.shape[0], max(1, int(batch_size))):
                    indices = order[start : start + max(1, int(batch_size))]
                    distribution, values = self._distribution(observations_t[indices])
                    action_tensor = self._canonical_actions(actions, observations_t.shape[0])[indices]
                    log_prob, entropy = self._values(distribution, action_tensor)
                    ratio = torch.exp(torch.clamp(log_prob - old_t[indices], -20.0, 20.0))
                    advantage = advantages_t[indices]
                    unclipped = ratio * advantage
                    clipped = torch.clamp(ratio, 1.0 - clip_epsilon, 1.0 + clip_epsilon) * advantage
                    policy_loss = -torch.minimum(unclipped, clipped).mean()
                    value_loss = F.mse_loss(values, returns_t[indices])
                    entropy_value = entropy.mean()
                    total_loss = policy_loss + value_coefficient * value_loss - entropy_coefficient * entropy_value
                    self.optimizer.zero_grad(set_to_none=True)
                    total_loss.backward()
                    nn.utils.clip_grad_norm_(self.parameters(), 0.5)
                    self.optimizer.step()
                    totals["policy_loss"] += float(policy_loss.item())
                    totals["value_loss"] += float(value_loss.item())
                    totals["entropy"] += float(entropy_value.item())
                    totals["total_loss"] += float(total_loss.item())
                    batches += 1
            return {key: value / max(1, batches) for key, value in totals.items()}

        def update(
            self,
            observations: np.ndarray,
            actions: np.ndarray,
            advantages: np.ndarray,
            returns: np.ndarray | None = None,
            old_log_probs: np.ndarray | None = None,
            **kwargs: Any,
        ) -> dict[str, float]:
            current, _, _ = self.evaluate_batch(observations, actions)
            if returns is None:
                returns = np.asarray(advantages, dtype=np.float32).reshape(-1)
            if old_log_probs is None:
                old_log_probs = current.detach().cpu().numpy()
            return self.ppo_update(observations, actions, old_log_probs, advantages, returns, **kwargs)


class NumPyPolicy(Policy):
    """A real NumPy actor-critic network with sampled actions and gradients.

    The network uses tanh hidden layers, a categorical head for discrete or
    branched actions, and an independent Gaussian head for continuous actions.
    Its PPO update computes the clipped surrogate, value, and entropy gradients
    and applies Adam updates to the actual parameters.
    """

    def __init__(
        self,
        obs_shape: tuple[int, ...],
        action_spec: Any,
        continuous: bool | None = None,
        hidden_units: int = 16,
        num_layers: int = 1,
        learning_rate: float = 0.01,
        seed: int | None = None,
    ) -> None:
        self.obs_shape = tuple(obs_shape)
        self.obs_dim = int(np.prod(self.obs_shape))
        if self.obs_dim < 1:
            raise ValueError("observation shape must contain at least one value")
        self.action_spec = action_spec
        if continuous is None:
            continuous = bool(action_spec.continuous_size > 0)
        self.continuous = bool(continuous)
        if self.continuous:
            self.action_dim = int(action_spec.continuous_size)
            self.branch_sizes: tuple[int, ...] | None = None
        else:
            branches = tuple(int(x) for x in getattr(action_spec, "discrete_branches", []))
            if branches:
                self.branch_sizes = branches
                self.action_dim = sum(branches)
            else:
                self.branch_sizes = None
                self.action_dim = int(action_spec.discrete_size)
        if self.action_dim < 1:
            raise ValueError("policy requires a positive action dimension")
        self.hidden_units = max(1, int(hidden_units))
        self.num_layers = max(1, int(num_layers))
        self.learning_rate = float(learning_rate)
        self._rng = np.random.default_rng(seed)
        self._adam_t = 0
        self._parameters: dict[str, np.ndarray] = {}
        self._adam_m: dict[str, np.ndarray] = {}
        self._adam_v: dict[str, np.ndarray] = {}
        self._build_parameters()
        self.log_std = np.full(self.action_dim, -0.5, dtype=np.float64)

    def _build_parameters(self) -> None:
        for prefix in ("actor", "critic"):
            width = self.obs_dim
            for layer in range(self.num_layers):
                key_w = f"{prefix}_layer_{layer}_w"
                key_b = f"{prefix}_layer_{layer}_b"
                self._parameters[key_w] = self._rng.normal(0.0, 0.08, (width, self.hidden_units))
                self._parameters[key_b] = np.zeros(self.hidden_units, dtype=np.float64)
                width = self.hidden_units
            self._parameters[f"{prefix}_out_w"] = self._rng.normal(0.0, 0.08, (width, 1 if prefix == "critic" else self.action_dim))
            self._parameters[f"{prefix}_out_b"] = np.zeros(1 if prefix == "critic" else self.action_dim, dtype=np.float64)
        self._adam_m = {key: np.zeros_like(value) for key, value in self._parameters.items()}
        self._adam_v = {key: np.zeros_like(value) for key, value in self._parameters.items()}

    @property
    def parameters(self) -> dict[str, np.ndarray]:
        return {key: value.copy() for key, value in self._parameters.items()}

    def parameter_norm(self) -> float:
        return float(math.sqrt(sum(float(np.sum(value * value)) for value in self._parameters.values())))

    def state_dict(self) -> dict[str, np.ndarray]:
        state = {key: value.copy() for key, value in self._parameters.items()}
        state["log_std"] = self.log_std.copy()
        return state

    def load_state_dict(self, state: dict[str, np.ndarray]) -> None:
        for key, value in state.items():
            if key == "log_std":
                if self.continuous:
                    self.log_std = np.asarray(value, dtype=np.float64).copy()
                continue
            if key not in self._parameters:
                raise ValueError(f"unknown policy parameter {key}")
            if self._parameters[key].shape != np.asarray(value).shape:
                raise ValueError(f"parameter shape mismatch for {key}")
            self._parameters[key] = np.asarray(value, dtype=np.float64).copy()
        self._adam_m = {key: np.zeros_like(value) for key, value in self._parameters.items()}
        self._adam_v = {key: np.zeros_like(value) for key, value in self._parameters.items()}
        self._adam_t = 0

    def _forward_layers(
        self, obs: np.ndarray, prefix: str
    ) -> tuple[np.ndarray, list[np.ndarray]]:
        values = [obs]
        current = obs
        for layer in range(self.num_layers):
            w = self._parameters[f"{prefix}_layer_{layer}_w"]
            b = self._parameters[f"{prefix}_layer_{layer}_b"]
            current = np.tanh(current @ w + b)
            values.append(current)
        output = current @ self._parameters[f"{prefix}_out_w"] + self._parameters[f"{prefix}_out_b"]
        return output, values

    def _forward(self, obs: np.ndarray) -> tuple[np.ndarray, np.ndarray, list[np.ndarray], list[np.ndarray]]:
        x = _batch(obs, self.obs_dim)
        actor_output, actor_values = self._forward_layers(x, "actor")
        critic_output, critic_values = self._forward_layers(x, "critic")
        return actor_output, critic_output[:, 0], actor_values, critic_values

    def _canonical_actions(self, actions: np.ndarray, count: int) -> np.ndarray:
        value = np.asarray(actions)
        if self.continuous:
            value = value.reshape(count, self.action_dim)
            return value.astype(np.float64, copy=False)
        if self.branch_sizes is not None:
            value = value.reshape(count, len(self.branch_sizes))
            if np.any(value < 0) or np.any(value >= np.asarray(self.branch_sizes)[None, :]):
                raise ValueError("action is outside its discrete branch")
            return value.astype(np.int64, copy=False)
        value = value.reshape(count)
        if np.any(value < 0) or np.any(value >= self.action_dim):
            raise ValueError(f"discrete action is outside [0, {self.action_dim})")
        return value.astype(np.int64, copy=False)

    def _distribution_values(
        self, actor_output: np.ndarray, actions: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        count = actor_output.shape[0]
        if self.continuous:
            std = np.exp(np.clip(self.log_std, -8.0, 2.0))[None, :]
            delta = actions - actor_output
            log_prob = -0.5 * (delta / std) ** 2
            log_prob -= np.log(std) + 0.5 * math.log(2.0 * math.pi)
            entropy = np.log(std) + 0.5 + 0.5 * math.log(2.0 * math.pi)
            return log_prob.sum(axis=1), entropy.sum(axis=1)
        if self.branch_sizes is not None:
            log_prob = np.zeros(count, dtype=np.float64)
            entropy = np.zeros(count, dtype=np.float64)
            offset = 0
            for branch, size in enumerate(self.branch_sizes):
                logits = actor_output[:, offset : offset + size]
                probabilities = _softmax(logits)
                choices = actions[:, branch].astype(np.int64)
                log_prob += np.log(probabilities[np.arange(count), choices] + 1e-12)
                entropy += -(probabilities * np.log(probabilities + 1e-12)).sum(axis=1)
                offset += size
            return log_prob, entropy
        probabilities = _softmax(actor_output)
        choices = actions.astype(np.int64)
        log_prob = np.log(probabilities[np.arange(count), choices] + 1e-12)
        entropy = -(probabilities * np.log(probabilities + 1e-12)).sum(axis=1)
        return log_prob, entropy

    def _sample_actions(self, actor_output: np.ndarray) -> np.ndarray:
        count = actor_output.shape[0]
        if self.continuous:
            std = np.exp(np.clip(self.log_std, -8.0, 2.0))[None, :]
            return actor_output + std * self._rng.normal(size=(count, self.action_dim))
        if self.branch_sizes is not None:
            result = np.zeros((count, len(self.branch_sizes)), dtype=np.int64)
            offset = 0
            for branch, size in enumerate(self.branch_sizes):
                probabilities = _softmax(actor_output[:, offset : offset + size])
                cumulative = np.cumsum(probabilities, axis=1)
                draws = self._rng.random(count)
                result[:, branch] = np.argmax(draws[:, None] <= cumulative, axis=1)
                offset += size
            return result
        probabilities = _softmax(actor_output)
        cumulative = np.cumsum(probabilities, axis=1)
        draws = self._rng.random(count)
        return np.argmax(draws[:, None] <= cumulative, axis=1).astype(np.int64)

    def _deterministic_actions(self, actor_output: np.ndarray) -> np.ndarray:
        if self.continuous:
            return actor_output
        if self.branch_sizes is not None:
            result = np.zeros((actor_output.shape[0], len(self.branch_sizes)), dtype=np.int64)
            offset = 0
            for branch, size in enumerate(self.branch_sizes):
                result[:, branch] = np.argmax(actor_output[:, offset : offset + size], axis=1)
                offset += size
            return result
        return np.argmax(actor_output, axis=1).astype(np.int64)

    def act(self, obs: np.ndarray, deterministic: bool = False) -> PolicyOutput:
        actor_output, value, _, _ = self._forward(obs)
        actions = self._deterministic_actions(actor_output) if deterministic else self._sample_actions(actor_output)
        log_prob, entropy = self._distribution_values(actor_output, actions)
        if self.continuous:
            action: Any = actions[0].astype(np.float32)
        elif self.branch_sizes is not None:
            action = actions[0].astype(np.int64)
        else:
            action = int(actions[0])
        return PolicyOutput(action=action, log_prob=float(log_prob[0]), value=float(value[0]), entropy=float(entropy[0]))

    def evaluate_batch(
        self, observations: np.ndarray, actions: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        actor_output, value, _, _ = self._forward(observations)
        canonical = self._canonical_actions(actions, actor_output.shape[0])
        log_prob, entropy = self._distribution_values(actor_output, canonical)
        return log_prob, entropy, value

    def evaluate_actions(
        self, observations: np.ndarray, actions: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return self.evaluate_batch(observations, actions)

    def evaluate(self, obs: np.ndarray, action: np.ndarray) -> tuple[float, float, float]:
        log_prob, entropy, value = self.evaluate_batch(np.asarray(obs), np.asarray(action))
        return float(log_prob[0]), float(entropy[0]), float(value[0])

    def value(self, obs: np.ndarray) -> float:
        _, value, _, _ = self._forward(obs)
        return float(value[0])

    def _backward(
        self,
        prefix: str,
        output_gradient: np.ndarray,
        activations: list[np.ndarray],
    ) -> dict[str, np.ndarray]:
        gradients = {
            f"{prefix}_out_w": activations[-1].T @ output_gradient,
            f"{prefix}_out_b": output_gradient.sum(axis=0),
        }
        current = output_gradient @ self._parameters[f"{prefix}_out_w"].T
        for layer in range(self.num_layers - 1, -1, -1):
            hidden = activations[layer + 1]
            gradients[f"{prefix}_layer_{layer}_w"] = activations[layer].T @ current
            gradients[f"{prefix}_layer_{layer}_b"] = current.sum(axis=0)
            if layer > 0:
                current = current @ self._parameters[f"{prefix}_layer_{layer}_w"].T
                current *= _tanh_backward(hidden)
        return gradients

    def _actor_output_gradient(
        self,
        actor_output: np.ndarray,
        actions: np.ndarray,
        log_prob_coefficient: np.ndarray,
        entropy_coefficient: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        count = actor_output.shape[0]
        if self.continuous:
            std = np.exp(np.clip(self.log_std, -8.0, 2.0))[None, :]
            delta = (actions - actor_output) / std
            output_gradient = log_prob_coefficient[:, None] * delta / std
            log_std_gradient = log_prob_coefficient * (delta * delta - 1.0)
            log_std_gradient -= entropy_coefficient
            return output_gradient, log_std_gradient / count
        output_gradient = np.zeros_like(actor_output)
        if self.branch_sizes is not None:
            offset = 0
            for branch, size in enumerate(self.branch_sizes):
                probabilities = _softmax(actor_output[:, offset : offset + size])
                one_hot = np.zeros_like(probabilities)
                one_hot[np.arange(count), actions[:, branch]] = 1.0
                output_gradient[:, offset : offset + size] = log_prob_coefficient[:, None] * (
                    one_hot - probabilities
                )
                output_gradient[:, offset : offset + size] += entropy_coefficient * probabilities * (
                    one_hot - probabilities
                )
                offset += size
            return output_gradient, np.zeros(self.action_dim, dtype=np.float64)
        probabilities = _softmax(actor_output)
        one_hot = np.zeros_like(probabilities)
        one_hot[np.arange(count), actions] = 1.0
        output_gradient[:] = log_prob_coefficient[:, None] * (one_hot - probabilities)
        output_gradient += entropy_coefficient * probabilities * (one_hot - probabilities)
        return output_gradient, np.zeros(self.action_dim, dtype=np.float64)

    def _apply_gradients(self, gradients: dict[str, np.ndarray], learning_rate: float) -> None:
        if not gradients:
            return
        norm = math.sqrt(sum(float(np.sum(value * value)) for value in gradients.values()))
        if norm > 5.0:
            scale = 5.0 / (norm + 1e-12)
            gradients = {key: value * scale for key, value in gradients.items()}
        self._adam_t += 1
        beta1 = 0.9
        beta2 = 0.999
        correction1 = 1.0 - beta1**self._adam_t
        correction2 = 1.0 - beta2**self._adam_t
        for key, gradient in gradients.items():
            if key == "log_std":
                self._adam_m[key] = beta1 * self._adam_m.get(key, np.zeros_like(gradient)) + (1.0 - beta1) * gradient
                self._adam_v[key] = beta2 * self._adam_v.get(key, np.zeros_like(gradient)) + (1.0 - beta2) * gradient * gradient
                m_hat = self._adam_m[key] / correction1
                v_hat = self._adam_v[key] / correction2
                self.log_std -= learning_rate * m_hat / (np.sqrt(v_hat) + 1e-8)
                self.log_std = np.clip(self.log_std, -8.0, 2.0)
                continue
            if key not in self._parameters:
                continue
            self._adam_m[key] = beta1 * self._adam_m[key] + (1.0 - beta1) * gradient
            self._adam_v[key] = beta2 * self._adam_v[key] + (1.0 - beta2) * gradient * gradient
            m_hat = self._adam_m[key] / correction1
            v_hat = self._adam_v[key] / correction2
            self._parameters[key] -= learning_rate * m_hat / (np.sqrt(v_hat) + 1e-8)

    def ppo_update(
        self,
        observations: np.ndarray,
        actions: np.ndarray,
        old_log_probs: np.ndarray,
        advantages: np.ndarray,
        returns: np.ndarray,
        clip_epsilon: float = 0.2,
        epochs: int = 2,
        batch_size: int = 64,
        learning_rate: float | None = None,
        value_coefficient: float = 0.5,
        entropy_coefficient: float = 0.01,
    ) -> dict[str, float]:
        x = _batch(observations, self.obs_dim)
        canonical_actions = self._canonical_actions(actions, x.shape[0])
        old_log_probs = np.asarray(old_log_probs, dtype=np.float64).reshape(-1)
        advantages = np.asarray(advantages, dtype=np.float64).reshape(-1)
        returns = np.asarray(returns, dtype=np.float64).reshape(-1)
        if not (len(old_log_probs) == len(advantages) == len(returns) == x.shape[0]):
            raise ValueError("policy update arrays must have the same length")
        if x.shape[0] == 0:
            raise ValueError("cannot update a policy with an empty batch")
        if np.std(advantages) > 1e-8:
            advantages = (advantages - np.mean(advantages)) / (np.std(advantages) + 1e-8)
        rate = self.learning_rate if learning_rate is None else float(learning_rate)
        totals = {"policy_loss": 0.0, "value_loss": 0.0, "entropy": 0.0, "total_loss": 0.0}
        batches = 0
        for _ in range(max(1, int(epochs))):
            order = self._rng.permutation(x.shape[0])
            for start in range(0, x.shape[0], max(1, int(batch_size))):
                indices = order[start : start + max(1, int(batch_size))]
                batch_x = x[indices]
                batch_actions = canonical_actions[indices]
                batch_old = old_log_probs[indices]
                batch_adv = advantages[indices]
                batch_returns = returns[indices]
                actor_output, value, actor_activations, critic_activations = self._forward(batch_x)
                log_prob, entropy = self._distribution_values(actor_output, batch_actions)
                ratio = np.exp(np.clip(log_prob - batch_old, -20.0, 20.0))
                unclipped = ratio * batch_adv
                clipped = np.clip(ratio, 1.0 - clip_epsilon, 1.0 + clip_epsilon) * batch_adv
                policy_loss = -np.minimum(unclipped, clipped).mean()
                value_loss = np.mean((value - batch_returns) ** 2)
                entropy_value = entropy.mean()
                total_loss = policy_loss + value_coefficient * value_loss - entropy_coefficient * entropy_value
                use_unclipped = unclipped <= clipped
                log_prob_coefficient = -batch_adv * ratio * use_unclipped / x.shape[0]
                output_gradient, log_std_gradient = self._actor_output_gradient(
                    actor_output,
                    batch_actions,
                    log_prob_coefficient,
                    entropy_coefficient,
                )
                gradients = self._backward("actor", output_gradient, actor_activations)
                value_gradient = (2.0 * (value - batch_returns) * value_coefficient / x.shape[0])[:, None]
                gradients.update(self._backward("critic", value_gradient, critic_activations))
                if self.continuous:
                    gradients["log_std"] = log_std_gradient
                self._apply_gradients(gradients, rate)
                totals["policy_loss"] += float(policy_loss)
                totals["value_loss"] += float(value_loss)
                totals["entropy"] += float(entropy_value)
                totals["total_loss"] += float(total_loss)
                batches += 1
        return {key: value / max(1, batches) for key, value in totals.items()}

    def update(
        self,
        observations: np.ndarray,
        actions: np.ndarray,
        advantages: np.ndarray,
        returns: np.ndarray | None = None,
        old_log_probs: np.ndarray | None = None,
        **kwargs: Any,
    ) -> dict[str, float]:
        current_log_prob, _, _ = self.evaluate_batch(observations, actions)
        if returns is None:
            returns = np.asarray(advantages, dtype=np.float64).reshape(-1)
        if old_log_probs is None:
            old_log_probs = current_log_prob
        return self.ppo_update(observations, actions, old_log_probs, advantages, returns, **kwargs)


class QNetwork:
    """A real NumPy action-value network with a differentiable TD update."""

    def __init__(
        self,
        obs_shape: tuple[int, ...],
        action_size: int,
        hidden_units: int = 16,
        num_layers: int = 1,
        learning_rate: float = 0.01,
        seed: int | None = None,
    ) -> None:
        self.obs_shape = tuple(obs_shape)
        self.obs_dim = int(np.prod(self.obs_shape))
        self.action_size = int(action_size)
        self.hidden_units = max(1, int(hidden_units))
        self.num_layers = max(1, int(num_layers))
        self.learning_rate = float(learning_rate)
        self._rng = np.random.default_rng(seed)
        self._parameters: dict[str, np.ndarray] = {}
        self._adam_m: dict[str, np.ndarray] = {}
        self._adam_v: dict[str, np.ndarray] = {}
        self._adam_t = 0
        self._build()

    def _build(self) -> None:
        width = self.obs_dim
        for layer in range(self.num_layers):
            key_w = f"layer_{layer}_w"
            key_b = f"layer_{layer}_b"
            self._parameters[key_w] = self._rng.normal(0.0, 0.08, (width, self.hidden_units))
            self._parameters[key_b] = np.zeros(self.hidden_units, dtype=np.float64)
            width = self.hidden_units
        self._parameters["out_w"] = self._rng.normal(0.0, 0.08, (width, self.action_size))
        self._parameters["out_b"] = np.zeros(self.action_size, dtype=np.float64)
        self._adam_m = {key: np.zeros_like(value) for key, value in self._parameters.items()}
        self._adam_v = {key: np.zeros_like(value) for key, value in self._parameters.items()}

    def state_dict(self) -> dict[str, np.ndarray]:
        return {key: value.copy() for key, value in self._parameters.items()}

    def load_state_dict(self, state: dict[str, np.ndarray]) -> None:
        for key, value in state.items():
            if key not in self._parameters:
                raise ValueError(f"unknown Q-network parameter {key}")
            if self._parameters[key].shape != np.asarray(value).shape:
                raise ValueError(f"parameter shape mismatch for {key}")
            self._parameters[key] = np.asarray(value, dtype=np.float64).copy()
        self._adam_m = {key: np.zeros_like(value) for key, value in self._parameters.items()}
        self._adam_v = {key: np.zeros_like(value) for key, value in self._parameters.items()}
        self._adam_t = 0

    def _forward(self, obs: np.ndarray) -> tuple[np.ndarray, list[np.ndarray]]:
        x = _batch(obs, self.obs_dim)
        activations = [x]
        current = x
        for layer in range(self.num_layers):
            current = np.tanh(current @ self._parameters[f"layer_{layer}_w"] + self._parameters[f"layer_{layer}_b"])
            activations.append(current)
        output = current @ self._parameters["out_w"] + self._parameters["out_b"]
        return output, activations

    def q_values(self, obs: np.ndarray) -> np.ndarray:
        output, _ = self._forward(obs)
        if np.asarray(obs).ndim == 1:
            return output[0]
        return output

    def _backward(self, output_gradient: np.ndarray, activations: list[np.ndarray]) -> dict[str, np.ndarray]:
        gradients = {"out_w": activations[-1].T @ output_gradient, "out_b": output_gradient.sum(axis=0)}
        current = output_gradient @ self._parameters["out_w"].T
        for layer in range(self.num_layers - 1, -1, -1):
            hidden = activations[layer + 1]
            gradients[f"layer_{layer}_w"] = activations[layer].T @ current
            gradients[f"layer_{layer}_b"] = current.sum(axis=0)
            if layer > 0:
                current = current @ self._parameters[f"layer_{layer}_w"].T
                current *= _tanh_backward(hidden)
        return gradients

    def loss_and_grad(
        self,
        obs: np.ndarray,
        actions: np.ndarray,
        targets: np.ndarray,
        weights: np.ndarray | None = None,
    ) -> tuple[float, dict[str, np.ndarray]]:
        output, activations = self._forward(obs)
        action_values = np.asarray(actions, dtype=np.int64).reshape(-1)
        if np.any(action_values < 0) or np.any(action_values >= self.action_size):
            raise ValueError("action is outside the Q-network action range")
        selected = output[np.arange(output.shape[0]), action_values]
        target_values = np.asarray(targets, dtype=np.float64).reshape(-1)
        if len(selected) != len(target_values):
            raise ValueError("Q-network targets must match observations")
        if weights is None:
            weights = np.ones_like(selected, dtype=np.float64)
        else:
            weights = np.asarray(weights, dtype=np.float64).reshape(-1)
            if len(weights) != len(selected):
                raise ValueError("Q-network weights must match observations")
        denominator = max(float(np.sum(weights)), 1e-12)
        errors = selected - target_values
        loss = float(np.sum(weights * errors * errors) / denominator)
        output_gradient = np.zeros_like(output)
        output_gradient[np.arange(output.shape[0]), action_values] = 2.0 * weights * errors / denominator
        return loss, self._backward(output_gradient, activations)

    def action_gradient(self, obs: np.ndarray, actions: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        output, activations = self._forward(obs)
        action_values = np.asarray(actions, dtype=np.int64).reshape(-1)
        output_gradient = np.zeros_like(output)
        output_gradient[np.arange(output.shape[0]), action_values] = 1.0
        return output[np.arange(output.shape[0]), action_values], self._backward(output_gradient, activations)

    def _apply(self, gradients: dict[str, np.ndarray], learning_rate: float) -> None:
        norm = math.sqrt(sum(float(np.sum(value * value)) for value in gradients.values()))
        if norm > 5.0:
            scale = 5.0 / (norm + 1e-12)
            gradients = {key: value * scale for key, value in gradients.items()}
        self._adam_t += 1
        beta1, beta2 = 0.9, 0.999
        correction1 = 1.0 - beta1**self._adam_t
        correction2 = 1.0 - beta2**self._adam_t
        for key, gradient in gradients.items():
            self._adam_m[key] = beta1 * self._adam_m[key] + (1.0 - beta1) * gradient
            self._adam_v[key] = beta2 * self._adam_v[key] + (1.0 - beta2) * gradient * gradient
            m_hat = self._adam_m[key] / correction1
            v_hat = self._adam_v[key] / correction2
            self._parameters[key] -= learning_rate * m_hat / (np.sqrt(v_hat) + 1e-8)

    def update(
        self,
        obs: np.ndarray,
        actions: np.ndarray,
        targets: np.ndarray,
        weights: np.ndarray | None = None,
        learning_rate: float | None = None,
    ) -> float:
        loss, gradients = self.loss_and_grad(obs, actions, targets, weights)
        self._apply(gradients, self.learning_rate if learning_rate is None else float(learning_rate))
        return loss


class SACPolicy:
    """A real NumPy soft actor-critic policy with twin linear Q critics."""

    def __init__(
        self,
        obs_shape: tuple[int, ...],
        action_size: int,
        hidden_units: int = 16,
        learning_rate: float = 0.01,
        target_entropy: float | None = None,
        seed: int | None = None,
    ) -> None:
        self.obs_shape = tuple(obs_shape)
        self.obs_dim = int(np.prod(self.obs_shape))
        self.action_size = int(action_size)
        self.hidden_units = max(1, int(hidden_units))
        self.target_entropy = float(-self.action_size if target_entropy is None else target_entropy)
        self.learning_rate = float(learning_rate)
        self._rng = np.random.default_rng(seed)
        self.actor_w = self._rng.normal(0.0, 0.08, (self.obs_dim, self.action_size))
        self.actor_b = np.zeros(self.action_size, dtype=np.float64)
        self.log_std = np.full(self.action_size, -0.4, dtype=np.float64)
        critic_size = self.obs_dim + self.action_size
        self.q1_w = self._rng.normal(0.0, 0.08, critic_size)
        self.q1_b = np.asarray(0.0, dtype=np.float64)
        self.q2_w = self._rng.normal(0.0, 0.08, critic_size)
        self.q2_b = np.asarray(0.0, dtype=np.float64)
        self.q1_target_w = self.q1_w.copy()
        self.q1_target_b = self.q1_b.copy()
        self.q2_target_w = self.q2_w.copy()
        self.q2_target_b = self.q2_b.copy()
        self.log_alpha = np.zeros(1, dtype=np.float64)
        self._critic_m = {key: np.zeros_like(value) for key, value in self._critic_state().items()}
        self._critic_v = {key: np.zeros_like(value) for key, value in self._critic_state().items()}
        self._actor_m = {key: np.zeros_like(value) for key, value in self._actor_state().items()}
        self._actor_v = {key: np.zeros_like(value) for key, value in self._actor_state().items()}
        self._critic_t = 0
        self._actor_t = 0

    def _actor_state(self) -> dict[str, np.ndarray]:
        return {"actor_w": self.actor_w, "actor_b": self.actor_b, "log_std": self.log_std}

    def _critic_state(self) -> dict[str, np.ndarray]:
        return {
            "q1_w": self.q1_w,
            "q1_b": np.asarray(self.q1_b, dtype=np.float64),
            "q2_w": self.q2_w,
            "q2_b": np.asarray(self.q2_b, dtype=np.float64),
        }

    def state_dict(self) -> dict[str, np.ndarray]:
        state = {
            "actor_w": self.actor_w.copy(),
            "actor_b": self.actor_b.copy(),
            "log_std": self.log_std.copy(),
            "q1_w": self.q1_w.copy(),
            "q1_b": np.asarray(self.q1_b, dtype=np.float64).copy(),
            "q2_w": self.q2_w.copy(),
            "q2_b": np.asarray(self.q2_b, dtype=np.float64).copy(),
            "q1_target_w": self.q1_target_w.copy(),
            "q1_target_b": np.asarray(self.q1_target_b, dtype=np.float64).copy(),
            "q2_target_w": self.q2_target_w.copy(),
            "q2_target_b": np.asarray(self.q2_target_b, dtype=np.float64).copy(),
            "log_alpha": self.log_alpha.copy(),
        }
        return state

    def load_state_dict(self, state: dict[str, np.ndarray]) -> None:
        required = (
            "actor_w", "actor_b", "log_std", "q1_w", "q1_b", "q2_w", "q2_b",
            "q1_target_w", "q1_target_b", "q2_target_w", "q2_target_b", "log_alpha",
        )
        missing = [key for key in required if key not in state]
        if missing:
            raise ValueError(f"missing SAC parameters: {missing}")
        for key in required:
            value = np.asarray(state[key], dtype=np.float64).copy()
            if key in self._actor_state() or key in self._critic_state():
                expected = self._actor_state().get(key) if key in self._actor_state() else self._critic_state()[key]
                if np.shape(value) != np.shape(expected):
                    raise ValueError(f"SAC parameter shape mismatch for {key}")
            setattr(self, key, value)
        self._critic_m = {key: np.zeros_like(value) for key, value in self._critic_state().items()}
        self._critic_v = {key: np.zeros_like(value) for key, value in self._critic_state().items()}
        self._actor_m = {key: np.zeros_like(value) for key, value in self._actor_state().items()}
        self._actor_v = {key: np.zeros_like(value) for key, value in self._actor_state().items()}
        self._critic_t = 0
        self._actor_t = 0

    def _mean(self, obs: np.ndarray) -> np.ndarray:
        return _batch(obs, self.obs_dim) @ self.actor_w + self.actor_b

    def _actor_values(self, obs: np.ndarray, deterministic: bool = False) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        mean = self._mean(obs)
        std = np.exp(np.clip(self.log_std, -8.0, 2.0))[None, :]
        raw = mean if deterministic else mean + std * self._rng.normal(size=mean.shape)
        action = np.tanh(raw)
        normal_lp = (-0.5 * ((raw - mean) / std) ** 2 - np.log(std) - 0.5 * math.log(2.0 * math.pi)).sum(axis=1)
        correction = (2.0 * (math.log(2.0) - raw - np.logaddexp(0.0, -2.0 * raw))).sum(axis=1)
        return action, normal_lp - correction, mean, std

    def sample(self, obs: np.ndarray, deterministic: bool = False) -> tuple[np.ndarray, np.ndarray]:
        action, log_prob, _, _ = self._actor_values(obs, deterministic)
        return action, log_prob

    def set_log_alpha(self, value: float) -> None:
        self.log_alpha[:] = float(value)

    def alpha(self) -> float:
        return float(np.exp(self.log_alpha[0]))

    def entropy(self) -> float:
        return float(np.sum(self.log_std + 0.5 * math.log(2.0 * math.pi * math.e)))

    def log_prob(self, obs: np.ndarray, actions: np.ndarray) -> np.ndarray:
        mean = self._mean(obs)
        bounded = np.clip(np.asarray(actions, dtype=np.float64), -0.999999, 0.999999)
        raw = 0.5 * np.log((1.0 + bounded) / (1.0 - bounded))
        std = np.exp(np.clip(self.log_std, -8.0, 2.0))[None, :]
        normal_lp = (-0.5 * ((raw - mean) / std) ** 2 - np.log(std) - 0.5 * math.log(2.0 * math.pi)).sum(axis=1)
        correction = (2.0 * (math.log(2.0) - raw - np.logaddexp(0.0, -2.0 * raw))).sum(axis=1)
        return normal_lp - correction

    def _q(self, obs: np.ndarray, actions: np.ndarray, weights: np.ndarray, bias: float, target: bool = False) -> np.ndarray:
        x = _batch(obs, self.obs_dim)
        a = np.asarray(actions, dtype=np.float64).reshape(x.shape[0], self.action_size)
        if target:
            if weights is self.q1_target_w:
                return (x @ weights[: self.obs_dim] + a @ weights[self.obs_dim :] + bias).reshape(-1)
            return (x @ weights[: self.obs_dim] + a @ weights[self.obs_dim :] + bias).reshape(-1)
        return (x @ weights[: self.obs_dim] + a @ weights[self.obs_dim :] + bias).reshape(-1)

    def act(self, obs: np.ndarray, deterministic: bool = False) -> PolicyOutput:
        action, log_prob = self.sample(obs, deterministic)
        value = np.minimum(self._q(obs, action, self.q1_w, self.q1_b), self._q(obs, action, self.q2_w, self.q2_b))
        return PolicyOutput(action[0].astype(np.float32), float(log_prob[0]), float(value[0]), self.entropy())

    def evaluate(self, obs: np.ndarray, action: np.ndarray) -> tuple[float, float, float]:
        actions = np.asarray(action, dtype=np.float64).reshape(1, -1)
        log_prob = self.log_prob(obs, actions)[0]
        value = min(
            float(self._q(obs, actions, self.q1_w, self.q1_b)[0]),
            float(self._q(obs, actions, self.q2_w, self.q2_b)[0]),
        )
        return float(log_prob), self.entropy(), value

    def critic_values(self, obs: np.ndarray, actions: np.ndarray, target: bool = False) -> tuple[np.ndarray, np.ndarray]:
        q1_w = self.q1_target_w if target else self.q1_w
        q2_w = self.q2_target_w if target else self.q2_w
        q1_b = self.q1_target_b if target else self.q1_b
        q2_b = self.q2_target_b if target else self.q2_b
        return self._q(obs, actions, q1_w, q1_b), self._q(obs, actions, q2_w, q2_b)

    def _apply_adam(
        self,
        parameters: dict[str, np.ndarray],
        gradients: dict[str, np.ndarray],
        moments_m: dict[str, np.ndarray],
        moments_v: dict[str, np.ndarray],
        step: int,
        learning_rate: float,
    ) -> int:
        norm = math.sqrt(sum(float(np.sum(value * value)) for value in gradients.values()))
        if norm > 5.0:
            scale = 5.0 / (norm + 1e-12)
            gradients = {key: value * scale for key, value in gradients.items()}
        step += 1
        correction1 = 1.0 - 0.9**step
        correction2 = 1.0 - 0.999**step
        for key, gradient in gradients.items():
            moments_m[key] = 0.9 * moments_m[key] + 0.1 * gradient
            moments_v[key] = 0.999 * moments_v[key] + 0.001 * gradient * gradient
            m_hat = moments_m[key] / correction1
            v_hat = moments_v[key] / correction2
            parameters[key] -= learning_rate * m_hat / (np.sqrt(v_hat) + 1e-8)
        return step

    def update_critics(self, obs: np.ndarray, actions: np.ndarray, targets: np.ndarray) -> tuple[float, float]:
        x = _batch(obs, self.obs_dim)
        a = np.asarray(actions, dtype=np.float64).reshape(x.shape[0], self.action_size)
        target = np.asarray(targets, dtype=np.float64).reshape(-1)
        if len(target) != x.shape[0]:
            raise ValueError("SAC critic targets must match observations")
        features = np.concatenate([x, a], axis=1)
        losses: list[float] = []
        gradients: dict[str, np.ndarray] = {}
        for prefix, weights, bias in (("q1", self.q1_w, self.q1_b), ("q2", self.q2_w, self.q2_b)):
            values = features @ weights + bias
            errors = values - target
            losses.append(float(np.mean(errors * errors)))
            scale = (2.0 * errors / x.shape[0])[:, None]
            gradients[f"{prefix}_w"] = features.T @ scale[:, 0]
            gradients[f"{prefix}_b"] = np.asarray(scale.mean(), dtype=np.float64)
        self._critic_t = self._apply_adam(
            self._critic_state(), gradients, self._critic_m, self._critic_v,
            self._critic_t, self.learning_rate,
        )
        return losses[0], losses[1]

    def update_actor(self, obs: np.ndarray, alpha: float) -> float:
        x = _batch(obs, self.obs_dim)
        action, log_prob, mean, std = self._actor_values(x)
        q1 = self._q(x, action, self.q1_w, self.q1_b)
        q2 = self._q(x, action, self.q2_w, self.q2_b)
        loss = float(np.mean(alpha * log_prob - np.minimum(q1, q2)))
        dq_da = (self.q1_w[self.obs_dim :] + self.q2_w[self.obs_dim :]) / 2.0
        raw = np.arctanh(np.clip(action, -0.999999, 0.999999))
        squash = 1.0 - action * action
        d_loss_draw = alpha * (-(raw - mean) / (std * std) + 2.0 * squash) - dq_da[None, :] * squash
        d_loss_dmean = d_loss_draw
        d_loss_dlogstd = alpha * ((raw - mean) ** 2 / (std * std) - 1.0)
        gradients = {
            "actor_w": x.T @ d_loss_dmean / x.shape[0],
            "actor_b": d_loss_dmean.mean(axis=0),
            "log_std": d_loss_dlogstd.mean(axis=0),
        }
        self._actor_t = self._apply_adam(
            self._actor_state(), gradients, self._actor_m, self._actor_v,
            self._actor_t, self.learning_rate,
        )
        return loss

    def update_alpha(self, log_prob: np.ndarray) -> float:
        values = np.asarray(log_prob, dtype=np.float64).reshape(-1) + self.target_entropy
        loss = float(-np.mean(self.log_alpha * values))
        self.log_alpha += self.learning_rate * values.mean()
        self.log_alpha = np.clip(self.log_alpha, -8.0, 2.0)
        return loss

    def soft_update(self, tau: float) -> None:
        self.q1_target_w = tau * self.q1_w + (1.0 - tau) * self.q1_target_w
        self.q1_target_b = tau * self.q1_b + (1.0 - tau) * self.q1_target_b
        self.q2_target_w = tau * self.q2_w + (1.0 - tau) * self.q2_target_w
        self.q2_target_b = tau * self.q2_b + (1.0 - tau) * self.q2_target_b


def create_policy(
    obs_shape: tuple[int, ...],
    action_spec: Any,
    network_settings: Any = None,
    continuous: bool | None = None,
    seed: int | None = None,
) -> Policy:
    """Create the real Torch policy when available, otherwise NumPy."""
    settings = network_settings or {}
    if not isinstance(settings, dict):
        settings = {}
    policy_type = TorchPolicy if TORCH_AVAILABLE else NumPyPolicy
    return policy_type(
        obs_shape=obs_shape,
        action_spec=action_spec,
        continuous=continuous,
        hidden_units=int(settings.get("hidden_units", 16)),
        num_layers=int(settings.get("num_layers", 1)),
        learning_rate=float(settings.get("learning_rate", 0.01)),
        seed=seed,
    )
