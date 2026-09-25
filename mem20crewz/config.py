"""config.py — YAML→runtime wiring (build gap #3).

Mirrors the mem20 crews YAML schema but binds to mem20 objects:
  agents.yaml:  {role: {role, goal, backstory, tools, capabilities, values,
                        max_iter, allow_delegation, allow_code_execution,
                        max_rpm, max_execution_time, verbose, knowledge, planning}}
  tasks.yaml:   {name: {description, expected_output, agent, context,
                        output_file, output_json, human_input, async_execution,
                        notes}}
  crew section: optional {name, process, guardrails, planning, cache,
                          verbose, manager} at top of tasks.yaml

Also ships default templates (`write_example(dir)`) and the CLI `init` helper.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import yaml

from .agents import Agent
from .crew import Crew
from .tasks import Task

SAMPLE_AGENTS_YAML = """researcher:
  role: "Researcher"
  goal: "Gather verifiable facts about {topic}"
  backstory: "A careful analyst that only reports what the substrate confirms."
  capabilities: [reason, plan, memory]
  values: [no workarounds, grounded output]
  tools: []
  max_iter: 8
  allow_delegation: true

writer:
  role: "Writer"
  goal: "Turn research into a concise markdown brief on {topic}"
  backstory: "Precise technical writer. Never fabricates facts."
  capabilities: [reason, self-model, memory]
  values: [honest output]
  tools: []
  max_iter: 8
"""

SAMPLE_TASKS_YAML = """crew:
  name: "example"
  process: "sequential"
  guardrails: true
  planning: false
  cache: true

research_step:
  description: "Research {topic} using the substrate."
  expected_output: "A routed list of 3-5 verifiable facts about {topic}"
  agent: "Researcher"
  output_file: "outputs/research.md"

write_step:
  description: "Write the final brief from {topic}."
  expected_output: "A markdown brief synthesizing the research."
  agent: "Writer"
  context: [research_step]
"""


def load_agents_yaml(path: str) -> list[Agent]:
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    agents: list[Agent] = []
    for role, spec in data.items():
        if not isinstance(spec, dict):
            continue
        agents.append(Agent(
            role=str(spec.get("role") or role),
            goal=str(spec.get("goal", "")),
            backstory=str(spec.get("backstory", "")),
            capabilities=list(spec.get("capabilities", []) or []),
            values=list(spec.get("values", []) or []),
            tools=list(spec.get("tools", []) or []),
            max_iter=int(spec.get("max_iter", 10)),
            guardrails=bool(spec.get("guardrails", True)),
            allow_delegation=bool(spec.get("allow_delegation", True)),
            allow_code_execution=bool(spec.get("allow_code_execution", False)),
            max_rpm=int(spec.get("max_rpm", 0)),
            max_execution_time=float(spec.get("max_execution_time", 0.0)),
            verbose=bool(spec.get("verbose", False)),
            knowledge=list(spec.get("knowledge", []) or []),
            planning=bool(spec.get("planning", False)),
        ))
    return agents


def load_tasks_yaml(path: str, agents: list[Agent],
                    require_agent: bool = True) -> list[Task]:
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    roles = {a.role.lower(): a.role for a in agents}
    for a in agents:
        roles.setdefault(a.namespace, a.role)
    tasks: list[Task] = []
    for name, spec in data.items():
        if not isinstance(spec, dict):
            continue  # skip crew section
        if (name or "").lower() == "crew":
            continue
        agent_name = str(spec.get("agent", "") or "")
        agent_role = roles.get(agent_name.lower(), agent_name)
        json_spec = spec.get("output_json", False)
        tasks.append(Task(
            name=str(name),
            description=str(spec.get("description", "")),
            expected_output=str(spec.get("expected_output", "")),
            agent=agent_role,
            context=list(spec.get("context", []) or []),
            output_file=spec.get("output_file"),
            output_json=(json_spec if isinstance(json_spec, (bool, dict)) else False),
            human_input=bool(spec.get("human_input", False)),
            async_execution=bool(spec.get("async_execution", False)),
            guardrails=bool(spec.get("guardrails", True)),
            persist_output=bool(spec.get("persist_output", True)),
            notes=str(spec.get("notes", "")),
        ))
    if require_agent and tasks and not all(t.agent for t in tasks):
        raise ValueError("every task in tasks.yaml must declare an agent")
    return tasks


def load_crew(top: Optional[dict] = None) -> dict:
    if not top:
        return {"name": "crew", "process": "sequential", "guardrails": True,
                "planning": False, "cache": True}
    return {
        "name": str(top.get("name", "crew")),
        "process": str(top.get("process", "sequential")),
        "guardrails": bool(top.get("guardrails", True)),
        "planning": bool(top.get("planning", False)),
        "cache": bool(top.get("cache", True)),
        "verbose": bool(top.get("verbose", False)),
        "manager": top.get("manager") if isinstance(top.get("manager"), dict) else None,
    }


def build_crew(name: str = "crew", agents: Optional[list[Agent]] = None,
               tasks: Optional[list[Task]] = None, **kw) -> Crew:
    agents = agents or []
    # tasks reference agents by role; drop unknown-agent tasks with a clear error.
    roles = {a.role: a for a in agents}
    for a in agents:
        roles.setdefault(a.namespace, a)
    resolved_tasks: list[Task] = []
    for t in tasks or []:
        if t.agent and t.agent not in roles:
            # allow build to skip nothing — fail loudly instead of faking.
            raise ValueError(
                f"task '{t.name}' references unknown agent '{t.agent}'")
        resolved_tasks.append(t)
    return Crew(name=name, agents=agents, tasks=resolved_tasks, **kw)


def build_crew_from_yaml(agents_yaml: str, tasks_yaml: str,
                         **kw) -> Crew:
    """One-shot loader for the CLI + tests: point at two YAML paths."""
    agents = load_agents_yaml(agents_yaml)
    meta = _crew_meta(_safe_load(tasks_yaml))
    tasks = load_tasks_yaml(tasks_yaml, agents)
    return build_crew(
        name=meta.get("name", "crew"),
        agents=agents,
        tasks=tasks,
        process=meta.get("process", "sequential"),
        planning=meta.get("planning", False),
        cache=meta.get("cache", True),
        verbose=meta.get("verbose", False),
        **kw,
    )


def write_example(dir_path: str) -> list[str]:
    os.makedirs(dir_path, exist_ok=True)
    a, t = os.path.join(dir_path, "agents.yaml"), os.path.join(dir_path, "tasks.yaml")
    for path, content in ((a, SAMPLE_AGENTS_YAML), (t, SAMPLE_TASKS_YAML)):
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
    return [a, t]


def _crew_meta(data: dict) -> dict:
    crew = data.get("crew", {}) or {}
    return {
        "name": str(crew.get("name", "crew")),
        "process": str(crew.get("process", "sequential")),
        "guardrails": bool(crew.get("guardrails", True)),
        "planning": bool(crew.get("planning", False)),
        "cache": bool(crew.get("cache", True)),
        "verbose": bool(crew.get("verbose", False)),
    }


def _safe_load(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}