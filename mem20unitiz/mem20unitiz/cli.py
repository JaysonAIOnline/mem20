"""Command-line training and environment inspection for mem20unitiz."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .buffer import Buffer
from .environment import CooperativeGridWorld, GridWorld
from .policy import create_policy
from .settings import TrainerType, get_default_settings
from .trainer import POCATrainer, create_trainer

import functools

try:
    from mem20cliz import json_main
except ImportError as _exc:  # never fail silently: a hidden fallback looks like success
    import sys as _sys

    def json_main(func):
        @functools.wraps(func)
        def _warn(*a, **k):
            _sys.stderr.write(
                "warning: mem20cliz unavailable, --json disabled for this CLI (%s)\n" % _exc
            )
            return func(*a, **k)

        return _warn


def _configure_settings(args: argparse.Namespace) -> Any:
    settings = get_default_settings(TrainerType(args.trainer))
    settings.max_steps = args.max_steps
    settings.batch_size = min(args.batch_size, max(1, args.rollout_size))
    settings.buffer_size = max(settings.buffer_size, args.rollout_size * 4)
    if args.learning_rate is not None:
        settings.learning_rate = args.learning_rate
    settings.num_epochs = args.epochs
    settings.time_horizon = args.rollout_size
    settings.network_settings.hidden_units = args.hidden_units
    settings.network_settings.num_layers = args.num_layers
    settings.network_settings.learning_rate = settings.learning_rate
    settings.seed = args.seed
    return settings


def _make_environment(args: argparse.Namespace) -> Any:
    if args.trainer == "poca":
        return CooperativeGridWorld(
            behavior_names=["agent_0", "agent_1"],
            grid_size=args.grid_size,
            max_steps=args.max_steps,
            seed=args.seed,
        )
    return GridWorld(
        behavior_name=args.behavior,
        grid_size=args.grid_size,
        discrete=args.trainer != "sac",
        max_steps=args.max_steps,
        seed=args.seed,
        goal=(args.goal_x, args.goal_y),
    )


def _make_trainer(args: argparse.Namespace, environment: Any, settings: Any) -> Any:
    if args.trainer == "poca":
        return POCATrainer(
            environment.behavior_specs,
            settings,
            buffer_size=max(settings.buffer_size, args.rollout_size * 4),
            batch_size=settings.batch_size,
            num_epochs=settings.num_epochs,
            seed=args.seed,
        )
    name = args.behavior
    spec = environment.behavior_specs[name]
    buffer = Buffer(
        buffer_size=max(settings.buffer_size, args.rollout_size * 4),
        observation_shape=spec.observation_shapes[0],
        action_shape=(spec.action_spec.continuous_size,) if spec.is_action_continuous else (1,),
        seed=args.seed,
    )
    return create_trainer(
        name,
        spec,
        settings,
        policy=None,
        buffer=buffer,
        seed=args.seed,
    )


def _cmd_train(args: argparse.Namespace) -> int:
    environment = _make_environment(args)
    settings = _configure_settings(args)
    trainer = _make_trainer(args, environment, settings)
    updates = trainer.fit(environment, args.max_steps, args.rollout_size)
    result = {
        "trainer": args.trainer,
        "steps": trainer.metrics.step,
        "episodes": trainer.metrics.episodes,
        "updates": len(updates),
        "mean_reward": trainer.metrics.mean_reward,
        "mean_episode_length": trainer.metrics.mean_episode_length,
        "loss_curve": [float(item.get("total_loss", item.get("critic_loss", item.get("q_loss", 0.0)))) for item in updates],
    }
    if args.save_dir:
        checkpoint_root = Path(args.save_dir)
        if args.trainer == "poca":
            trainer.save(str(checkpoint_root / "poca"))
        else:
            trainer.save(str(checkpoint_root / args.trainer))
        result["checkpoint_dir"] = str(checkpoint_root)
    print(json.dumps(result, sort_keys=True))
    return 0


def _cmd_test(args: argparse.Namespace) -> int:
    environment = GridWorld(
        behavior_name="grid",
        grid_size=4,
        discrete=True,
        max_steps=16,
        seed=args.seed,
    )
    spec = environment.behavior_specs["grid"]
    policy = create_policy(
        spec.observation_shapes[0],
        spec.action_spec,
        {"hidden_units": 8, "num_layers": 1},
        continuous=False,
        seed=args.seed,
    )
    infos = environment.reset()
    total_reward = 0.0
    transitions = 0
    final_position = environment.position
    for _ in range(environment.max_steps):
        observation = infos["grid"].observations[0]
        output = policy.act(observation)
        step_output = environment.step({"grid": output.action})
        info = step_output.agent_info["grid"]
        total_reward += info.reward
        transitions += 1
        infos = {"grid": info}
        final_position = environment.position
        if info.done:
            break
    print(
        json.dumps(
            {
                "transitions": transitions,
                "total_reward": total_reward,
                "final_position": list(final_position),
                "done": infos["grid"].done,
            },
            sort_keys=True,
        )
    )
    return 0


def _cmd_demo(args: argparse.Namespace) -> int:
    environment = CooperativeGridWorld(grid_size=3, max_steps=16, seed=args.seed)
    settings = get_default_settings(TrainerType.POCA)
    settings.batch_size = min(settings.batch_size, 16)
    settings.time_horizon = 16
    trainer = POCATrainer(environment.behavior_specs, settings, buffer_size=64, batch_size=16, num_epochs=1, seed=args.seed)
    infos = environment.reset()
    total_reward = 0.0
    transitions = 0
    for _ in range(environment.max_steps):
        actions = {}
        outputs = {}
        for name in environment.behavior_specs:
            output = trainer.policies[name].act(infos[name].observations[0])
            outputs[name] = output
            actions[name] = output.action
        step_output = environment.step(actions)
        infos = step_output.agent_info
        for name in environment.behavior_specs:
            total_reward += infos[name].reward / len(environment.behavior_specs)
        transitions += 1
        if any(info.done for info in infos.values()):
            break
    print(json.dumps({"transitions": transitions, "mean_team_reward": total_reward / max(1, transitions)}, sort_keys=True))
    return 0


@json_main
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mem20unitiz", description="Real reinforcement-learning training")
    subparsers = parser.add_subparsers(dest="command", required=True)

    train = subparsers.add_parser("train", help="Train a real environment")
    train.add_argument("--trainer", choices=["ppo", "dqn", "sac", "poca"], default="ppo")
    train.add_argument("--behavior", default="grid")
    train.add_argument("--grid-size", type=int, default=3)
    train.add_argument("--goal-x", type=int, default=2)
    train.add_argument("--goal-y", type=int, default=2)
    train.add_argument("--max-steps", type=int, default=256)
    train.add_argument("--rollout-size", type=int, default=64)
    train.add_argument("--batch-size", type=int, default=32)
    train.add_argument("--epochs", type=int, default=2)
    train.add_argument("--hidden-units", type=int, default=16)
    train.add_argument("--num-layers", type=int, default=1)
    train.add_argument("--learning-rate", type=float, default=None)
    train.add_argument("--seed", type=int, default=42)
    train.add_argument("--save-dir", default="")
    train.set_defaults(func=_cmd_train)

    test = subparsers.add_parser("test", help="Run a real environment smoke episode")
    test.add_argument("--seed", type=int, default=42)
    test.set_defaults(func=_cmd_test)

    demo = subparsers.add_parser("demo", help="Run a real cooperative environment episode")
    demo.add_argument("--seed", type=int, default=42)
    demo.set_defaults(func=_cmd_demo)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
