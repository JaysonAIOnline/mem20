"""PyTorch backends for DQN and SAC.

These implement the same public contract as the NumPy `QNetwork` and
`SACPolicy`, so the trainers accept either without knowing which is in use.
The NumPy implementations remain the fallback when torch is absent, which is
what makes the suite runnable on a torch-less interpreter.

Torch is used for what it is actually good at here: autograd, so the TD and
soft-policy updates are differentiated by the framework rather than by
hand-written backward passes. The observable contract is unchanged: NumPy in,
NumPy out, so no caller has to know which backend is active.
"""

from __future__ import annotations

import numpy as np

from .policy import PolicyOutput

try:
    import torch
    from torch import nn
    from torch.nn import functional as F
    TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised on torch-less interpreters
    torch = None
    nn = None
    F = None
    TORCH_AVAILABLE = False

_DTYPE = torch.float32 if TORCH_AVAILABLE else None


def _to_tensor(values, dtype=None):
    return torch.as_tensor(np.asarray(values, dtype=np.float32),
                           dtype=dtype or _DTYPE)


def _seed_everything(seed: int | None) -> None:
    if TORCH_AVAILABLE and seed is not None:
        torch.manual_seed(int(seed))


if TORCH_AVAILABLE:

    class _QNet(nn.Module):
        def __init__(self, obs_dim: int, action_size: int, hidden_units: int,
                     num_layers: int) -> None:
            super().__init__()
            layers: list[nn.Module] = []
            width = obs_dim
            for _ in range(max(1, num_layers)):
                layers.append(nn.Linear(width, hidden_units))
                layers.append(nn.Tanh())
                width = hidden_units
            layers.append(nn.Linear(width, action_size))
            self.net = nn.Sequential(*layers)

        def forward(self, obs):
            return self.net(obs)

    class _Critic(nn.Module):
        def __init__(self, obs_dim: int, action_size: int, hidden_units: int) -> None:
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(obs_dim + action_size, hidden_units),
                nn.Tanh(),
                nn.Linear(hidden_units, 1),
            )

        def forward(self, obs, actions):
            return self.net(torch.cat([obs, actions], dim=-1)).squeeze(-1)

    class TorchQNetwork:
        """DQN action-value network with autograd TD updates."""

        def __init__(self, obs_shape, action_size: int, hidden_units: int = 16,
                     num_layers: int = 1, learning_rate: float = 0.01,
                     seed: int | None = None) -> None:
            self.obs_shape = tuple(obs_shape)
            self.obs_dim = int(np.prod(self.obs_shape))
            self.action_size = int(action_size)
            self.hidden_units = max(1, int(hidden_units))
            self.num_layers = max(1, int(num_layers))
            self.learning_rate = float(learning_rate)
            self._rng = np.random.default_rng(seed)
            _seed_everything(seed)
            self.net = _QNet(self.obs_dim, self.action_size,
                             self.hidden_units, self.num_layers)
            self.optimizer = torch.optim.Adam(self.net.parameters(),
                                              lr=self.learning_rate)

        # -------------------------------------------------- serialisation
        def state_dict(self) -> dict[str, np.ndarray]:
            return {key: value.detach().cpu().numpy().copy()
                    for key, value in self.net.state_dict().items()}

        def load_state_dict(self, state) -> None:
            converted = {}
            for key, value in state.items():
                tensor = torch.as_tensor(np.asarray(value, dtype=np.float32))
                target = self.net.state_dict().get(key)
                if target is not None and tuple(target.shape) != tuple(tensor.shape):
                    raise ValueError(f"parameter shape mismatch for {key}")
                converted[key] = tensor
            self.net.load_state_dict(converted)

        # ------------------------------------------------------ inference
        @torch.no_grad()
        def q_values(self, obs) -> np.ndarray:
            single = np.asarray(obs).ndim == 1
            tensor = _to_tensor(obs).reshape(1, -1) if single \
                else _to_tensor(obs).reshape(len(np.asarray(obs)), -1)
            output = self.net(tensor)
            return output.numpy()[0] if single else output.numpy()

        def loss_and_grad(self, obs, actions, targets, weights=None):
            """Return (weighted MSE, gradients keyed like state_dict)."""
            batch = _to_tensor(obs).reshape(len(np.asarray(obs)), -1)
            action_values = np.asarray(actions, dtype=np.int64).reshape(-1)
            if np.any(action_values < 0) or np.any(action_values >= self.action_size):
                raise ValueError("action is outside the Q-network action range")
            index = torch.as_tensor(action_values, dtype=torch.long)
            selected = self.net(batch).gather(1, index.unsqueeze(1)).squeeze(1)
            target_values = torch.as_tensor(
                np.asarray(targets, dtype=np.float32).reshape(-1))
            if selected.numel() != target_values.numel():
                raise ValueError("Q-network targets must match observations")
            if weights is None:
                weight_tensor = torch.ones_like(selected)
            else:
                weight_tensor = _to_tensor(weights).reshape(-1)
                if weight_tensor.numel() != selected.numel():
                    raise ValueError("Q-network weights must match observations")
            denominator = torch.clamp(weight_tensor.sum(), min=1e-12)
            errors = selected - target_values
            loss = (weight_tensor * errors * errors).sum() / denominator
            self.optimizer.zero_grad(set_to_none=True)
            loss.backward()
            grads = {name: (param.grad.detach().cpu().numpy().copy()
                            if param.grad is not None else np.zeros_like(
                                param.detach().cpu().numpy()))
                     for name, param in self.net.named_parameters()}
            return float(loss.detach()), grads

        def action_gradient(self, obs, actions):
            """Q(s, a) for the given actions, plus gradients of that sum."""
            batch = _to_tensor(obs).reshape(len(np.asarray(obs)), -1)
            action_values = np.asarray(actions, dtype=np.int64).reshape(-1)
            index = torch.as_tensor(action_values, dtype=torch.long)
            selected = self.net(batch).gather(1, index.unsqueeze(1)).squeeze(1)
            self.optimizer.zero_grad(set_to_none=True)
            selected.sum().backward()
            grads = {name: (param.grad.detach().cpu().numpy().copy()
                            if param.grad is not None else np.zeros_like(
                                param.detach().cpu().numpy()))
                     for name, param in self.net.named_parameters()}
            return selected.detach().cpu().numpy(), grads

        # ---------------------------------------------------------- update
        def update(self, obs, actions, targets, weights=None,
                   learning_rate: float | None = None) -> float:
            for group in self.optimizer.param_groups:
                group["lr"] = self.learning_rate if learning_rate is None \
                    else float(learning_rate)
            loss, _ = self.loss_and_grad(obs, actions, targets, weights)
            self.optimizer.step()
            return loss

