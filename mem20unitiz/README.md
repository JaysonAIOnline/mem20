# mem20unitiz

`mem20unitiz` is a small, real reinforcement-learning package for training compact agents in Python environments. Every trainer has a **Torch backend and a NumPy backend**; Torch is used when installed, and the NumPy backend remains fully functional without it. Both perform real parameter updates — no metric is hard-coded and no behavioural test uses a mock environment.

## Implemented and verified

- `PPOTrainer`: categorical or Gaussian actor, value network, clipped surrogate objective, GAE, entropy regularization, value loss, and real parameter updates.
- `DQNTrainer`: discrete Q-network, target network, epsilon-greedy exploration, TD targets, and prioritized experience replay. Backends: `TorchQNetwork` (autograd TD loss) or the NumPy `QNetwork` (hand-written backward pass).
- `SACTrainer`: tanh-squashed Gaussian actor, twin Q critics, target critics, learned entropy temperature, and soft target updates. Backends: `TorchSACPolicy` or the NumPy `SACPolicy`. Both use the exact tanh change-of-variables log-prob correction.
- `POCATrainer`: two independent cooperative actors with a shared centralized team critic.
- `GridWorld`: discrete or continuous navigation with bounded transitions, terminal states, goal rewards, and potential-based distance shaping.
- `CooperativeGridWorld`: two agents moving in lockstep and receiving one shared team reward.
- `SimpleEnvironment`: a small one-dimensional corridor used for fast real training and tests.
- `Buffer`: fixed-capacity ring storage with exact shapes, uniform sampling, prioritized sampling, importance weights, priority updates, and boundary-aware GAE.
- `ModelSaver`: real parameter checkpoints, not metadata. `.pt` for Torch `nn.Module` policies, `.npz` for policies whose `state_dict()` returns NumPy arrays (which includes `TorchQNetwork` and `TorchSACPolicy`, so they interoperate with a NumPy-only reader).

### Backend selection

`mem20unitiz.torch_policy` exposes the factories:

```python
create_q_network(...)     # TorchQNetwork when torch is present, else QNetwork
create_sac_policy(...)    # TorchSACPolicy when torch is present, else SACPolicy
```

Both accept `prefer_torch=False` to force the NumPy path, which is what makes the
suite runnable on a torch-less interpreter. The trainers call the factories, so
`DQN` and `SAC` get the Torch backend automatically and `PPO`/`POCA` are
unaffected.

The observable contract is identical across backends: NumPy in, NumPy out. No
caller has to know which is active.

Every trainer action is sampled from a real categorical, Gaussian, or epsilon-greedy distribution. Updates call the corresponding network parameter store; no metric is hard-coded and no mock environment is used by the behavioral suite.

## Install

From this directory:

```bash
python -m pip install -e .
```

The required runtime dependencies are NumPy and PyYAML. PyTorch is optional: the package detects it and uses the real Torch backend when available; the NumPy backend remains fully functional without it.

## Run

Train a real grid policy:

```bash
mem20unitiz train --trainer ppo --max-steps 256 --rollout-size 32 --batch-size 16
mem20unitiz train --trainer dqn --max-steps 256 --rollout-size 32 --batch-size 16
mem20unitiz train --trainer sac --max-steps 256 --rollout-size 32 --batch-size 16
mem20unitiz train --trainer poca --max-steps 128 --rollout-size 16 --batch-size 8
```

Run a real environment smoke episode or cooperative episode:

```bash
mem20unitiz test
mem20unitiz demo
```

The training command prints the actual update count, step count, mean episode reward, and measured loss curve as JSON. Supply `--save-dir` to write complete policy checkpoints.

## Verification

```bash
python -m pytest -q
ruff check .
```

The tests exercise real transitions, reward and termination behavior, buffer shapes and sampling, distribution probabilities, parameter changes, checkpoint round trips, and real PPO/DQN/SAC/cooperative updates. The PPO and DQN loss-decrease tests run on transitions collected from `SimpleEnvironment`; the environment and replay data are not mocked.

## Scope boundaries

This package does not currently provide a Unity Editor bridge, a distributed trainer, a curriculum scheduler, a visual-observation encoder, or a long-lived server. Those capabilities are intentionally not advertised until they are implemented and tested. The former no-op `serve` command was removed rather than presented as a service.
