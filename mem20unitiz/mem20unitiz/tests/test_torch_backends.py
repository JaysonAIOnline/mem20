"""Tests for the PyTorch DQN and SAC backends.

These assert the backends actually learn and satisfy the same contract as the
NumPy implementations, so the trainers can use either without knowing which.
All are skipped when torch is unavailable.
"""

from __future__ import annotations

import numpy as np
import pytest

from mem20unitiz.environment import ActionSpec, BehaviorSpec, ObservationSpec
from mem20unitiz.policy import QNetwork, SACPolicy
from mem20unitiz.settings import TrainerType, get_default_settings
from mem20unitiz.torch_policy import (
    TORCH_AVAILABLE,
    TorchQNetwork,
    TorchSACPolicy,
    create_q_network,
    create_sac_policy,
)
from mem20unitiz.trainer import create_trainer

pytestmark = pytest.mark.skipif(not TORCH_AVAILABLE, reason="torch not installed")


def discrete_behavior(observation_size: int = 4, actions: int = 3) -> BehaviorSpec:
    return BehaviorSpec("agent", [ObservationSpec((observation_size,))],
                        ActionSpec(discrete_size=actions))


def continuous_behavior(observation_size: int = 4, actions: int = 2) -> BehaviorSpec:
    return BehaviorSpec("agent", [ObservationSpec((observation_size,))],
                        ActionSpec(continuous_size=actions))


def batch(seed: int = 0, rows: int = 64, obs: int = 4):
    rng = np.random.default_rng(seed)
    return (rng.normal(size=(rows, obs)).astype(np.float32),
            rng.integers(0, 3, size=rows),
            rng.normal(size=rows).astype(np.float32))


class TestFactory:
    def test_prefers_torch_by_default(self):
        assert isinstance(create_q_network((4,), 3), TorchQNetwork)
        assert isinstance(create_sac_policy((4,), 2), TorchSACPolicy)

    def test_can_force_numpy_fallback(self):
        assert type(create_q_network((4,), 3, 16, 1, 0.01, 0,
                                     prefer_torch=False)) is QNetwork
        assert type(create_sac_policy((4,), 2, 16, 0.01, None, 0,
                                      prefer_torch=False)) is SACPolicy


class TestTorchQNetwork:
    def test_q_values_shapes(self):
        q = TorchQNetwork((4,), 3, seed=1)
        assert q.q_values(np.zeros(4, dtype=np.float32)).shape == (3,)
        assert q.q_values(np.zeros((10, 4), dtype=np.float32)).shape == (10, 3)

    def test_td_update_reduces_loss_on_fixed_targets(self):
        q = TorchQNetwork((4,), 3, hidden_units=16, learning_rate=0.01, seed=2)
        obs, actions, targets = batch(3)
        first = q.update(obs, actions, targets)
        losses = [q.update(obs, actions, targets) for _ in range(250)]
        assert np.mean(losses[-10:]) < first * 0.5

    def test_rejects_out_of_range_action(self):
        q = TorchQNetwork((4,), 3, seed=4)
        obs = np.zeros((4, 4), dtype=np.float32)
        with pytest.raises(ValueError, match="outside the Q-network action range"):
            q.update(obs, np.array([0, 1, 9, 2]), np.zeros(4))

    def test_rejects_mismatched_targets(self):
        q = TorchQNetwork((4,), 3, seed=5)
        obs = np.zeros((4, 4), dtype=np.float32)
        with pytest.raises(ValueError, match="targets must match"):
            q.update(obs, np.array([0, 1, 2, 0]), np.zeros(3))

    def test_rejects_mismatched_weights(self):
        q = TorchQNetwork((4,), 3, seed=6)
        obs = np.zeros((4, 4), dtype=np.float32)
        with pytest.raises(ValueError, match="weights must match"):
            q.update(obs, np.array([0, 1, 2, 0]), np.zeros(4),
                     weights=np.ones(2))

    def test_state_dict_roundtrip_preserves_predictions(self):
        q = TorchQNetwork((4,), 3, seed=7)
        obs = np.random.default_rng(0).normal(size=(8, 4)).astype(np.float32)
        before = q.q_values(obs)
        twin = TorchQNetwork((4,), 3, seed=99)
        twin.load_state_dict(q.state_dict())
        assert np.allclose(before, twin.q_values(obs), atol=1e-6)

    def test_load_state_dict_rejects_wrong_shape(self):
        q = TorchQNetwork((4,), 3, seed=8)
        state = q.state_dict()
        key = next(iter(state))
        state[key] = np.zeros((99, 99), dtype=np.float32)
        with pytest.raises(ValueError, match="shape mismatch"):
            q.load_state_dict(state)

    def test_action_gradient_returns_finite_values(self):
        q = TorchQNetwork((4,), 3, seed=9)
        obs, actions, _ = batch(10, rows=16)
        values, grads = q.action_gradient(obs, actions)
        assert values.shape == (16,)
        assert all(np.all(np.isfinite(v)) for v in grads.values())


