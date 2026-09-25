"""Real torch value/policy networks for mem20gamez agents.

These are genuine nn.Module networks used by DQN / REINFORCE / PPO / SAC.
No mock layers — every forward pass performs real affine + nonlinear transforms.
"""

from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import nn


def build_mlp(
    input_dim: int,
    hidden_size: int,
    output_dim: int,
    num_layers: int,
    activation: str = "relu",
) -> nn.Sequential:
    """Build a real multi-layer perceptron.

    input_dim -> (hidden_size -> activation) * num_layers -> output_dim
    """
    act = {"relu": nn.ReLU, "tanh": nn.Tanh, "elu": nn.ELU}[activation]
    layers: list[nn.Module] = []
    in_dim = input_dim
    for _ in range(num_layers):
        layers.append(nn.Linear(in_dim, hidden_size))
        layers.append(act())
        in_dim = hidden_size
    layers.append(nn.Linear(in_dim, output_dim))
    return nn.Sequential(*layers)


class QNetwork(nn.Module):
    """Action-value network: state -> Q(s, a) for each discrete action."""

    def __init__(
        self,
        input_dim: int,
        action_size: int,
        hidden_size: int = 128,
        num_layers: int = 2,
    ):
        super().__init__()
        self.input_dim = input_dim
        self.action_size = action_size
        self.mlp = build_mlp(input_dim, hidden_size, action_size, num_layers)

    def forward(self, states: torch.Tensor) -> torch.Tensor:
        return self.mlp(states)


class DuelingQNetwork(nn.Module):
    """Dueling DQN head (Wang et al. 2016): shared trunk -> value + advantage."""

    def __init__(
        self,
        input_dim: int,
        action_size: int,
        hidden_size: int = 128,
        num_layers: int = 2,
    ):
        super().__init__()
        self.input_dim = input_dim
        self.action_size = action_size
        self.trunk = build_mlp(input_dim, hidden_size, hidden_size, num_layers)
        self.value_head = nn.Linear(hidden_size, 1)
        self.advantage_head = nn.Linear(hidden_size, action_size)

    def forward(self, states: torch.Tensor) -> torch.Tensor:
        features = self.trunk(states)
        value = self.value_head(features)
        advantage = self.advantage_head(features)
        # Q = V + A - mean(A) keeps the decomposition identifiable.
        return value + advantage - advantage.mean(dim=-1, keepdim=True)


class ValueNetwork(nn.Module):
    """State-value network: state -> scalar V(s)."""

    def __init__(
        self,
        input_dim: int,
        hidden_size: int = 128,
        num_layers: int = 2,
    ):
        super().__init__()
        self.input_dim = input_dim
        self.mlp = build_mlp(input_dim, hidden_size, 1, num_layers)

    def forward(self, states: torch.Tensor) -> torch.Tensor:
        return self.mlp(states).squeeze(-1)


class PolicyNetwork(nn.Module):
    """Policy network: state -> action logits (discrete softmax policy)."""

    def __init__(
        self,
        input_dim: int,
        action_size: int,
        hidden_size: int = 128,
        num_layers: int = 2,
    ):
        super().__init__()
        self.input_dim = input_dim
        self.action_size = action_size
        self.mlp = build_mlp(input_dim, hidden_size, action_size, num_layers)

    def forward(self, states: torch.Tensor) -> torch.Tensor:
        return self.mlp(states)

    def probs(self, states: torch.Tensor) -> torch.Tensor:
        return F.softmax(self.forward(states), dim=-1)

    def sample_action(self, states: torch.Tensor) -> torch.Tensor:
        probs = self.probs(states)
        return torch.multinomial(probs, num_samples=1).squeeze(-1)

    def greedy_action(self, states: torch.Tensor) -> torch.Tensor:
        return self.forward(states).argmax(dim=-1)