else:  # pragma: no cover - torch absent
    TorchQNetwork = None


if TORCH_AVAILABLE:

    class TorchSACPolicy:
        """Soft actor-critic with tanh-squashed Gaussian actor and twin critics.

        Mirrors the NumPy `SACPolicy` contract exactly: the tanh change-of-variables
        log-prob correction, target critics, entropy temperature as a learned
        parameter, and soft target updates. Autograd replaces the hand-written
        backward passes; the caller still sees NumPy in and NumPy out.
        """

        LOG_STD_MIN, LOG_STD_MAX = -8.0, 2.0

        def __init__(self, obs_shape, action_size: int, hidden_units: int = 16,
                     learning_rate: float = 0.01,
                     target_entropy: float | None = None,
                     seed: int | None = None) -> None:
            self.obs_shape = tuple(obs_shape)
            self.obs_dim = int(np.prod(self.obs_shape))
            self.action_size = int(action_size)
            self.hidden_units = max(1, int(hidden_units))
            self.target_entropy = float(
                -self.action_size if target_entropy is None else target_entropy)
            self.learning_rate = float(learning_rate)
            self._rng = np.random.default_rng(seed)
            _seed_everything(seed)

            self.actor = nn.Sequential(
                nn.Linear(self.obs_dim, self.hidden_units),
                nn.Tanh(),
                nn.Linear(self.hidden_units, self.action_size),
            )
            self.log_std = nn.Parameter(torch.full((self.action_size,), -0.4))
            self.q1 = _Critic(self.obs_dim, self.action_size, self.hidden_units)
            self.q2 = _Critic(self.obs_dim, self.action_size, self.hidden_units)
            self.q1_target = _Critic(self.obs_dim, self.action_size,
                                     self.hidden_units)
            self.q2_target = _Critic(self.obs_dim, self.action_size,
                                     self.hidden_units)
            self.q1_target.load_state_dict(self.q1.state_dict())
            self.q2_target.load_state_dict(self.q2.state_dict())
            for param in list(self.q1_target.parameters()) + \
                    list(self.q2_target.parameters()):
                param.requires_grad_(False)
            self.log_alpha = torch.zeros(1)
            self.log_alpha.requires_grad_(True)

            self.actor_optimizer = torch.optim.Adam(
                list(self.actor.parameters()) + [self.log_std],
                lr=self.learning_rate)
            self.critic_optimizer = torch.optim.Adam(
                list(self.q1.parameters()) + list(self.q2.parameters()),
                lr=self.learning_rate)
            self.alpha_optimizer = torch.optim.Adam([self.log_alpha],
                                                   lr=self.learning_rate)

        # -------------------------------------------------- serialisation
        def state_dict(self) -> dict[str, np.ndarray]:
            state: dict[str, np.ndarray] = {}
            for prefix, module in (("q1", self.q1), ("q2", self.q2),
                                   ("q1_target", self.q1_target),
                                   ("q2_target", self.q2_target)):
                for key, value in module.state_dict().items():
                    state[f"{prefix}.{key}"] = value.detach().cpu().numpy().copy()
            state["log_alpha"] = self.log_alpha.detach().cpu().numpy().copy()
            return state

        def load_state_dict(self, state) -> None:
            for prefix, module in (("q1", self.q1), ("q2", self.q2),
                                   ("q1_target", self.q1_target),
                                   ("q2_target", self.q2_target)):
                subset = {key[len(prefix) + 1:]: torch.as_tensor(
                    np.asarray(value, dtype=np.float32))
                    for key, value in state.items() if key.startswith(prefix + ".")}
                if subset:
                    module.load_state_dict(subset)
            if "log_alpha" in state:
                with torch.no_grad():
                    self.log_alpha.copy_(torch.as_tensor(
                        np.asarray(state["log_alpha"], dtype=np.float32)))

        # ---------------------------------------------------------- actor
        def _batch(self, obs):
            array = np.asarray(obs)
            single = array.ndim == 1
            tensor = _to_tensor(obs)
            tensor = tensor.reshape(1, -1) if single else tensor.reshape(
                len(array), -1)
            return tensor, single

        def _distribution_params(self, obs):
            tensor, single = self._batch(obs)
            mean = self.actor(tensor)
            log_std = self.log_std.clamp(self.LOG_STD_MIN, self.LOG_STD_MAX)
            return mean, log_std, single

        @torch.no_grad()
        def sample(self, obs, deterministic: bool = False):
            mean, log_std, single = self._distribution_params(obs)
            std = log_std.exp()
            if deterministic:
                raw = mean
            else:
                raw = mean + std * torch.randn_like(mean)
            action = torch.tanh(raw)
            log_prob = self._squashed_log_prob(raw, mean, log_std)
            action = action.detach()
            log_prob = log_prob.detach()
            if single:
                return action.numpy().reshape(1, -1), log_prob.numpy().reshape(1)
            return action.numpy(), log_prob.numpy()

        @staticmethod
        def _squashed_log_prob(raw, mean, log_std):
            normal_lp = (-0.5 * ((raw - mean) / log_std.exp()) ** 2
                         - log_std - 0.5 * float(np.log(2 * np.pi))).sum(dim=-1)
            correction = (2.0 * (float(np.log(2.0)) - raw
                                 - torch.logaddexp(torch.zeros_like(raw),
                                                   -2.0 * raw))).sum(dim=-1)
            return normal_lp - correction

        @torch.no_grad()
        def set_log_alpha(self, value: float) -> None:
            self.log_alpha.copy_(torch.as_tensor(float(value)))

        @torch.no_grad()
        def alpha(self) -> float:
            return float(self.log_alpha.exp().item())

        @torch.no_grad()
        def entropy(self) -> float:
            std = self.log_std.clamp(self.LOG_STD_MIN, self.LOG_STD_MAX).exp()
            return float(torch.sum(
                std * (std.log() + 0.5 * float(np.log(2 * np.pi)))))

        @torch.no_grad()
        def log_prob(self, obs, actions) -> np.ndarray:
            mean, log_std, _ = self._distribution_params(obs)
            bounded = _to_tensor(np.clip(
                np.asarray(actions, dtype=np.float32), -0.999999, 0.999999))
            raw = 0.5 * torch.log((1.0 + bounded) / (1.0 - bounded))
            return self._squashed_log_prob(raw, mean, log_std).numpy()

        def critic_values(self, obs, actions, target: bool = False):
            tensor, _ = self._batch(obs)
            action_tensor = _to_tensor(actions).reshape(
                tensor.shape[0], self.action_size)
            # always detached: this method is for reporting and target
            # computation. update_actor differentiates through the critic
            # modules directly, where the graph is required.
            with torch.no_grad():
                if target:
                    return (self.q1_target(tensor, action_tensor).numpy(),
                            self.q2_target(tensor, action_tensor).numpy())
                return (self.q1(tensor, action_tensor).numpy(),
                        self.q2(tensor, action_tensor).numpy())

        def act(self, obs, deterministic: bool = False):
            action, log_prob = self.sample(obs, deterministic)
            q1, q2 = self.critic_values(obs, action)
            value = np.minimum(q1, q2)
            return PolicyOutput(
                np.asarray(action[0], dtype=np.float32),
                float(np.asarray(log_prob).reshape(-1)[0]),
                float(np.asarray(value).reshape(-1)[0]),
                self.entropy(),
            )

        def evaluate(self, obs, action):
            actions = np.asarray(action, dtype=np.float32).reshape(1, -1)
            q1, _ = self.critic_values(obs, actions)
            return (float(np.asarray(q1).reshape(-1)[0]),
                    float(np.asarray(self.log_prob(obs, actions)).reshape(-1)[0]),
                    self.entropy())

        # --------------------------------------------------------- updates
        def update_critics(self, obs, actions, targets):
            tensor, _ = self._batch(obs)
            action_tensor = _to_tensor(actions).reshape(
                tensor.shape[0], self.action_size)
            target_tensor = _to_tensor(targets).reshape(-1)
            q1_loss = F.mse_loss(self.q1(tensor, action_tensor), target_tensor)
            q2_loss = F.mse_loss(self.q2(tensor, action_tensor), target_tensor)
            self.critic_optimizer.zero_grad(set_to_none=True)
            (q1_loss + q2_loss).backward()
            self.critic_optimizer.step()
            return float(q1_loss.detach()), float(q2_loss.detach())

        def update_actor(self, obs, alpha: float) -> float:
            tensor, _ = self._batch(obs)
            mean, log_std, _ = self._distribution_params(obs)
            raw = mean + log_std.exp() * torch.randn_like(mean)
            action = torch.tanh(raw)
            log_prob = self._squashed_log_prob(raw, mean, log_std)
            q = torch.min(self.q1(tensor, action), self.q2(tensor, action))
            loss = (alpha * log_prob - q).mean()
            self.actor_optimizer.zero_grad(set_to_none=True)
            loss.backward()
            self.actor_optimizer.step()
            return float(loss.detach())

        def update_alpha(self, log_prob) -> float:
            tensor = _to_tensor(log_prob).reshape(-1)
            loss = -(self.log_alpha.exp() * (tensor.detach()
                                             + self.target_entropy).mean())
            self.alpha_optimizer.zero_grad(set_to_none=True)
            loss.backward()
            self.alpha_optimizer.step()
            return float(loss.detach())

        def soft_update(self, tau: float) -> None:
            with torch.no_grad():
                for target_module, source_module in (
                        (self.q1_target, self.q1), (self.q2_target, self.q2)):
                    for target_param, source_param in zip(
                            target_module.parameters(), source_module.parameters()):
                        target_param.mul_(1.0 - tau).add_(tau * source_param)

else:  # pragma: no cover - torch absent
    TorchSACPolicy = None


def create_q_network(obs_shape, action_size: int, hidden_units: int = 16,
                     num_layers: int = 1, learning_rate: float = 0.01,
                     seed: int | None = None, prefer_torch: bool = True):
    """Torch Q-network when available, else the NumPy implementation."""
    if prefer_torch and TORCH_AVAILABLE:
        return TorchQNetwork(obs_shape, action_size, hidden_units, num_layers,
                            learning_rate, seed)
    from .policy import QNetwork
    return QNetwork(obs_shape, action_size, hidden_units, num_layers,
                    learning_rate, seed)


def create_sac_policy(obs_shape, action_size: int, hidden_units: int = 16,
                      learning_rate: float = 0.01,
                      target_entropy: float | None = None,
                      seed: int | None = None, prefer_torch: bool = True):
    """Torch SAC policy when available, else the NumPy implementation."""
    if prefer_torch and TORCH_AVAILABLE:
        return TorchSACPolicy(obs_shape, action_size, hidden_units,
                              learning_rate, target_entropy, seed)
    from .policy import SACPolicy
    return SACPolicy(obs_shape, action_size, hidden_units, learning_rate,
                     target_entropy, seed)