class TestTorchSACPolicy:
    def test_sample_shapes_and_bounds(self):
        sac = TorchSACPolicy((4,), 2, seed=1)
        obs = np.zeros((8, 4), dtype=np.float32)
        action, log_prob = sac.sample(obs)
        assert action.shape == (8, 2)
        assert log_prob.shape == (8,)
        assert np.all(np.abs(action) <= 1.0)

    def test_single_observation_sample_is_batched(self):
        sac = TorchSACPolicy((4,), 2, seed=2)
        action, log_prob = sac.sample(np.zeros(4, dtype=np.float32))
        assert action.shape == (1, 2)
        assert log_prob.shape == (1,)

    def test_deterministic_sampling_is_repeatable(self):
        sac = TorchSACPolicy((4,), 2, seed=3)
        obs = np.random.default_rng(1).normal(size=(6, 4)).astype(np.float32)
        first, _ = sac.sample(obs, deterministic=True)
        second, _ = sac.sample(obs, deterministic=True)
        assert np.allclose(first, second)

    def test_critic_values_shapes(self):
        sac = TorchSACPolicy((4,), 2, seed=4)
        obs = np.zeros((8, 4), dtype=np.float32)
        action, _ = sac.sample(obs)
        online = sac.critic_values(obs, action)
        target = sac.critic_values(obs, action, target=True)
        assert online[0].shape == (8,) and target[0].shape == (8,)

    def test_critic_update_reduces_loss_on_fixed_targets(self):
        sac = TorchSACPolicy((4,), 2, learning_rate=0.01, seed=5)
        obs = np.random.default_rng(2).normal(size=(32, 4)).astype(np.float32)
        action = np.random.default_rng(3).uniform(
            -0.9, 0.9, size=(32, 2)).astype(np.float32)
        targets = np.random.default_rng(4).normal(size=32).astype(np.float32)
        first = sac.update_critics(obs, action, targets)[0]
        losses = [sac.update_critics(obs, action, targets)[0] for _ in range(200)]
        assert np.mean(losses[-10:]) < first * 0.5

    def test_actor_and_alpha_updates_return_finite_scalars(self):
        sac = TorchSACPolicy((4,), 2, seed=6)
        obs = np.random.default_rng(5).normal(size=(16, 4)).astype(np.float32)
        _, log_prob = sac.sample(obs)
        assert np.isfinite(sac.update_actor(obs, float(sac.alpha())))
        assert np.isfinite(sac.update_alpha(log_prob))
        assert np.isfinite(sac.alpha())

    def test_soft_update_moves_targets_toward_online(self):
        sac = TorchSACPolicy((4,), 2, seed=7)
        before = sac.critic_values(np.zeros((4, 4), dtype=np.float32),
                                   np.zeros((4, 2), dtype=np.float32),
                                   target=True)[0].copy()
        with torch_no_grad():
            for param in sac.q1.parameters():
                param.add_(1.0)
        sac.soft_update(0.5)
        after = sac.critic_values(np.zeros((4, 4), dtype=np.float32),
                                  np.zeros((4, 2), dtype=np.float32),
                                  target=True)[0]
        assert not np.allclose(before, after), "soft_update did not move the target"

    def test_log_prob_matches_sampled_action(self):
        sac = TorchSACPolicy((4,), 2, seed=8)
        obs = np.random.default_rng(6).normal(size=(8, 4)).astype(np.float32)
        action, log_prob = sac.sample(obs, deterministic=True)
        assert np.allclose(log_prob, sac.log_prob(obs, action), atol=1e-4)

    def test_entropy_is_finite_and_positive(self):
        assert TorchSACPolicy((4,), 2, seed=9).entropy() > 0.0

    def test_act_returns_action_vector(self):
        sac = TorchSACPolicy((4,), 2, seed=10)
        out = sac.act(np.zeros(4, dtype=np.float32))
        assert np.asarray(out.action).shape == (2,)
        assert np.isfinite(out.value)

    def test_set_log_alpha_and_alpha_roundtrip(self):
        sac = TorchSACPolicy((4,), 2, seed=11)
        sac.set_log_alpha(np.log(0.25))
        assert abs(sac.alpha() - 0.25) < 1e-6

    def test_state_dict_roundtrip(self):
        sac = TorchSACPolicy((4,), 2, seed=12)
        state = sac.state_dict()
        assert state
        twin = TorchSACPolicy((4,), 2, seed=99)
        twin.load_state_dict(state)
        obs = np.random.default_rng(7).normal(size=(5, 4)).astype(np.float32)
        action = np.random.default_rng(8).uniform(-.5, .5, size=(5, 2))
        assert np.allclose(
            sac.critic_values(obs, action)[0],
            twin.critic_values(obs, action)[0],
            atol=1e-6,
        )


