# mem20gamez

`mem20gamez` is mem20's native OpenGame-style reinforcement-learning package. It
contains executable torch agents, a deterministic in-package environment,
potential-based reward shaping, performance-gated curriculum, prioritized
replay, independent multi-agent DQN training, and an optional live HTTP server.

No pretrained model, canned learning curve, random fallback environment, or
mock learning loop is used.

## Verified capabilities

| Area | Implemented behavior |
|---|---|
| `environment.py` | `TinyGridWorld-v0` uses a fixed-size one-hot canvas, active-grid difficulty, deterministic movement, optional wind, wall/step penalties, and separate termination/truncation signals. `GymnasiumEnvironment` is a strict optional wrapper; unknown environments fail instead of falling back to synthetic behavior. |
| `reward_shaper.py` | `PotentialBasedShaper` implements `F = scale * (gamma * Phi(s') - Phi(s))`, forces terminal potential to zero, preserves the original reward, and rejects clipping that would break policy invariance. |
| `curriculum.py` | Adaptive difficulty advances or regresses from measured grid progress. It acts once per complete performance window and clamps difficulty to configured bounds. The fixed observation canvas keeps replay and network shapes compatible across stages. |
| `replay_buffer.py` | A deterministic circular prioritized replay with exact-capacity eviction, proportional sampling, annealed importance weights, TD-error priority updates, explicit exact-size batches, and shape-checked NumPy outputs. |
| `agents.py` | Double DQN with a target network, prioritized replay, optional dueling head, hard or Polyak target synchronization, plus REINFORCE, clipped PPO, and discrete SAC gradient implementations. |
| `trainer.py` | Single-agent rollout/evaluation loops and interleaved multi-agent DQN. Every multi-agent instance has its own environment, network, optimizer, target network, and replay buffer. |
| `cli.py` | Training, evaluation, multi-agent training, checkpointing, subsystem checks, and an aiohttp server exposing `/health`, `/reset`, `/act`, `/step`, and `/learn`. |

The behavioral suite proves finite real gradient updates for REINFORCE, PPO, and
SAC. The task-mastery learning assertion and the measured proof below use DQN,
which is the package's fully exercised short-run benchmark.

## Measured DQN proof

Command:

```bash
mem20gamez train \
  --agent dqn \
  --env TinyGridWorld-v0 \
  --grid-size 4 \
  --episodes 80 \
  --eval-episodes 20 \
  --batch-size 32 \
  --update-every 1 \
  --lr 0.01 \
  --gamma 0.99 \
  --shape \
  --seed 7
```

Observed on the root venv with `torch 2.14.0+cpu`:

```text
before_mean_reward -9.730  before_success_rate 0.000
after_mean_reward   9.940  after_success_rate  1.000
first_window_reward 9.576  last_window_reward 9.928
first_window_loss   0.069549  last_window_loss 0.036290
elapsed=6.20 sec
```

Those values come from the run itself. The agent learns the six-step optimal
route on the deterministic 4×4 grid: goal reward `10.0` plus six step penalties
`-0.01` equals `9.94`.

A separate two-agent 2×2 run moved each agent from mean reward `-9.91` to
`9.98`, with greedy success rate `1.00`, in `4.97 sec`.

A 40-episode curriculum run measured the expected 10-episode gates on the 4×4
canvas: difficulty `0.25`, `0.50`, `0.75`, then `1.00` at episodes 10, 20, 30,
and 40. Runtime was `2.19 sec`.

## Install

The runtime requires Python 3.11+, NumPy, torch, PyYAML, and aiohttp.

```bash
cd /opt/mem20/mem20gamez
/root/.venv/bin/python -m pip install -e .
/root/.venv/bin/python -m pip install -e ".[dev]"
```

Install Gymnasium only when external Gym environments are needed:

```bash
/root/.venv/bin/python -m pip install -e ".[gym]"
```

`TinyGridWorld-v0` needs no external environment package.

## Commands

```bash
# Measured 4x4 DQN run
mem20gamez train --agent dqn --env TinyGridWorld-v0 --grid-size 4 \
  --episodes 80 --eval-episodes 20 --batch-size 32 --update-every 1 \
  --lr 0.01 --gamma 0.99 --shape --seed 7

# Save a trained DQN checkpoint
mem20gamez train --agent dqn --shape --checkpoint /tmp/mem20gamez-dqn.pt

# Independent, interleaved DQN agents
mem20gamez multi --agents 2 --grid-size 2 --episodes 35 \
  --batch-size 8 --update-every 1 --lr 0.02 --gamma 0.95 --shape --seed 31

# Live DQN process
mem20gamez serve --env TinyGridWorld-v0 --agent dqn --host 127.0.0.1 --port 8007

# Fast subsystem contract check
mem20gamez test
```

The packaged server is persisted as `mem20gamez.service`, enabled and started
with systemd, so it survives reboot rather than running as a floating process.

## Verification

```bash
cd /opt/mem20/mem20gamez
/root/.venv/bin/python -m pytest -q
/root/.venv/bin/python -m ruff check .
```

Current result: `29 passed`, and Ruff reports `All checks passed!`.
