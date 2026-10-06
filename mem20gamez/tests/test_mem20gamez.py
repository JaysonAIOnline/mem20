from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
import torch

import mem20gamez
from mem20gamez.agent import AgentConfig, AgentType, RandomAgent, RuleBasedAgent, create_agent
from mem20gamez.agents import DQNAgent, PPOAgent, REINFORCEAgent, SACAgent
from mem20gamez.cli import _apply_config, _build_parser, _LiveServer, create_app, main
from mem20gamez.config import GameConfig
from mem20gamez.curriculum import (
    AdaptiveCurriculum,
    CurriculumConfig,
    CurriculumType,
    create_curriculum,
)
from mem20gamez.environment import EnvConfig, TinyGridWorld, create_environment
from mem20gamez.replay_buffer import Experience, ReplayBuffer, stack_batch
from mem20gamez.reward_shaper import PotentialBasedShaper, RewardConfig
from mem20gamez.trainer import DQNTrainer, MultiAgentTrainer, default_reward_shaper


def make_experience(
    value: float = 0.0,
    *,
    action: int = 0,
    reward: float = 1.0,
    done: bool = False,
    truncated: bool = False,
) -> Experience:
    state = np.asarray([value, 0.0], dtype=np.float32)
    return Experience(
        state=state,
        action=action,
        reward=reward,
        next_state=np.asarray([value + 1.0, 0.0], dtype=np.float32),
        done=done,
        truncated=truncated,
    )


def make_dqn_config(**overrides: object) -> AgentConfig:
    values: dict[str, object] = {
        "agent_type": AgentType.DQN,
        "obs_shape": (10,),
        "action_size": 4,
        "hidden_size": 32,
        "num_layers": 1,
        "learning_rate": 0.01,
        "gamma": 0.95,
        "epsilon": 1.0,
        "epsilon_min": 0.02,
        "epsilon_decay": 0.9,
        "buffer_size": 2000,
        "batch_size": 32,
        "target_update": 20,
        "tau": 0.05,
        "seed": 7,
    }
    values.update(overrides)
    return AgentConfig(**values)


def mean(values: list[float]) -> float:
    return float(np.mean(values)) if values else 0.0


