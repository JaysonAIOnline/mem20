"""mem20gamez CLI — real training, serving, and demonstration entry points."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import numpy as np

from .agent import AgentConfig, AgentType
from .config import GameConfig
from .curriculum import CurriculumConfig, CurriculumType, create_curriculum
from .environment import EnvConfig, create_environment
from .reward_shaper import RewardConfig, create_shaper
from .trainer import DQNTrainer, MultiAgentTrainer, default_reward_shaper

import functools

try:
    from mem20cliz import json_main
except ImportError as _exc:  # never fail silently: a hidden fallback looks like success
    import sys as _sys

    # Python deletes the `except ... as _exc` binding when the block ends, so the
    # message has to be captured now. Referencing _exc later raised NameError the
    # first time anyone actually used --json without mem20cliz installed.
    _MEM20CLIZ_MISSING = str(_exc)

    def json_main(func):
        @functools.wraps(func)
        def _warn(*a, **k):
            _sys.stderr.write(
                "warning: mem20cliz unavailable, --json disabled for this CLI (%s)\n"
                % _MEM20CLIZ_MISSING
            )
            return func(*a, **k)

        return _warn

_AGENT_CHOICES = [a.value for a in AgentType]

_AGENT_TYPE = {a.value: a for a in AgentType}


def _parse_env_config(env_name: str, max_steps: int, grid_size: int) -> EnvConfig:
    cfg = EnvConfig(env_id=env_name, max_episode_steps=max_steps)
    if env_name == "TinyGridWorld-v0":
        cfg.grid_size = grid_size
    return cfg


def _window_metrics(history: list[dict[str, float]]) -> dict[str, float]:
    if not history:
        return {
            "first_window_reward": 0.0,
            "last_window_reward": 0.0,
            "first_window_loss": 0.0,
            "last_window_loss": 0.0,
        }
    window_size = max(1, min(10, len(history) // 3))
    first = history[:window_size]
    last = history[-window_size:]
    first_losses = [entry["loss"] for entry in first if entry["loss"] > 0.0]
    last_losses = [entry["loss"] for entry in last if entry["loss"] > 0.0]
    return {
        "first_window_reward": float(np.mean([entry["reward"] for entry in first])),
        "last_window_reward": float(np.mean([entry["reward"] for entry in last])),
        "first_window_loss": float(np.mean(first_losses)) if first_losses else 0.0,
        "last_window_loss": float(np.mean(last_losses)) if last_losses else 0.0,
    }


def _cmd_train(args) -> int:
    """Train an agent and print measured before/after and learning-window metrics."""
    env_config = _parse_env_config(args.env, args.max_steps, args.grid_size)
    agent_config = AgentConfig(
        agent_type=_AGENT_TYPE[args.agent],
        learning_rate=args.lr,
        gamma=args.gamma,
        batch_size=args.batch_size,
        buffer_size=args.buffer_size,
        seed=args.seed,
    )
    shaper = default_reward_shaper(gamma=args.gamma) if args.shape else None
    curriculum = (
        create_curriculum(
            CurriculumConfig(
                curriculum_type=CurriculumType.ADAPTIVE,
                start_difficulty=0.0,
                end_difficulty=1.0,
                step_size=0.25,
                threshold=0.6,
                regress_threshold=0.1,
                window_size=10,
                seed=args.seed,
            )
        )
        if args.curriculum
        else None
    )
    trainer = DQNTrainer(
        env_config=env_config,
        agent_config=agent_config,
        reward_shaper=shaper,
        curriculum=curriculum,
        seed=args.seed,
    )
    before = trainer.evaluate(episodes=args.eval_episodes)
    history = trainer.train(episodes=args.episodes, update_every=args.update_every)
    after = trainer.evaluate(episodes=args.eval_episodes)
    windows = _window_metrics(history)

    print("\nMeasured learning evidence:")
    print(
        f"  before_mean_reward {before['mean_reward']:.3f}  "
        f"before_success_rate {before['success_rate']:.3f}"
    )
    print(
        f"  after_mean_reward  {after['mean_reward']:.3f}  "
        f"after_success_rate  {after['success_rate']:.3f}"
    )
    print(
        f"  first_window_reward {windows['first_window_reward']:.3f}  "
        f"last_window_reward {windows['last_window_reward']:.3f}"
    )
    print(
        f"  first_window_loss {windows['first_window_loss']:.6f}  "
        f"last_window_loss {windows['last_window_loss']:.6f}"
    )
    if args.checkpoint:
        trainer.agent.save(args.checkpoint)
        print(f"  checkpoint_saved {args.checkpoint}")
    return 0


def _cmd_multi(args) -> int:
    """Interleave several agents, one real value stream per agent."""
    env_config = _parse_env_config(args.env, args.max_steps, args.grid_size)
    base_cfg = AgentConfig(
        agent_type=_AGENT_TYPE[args.agent],
        learning_rate=args.lr,
        gamma=args.gamma,
        batch_size=args.batch_size,
        seed=args.seed,
    )

    def shaper_factory(i: int):
        if not args.shape:
            return None
        return default_reward_shaper(gamma=args.gamma)

    trainer = MultiAgentTrainer(
        n_agents=args.agents,
        env_config=env_config,
        agent_config=base_cfg,
        reward_shaper_factory=shaper_factory if args.shape else None,
        seed=args.seed,
    )
    before = trainer.evaluate(episodes=5, seed=args.seed + 1000)
    histories = trainer.train(episodes=args.episodes, update_every=args.update_every)
    after = trainer.evaluate(episodes=5, seed=args.seed + 2000)
    trainer.close()

    for name, history in sorted(histories.items()):
        windows = _window_metrics(history)
        print(
            f"{name:8s} before_mean {before[name]['mean_reward']:7.2f}  "
            f"after_mean {after[name]['mean_reward']:7.2f}  "
            f"success {after[name]['success_rate']:.2f}  "
            f"loss {windows['first_window_loss']:.4f}->{windows['last_window_loss']:.4f}"
        )
    return 0


class _LiveServer:
    """A real aiohttp server that holds a live agent and its environment."""

    def __init__(self, env_name: str, agent_name: str, seed: int = 0):
        if _AGENT_TYPE[agent_name] != AgentType.DQN:
            raise ValueError("serve supports the step-based DQN agent only")
        self.env_config = EnvConfig(env_id=env_name, max_episode_steps=200)
        self.agent_config = AgentConfig(agent_type=_AGENT_TYPE[agent_name], seed=seed)
        self.state: np.ndarray = np.zeros((1,), dtype=np.float32)
        self.episode_rewards: list[float] = []
        self.total_steps = 0
        self._reward_running = 0.0

    def setup(self):
        self.env = create_environment(self.env_config)
        self.trainer = DQNTrainer(
            env_config=self.env_config,
            agent_config=self.agent_config,
            reward_shaper=default_reward_shaper(gamma=self.agent_config.gamma),
            seed=self.agent_config.seed,
        )
        self.agent = self.trainer.agent
        shaper = self.trainer.reward_shaper
        if shaper is None:
            raise RuntimeError("live server reward shaper was not initialized")
        self.shaper = shaper
        return self

    def reset(self) -> dict[str, Any]:
        self._reward_running = 0.0
        self.shaper.reset()
        self.state, _ = self.env.reset(seed=self.agent_config.seed)
        return self._observe(0.0, False, {})

    def act(self, training: bool = False) -> dict[str, Any]:
        action = int(self.agent.act(self.state, training=training))
        return {"action": action, "steps": self.total_steps}

    def step(self, training: bool = True, learn: bool = True) -> dict[str, Any]:
        action = int(self.agent.act(self.state, training=training))
        result = self.env.step(action)
        done = bool(result.terminated or result.truncated)
        self._reward_running += float(result.reward)
        self.total_steps += 1

        shaped = self.shaper.shape(
            result.reward,
            self.state,
            action,
            result.observation,
            bool(result.terminated),
            result.info,
        )
        from .replay_buffer import Experience

        self.agent.remember(
            Experience(
                state=np.asarray(self.state, dtype=np.float32),
                action=action,
                reward=float(shaped),
                next_state=np.asarray(result.observation, dtype=np.float32),
                done=bool(result.terminated),
                info=dict(result.info),
                truncated=bool(result.truncated),
            )
        )
        metrics: dict[str, float] = {}
        buf = getattr(self.agent, "buffer", None)
        batch_size = getattr(self.agent.config, "batch_size", 64)
        if learn and buf is not None and len(buf) >= batch_size:
            m = self.agent.replay()
            if m is not None:
                metrics = {"loss": m.get("loss", 0.0), "epsilon": m.get("epsilon", 0.0)}

        self.state = result.observation
        if done:
            self.agent.end_episode()
            self.episode_rewards.append(self._reward_running)
            self._reward_running = 0.0
            self.shaper.reset()
            self.state, _ = self.env.reset(seed=self.agent_config.seed + len(self.episode_rewards))

        return self._observe(float(result.reward), done, metrics)

    def _observe(self, reward: float, done: bool, extra: dict[str, float]) -> dict[str, Any]:
        out: dict[str, Any] = {
            "obs": self.state.tolist() if self.state is not None else [],
            "reward": reward,
            "done": done,
            "episode": len(self.episode_rewards),
            "total_steps": self.total_steps,
            "episode_rewards": self.episode_rewards[-20:],
        }
        out.update(extra)
        return out

    def close(self) -> None:
        self.env.close()


def create_app(live: _LiveServer):
    """Build the aiohttp application that drives a live learning agent."""
    from aiohttp import web

    async def health(request):
        return web.json_response(
            {
                "ok": True,
                "env": live.env_config.env_id,
                "agent": live.agent_config.agent_type.value,
                "episodes": len(live.episode_rewards),
                "steps": live.total_steps,
            }
        )

    async def reset(request):
        return web.json_response(live.reset())

    async def act(request):
        data = await request.json() if request.can_read_body else {}
        return web.json_response(live.act(training=bool(data.get("training", False))))

    async def step(request):
        data = await request.json() if request.can_read_body else {}
        return web.json_response(live.step(training=bool(data.get("training", True)), learn=bool(data.get("learn", True))))

    async def learn(request):
        metrics = live.agent.replay()
        if metrics is None:
            buffer = getattr(live.agent, "buffer", None)
            return web.json_response(
                {
                    "updated": False,
                    "buffer_size": len(buffer) if buffer is not None else 0,
                    "required_batch_size": live.agent.config.batch_size,
                }
            )
        return web.json_response({"updated": True, **metrics})

    async def cleanup(_app):
        live.close()

    app = web.Application()
    app.on_cleanup.append(cleanup)
    app.router.add_get("/health", health)
    app.router.add_get("/reset", reset)
    app.router.add_post("/act", act)
    app.router.add_post("/step", step)
    app.router.add_post("/learn", learn)
    return app


def _cmd_serve(args) -> int:
    """Run a real HTTP server with a live, learning agent."""
    from aiohttp import web

    live = _LiveServer(args.env, args.agent, seed=args.seed).setup()
    app = create_app(live)

    print(f"mem20gamez serving {args.env}/{args.agent} on {args.host}:{args.port}")
    web.run_app(app, host=args.host, port=args.port)
    return 0


def _cmd_test(args) -> int:
    """Real end-to-end sanity check of every subsystem."""
    env = create_environment(EnvConfig(env_id="TinyGridWorld-v0", grid_size=4))
    obs, _ = env.reset(seed=42)
    print(f"env: {type(env).__name__}  obs={obs.shape}  actions={env.action_size}")

    agent = _AGENT_TYPE[args.agent]
    acfg = AgentConfig(agent_type=agent, obs_shape=env.obs_shape, action_size=env.action_size, batch_size=32)
    from .agent import create_agent

    ag = create_agent(acfg)
    a = ag.act(obs)
    print(f"agent: {agent.value}  action={a}  type={type(ag).__name__}")

    shaper = create_shaper(RewardConfig(shaping_type="potential"), potential_fn=lambda s: 0.0)
    shaped = shaper.shape(1.0, obs, a, obs, False, {})
    print(f"shaper: {type(shaper).__name__}  shaped={shaped:.2f}")

    cur = create_curriculum(CurriculumConfig(curriculum_type=CurriculumType.LINEAR))
    print(f"curriculum: {type(cur).__name__}  difficulty={cur.get_difficulty():.2f}")

    from .replay_buffer import ReplayBuffer

    buf = ReplayBuffer(capacity=1000)
    buf.add({"state": obs, "action": a, "reward": 1.0, "next_state": obs, "done": False})
    print(f"replay: {len(buf)} samples")
    env.close()
    print("All subsystems OK")
    return 0


def _cmd_demo(args) -> int:
    """Real interactive demo: train DQN with shaping, print the learning curve."""
    trainer = DQNTrainer(
        env_config=_parse_env_config("TinyGridWorld-v0", args.max_steps, args.grid_size),
        agent_config=AgentConfig(agent_type=AgentType.DQN, batch_size=args.batch_size, seed=args.seed),
        reward_shaper=default_reward_shaper(),
        seed=args.seed,
    )
    print(f"Training DQN on TinyGridWorld-v0 ({args.grid_size}x{args.grid_size}) with potential-based shaping")
    trainer.train(episodes=args.episodes, update_every=args.update_every, log_every=max(1, args.episodes // 5))
    ev = trainer.evaluate(episodes=args.eval_episodes)
    print(f"greedy policy: mean reward {ev['mean_reward']:.2f} over {int(ev['episodes'])} episodes")
    return 0


# ---------------------------------------------------------------------------
# build harness
# ---------------------------------------------------------------------------


def _cmd_build_harness(args) -> int:
    """`mem20gamez build-harness` — the swarm build pipeline."""
    import json as _json

    from .build_harness import surface

    if args.harness_cmd == "docs":
        from .build_harness import docs as harness_docs

        if args.format == "html":
            print(harness_docs.as_html())
        elif args.format == "json":
            print(_json.dumps(harness_docs.pointer(), indent=2))
        else:
            print(harness_docs.read())
        return 0

    if args.harness_cmd == "surface":
        info = surface()
        print(_json.dumps(info, indent=2))
        docs = info.get("docs") or {}
        if docs.get("exists"):
            print(f"\nguide: {docs['terminal']}  (or {docs['http']})", file=sys.stderr)
            print(f"law:   {docs['one_line']}", file=sys.stderr)
        return 0

    if args.harness_cmd == "serve":
        try:
            import uvicorn
        except ImportError:
            print("uvicorn is required for `build-harness serve`", file=sys.stderr)
            return 1
        from .build_harness.app import app
        uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)
        return 0

    if args.harness_cmd == "plan":
        # Plan-only: prove the pipeline is wired without spending a provider call.
        from .build_harness import runner as harness_runner
        project = _json.loads(Path(args.project).read_text()) if args.project else {}
        report = harness_runner.run_project(project, dry_run=True)
        print(_json.dumps(report, indent=2, default=str))
        return 0

    if args.harness_cmd == "run":
        from .build_harness import runner as harness_runner
        project = _json.loads(Path(args.project).read_text()) if args.project else {}
        report = harness_runner.run_project(
            project,
            dry_run=args.dry_run,
            phase_filter=args.phase or None,
            max_workers=args.max_workers,
        )
        print(_json.dumps(report, indent=2, default=str))
        return 0 if report.get("ok", True) else 1

    return 1


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mem20gamez", description="mem20 native OpenGame — real agents, envs, shaping")
    p.add_argument("--config", help="path to a YAML GameConfig")
    sub = p.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--env", default="TinyGridWorld-v0", help="TinyGridWorld-v0 or a gymnasium id like CartPole-v1")
    common.add_argument("--max-steps", type=int, default=100)
    common.add_argument("--seed", type=int, default=0)

    s = sub.add_parser("serve", help="Run a live HTTP server (learning agent)", parents=[common])
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8007)
    s.add_argument("--agent", choices=["dqn"], default="dqn")
    s.set_defaults(func=_cmd_serve)

    t = sub.add_parser("train", help="Train an agent and report real numbers", parents=[common])
    t.add_argument("--agent", choices=_AGENT_CHOICES, default="dqn")
    t.add_argument("--episodes", type=int, default=120)
    t.add_argument("--update-every", type=int, default=4)
    t.add_argument("--eval-episodes", type=int, default=20)
    t.add_argument("--batch-size", type=int, default=64)
    t.add_argument("--buffer-size", type=int, default=100000)
    t.add_argument("--lr", type=float, default=3e-4)
    t.add_argument("--gamma", type=float, default=0.99)
    t.add_argument("--grid-size", type=int, default=4)
    t.add_argument("--curriculum", action="store_true", help="gate env difficulty on real performance")
    t.add_argument("--shape", action="store_true", help="apply potential-based reward shaping")
    t.add_argument("--checkpoint", default="", help="path to save the trained network")
    t.set_defaults(func=_cmd_train)

    m = sub.add_parser("multi", help="Interleave several independent DQN agents", parents=[common])
    m.add_argument("--agent", choices=["dqn"], default="dqn")
    m.add_argument("--agents", type=int, default=3)
    m.add_argument("--episodes", type=int, default=60)
    m.add_argument("--update-every", type=int, default=4)
    m.add_argument("--batch-size", type=int, default=64)
    m.add_argument("--lr", type=float, default=3e-4)
    m.add_argument("--gamma", type=float, default=0.99)
    m.add_argument("--grid-size", type=int, default=4)
    m.add_argument("--shape", action="store_true")
    m.set_defaults(func=_cmd_multi)

    d = sub.add_parser("demo", help="Real interactive learning demo", parents=[common])
    d.add_argument("--episodes", type=int, default=120)
    d.add_argument("--update-every", type=int, default=4)
    d.add_argument("--eval-episodes", type=int, default=20)
    d.add_argument("--batch-size", type=int, default=64)
    d.add_argument("--grid-size", type=int, default=4)
    d.set_defaults(func=_cmd_demo)

    test_parser = sub.add_parser(
        "test",
        help="Run the subsystem contract check",
        parents=[common],
    )
    test_parser.add_argument("--agent", choices=_AGENT_CHOICES, default="dqn")
    test_parser.set_defaults(func=_cmd_test)

    b = sub.add_parser(
        "build-harness",
        help="Swarm build harness: Blender/Unity/Godot asset pipeline",
    )
    bsub = b.add_subparsers(dest="harness_cmd", required=True)

    bsub.add_parser("surface", help="what the harness can actually do right now")

    bd = bsub.add_parser("docs", help="the harness guide (how the harness works)")
    bd.add_argument("--format", choices=["markdown", "html", "json"], default="markdown")

    bs = bsub.add_parser("serve", help="run the harness control surface")
    bs.add_argument("--host", default="127.0.0.1")
    bs.add_argument("--port", type=int, default=8085)
    bs.add_argument("--log-level", default="info")

    bp = bsub.add_parser("plan", help="plan the pipeline without spending a provider call")
    bp.add_argument("--project", default="", help="path to a project JSON")

    br = bsub.add_parser("run", help="execute the pipeline")
    br.add_argument("--project", default="", help="path to a project JSON")
    br.add_argument("--dry-run", action="store_true")
    br.add_argument("--phase", default="", help="run only this phase")
    br.add_argument("--max-workers", type=int, default=None)
    b.set_defaults(func=_cmd_build_harness)
    return p



def _apply_config(args, argv: list[str]) -> None:
    if not getattr(args, "config", None):
        return
    config = GameConfig.load(args.config)
    explicit = {token for token in argv if token.startswith("--")}
    values = {
        "--host": ("host", config.host),
        "--port": ("port", config.port),
        "--env": ("env", config.default_env),
        "--max-steps": ("max_steps", config.max_episode_steps),
        "--batch-size": ("batch_size", config.batch_size),
        "--buffer-size": ("buffer_size", config.replay_buffer_size),
        "--lr": ("lr", config.lr),
        "--gamma": ("gamma", config.gamma),
    }
    for option, (attribute, value) in values.items():
        if option not in explicit and hasattr(args, attribute):
            setattr(args, attribute, value)


@json_main
def main(argv=None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    args = _build_parser().parse_args(arguments)
    _apply_config(args, arguments)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
