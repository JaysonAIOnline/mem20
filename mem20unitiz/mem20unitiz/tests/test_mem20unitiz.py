"""Behavioral tests for the real mem20unitiz reinforcement-learning stack."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from mem20unitiz import (
    ActionSpec,
    BehaviorSpec,
    Buffer,
    CooperativeGridWorld,
    DQNTrainer,
    GridWorld,
    MLConfig,
    ModelSaver,
    ObservationSpec,
    POCATrainer,
    PPOTrainer,
    SACTrainer,
    SimpleEnvironment,
    TrainerType,
    Trajectory,
    create_policy,
    create_trainer,
    get_default_settings,
)
from mem20unitiz.policy import QNetwork, SACPolicy


def discrete_behavior(name: str = "agent", observation_size: int = 1, actions: int = 2) -> BehaviorSpec:
    return BehaviorSpec(
        name,
        [ObservationSpec((observation_size,))],
        ActionSpec(discrete_size=actions),
    )


def simple_environment(seed: int = 0, episode_length: int = 8) -> SimpleEnvironment:
    return SimpleEnvironment(
        {"agent": discrete_behavior()},
        episode_length=episode_length,
    )


def add_transition(buffer: Buffer, index: int, done: bool = False, priority: float = 1.0) -> None:
    buffer.add(
        {
            "observation": np.asarray([index / 10.0], dtype=np.float32),
            "action": np.asarray([index % 2], dtype=np.float32),
            "reward": float(index),
            "next_observation": np.asarray([(index + 1) / 10.0], dtype=np.float32),
            "done": done,
            "priority": priority,
        }
    )


def test_config_yaml_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    original = MLConfig(default_trainer="dqn", max_steps=17, seed=9)
    original.save(str(path))
    loaded = MLConfig.load(str(path))
    assert loaded == original


def test_settings_return_implemented_types() -> None:
    assert get_default_settings(TrainerType.PPO).__class__.__name__ == "PPOSettings"
    assert get_default_settings("dqn").__class__.__name__ == "DQNSettings"
    assert get_default_settings(TrainerType.SAC).__class__.__name__ == "SACSettings"
    assert get_default_settings(TrainerType.POCA).__class__.__name__ == "POCASettings"
    with pytest.raises(ValueError):
        get_default_settings("lstm")


def test_action_spec_rejects_mixed_action_modes() -> None:
    with pytest.raises(ValueError):
        ActionSpec(continuous_size=1, discrete_size=2)
    with pytest.raises(ValueError):
        ActionSpec(discrete_branches=[2, 0])


def test_gridworld_discrete_transition_and_goal_reward() -> None:
    environment = GridWorld(grid_size=3, discrete=True, max_steps=5, goal=(0, 1))
    infos = environment.reset()
    assert infos["grid"].observations[0].shape == (2,)
    output = environment.step({"grid": np.asarray([0], dtype=np.float32)})
    info = output.agent_info["grid"]
    assert environment.position == (0, 1)
    assert info.done
    assert info.reward > 0.5
    assert np.all(np.isfinite(info.observations[0]))


def test_gridworld_continuous_action_stays_in_bounds() -> None:
    environment = GridWorld(grid_size=4, discrete=False, max_steps=3, seed=2)
    environment.reset()
    output = environment.step({"grid": np.asarray([100.0, -100.0], dtype=np.float32)})
    x, y = environment.position
    assert 0 <= x < 4
    assert 0 <= y < 4
    assert np.all(np.isfinite(output.agent_info["grid"].observations[0]))


def test_simple_environment_preserves_observation_shape_and_terminates() -> None:
    environment = SimpleEnvironment(
        {"agent": discrete_behavior(observation_size=4)},
        episode_length=4,
    )
    infos = environment.reset()
    assert infos["agent"].observations[0].shape == (4,)
    outputs = []
    rewards = []
    for _ in range(4):
        output = environment.step({"agent": np.asarray([0], dtype=np.float32)})
        outputs.append(output)
        rewards.append(output.agent_info["agent"].reward)
    output = outputs[-1]
    assert output.agent_info["agent"].done
    assert output.agent_info["agent"].observations[0].shape == (4,)
    assert rewards[-1] == 0.0


def test_cooperative_environment_assigns_one_team_reward() -> None:
    environment = CooperativeGridWorld(grid_size=3, max_steps=8, seed=1)
    infos = environment.reset()
    output = environment.step(
        {
            "agent_0": np.asarray([0], dtype=np.float32),
            "agent_1": np.asarray([0], dtype=np.float32),
        }
    )
    first = output.agent_info["agent_0"]
    second = output.agent_info["agent_1"]
    assert first.reward == second.reward
    assert first.done == second.done
    assert set(output.agent_info) == set(infos)


def test_buffer_allocates_exact_shapes_and_wraps() -> None:
    buffer = Buffer(4, (1,), (1,))
    for index in range(6):
        add_transition(buffer, index)
    assert buffer.size == 4
    assert buffer.observations.shape == (4, 1)
    assert buffer.actions.shape == (4, 1)
    assert buffer.next_observations.shape == (4, 1)
    batch = buffer.get_batch(3)
    assert batch["observations"].shape == (3, 1)
    assert batch["actions"].shape == (3, 1)
    assert np.all(batch["rewards"] >= 0)


def test_buffer_rejects_wrong_shapes() -> None:
    buffer = Buffer(3, (2,), (1,))
    with pytest.raises(ValueError):
        buffer.add(
            {
                "observation": np.zeros(3),
                "action": np.zeros(1),
                "reward": 0.0,
                "next_observation": np.zeros(2),
                "done": False,
            }
        )
    with pytest.raises(ValueError):
        buffer.get_batch(1)


def test_prioritized_sampling_returns_indices_and_updates_priorities() -> None:
    buffer = Buffer(5, (1,), (1,), seed=4)
    for index in range(5):
        add_transition(buffer, index, priority=1.0 + index)
    batch, indices, weights = buffer.sample_prioritized(3, alpha=1.0, beta=0.5)
    assert batch["observations"].shape == (3, 1)
    assert indices.shape == (3,)
    assert weights.shape == (3,)
    assert np.all(weights > 0)
    buffer.update_priorities(indices, np.asarray([10.0, 20.0, 30.0]))
    assert np.all(buffer.priorities[indices] > 1.0)


def test_buffer_gae_respects_terminal_boundary() -> None:
    buffer = Buffer(2, (1,), (1,))
    add_transition(buffer, 1, done=False)
    add_transition(buffer, 1, done=True)
    buffer.values[:2] = np.asarray([1.0, 1.0], dtype=np.float32)
    buffer.compute_advantages(gamma=0.99, gae_lambda=0.95)
    np.testing.assert_allclose(buffer.advantages[:2], [0.99, 0.0], atol=1e-6)
    np.testing.assert_allclose(buffer.returns[:2], [1.99, 1.0], atol=1e-6)


def test_trajectory_returns_reset_at_done() -> None:
    trajectory = Trajectory("agent")
    for index, done in enumerate((False, True, False)):
        trajectory.add_step(
            np.asarray([index], dtype=np.float32),
            np.asarray([index % 2], dtype=np.float32),
            1.0,
            -0.5,
            0.0,
            done,
            next_observation=np.asarray([index + 1], dtype=np.float32),
        )
    np.testing.assert_allclose(trajectory.compute_returns(0.99), [1.99, 1.0, 1.0])
    advantages = trajectory.compute_advantages(0.99, 0.95)
    assert advantages.shape == (3,)
    assert np.all(np.isfinite(advantages))


def test_discrete_policy_samples_and_evaluates_real_distribution() -> None:
    policy = create_policy((2,), ActionSpec(discrete_size=4), {"hidden_units": 8}, continuous=False, seed=5)
    observation = np.asarray([0.25, -0.5], dtype=np.float32)
    output = policy.act(observation)
    assert isinstance(output.action, int)
    assert 0 <= output.action < 4
    log_prob, entropy, value = policy.evaluate(observation, output.action)
    assert math.isfinite(log_prob)
    assert entropy > 0
    assert math.isfinite(value)


def test_continuous_policy_samples_bounded_environment_valid_action() -> None:
    policy = create_policy((2,), ActionSpec(continuous_size=2), {"hidden_units": 8}, continuous=True, seed=6)
    output = policy.act(np.asarray([0.1, 0.2], dtype=np.float32))
    assert output.action.shape == (2,)
    assert np.all(np.isfinite(output.action))
    assert math.isfinite(output.log_prob)


def test_policy_update_changes_real_parameters() -> None:
    environment = simple_environment(seed=7)
    behavior = environment.behavior_specs["agent"]
    policy = create_policy(behavior.observation_shapes[0], behavior.action_spec, {"hidden_units": 6}, continuous=False, seed=8)
    observations, actions, rewards = [], [], []
    infos = environment.reset()
    for _ in range(64):
        observation = infos["agent"].observations[0]
        output = policy.act(observation)
        step = environment.step({"agent": output.action})
        observations.append(observation)
        actions.append(output.action)
        rewards.append(step.agent_info["agent"].reward)
        infos = {"agent": step.agent_info["agent"]}
    observations_array = np.asarray(observations, dtype=np.float32)
    actions_array = np.asarray(actions, dtype=np.int64)
    log_probs, _, _ = policy.evaluate_batch(observations_array, actions_array)
    before = policy.parameter_norm()
    policy.ppo_update(
        observations_array,
        actions_array,
        log_probs,
        np.asarray(rewards, dtype=np.float32),
        np.asarray(rewards, dtype=np.float32),
        epochs=1,
        batch_size=32,
    )
    assert policy.parameter_norm() != before


def test_policy_state_dict_round_trip() -> None:
    policy = create_policy((3,), ActionSpec(discrete_size=3), {"hidden_units": 5}, continuous=False, seed=10)
    clone = create_policy((3,), ActionSpec(discrete_size=3), {"hidden_units": 5}, continuous=False, seed=11)
    clone.load_state_dict(policy.state_dict())
    observation = np.asarray([0.2, 0.4, -0.1], dtype=np.float32)
    assert policy.act(observation, deterministic=True).action == clone.act(observation, deterministic=True).action


def test_qnetwork_update_changes_q_values() -> None:
    network = QNetwork((2,), 3, hidden_units=6, learning_rate=0.05, seed=12)
    observations = np.asarray([[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]], dtype=np.float32)
    actions = np.asarray([0, 1, 2], dtype=np.int64)
    before = network.q_values(observations).copy()
    loss = network.update(observations, actions, np.asarray([1.0, 2.0, 3.0]))
    after = network.q_values(observations)
    assert loss >= 0
    assert not np.allclose(before, after)


def test_sac_policy_samples_and_updates_real_networks() -> None:
    policy = SACPolicy((2,), 2, learning_rate=0.01, seed=13)
    observation = np.asarray([[0.2, -0.1], [0.4, 0.3]], dtype=np.float32)
    actions, log_probs = policy.sample(observation)
    assert actions.shape == (2, 2)
    assert np.all(np.abs(actions) < 1.0)
    assert log_probs.shape == (2,)
    before_actor = policy.actor_w.copy()
    before_q = policy.q1_w.copy()
    targets = np.asarray([0.2, 0.4], dtype=np.float64)
    critic_losses = policy.update_critics(observation, actions, targets)
    actor_loss = policy.update_actor(observation, 0.5)
    alpha_loss = policy.update_alpha(log_probs)
    assert all(math.isfinite(value) for value in (*critic_losses, actor_loss, alpha_loss))
    assert not np.allclose(before_actor, policy.actor_w)
    assert not np.allclose(before_q, policy.q1_w)


def test_ppo_trainer_runs_real_update() -> None:
    environment = simple_environment(seed=14)
    behavior = environment.behavior_specs["agent"]
    settings = get_default_settings(TrainerType.PPO)
    settings.batch_size = 16
    settings.buffer_size = 128
    settings.num_epochs = 1
    settings.network_settings.hidden_units = 6
    trainer = PPOTrainer("agent", behavior, settings, seed=15)
    for _ in range(3):
        trajectory = trainer.collect_trajectory(environment)
        trainer.process_experiences([trajectory])
    losses = trainer.update()
    assert losses
    assert math.isfinite(losses["total_loss"])
    assert trainer.metrics.updates == 1
    assert trainer.buffer.size == 0


def test_ppo_loss_decreases_on_real_corridor_data() -> None:
    environment = simple_environment(seed=0, episode_length=8)
    behavior = environment.behavior_specs["agent"]
    settings = get_default_settings(TrainerType.PPO)
    settings.batch_size = 64
    settings.buffer_size = 256
    settings.num_epochs = 1
    settings.beta = 0.0
    settings.learning_rate = 0.01
    settings.clear_after_update = False
    settings.network_settings.hidden_units = 4
    trainer = PPOTrainer("agent", behavior, settings, seed=16)
    while trainer.buffer.size < 64:
        trajectory = trainer.collect_trajectory(environment)
        trainer.process_experiences([trajectory])
    losses = [trainer.update()["total_loss"] for _ in range(12)]
    assert all(math.isfinite(value) for value in losses)
    assert losses[-1] < losses[0]


def test_dqn_trainer_runs_real_prioritized_update() -> None:
    environment = simple_environment(seed=17)
    behavior = environment.behavior_specs["agent"]
    settings = get_default_settings(TrainerType.DQN)
    settings.batch_size = 16
    settings.buffer_size = 128
    settings.target_update_freq = 2
    settings.network_settings.hidden_units = 6
    trainer = DQNTrainer("agent", behavior, settings, seed=18)
    for _ in range(4):
        trajectory = trainer.collect_trajectory(environment)
        trainer.process_experiences([trajectory])
    losses = trainer.update()
    assert losses
    assert math.isfinite(losses["q_loss"])
    assert 0 <= losses["epsilon"] <= 1
    assert trainer.metrics.updates == 1


def test_dqn_loss_decreases_on_real_replay_data() -> None:
    environment = simple_environment(seed=19)
    behavior = environment.behavior_specs["agent"]
    settings = get_default_settings(TrainerType.DQN)
    settings.batch_size = 32
    settings.buffer_size = 256
    settings.prioritized = False
    settings.learning_rate = 0.02
    settings.network_settings.hidden_units = 4
    trainer = DQNTrainer("agent", behavior, settings, seed=20)
    while trainer.buffer.size < 32:
        trajectory = trainer.collect_trajectory(environment)
        trainer.process_experiences([trajectory])
    losses = []
    for _ in range(12):
        trajectory = trainer.collect_trajectory(environment)
        trainer.process_experiences([trajectory])
        losses.append(trainer.update()["q_loss"])
    assert all(math.isfinite(value) for value in losses)
    assert losses[-1] < losses[0]


def test_sac_trainer_runs_real_continuous_update() -> None:
    environment = GridWorld(grid_size=3, discrete=False, max_steps=8, seed=21)
    behavior = environment.behavior_specs["grid"]
    settings = get_default_settings(TrainerType.SAC)
    settings.batch_size = 16
    settings.buffer_size = 128
    settings.network_settings.hidden_units = 6
    trainer = SACTrainer("grid", behavior, settings, seed=22)
    for _ in range(4):
        trajectory = trainer.collect_trajectory(environment)
        trainer.process_experiences([trajectory])
    losses = trainer.update()
    assert losses
    assert math.isfinite(losses["critic_loss"])
    assert math.isfinite(losses["actor_loss"])


def test_poca_trainer_runs_real_team_update() -> None:
    environment = CooperativeGridWorld(grid_size=3, max_steps=8, seed=23)
    settings = get_default_settings(TrainerType.POCA)
    settings.batch_size = 8
    settings.hidden_units = 6
    trainer = POCATrainer(environment.behavior_specs, settings, buffer_size=64, batch_size=8, num_epochs=1, seed=24)
    updates = trainer.fit(environment, total_steps=24, rollout_size=8)
    assert updates
    assert trainer.metrics.updates >= 1
    assert all(math.isfinite(value["critic_loss"]) for value in updates)


def test_trainer_factory_creates_each_real_algorithm() -> None:
    discrete = discrete_behavior()
    continuous = BehaviorSpec("continuous", [ObservationSpec((2,))], ActionSpec(continuous_size=2))
    assert isinstance(create_trainer("agent", discrete, get_default_settings("ppo")), PPOTrainer)
    assert isinstance(create_trainer("agent", discrete, get_default_settings("dqn")), DQNTrainer)
    assert isinstance(create_trainer("continuous", continuous, get_default_settings("sac")), SACTrainer)


def test_model_saver_round_trips_real_policy_parameters(tmp_path: Path) -> None:
    policy = create_policy((2,), ActionSpec(discrete_size=3), {"hidden_units": 5}, continuous=False, seed=25)
    clone = create_policy((2,), ActionSpec(discrete_size=3), {"hidden_units": 5}, continuous=False, seed=26)
    saver = ModelSaver(str(tmp_path))
    path = saver.save(policy, step=4, metrics={"loss": 0.25}, trainer_type="ppo")
    assert Path(path).exists()
    saver.load(path, policy=clone)
    observation = np.asarray([0.2, 0.3], dtype=np.float32)
    assert policy.act(observation, deterministic=True).action == clone.act(observation, deterministic=True).action
    assert saver.get_latest_checkpoint().step == 4


def test_cli_runs_real_test_episode(capsys: pytest.CaptureFixture[str]) -> None:
    from mem20unitiz.cli import main

    assert main(["test", "--seed", "27"]) == 0
    result = json.loads(capsys.readouterr().out.strip())
    assert result["transitions"] > 0
    assert math.isfinite(result["total_reward"])
    assert len(result["final_position"]) == 2


def test_torch_policy_backend_is_real_when_available() -> None:
    import mem20unitiz

    if not mem20unitiz.TORCH_AVAILABLE:
        pytest.skip("Torch is not installed in this interpreter")
    policy = create_policy((2,), ActionSpec(discrete_size=3), {"hidden_units": 6}, continuous=False, seed=28)
    assert type(policy).__name__ == "TorchPolicy"
    output = policy.act(np.asarray([0.2, -0.1], dtype=np.float32))
    assert 0 <= output.action < 3
    observations = np.asarray([[0.2, -0.1], [0.4, 0.3]], dtype=np.float32)
    actions = np.asarray([output.action, (output.action + 1) % 3], dtype=np.int64)
    log_probs, _, _ = policy.evaluate_batch(observations, actions)
    losses = policy.ppo_update(
        observations,
        actions,
        log_probs.detach().cpu().numpy(),
        np.asarray([1.0, -1.0], dtype=np.float32),
        np.asarray([1.0, -1.0], dtype=np.float32),
        epochs=1,
        batch_size=2,
    )
    assert math.isfinite(losses["total_loss"])
