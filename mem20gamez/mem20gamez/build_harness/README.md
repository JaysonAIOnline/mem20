# mem20gamez build harness

The **Lumen Forge** swarm build pipeline, now installed here as a permanent
subpackage of `mem20gamez`. It drives real game-asset production through Godot,
Blender and audio tooling, with AI vision and audio gates that decide what counts
as done.

Installed from the owner's `harness-src.zip`. The implementation modules are the
harness's own, kept intact so behaviour does not drift from what was tested.

---

## The one rule everything else follows

> **"If they don't see it with vision approval models, then how will Jayson see
> it when he plays?"**

Code that runs is **not** the game being playable. The proof is a real, in-engine
screenshot that an AI vision model looks at and describes back — and if that
description does not match what the production pack asked for, it is a **FAIL**,
even when the frame is real.

This is why the harness refuses to say "done" on the strength of files alone.

---

## The pipeline

```
ProjectProduction pack: goals, art style, naming law, asset list
        ↓
Phase start gate      vision & audio inspectors MUST be in the swarm
        ↓
Swarm runs            many workers in parallel, each with real tools
        ↓
Every gate            real render + vision-check and audio-check must PASS
        ↓
Ready                 handoff signed "Ready for integration: Yes"
```

Anything not ready — a fake or black frame, a naming violation, silent audio, a
tester's bug report — dispatches a **repair worker**: a *different* agent given a
surgical work order listing the exact machine-verified defects. It fixes only
those, and the gates re-verify. That replaces the old retry loop that re-ran the
whole task and burned CPU.

---

## 1. Production pack → project config

| Thing | How it works |
|---|---|
| **Phases** | A game is built in phases (bootstrap → props → VFX → scene assembly → QA & beta). Each phase has a supervisor. |
| **Swarm** | Each phase has many worker agents (e.g. 25 in Phase 7). Workers run in parallel. |
| **Naming law** | Every file must use a prefix: `SM_` static mesh, `M_` mesh, `T_` texture, `A_` audio, `Scene_`/`Prefab_`. A machine audit checks this — no guessing. |

## 2. The phase start gate

Before a phase runs, the harness checks the swarm actually contains vision
inspectors, and audio inspectors for audio phases. A missing verifier means the
phase is **refused**. They are not optional.

## 3. Workers run with real tools

| Tool | What it really does |
|---|---|
| `engine-capture` | Runs the **real** game project in Godot (`LF_CAPTURE=1`) and saves an actual in-engine screenshot from the real scene. |
| `vision-check` | Sends the screenshot to an AI vision model (NVIDIA llama vision). The verdict line must be `PASS` **and** the reason must semantically match the pack. Black, empty or fake frames fail instantly — no AI call wasted. |
| `audio-check` | Confirms the audio is a real playable sample with real content, not silence, and matches the pack when a transcriber is available. |
| `write-file`, `blender-gen`, `sox` | Produce the real deliverable files. |

## 4. The ready gate

A worker is **ready** only when all of these hold:

| Check | Pass | Fail |
|---|---|---|
| Output files exist | ≥1 real deliverable | nothing written |
| Naming law | `SM_`/`M_`/`T_`/`A_`/`Prefab_`/`Scene_` prefixes | `--frames.png`, `Main.tscn`, wrong names |
| Handoff report | all fields + final "Ready" line | missing fields / no "Ready" line |
| Vision gate (visual) | real screenshot, `vision-check` PASS, description matches pack | black/empty frame, fake 4-pixel frame, mismatch |
| Audio gate (audio) | real sound, non-silent, matches pack | silent/empty/broken file |

The old prompts told workers *"no live render is available — judge on files
alone."* That is deleted. Live render **is** available, and a missing or FAILED
render is grounds for refusal.

## 5. Beta testers → supervisor → repair (Phase 7 law)

| Step | What happens |
|---|---|
| Tester plays & tests | Five beta tester agents play the real build, capture screenshots, run `vision-check`. |
| Bug found | They write a bug report to their supervisor. |
| Repair | The supervisor dispatches a repair worker, the tester re-tests, vision re-verifies, the supervisor signs off. |
| No bugs reported | Still needs vision proof — every tester's own readiness requires its real frame to pass vision. Reporting alone is not readiness. |

---

## Running it

```sh
# What the harness can actually do right now
mem20gamez build-harness surface

# This guide, from the terminal
mem20gamez build-harness docs

# Plan the pipeline without spending a provider call
mem20gamez build-harness plan --project project.json

# Execute it
mem20gamez build-harness run --project project.json [--dry-run] [--phase NAME]

# The control surface
mem20gamez build-harness serve --port 8085
```

Then:

| What | How |
|---|---|
| Live status | `http://127.0.0.1:8085/api/projects/<id>/run/status` |
| API reference (Swagger) | `http://127.0.0.1:8085/docs` |
| This guide in a browser | `http://127.0.0.1:8085/guide` |
| Live event log | `tail -f /tmp/opencode/harness-phase7.log` |
| 3D LLM escape hatch | `HARNESS_3D_LLM=1` lets a 3D LLM take the visual inspector's place (allowed by the law) |
| Max repair rounds | `HARNESS_MAX_ATTEMPTS` (default 3) |

### Environment

| Variable | Meaning |
|---|---|
| `HARNESS_PROJECT_DIR` | Where project JSON lives. Default `/opt/mem20/store/harness` |
| `HARNESS_STATIC_DIR` | Static assets. Default `build_harness/static` |
| `HARNESS_PORT` | Control-surface port. Default 8085 |
| `HARNESS_MAX_ATTEMPTS` | Max repair rounds. Default 3 |
| `HARNESS_3D_LLM` | Set to `1` to allow a 3D LLM in the inspector's place |
| `MEM20_ENTRIES` | mem20 entries store for the project mirror |

---

## Modules

| Module | Lines | Role |
|---|--:|---|
| `runner` | 3,946 | The production pipeline: phases, workers, assembly, progress. Entry point `run_project()`. |
| `v21` | 979 | Provider key resolution, role-aware chat, and the seam that routes worker calls by bucket. |
| `app` | 401 | FastAPI control surface: projects, run, build, status, docs. |
| `worker` | 363 | Builds the orchestrator, supervisors and swarm members. |
| `mem20store` | 99 | Mirrors project state into the mem20 entries store. |

`bpy` is only importable inside Blender, so it is never imported at module
scope. Without Blender present the harness degrades to planning rather than
refusing to load.

---

**Bottom line: the pipeline is honest.** It never claims "done" from files a
model never looked at. Every visual and audio gate is verified by a model that has
to describe what it sees out loud — and if the description does not match the
production pack, it fails, and a repair worker is already on the way.

---

*Guide adapted from the owner's `how-the-harness-works.html`. Paths updated for
the permanent home under `mem20gamez`; the law is unchanged.*
