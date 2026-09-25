"""Task-context assembly (build gap #1).

A Task's context is NOT just the description string — it is assembled from:
- the task description + expected_output (interpolated with crew inputs)
- outputs of upstream tasks (the `context` list)
- the assigned agent's identity (role/goal/backstory/values/capabilities)
- namespaced memory recall for that agent
- the tool inventory it can call

The assembled block is a plain-text prompt passed to the brain, and also kept
as provenance on the task outcome so anyone can see exactly what the agent saw.
"""

from __future__ import annotations

from typing import Any

from ._substrate import backend as sub


class TaskContext:
    """Immutable assembly of everything a task sees when it runs."""

    def __init__(self, *, task_name: str, description: str, expected_output: str,
                 inputs: dict, upstream: dict, agent_identity: dict,
                 memory_recall: str, tools: str, notes: str = "") -> None:
        self.task_name = task_name
        self.description = description
        self.expected_output = expected_output
        self.inputs = dict(inputs)
        self.upstream = dict(upstream)
        self.agent_identity = dict(agent_identity)
        self.memory_recall = memory_recall
        self.tools = tools
        self.notes = notes

    def prompt(self) -> str:
        blocks = [
            f"# Task: {self.task_name}",
            f"## Description\n{self.description}",
            f"## Expected output\n{self.expected_output}",
        ]
        if self.agent_identity:
            blocks.append(
                "## Agent identity\n" + "\n".join(
                    f"- {k}: {v}" for k, v in self.agent_identity.items() if v))
        if self.upstream:
            blocks.append("## Contributions from upstream tasks\n" +
                          _render_upstream(self.upstream))
        if self.memory_recall:
            blocks.append("## Relevant memory (namespaced recall)\n" + self.memory_recall)
        if self.tools:
            blocks.append("## Tools you may call\n" + self.tools)
        if self.notes:
            blocks.append(f"## Notes\n{self.notes}")
        return "\n\n".join(blocks)

    def to_dict(self) -> dict:
        return {
            "task_name": self.task_name,
            "description": self.description,
            "expected_output": self.expected_output,
            "inputs": self.inputs,
            "upstream": {k: _trunc(v, 1500) for k, v in self.upstream.items()},
            "agent_identity": self.agent_identity,
            "memory_recall": self.memory_recall,
            "tools": self.tools,
            "notes": self.notes,
        }


def _render_upstream(upstream: dict) -> str:
    parts = []
    for name, value in upstream.items():
        parts.append(f"### {name}\n{_trunc(value, 2000)}")
    return "\n\n".join(parts)


def _trunc(value: Any, length: int = 2000) -> str:
    text = value if isinstance(value, str) else _as_text(value)
    return text[:length] + ("…" if len(text) > length else "")


def _as_text(value: Any) -> str:
    import json
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return str(value)


def interpolate(template: str, inputs: dict) -> str:
    """{var} interpolation over crew inputs (same shape as mem20 crews)."""
    out = template
    for k, v in inputs.items():
        out = out.replace("{" + str(k) + "}", _as_text(v))
    return out


def assemble(task, agent, upstream: dict, inputs: dict, memory_k: int = 5) -> TaskContext:
    """Build a TaskContext for one task.

    `task` has .name/.description/.expected_output; `agent` has an identity()
    method (or is None for identity-less tasks).
    """
    identity = agent.identity() if agent is not None else {}
    ns = agent.namespace if agent is not None else None
    recall_text = ""
    if ns:
        try:
            records = sub.recall(topic=ns, tags=["mem20crewz"] + [ns], k=memory_k)
            recall_text = "\n".join(
                f"- [{r.get('ts', '')[:19]}] {r.get('content', '')[:300]}"
                for r in records) if records else ""
        except Exception:
            recall_text = ""
    tools = task.tools if isinstance(getattr(task, "tools", None), str) else \
        (task.tools if hasattr(task, "tools") else "")
    return TaskContext(
        task_name=task.name,
        description=interpolate(task.description, inputs) if inputs else task.description,
        expected_output=interpolate(task.expected_output, inputs) if inputs
        else task.expected_output,
        inputs=inputs,
        upstream=upstream,
        agent_identity=identity,
        memory_recall=recall_text,
        tools=tools or "",
        notes=getattr(task, "notes", ""),
    )