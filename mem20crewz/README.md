# 01_mem20crewz — CLEANROOM BUILD MANIFEST (hypo-map-1 phase 01)

Green-lit 2026-09-08 by Jayson. Rebuild the mem20 crews surface (Agent / Task / Crew /
Flow) as a cleanroom on mem20 primitives. ZERO dependency on the `mem20 crews` package —
this package imports nothing named mem20 crews and ships no runtime dep on it. Every
abstraction is backed by a mem20 native.

## Mapping (directive → implementation)

| mem20 crews surface    | mem20 native backing                                   |
|-------------------|--------------------------------------------------------|
| agent             | memory.SelfModel (capabilities/values/identity) + a namespace (memory scope per agent) |
| reasoning         | cog/cognitive_engine: plan, reason, reflect, beam/tot (react_reason for the action loop) |
| crew run          | roadmap: RoadmapRun persists phases planned→in_progress→completed/blocked to runtime/roadmaps/<name>.jsonl |
| delegation        | A2A fan-out to 22 peers (localhost:9901..9922, read from mem20 peers.yaml (a2a_agents)) |
| tools             | procedural skills (memory.procedural_* ) + python callables, via one Skills registry |
| guardrails        | epistemic veto (epistemic_veto / require_epistemic_clearance) + quarantine (quarantine_expired_simulated) + plan-execution guard (run_plan_execution_guard) |
| yaml config       | agents.yaml / tasks.yaml → Agent/Task/Crew objects (build gap #3) |

## Build gaps (explicitly called out in phase 01) — resolved as follows

1. **task-context assembly** → `mem20crewz/context.py:TaskContext`. Fuses:
   task description + expected_output + `{input}` interpolation + upstream task
   outputs + agent identity (role/goal/backstory/values) + agent memory recall
   (namespaced recall via substrate) + tool inventory. Rendered into a stable
   prompt block attached as `task.context` provenance.
2. **tool-callback loop** → `mem20crewz/loop.py:ToolLoop`. Deterministic loop:
   brain proposes (tool|delegate|final) → Skills executes callable/procedural
   skill, or A2A delegates by capability → the observation feeds the next
   proposal → bounded by max_iter; guardrails gate each iteration and the final
   answer. Real path uses cog `react_reason`-style thinking via llm.chat with a
   strict JSON action contract; tests use a deterministic FakeBrain.
3. **YAML→runtime wiring** → `mem20crewz/config.py`: `load_agents_yaml(path)`,
   `load_tasks_yaml(path, agents)`, `build_crew(...)`. Mirrors the mem20 crews
   YAML schema (agents.yaml roles/goal/backstory/tools; tasks.yaml
   description/expected_output/context/agent) but binds to mem20 objects.
   CLI: `python -m mem20crewz run`.

## Runtime layout

    /opt/mem20/mem20crewz/
        __init__.py     exports: Agent, Task, Crew, Flow, start, listen, A2AClient, build_crew, ...
        _substrate.py   lazy import shims over memory / cog / llm + injectable seams (tests stay hermetic)
        neural.py       Brain, CogBrain (real), FakeBrain (deterministic)
        context.py      TaskContext assembly (gap #1)
        loop.py         ToolLoop — tool-callback loop (gap #2)
        skills.py       Skills registry (procedural skills + callables)
        guardrails.py   Guards: plan gate, epistemic veto, quarantine sweep
        agents.py       Agent (self-model + namespace), Agent.kickoff()
        tasks.py        Task (description/expected_output/context/output_file/output_json)
        crew.py         Crew.kickoff() = roadmap-backed sequential run + result provenance
        flow.py         Flow with @start / @listen over roadmap phases + {var} interpolation
        roadmap.py      RoadmapRun — persisted phase ledger
        a2a.py          A2AClient — discover / call / fan_out (parallel) over JSON-RPC v1.0
        config.py       YAML → runtime wiring (gap #3) + default templates
        cli.py/__main__ `python -m mem20crewz`
        runtime/        roadmaps + gitignore (runtime state, not committed)
        tests/test_mem20crewz.py
        demo/demo_crew.py
        README.md (this file)

## Honesty rules (from no-fake-everything)

- llm.chat / cog raise LLMError when no key — the cleanroom never fabricates a
  completion. FakeBrain is used ONLY in tests/demo-fake, clearly labelled.
- Every module is exercised by the test suite and the live demo (real key).
- A2A peers are live (9901/9902/9905/9909 verified open) — fan-out tested
  against the real protocol, with a loopback A2A server for hermetic tests.
- Status claims below are backed by a test run + live demo on disk (see VERIFY).

## VERIFY (update after run)

- [ ] tests pass (python3 -m unittest mem20crewz.tests.test_mem20crewz)
- [ ] demo_crew.py runs against real cog + real A2A peers
- [ ] phase 01 status bumped in hypo-map-1.json

## Managed members (package-review integration)

Single-purpose crew/labor organs grouped here by reference; they live in
their own top-level directories and are smoke-verified there:

- `mem20adversarialqacrewz`
- `mem20agentoutputcompilerz`
- `mem20asynccollaborationcapsulesz`
- `mem20batteryawareagentschedulerz`
- `mem20causalroutingbrainz`
- `mem20emotionsensitivemessagerouterz`
- `mem20eventshaperouterz`
- `mem20executableroadmapcompilerz`
- `mem20goaleconomyschedulerz`
- `mem20goapagentdesignerz`
- `mem20hardwareawareinferencecompilerz`
- `mem20humanagentcoworkcanvasz`
- `mem20intentcompilerz`
- `mem20intenttoagentmatchmakerz`
- `mem20intenttomissioncompilerz`
- `mem20locationawareworkrouterz`
- `mem20missionroutingcockpitz`
- `mem20realitytosoftwarecompilerz`
- `mem20roamingworkloadschedulerz`