def torch_no_grad():
    import torch
    return torch.no_grad()


class TestTrainerIntegration:
    def test_dqn_trainer_uses_torch_policy(self):
        trainer = create_trainer("agent", discrete_behavior(),
                                 get_default_settings(TrainerType.DQN))
        assert isinstance(trainer.policy, TorchQNetwork)
        assert isinstance(trainer.target, TorchQNetwork)

    def test_sac_trainer_uses_torch_policy(self):
        trainer = create_trainer("agent", continuous_behavior(),
                                 get_default_settings(TrainerType.SAC))
        assert isinstance(trainer.policy, TorchSACPolicy)

    def test_dqn_trainer_runs_a_real_update(self):
        from mem20unitiz.environment import GridWorld
        env = GridWorld(grid_size=3, discrete=True, max_steps=5, goal=(0, 1))
        spec = env.behavior_specs["grid"]
        trainer = create_trainer("grid", spec, get_default_settings(TrainerType.DQN))
        for _ in range(3):
            trajectory = trainer.collect_trajectory(env)
            trainer.process_experiences([trajectory])
            trainer.update()
        assert np.isfinite(trainer.metrics.policy_loss)

    def test_sac_trainer_update_runs(self):
        trainer = create_trainer("agent", continuous_behavior(),
                                 get_default_settings(TrainerType.SAC))
        obs = np.random.default_rng(0).normal(size=(16, 4)).astype(np.float32)
        action, log_prob = trainer.policy.sample(obs)
        q1, q2 = trainer.policy.update_critics(
            obs, action, np.zeros(16, dtype=np.float32))
        assert np.isfinite(q1) and np.isfinite(q2)
        assert np.isfinite(trainer.policy.update_actor(obs, trainer.policy.alpha()))
        assert np.isfinite(trainer.policy.update_alpha(log_prob))

    def test_dqn_rejects_a_foreign_policy(self):
        from mem20unitiz.trainer import DQNTrainer
        settings = get_default_settings(TrainerType.DQN)
        with pytest.raises(TypeError):
            DQNTrainer("agent", discrete_behavior(), settings,
                       policy=object(), seed=0)

    def test_sac_rejects_a_foreign_policy(self):
        from mem20unitiz.trainer import SACTrainer
        settings = get_default_settings(TrainerType.SAC)
        with pytest.raises(TypeError):
            SACTrainer("agent", continuous_behavior(), settings,
                       policy=object(), seed=0)

    def test_dqn_checkpoint_roundtrip(self, tmp_path):
        from mem20unitiz.model_saver import ModelSaver
        original = TorchQNetwork((4,), 3, seed=21)
        saver = ModelSaver(str(tmp_path))
        path = saver.save(original, 5)
        restored = TorchQNetwork((4,), 3, seed=77)
        saver.load(path, restored)
        obs = np.random.default_rng(12).normal(size=(6, 4)).astype(np.float32)
        actions = np.random.default_rng(13).integers(0, 3, size=6)
        index = np.arange(6)
        assert np.allclose(original.q_values(obs)[index, actions],
                           restored.q_values(obs)[index, actions], atol=1e-6)

    def test_sac_checkpoint_roundtrip(self, tmp_path):
        from mem20unitiz.model_saver import ModelSaver
        original = TorchSACPolicy((4,), 2, seed=22)
        saver = ModelSaver(str(tmp_path))
        path = saver.save(original, 5)
        restored = TorchSACPolicy((4,), 2, seed=78)
        saver.load(path, restored)
        obs = np.random.default_rng(14).normal(size=(6, 4)).astype(np.float32)
        actions = np.random.default_rng(15).uniform(-.5, .5, size=(6, 2))
        assert np.allclose(original.critic_values(obs, actions)[0],
                           restored.critic_values(obs, actions)[0], atol=1e-6)
