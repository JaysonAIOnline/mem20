"""Real learning agents for mem20gamez.

Every agent performs real torch gradient updates over stored experience. DQN
has task-mastery behavioral coverage on ``TinyGridWorld``; the policy-gradient
agents have finite-update coverage.
  * DQNAgent       — Double DQN with prioritized replay, optional dueling
                     head, and hard or Polyak target synchronization.
  * REINFORCEAgent — Monte-Carlo policy gradient (Williams 1992) with a
                     return baseline and entropy bonus.
  * PPOAgent       — clipped PPO (Schulman et al. 2017), value network,
                     multi-epoch minibatch updates.
  * SACAgent       — discrete soft actor-critic (Christodoulou 2019):
                     twin Q critics, soft policy, learned temperature.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn

from .agent import AgentConfig, GameAgent
from .networks import DuelingQNetwork, PolicyNetwork, QNetwork, ValueNetwork
from .replay_buffer import Experience, ReplayBuffer, stack_batch

DEVICE = "cpu"


def _to_tensor(x: Any, dtype: torch.dtype = torch.float32) -> torch.Tensor:
    return torch.as_tensor(np.asarray(x, dtype=np.float32), dtype=dtype, device=DEVICE)


def _soft_update(target: nn.Module, source: nn.Module, tau: float) -> None:
    """Polyak averaging: target.theta = (1-tau)*target.theta + tau*source.theta."""
    for tp, sp in zip(target.parameters(), source.parameters()):
        tp.data.copy_((1.0 - tau) * tp.data + tau * sp.data)


class DQNAgent(GameAgent):
    """Deep Q-Network agent with prioritized experience replay."""

    def __init__(self, config: AgentConfig):
        super().__init__(config)
        torch.manual_seed(config.seed)
        net_cls = DuelingQNetwork if config.dueling else QNetwork
        self.q_network = net_cls(config.input_dim, config.action_size, config.hidden_size, config.num_layers)
        self.target_network = deepcopy(self.q_network)
        self.target_network.eval()
        self.target_network.requires_grad_(False)
        self.optimizer = torch.optim.Adam(self.q_network.parameters(), lr=config.learning_rate)
        self.buffer = ReplayBuffer(capacity=config.buffer_size, seed=config.seed)
        self.epsilon = config.epsilon
        self._rng = np.random.default_rng(config.seed)

    def act(self, obs: np.ndarray, training: bool = True) -> int:
        if training and self._rng.random() < self.epsilon:
            return int(self._rng.integers(self.config.action_size))
        with torch.no_grad():
            state = _to_tensor(obs).reshape(1, -1)
            q = self.q_network(state)
            return int(q.argmax(dim=-1).item())

    def greedy_action(self, obs: np.ndarray) -> int:
        return self.act(obs, training=False)

    def remember(self, experience: Any) -> None:
        self.buffer.add(experience)

    def end_episode(self) -> None:
        self.episode_count += 1

    def _sync_target(self) -> None:
        if self.config.tau >= 1.0:
            self.target_network.load_state_dict(self.q_network.state_dict())
        else:
            _soft_update(self.target_network, self.q_network, self.config.tau)

    def replay(self) -> dict[str, float] | None:
        """Sample from the internal buffer and do one real value update."""
        if len(self.buffer) < self.config.batch_size:
            return None
        batch, indices, weights = self.buffer.sample(self.config.batch_size)
        return self.learn(batch, weights=weights, indices=indices)

    def learn(
        self,
        experiences: list[Any] | None = None,
        weights: np.ndarray | None = None,
        indices: list[int] | None = None,
    ) -> dict[str, float]:
        self.step_count += 1
        if experiences is None:
            batch, indices, weights = self.buffer.sample(self.config.batch_size)
        else:
            batch = experiences

        arr = stack_batch(batch)
        states = _to_tensor(arr["states"])
        next_states = _to_tensor(arr["next_states"])
        actions = _to_tensor(arr["actions"], torch.int64)
        rewards = _to_tensor(arr["rewards"])
        dones = _to_tensor(arr["dones"])

        with torch.no_grad():
            next_actions = self.q_network(next_states).argmax(dim=-1, keepdim=True)
            next_q = self.target_network(next_states).gather(1, next_actions)
            targets = rewards.unsqueeze(-1) + self.config.gamma * next_q * (1.0 - dones.unsqueeze(-1))

        q_values = self.q_network(states).gather(1, actions.unsqueeze(-1))
        td_errors = (targets - q_values).squeeze(-1)

        if weights is not None and weights.size > 0:
            w = _to_tensor(weights)
            loss = (td_errors**2 * w).mean()
        else:
            loss = (td_errors**2).mean()

        self.optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self.q_network.parameters(), self.config.max_grad_norm)
        self.optimizer.step()

        self.epsilon = max(self.config.epsilon_min, self.epsilon * self.config.epsilon_decay)
        if (
            self.config.tau >= 1.0
            and self.step_count % max(self.config.target_update, 1) == 0
        ) or self.config.tau < 1.0:
            self._sync_target()

        if indices is not None:
            self.buffer.update_priorities(indices, td_errors.detach().abs().numpy())

        return {
            "loss": float(loss.item()),
            "epsilon": float(self.epsilon),
            "q_value": float(q_values.mean().item()),
            "td_errors": td_errors.detach().abs().mean().item(),
        }

    def save(self, path: str) -> bool:
        torch.save(
            {
                "q_network": self.q_network.state_dict(),
                "target_network": self.target_network.state_dict(),
                "optimizer": self.optimizer.state_dict(),
                "epsilon": self.epsilon,
                "step_count": self.step_count,
                "episode_count": self.episode_count,
            },
            path,
        )
        return True

    def load(self, path: str) -> bool:
        ckpt = torch.load(path, map_location=DEVICE, weights_only=False)
        self.q_network.load_state_dict(ckpt["q_network"])
        self.target_network.load_state_dict(ckpt["target_network"])
        self.optimizer.load_state_dict(ckpt["optimizer"])
        self.epsilon = float(ckpt["epsilon"])
        self.step_count = int(ckpt["step_count"])
        self.episode_count = int(ckpt["episode_count"])
        return True


class REINFORCEAgent(GameAgent):
    """Monte-Carlo policy gradient (Williams 1992)."""

    def __init__(self, config: AgentConfig):
        super().__init__(config)
        torch.manual_seed(config.seed)
        self.policy = PolicyNetwork(config.input_dim, config.action_size, config.hidden_size, config.num_layers)
        self.optimizer = torch.optim.Adam(self.policy.parameters(), lr=config.learning_rate)
        self._memory: list[Experience] = []

    def act(self, obs: np.ndarray, training: bool = True) -> int:
        with torch.no_grad():
            state = _to_tensor(obs).reshape(1, -1)
            if training:
                probs = self.policy.probs(state)
                return int(torch.multinomial(probs, 1).item())
            return int(self.policy.greedy_action(state).item())

    def remember(self, experience: Any) -> None:
        self._memory.append(ReplayBuffer.normalize(experience))

    def end_episode(self) -> None:
        self.episode_count += 1

    def replay(self) -> dict[str, float] | None:
        return None

    def learn(self, experiences: list[Any] | None = None) -> dict[str, float]:
        self.step_count += 1
        data = experiences if experiences is not None else self._memory
        self._memory = []
        if not data:
            return {"policy_loss": 0.0, "return_mean": 0.0, "entropy": 0.0}

        arr = stack_batch(data)
        states = _to_tensor(arr["states"])
        actions = _to_tensor(arr["actions"], torch.int64)
        rewards = _to_tensor(arr["rewards"])

        # Discounted Monte-Carlo returns.
        returns = torch.zeros_like(rewards)
        g = 0.0
        for t in range(len(rewards) - 1, -1, -1):
            g = float(rewards[t]) + self.config.gamma * g * (1.0 - float(arr["dones"][t]))
            returns[t] = g
        baseline = returns.mean()
        advantages = returns - baseline

        logits = self.policy(states)
        log_probs = F.log_softmax(logits, dim=-1)
        log_pi_a = log_probs.gather(1, actions.unsqueeze(-1)).squeeze(-1)
        entropy = -(log_probs.exp() * log_probs).sum(dim=-1).mean()

        normalized_advantages = advantages / (advantages.std(unbiased=False) + 1e-8)
        loss = -(log_pi_a * normalized_advantages).mean() - self.config.entropy_coef * entropy

        self.optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self.policy.parameters(), self.config.max_grad_norm)
        self.optimizer.step()

        return {
            "policy_loss": float(loss.item()),
            "return_mean": float(returns.mean().item()),
            "entropy": float(entropy.item()),
        }

    def save(self, path: str) -> bool:
        torch.save(
            {
                "policy": self.policy.state_dict(),
                "optimizer": self.optimizer.state_dict(),
                "step_count": self.step_count,
                "episode_count": self.episode_count,
            },
            path,
        )
        return True

    def load(self, path: str) -> bool:
        ckpt = torch.load(path, map_location=DEVICE, weights_only=False)
        self.policy.load_state_dict(ckpt["policy"])
        self.optimizer.load_state_dict(ckpt["optimizer"])
        self.step_count = int(ckpt["step_count"])
        self.episode_count = int(ckpt["episode_count"])
        return True


class PPOAgent(GameAgent):
    """Clipped Proximal Policy Optimization (Schulman et al. 2017)."""

    def __init__(self, config: AgentConfig):
        super().__init__(config)
        torch.manual_seed(config.seed)
        self.policy = PolicyNetwork(config.input_dim, config.action_size, config.hidden_size, config.num_layers)
        self.value = ValueNetwork(config.input_dim, config.hidden_size, config.num_layers)
        self.optimizer = torch.optim.Adam(
            list(self.policy.parameters()) + list(self.value.parameters()), lr=config.learning_rate
        )
        self._rollout: list[Experience] = []

    def act(self, obs: np.ndarray, training: bool = True) -> int:
        with torch.no_grad():
            state = _to_tensor(obs).reshape(1, -1)
            if training:
                probs = self.policy.probs(state)
                return int(torch.multinomial(probs, 1).item())
            return int(self.policy.greedy_action(state).item())

    def remember(self, experience: Any) -> None:
        self._rollout.append(ReplayBuffer.normalize(experience))

    def end_episode(self) -> None:
        self.episode_count += 1

    def replay(self) -> dict[str, float] | None:
        return None

    def learn(self, experiences: list[Any] | None = None) -> dict[str, float]:
        self.step_count += 1
        data = experiences if experiences is not None else self._rollout
        self._rollout = []
        if len(data) < 2:
            return {"policy_loss": 0.0, "value_loss": 0.0, "clip_frac": 0.0}

        arr = stack_batch(data)
        states = _to_tensor(arr["states"])
        actions = _to_tensor(arr["actions"], torch.int64)
        rewards = _to_tensor(arr["rewards"])
        dones = _to_tensor(arr["dones"])

        # Discounted returns.
        returns = torch.zeros_like(rewards)
        g = 0.0
        for t in range(len(rewards) - 1, -1, -1):
            g = float(rewards[t]) + self.config.gamma * g * (1.0 - float(dones[t]))
            returns[t] = g
        returns_np = returns.numpy()

        with torch.no_grad():
            old_logits = self.policy(states)
            old_logp = F.log_softmax(old_logits, dim=-1).gather(1, actions.unsqueeze(-1)).squeeze(-1)
            baseline = self.value(states)
        advantages = returns - baseline.detach()
        advantages = (advantages - advantages.mean()) / (advantages.std(unbiased=False) + 1e-8)

        n = len(states)
        minibatch_size = min(self.config.minibatch_size, n)
        last_pi_loss = last_v_loss = torch.zeros((), dtype=torch.float32)
        for _ in range(self.config.train_epochs):
            perm = np.random.permutation(n)
            for start in range(0, n, minibatch_size):
                idx = perm[start : start + minibatch_size]
                s_b = states[idx]
                a_b = actions[idx]
                r_b = _to_tensor(returns_np[idx])
                adv_b = advantages[idx]
                old_b = old_logp[idx]

                logits_b = self.policy(s_b)
                logp_b = F.log_softmax(logits_b, dim=-1).gather(1, a_b.unsqueeze(-1)).squeeze(-1)
                ratio = (logp_b - old_b).exp()

                clipped = torch.clamp(ratio, 1.0 - self.config.clip_ratio, 1.0 + self.config.clip_ratio)
                pi_loss = -torch.min(ratio * adv_b, clipped * adv_b).mean()
                entropy = -(logits_b.softmax(dim=-1) * logits_b.log_softmax(dim=-1)).sum(dim=-1).mean()
                v_pred = self.value(s_b)
                v_loss = F.mse_loss(v_pred, r_b)

                loss = pi_loss + self.config.vf_coef * v_loss - self.config.entropy_coef * entropy

                self.optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(
                    list(self.policy.parameters()) + list(self.value.parameters()), self.config.max_grad_norm
                )
                self.optimizer.step()
                self.step_count += 1
                last_pi_loss, last_v_loss = pi_loss.detach(), v_loss.detach()

        with torch.no_grad():
            final_logits = self.policy(states)
            final_logp = F.log_softmax(final_logits, dim=-1).gather(1, actions.unsqueeze(-1)).squeeze(-1)
            clip_frac = float(((final_logp - old_logp).abs() > 1e-3).float().mean().item())

        return {
            "policy_loss": float(last_pi_loss.item()),
            "value_loss": float(last_v_loss.item()),
            "clip_frac": clip_frac,
            "return_mean": float(returns.mean().item()),
        }

    def save(self, path: str) -> bool:
        torch.save(
            {
                "policy": self.policy.state_dict(),
                "value": self.value.state_dict(),
                "optimizer": self.optimizer.state_dict(),
                "step_count": self.step_count,
                "episode_count": self.episode_count,
            },
            path,
        )
        return True

    def load(self, path: str) -> bool:
        ckpt = torch.load(path, map_location=DEVICE, weights_only=False)
        self.policy.load_state_dict(ckpt["policy"])
        self.value.load_state_dict(ckpt["value"])
        self.optimizer.load_state_dict(ckpt["optimizer"])
        self.step_count = int(ckpt["step_count"])
        self.episode_count = int(ckpt["episode_count"])
        return True


class SACAgent(GameAgent):
    """Discrete Soft Actor-Critic (Christodoulou 2019)."""

    def __init__(self, config: AgentConfig):
        super().__init__(config)
        torch.manual_seed(config.seed)
        self.action_size = config.action_size
        self.policy = PolicyNetwork(config.input_dim, config.action_size, config.hidden_size, config.num_layers)
        self.q1 = QNetwork(config.input_dim, config.action_size, config.hidden_size, config.num_layers)
        self.q2 = QNetwork(config.input_dim, config.action_size, config.hidden_size, config.num_layers)
        self.target_q1 = deepcopy(self.q1)
        self.target_q2 = deepcopy(self.q2)
        self.target_q1.eval()
        self.target_q2.eval()
        self.target_q1.requires_grad_(False)
        self.target_q2.requires_grad_(False)

        self.log_alpha = nn.Parameter(torch.tensor(np.log(config.alpha), dtype=torch.float32))
        self.target_entropy = config.target_entropy if config.target_entropy is not None else -np.log(config.action_size)

        self.q_optimizer = torch.optim.Adam(
            list(self.q1.parameters()) + list(self.q2.parameters()), lr=config.learning_rate
        )
        self.policy_optimizer = torch.optim.Adam(self.policy.parameters(), lr=config.learning_rate)
        self.alpha_optimizer = torch.optim.Adam([self.log_alpha], lr=config.learning_rate)

        self.buffer = ReplayBuffer(capacity=config.buffer_size, seed=config.seed)

    def act(self, obs: np.ndarray, training: bool = True) -> int:
        with torch.no_grad():
            state = _to_tensor(obs).reshape(1, -1)
            if training:
                probs = self.policy.probs(state)
                return int(torch.multinomial(probs, 1).item())
            return int(self.policy.greedy_action(state).item())

    def remember(self, experience: Any) -> None:
        self.buffer.add(experience)

    def end_episode(self) -> None:
        self.episode_count += 1

    def replay(self) -> dict[str, float] | None:
        if len(self.buffer) < self.config.batch_size:
            return None
        batch, indices, weights = self.buffer.sample(self.config.batch_size)
        return self.learn(batch, weights=weights, indices=indices)

    def learn(
        self,
        experiences: list[Any] | None = None,
        weights: np.ndarray | None = None,
        indices: list[int] | None = None,
    ) -> dict[str, float]:
        self.step_count += 1
        if experiences is None:
            batch, indices, weights = self.buffer.sample(self.config.batch_size)
        else:
            batch = experiences

        arr = stack_batch(batch)
        states = _to_tensor(arr["states"])
        next_states = _to_tensor(arr["next_states"])
        actions = _to_tensor(arr["actions"], torch.int64)
        rewards = _to_tensor(arr["rewards"])
        dones = _to_tensor(arr["dones"])

        # --- Policy probabilities for the current batch ---
        logits = self.policy(states)
        log_prob_all = F.log_softmax(logits, dim=-1)  # (B, A)
        prob_all = log_prob_all.exp()                 # (B, A)

        with torch.no_grad():
            next_logits = self.policy(next_states)
            next_log_prob_all = F.log_softmax(next_logits, dim=-1)
            next_probs = next_log_prob_all.exp()
            # Expected next-state action value under the soft policy.
            next_q1 = self.target_q1(next_states)
            next_q2 = self.target_q2(next_states)
            next_min_q = torch.minimum(next_q1, next_q2)
            # V(s') = sum_a pi(a|s') [ minQ(s',a) - alpha ln pi(a|s') ]
            next_v = (next_probs * (next_min_q - self.log_alpha.exp() * next_log_prob_all)).sum(dim=-1)
            targets = rewards + self.config.gamma * next_v * (1.0 - dones)

        # --- Critic losses ---
        q1_pred = self.q1(states).gather(1, actions.unsqueeze(-1)).squeeze(-1)
        q2_pred = self.q2(states).gather(1, actions.unsqueeze(-1)).squeeze(-1)
        if weights is not None and weights.size > 0:
            w = _to_tensor(weights)
            q1_loss = ((targets - q1_pred) ** 2 * w).mean()
            q2_loss = ((targets - q2_pred) ** 2 * w).mean()
        else:
            q1_loss = ((targets - q1_pred) ** 2).mean()
            q2_loss = ((targets - q2_pred) ** 2).mean()

        self.q_optimizer.zero_grad()
        (q1_loss + q2_loss).backward()
        nn.utils.clip_grad_norm_(list(self.q1.parameters()) + list(self.q2.parameters()), self.config.max_grad_norm)
        self.q_optimizer.step()

        # --- Policy loss: minimize D_KL toward exp(Q/alpha) ---
        q1_now = self.q1(states).detach()
        q2_now = self.q2(states).detach()
        min_q = torch.minimum(q1_now, q2_now)
        alpha = self.log_alpha.exp().detach()
        # J_pi = E[ sum_a pi(a|s) ( alpha ln pi(a|s) - Q(s,a) ) ]
        policy_loss = (prob_all * (alpha * log_prob_all - min_q)).sum(dim=-1).mean()

        self.policy_optimizer.zero_grad()
        policy_loss.backward()
        nn.utils.clip_grad_norm_(self.policy.parameters(), self.config.max_grad_norm)
        self.policy_optimizer.step()

        # --- Temperature loss: keep policy entropy near target ---
        with torch.no_grad():
            logits_new = self.policy(states)
            logp_new = F.log_softmax(logits_new, dim=-1)
            probs_new = logp_new.exp()
            entropy = -(probs_new * logp_new).sum(dim=-1)
        alpha_loss = -(self.log_alpha.exp() * (entropy + self.target_entropy).detach()).mean()

        self.alpha_optimizer.zero_grad()
        alpha_loss.backward()
        self.alpha_optimizer.step()

        _soft_update(self.target_q1, self.q1, self.config.tau if self.config.tau < 1.0 else 0.005)
        _soft_update(self.target_q2, self.q2, self.config.tau if self.config.tau < 1.0 else 0.005)

        with torch.no_grad():
            td = (targets - q1_pred).abs().numpy()

        if indices is not None:
            self.buffer.update_priorities(indices, td)

        return {
            "q1_loss": float(q1_loss.item()),
            "q2_loss": float(q2_loss.item()),
            "policy_loss": float(policy_loss.item()),
            "alpha": float(alpha.item()),
            "entropy": float(entropy.mean().item()),
        }

    def save(self, path: str) -> bool:
        torch.save(
            {
                "policy": self.policy.state_dict(),
                "q1": self.q1.state_dict(),
                "q2": self.q2.state_dict(),
                "target_q1": self.target_q1.state_dict(),
                "target_q2": self.target_q2.state_dict(),
                "log_alpha": self.log_alpha.detach(),
                "q_optimizer": self.q_optimizer.state_dict(),
                "policy_optimizer": self.policy_optimizer.state_dict(),
                "alpha_optimizer": self.alpha_optimizer.state_dict(),
                "step_count": self.step_count,
                "episode_count": self.episode_count,
            },
            path,
        )
        return True

    def load(self, path: str) -> bool:
        ckpt = torch.load(path, map_location=DEVICE, weights_only=False)
        self.policy.load_state_dict(ckpt["policy"])
        self.q1.load_state_dict(ckpt["q1"])
        self.q2.load_state_dict(ckpt["q2"])
        self.target_q1.load_state_dict(ckpt["target_q1"])
        self.target_q2.load_state_dict(ckpt["target_q2"])
        with torch.no_grad():
            self.log_alpha.copy_(ckpt["log_alpha"])
        self.q_optimizer.load_state_dict(ckpt["q_optimizer"])
        self.policy_optimizer.load_state_dict(ckpt["policy_optimizer"])
        self.alpha_optimizer.load_state_dict(ckpt["alpha_optimizer"])
        self.step_count = int(ckpt["step_count"])
        self.episode_count = int(ckpt["episode_count"])
        return True