def test_game_config_rejects_missing_and_unknown_settings(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        GameConfig.load(str(tmp_path / "missing.yaml"))
    config_path = tmp_path / "invalid.yaml"
    config_path.write_text("batch_sizee: 32\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown configuration"):
        GameConfig.load(str(config_path))


def test_cli_config_fills_defaults_without_overriding_explicit_options(tmp_path: Path) -> None:
    config_path = tmp_path / "game.yaml"
    config_path.write_text(
        "batch_size: 7\nlr: 0.02\ngamma: 0.9\nmax_episode_steps: 12\n",
        encoding="utf-8",
    )
    parser = _build_parser()
    default_args = parser.parse_args(["--config", str(config_path), "train"])
    _apply_config(default_args, ["--config", str(config_path), "train"])
    assert default_args.batch_size == 7
    assert default_args.lr == 0.02
    assert default_args.gamma == 0.9
    assert default_args.max_steps == 12

    explicit_args = parser.parse_args(
        ["--config", str(config_path), "train", "--batch-size", "8"]
    )
    _apply_config(
        explicit_args,
        ["--config", str(config_path), "train", "--batch-size", "8"],
    )
    assert explicit_args.batch_size == 8


def test_public_api_exports_learning_agents_without_mock_environment() -> None:
    assert mem20gamez.DQNAgent is DQNAgent
    assert mem20gamez.REINFORCEAgent is REINFORCEAgent
    assert mem20gamez.PPOAgent is PPOAgent
    assert mem20gamez.SACAgent is SACAgent
    assert not hasattr(mem20gamez, "MockEnvironment")


def test_tiny_gridworld_reaches_goal_with_real_transition() -> None:
    env = TinyGridWorld(EnvConfig(grid_size=2, max_grid_size=2, max_episode_steps=10))
    observation, info = env.reset(seed=11)
    assert observation.shape == (5,)
    assert info == {"pos": (0, 0), "grid_size": 2}

    first = env.step(1)
    second = env.step(3)
    assert first.info == {"pos": (1, 0), "grid_size": 2, "goal_reached": False, "hit_wall": False}
    assert second.terminated is True
    assert second.truncated is False
    assert second.reward == pytest.approx(9.99)
    assert second.info["goal_reached"] is True


def test_unknown_environment_fails_instead_of_returning_fake_random_environment() -> None:
    with pytest.raises(RuntimeError, match="environment"):
        create_environment(EnvConfig(env_id="Not-A-Real-Environment-v0"))


def test_potential_shaper_preserves_base_reward_and_uses_exact_ng_bonus() -> None:
    shaper = PotentialBasedShaper(
        RewardConfig(shaping_type="potential", gamma=0.9, scale=2.0),
        lambda state: float(state[0]),
    )
    shaped = shaper.shape(
        reward=2.0,
        state=np.asarray([3.0]),
        action=0,
        next_state=np.asarray([5.0]),
        done=False,
        info={},
    )
    assert shaped == pytest.approx(2.0 + 2.0 * (0.9 * 5.0 - 3.0))


def test_potential_shaper_forces_zero_terminal_potential() -> None:
    shaper = PotentialBasedShaper(
        RewardConfig(gamma=0.9),
        lambda state: float(state[0]),
    )
    shaped = shaper.shape(
        reward=1.0,
        state=np.asarray([4.0]),
        action=0,
        next_state=np.asarray([100.0]),
        done=True,
        info={},
    )
    assert shaped == pytest.approx(-3.0)


def test_discounted_potential_bonus_telescopes_to_minus_initial_potential() -> None:
    gamma = 0.9
    shaper = PotentialBasedShaper(RewardConfig(gamma=gamma), lambda state: float(state[0]))
    states = [np.asarray([value], dtype=np.float32) for value in (4.0, 3.0, 1.0, 0.0)]
    rewards = (0.5, -0.25, 2.0)
    done_flags = (False, False, True)
    discounted_bonus = 0.0
    for index, (reward, done) in enumerate(zip(rewards, done_flags)):
        shaped = shaper.shape(
            reward=reward,
            state=states[index],
            action=0,
            next_state=states[index + 1],
            done=done,
            info={},
        )
        discounted_bonus += (gamma**index) * (shaped - reward)
    assert discounted_bonus == pytest.approx(-4.0)


def test_potential_shaper_rejects_clipping_because_it_breaks_the_pb_rs_invariant() -> None:
    with pytest.raises(ValueError, match="clip"):
        PotentialBasedShaper(
            RewardConfig(clip=(-1.0, 1.0)),
            lambda state: float(state[0]),
        )


def test_stack_batch_has_exact_shapes_and_terminal_masks() -> None:
    batch = [make_experience(0.0, truncated=True), make_experience(1.0, done=True)]
    stacked = stack_batch(batch)
    assert stacked["states"].shape == (2, 2)
    assert stacked["next_states"].shape == (2, 2)
    assert stacked["actions"].shape == (2,)
    assert stacked["rewards"].shape == (2,)
    assert stacked["dones"].shape == (2,)
    assert stacked["truncateds"].shape == (2,)
    assert stacked["states"].dtype == np.float32
    assert stacked["actions"].dtype == np.int64
    np.testing.assert_array_equal(stacked["dones"], np.asarray([0.0, 1.0], dtype=np.float32))
    np.testing.assert_array_equal(stacked["truncateds"], np.asarray([1.0, 0.0], dtype=np.float32))


def test_stack_batch_rejects_mismatched_state_shapes() -> None:
    first = make_experience()
    second = make_experience()
    second.next_state = np.zeros(3, dtype=np.float32)
    with pytest.raises(ValueError, match="shape"):
        stack_batch([first, second])


def test_replay_buffer_is_an_exact_ring_buffer() -> None:
    buffer = ReplayBuffer(capacity=3, seed=5)
    for value in range(5):
        buffer.add(make_experience(float(value)))
    assert len(buffer) == 3
    np.testing.assert_array_equal(
        np.asarray([experience.state[0] for experience in buffer]),
        np.asarray([2.0, 3.0, 4.0], dtype=np.float32),
    )
    assert buffer.pos == 2


def test_replay_sampling_is_reproducible_and_exactly_sized() -> None:
    def populated(seed: int) -> ReplayBuffer:
        replay = ReplayBuffer(capacity=100, seed=seed)
        for value in range(50):
            replay.add(make_experience(float(value)))
        return replay

    first_batch, first_indices, first_weights = populated(19).sample(12)
    second_batch, second_indices, second_weights = populated(19).sample(12)
    assert len(first_batch) == len(second_batch) == 12
    np.testing.assert_array_equal(first_indices, second_indices)
    np.testing.assert_allclose(first_weights, second_weights)
    assert first_weights.max() == pytest.approx(1.0)
    assert np.isfinite(first_weights).all()


def test_replay_requesting_more_than_available_is_rejected() -> None:
    buffer = ReplayBuffer(capacity=4)
    buffer.add(make_experience())
    with pytest.raises(ValueError, match="requested batch"):
        buffer.sample(2)


def test_proportional_replay_sampling_prefers_high_priority_transition() -> None:
    buffer = ReplayBuffer(capacity=100, alpha=1.0, seed=3)
    for value in range(50):
        buffer.add(make_experience(float(value)))
    buffer.update_priorities([0], np.asarray([1_000_000.0]))
    sampled, indices, weights = buffer.sample(30)
    assert len(sampled) == 30
    assert np.count_nonzero(indices == 0) == 1
    assert weights.shape == (30,)
    assert buffer.priorities[0] > buffer.priorities[1]


def test_replay_normalizes_truncation_separately_from_termination() -> None:
    replay = ReplayBuffer(capacity=2)
    replay.add({"state": [0, 0], "action": 1, "reward": 2, "next_state": [1, 0], "truncated": True})
    stored = next(iter(replay))
    assert stored.done is False
    assert stored.truncated is True


def test_dqn_update_changes_real_network_parameters() -> None:
    torch.manual_seed(23)
    agent = DQNAgent(make_dqn_config(obs_shape=(2,)))
    before = deepcopy(agent.q_network.state_dict())
    metrics = agent.learn([make_experience(float(index), action=index % 4) for index in range(8)])
    assert metrics["loss"] > 0.0
    assert any(
        not torch.equal(before[name], agent.q_network.state_dict()[name])
        for name in before
    )


def test_dqn_bootstraps_truncation_but_not_termination() -> None:
    torch.manual_seed(29)
    agent = DQNAgent(make_dqn_config(obs_shape=(2,), batch_size=2))
    for parameter in agent.q_network.parameters():
        torch.nn.init.zeros_(parameter)
    for parameter in agent.target_network.parameters():
        torch.nn.init.zeros_(parameter)
    with torch.no_grad():
        agent.target_network.mlp[-1].bias[0] = 10.0
    metrics = agent.learn([make_experience(truncated=True), make_experience(done=True)])
    assert metrics["td_errors"] == pytest.approx(5.75, rel=1e-4)


def test_adaptive_curriculum_waits_for_a_complete_performance_window() -> None:
    curriculum = create_curriculum(
        CurriculumConfig(
            curriculum_type=CurriculumType.ADAPTIVE,
            start_difficulty=0.0,
            end_difficulty=1.0,
            step_size=0.25,
            threshold=0.8,
            regress_threshold=0.1,
            window_size=3,
        )
    )
    assert isinstance(curriculum, AdaptiveCurriculum)
    curriculum.update(0.9)
    curriculum.update(0.9)
    assert curriculum.get_difficulty() == 0.0
    curriculum.update(0.9)
    assert curriculum.get_difficulty() == 0.25
    curriculum.update(0.9)
    curriculum.update(0.9)
    assert curriculum.get_difficulty() == 0.25
    curriculum.update(0.9)
    assert curriculum.get_difficulty() == 0.5


def test_curriculum_is_gated_by_actual_gridworld_successes_and_keeps_observation_shape() -> None:
    curriculum = create_curriculum(
        CurriculumConfig(
            curriculum_type=CurriculumType.ADAPTIVE,
            start_difficulty=0.0,
            end_difficulty=1.0,
            step_size=0.5,
            threshold=0.8,
            regress_threshold=0.1,
            window_size=2,
        )
    )
    env_config = EnvConfig(grid_size=2, max_grid_size=3, max_episode_steps=10)
    trainer = DQNTrainer(
        env_config=env_config,
        agent_config=AgentConfig(agent_type=AgentType.RULE_BASED),
        curriculum=curriculum,
        seed=13,
    )
    history = trainer.train(episodes=2, log_every=0)
    assert history[0]["difficulty"] == 0.0
    assert history[1]["difficulty"] == 0.5
    assert all(performance > 0.8 for performance in curriculum.performance_history)
    staged_env = trainer._make_env()
    assert staged_env.grid_size == 3
    assert staged_env.obs_shape == (10,)
    staged_env.close()


def test_curriculum_regresses_after_actual_failed_episodes() -> None:
    curriculum = create_curriculum(
        CurriculumConfig(
            curriculum_type=CurriculumType.ADAPTIVE,
            start_difficulty=0.0,
            end_difficulty=1.0,
            step_size=0.5,
            threshold=0.8,
            regress_threshold=0.1,
            window_size=2,
        )
    )
    curriculum.current_difficulty = 1.0
    trainer = DQNTrainer(
        env_config=EnvConfig(grid_size=8, max_grid_size=8, max_episode_steps=1),
        agent_config=AgentConfig(agent_type=AgentType.RULE_BASED),
        curriculum=curriculum,
        seed=17,
    )
    history = trainer.train(episodes=2, log_every=0)
    assert all(performance < 0.1 for performance in curriculum.performance_history)
    assert history[-1]["difficulty"] == 0.5


def test_dqn_trainer_learns_tiny_gridworld_in_a_short_run() -> None:
    trainer = DQNTrainer(
        env_config=EnvConfig(grid_size=3, max_grid_size=3, max_episode_steps=12),
        agent_config=make_dqn_config(),
        reward_shaper=default_reward_shaper(gamma=0.95),
        seed=7,
    )
    before = trainer.evaluate(episodes=8, seed=500)
    history = trainer.train(episodes=45, update_every=1, log_every=0)
    after = trainer.evaluate(episodes=12, seed=700)

    first_rewards = [entry["reward"] for entry in history[:10]]
    last_rewards = [entry["reward"] for entry in history[-10:]]
    first_losses = [entry["loss"] for entry in history[4:14] if entry["loss"] > 0.0]
    last_losses = [entry["loss"] for entry in history[-10:] if entry["loss"] > 0.0]

    assert before["success_rate"] == 0.0
    assert after["success_rate"] >= 0.9
    assert after["mean_reward"] > before["mean_reward"] + 5.0
    assert mean(last_rewards) > mean(first_rewards) + 3.0
    assert mean(last_losses) < mean(first_losses)
    assert any(entry["buffer"] >= 32 for entry in history)


def test_multi_agent_dqn_keeps_separate_experience_and_updates_every_agent() -> None:
    torch.manual_seed(31)
    trainer = MultiAgentTrainer(
        n_agents=2,
        env_config=EnvConfig(grid_size=2, max_grid_size=2, max_episode_steps=5),
        agent_config=make_dqn_config(
            obs_shape=(5,),
            hidden_size=16,
            learning_rate=0.02,
            batch_size=8,
            epsilon_decay=0.85,
            tau=0.1,
        ),
        reward_shaper_factory=lambda index: default_reward_shaper(gamma=0.95),
        seed=31,
    )
    before_evaluations = trainer.evaluate(episodes=6, seed=800)
    initial_parameters = [deepcopy(agent.q_network.state_dict()) for agent in trainer.agents]
    histories = trainer.train(episodes=35, update_every=1)
    after_evaluations = trainer.evaluate(episodes=8, seed=900)
    trainer.close()

    assert trainer.agents[0].buffer is not trainer.agents[1].buffer
    assert trainer.agents[0].q_network is not trainer.agents[1].q_network
    for index, agent in enumerate(trainer.agents):
        history = histories[f"agent_{index}"]
        assert len(history) == 35
        assert len(agent.buffer) > 0
        assert agent.step_count > 0
        assert any(entry["loss"] > 0.0 for entry in history)
        assert any(
            not torch.equal(initial_parameters[index][name], agent.q_network.state_dict()[name])
            for name in initial_parameters[index]
        )
        assert after_evaluations[f"agent_{index}"]["success_rate"] >= 0.8
        assert (
            after_evaluations[f"agent_{index}"]["mean_reward"]
            > before_evaluations[f"agent_{index}"]["mean_reward"] + 4.0
        )


def test_policy_gradient_agents_perform_real_gradient_updates() -> None:
    transitions = [
        make_experience(0.0, action=0, reward=1.0, done=False),
        make_experience(1.0, action=1, reward=2.0, done=True),
    ]
    for agent_type, agent_class in (
        (AgentType.REINFORCE, REINFORCEAgent),
        (AgentType.PPO, PPOAgent),
        (AgentType.SAC, SACAgent),
    ):
        torch.manual_seed(37)
        config = make_dqn_config(agent_type=agent_type, obs_shape=(2,), hidden_size=16, batch_size=2)
        agent = create_agent(config)
        assert isinstance(agent, agent_class)
        metrics = agent.learn(deepcopy(transitions))
        assert metrics
        assert all(np.isfinite(value) for value in metrics.values())


def test_non_learning_agents_do_not_fake_checkpoint_io() -> None:
    config = AgentConfig(agent_type=AgentType.RANDOM)
    for agent in (RandomAgent(config), RuleBasedAgent(config)):
        with pytest.raises(NotImplementedError):
            agent.save("unused")
        with pytest.raises(NotImplementedError):
            agent.load("unused")


def test_live_http_app_health_reset_step_and_learn_contract() -> None:
    from aiohttp.test_utils import TestClient, TestServer

    async def exercise() -> None:
        live = _LiveServer("TinyGridWorld-v0", "dqn", seed=43).setup()
        client = TestClient(TestServer(create_app(live)))
        await client.start_server()
        try:
            health = await (await client.get("/health")).json()
            assert health["ok"] is True
            assert health["agent"] == "dqn"
            reset = await (await client.get("/reset")).json()
            assert len(reset["obs"]) == 17
            stepped = await (await client.post("/step", json={"training": True})).json()
            assert stepped["total_steps"] == 1
            assert len(live.agent.buffer) == 1
            learned = await (await client.post("/learn", json={})).json()
            assert learned["updated"] is False
            assert learned["buffer_size"] == 1
        finally:
            await client.close()

    asyncio.run(exercise())


def test_cli_subsystem_check_runs_with_its_default_agent(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["test"]) == 0
    assert "All subsystems OK" in capsys.readouterr().out


def test_cli_train_reports_real_before_after_and_loss_windows(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(
        [
            "train",
            "--env",
            "TinyGridWorld-v0",
            "--agent",
            "dqn",
            "--grid-size",
            "3",
            "--episodes",
            "15",
            "--eval-episodes",
            "3",
            "--batch-size",
            "8",
            "--update-every",
            "1",
            "--shape",
        ]
    )
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "before" in output.lower()
    assert "after" in output.lower()
    assert "first_window_loss" in output
    assert "last_window_loss" in output
    assert "first_window_reward" in output
    assert "last_window_reward" in output


def test_dqn_checkpoint_roundtrip_preserves_greedy_policy(tmp_path: Path) -> None:
    torch.manual_seed(41)
    agent = DQNAgent(make_dqn_config(obs_shape=(5,)))
    states = [np.eye(5, dtype=np.float32)[index] for index in range(5)]
    expected = [agent.greedy_action(state) for state in states]
    checkpoint = tmp_path / "dqn.pt"
    assert agent.save(str(checkpoint)) is True

    restored = DQNAgent(make_dqn_config(obs_shape=(5,)))
    assert restored.load(str(checkpoint)) is True
    assert [restored.greedy_action(state) for state in states] == expected
