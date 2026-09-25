"""Demo crew — exercises the full cleanroom surface end to end.

Two modes:
  fake (default, deterministic): every agent uses a scripted FakeBrain. Used for
    offline demos and the DEV loop — never a substitute for a real run.
  real: CogBrain (llm.chat via the mem20 key) + live A2A peers. Honest-failure
    mode: if the key is missing, llm.chat raises LLMError and the run reports it
    instead of fabricating an answer.

Crew:  researcher (tools: a python callable + the mem20 procedural skill)
       writer (upstream context from researcher; output_file written to disk)
Flow:  brief-flow — start -> researched -> written, each step a roadmap phase.
"""

from __future__ import annotations

import datetime
import os
from typing import Optional, Tuple

from ..agents import Agent
from ..crew import Crew, CrewResult
from ..flow import Flow, FlowResult, listen, start
from ..neural import FakeBrain


def stamp(arg: str = "") -> str:
    """Callable tool: returns the current UTC timestamp."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class _DemoMemory:
    """Hermetic in-memory substrate stub for FAKE mode.

    Guarantees zero writes to (and zero reads from) the real mem20 store:
    every hook is fulfilled in-process and every guard passes through without
    blocking. Clearly a stub — never used by the REAL mode.
    """

    def __init__(self) -> None:
        import uuid
        self._uuid = uuid
        self._facts: dict[str, dict] = {}
        self._procs: dict[str, str] = {}

    def remember(self, topic, content, tags=None, actor="agent"):
        fid = self._uuid.uuid4().hex[:16]
        self._facts[fid] = {"topic": topic, "content": content, "tags": tags or []}
        return {"id": fid, "topic": topic, "ok": True}

    def recall(self, topic=None, tags=None, k=5):
        return []

    def procedural_list(self, category=None):
        return [{"name": n, "description": d} for n, d in self._procs.items()]

    def procedural_get(self, name):
        d = self._procs.get(name, "")
        return {"name": name, "skill": name, "description": d or ""}

    def procedural_execute(self, name, context=None):
        if name in self._procs:
            return {"ok": True, "output": self._procs[name]}
        return {"ok": False, "output": f"demo stub has no skill '{name}'",
                "error": "demo-stub-unknown-skill"}

    def plan_guard(self, fact_ids=None, actor="agent"):
        return {"blocked": False, "reason": "demo stub: no plan gate (fake)"}

    def veto(self, fact_ids, actor="agent"):
        return {"vetoed": False, "reason": "demo stub: veto cleared (fake)"}

    def quarantine(self, actor="agent"):
        return {"acted": 0, "note": "demo stub: nothing expired"}


def _install_demo_stub() -> _DemoMemory:
    """Point the shared backend's 8 seams at the hermetic stub."""
    from .._substrate import backend
    stub = _DemoMemory()
    for name in ("remember", "recall", "procedural_list", "procedural_get",
                 "procedural_execute", "plan_guard", "veto", "quarantine"):
        backend.hooks[name] = getattr(stub, name)
    return stub


def run(real: bool = False, topic: str = "mem20 substrate",
        crew_name: str = "fountain") -> Tuple[str, CrewResult, FlowResult]:
    topic = topic or "mem20 substrate"
    os.makedirs(os.path.join(os.path.dirname(__file__), "..", "runtime", "outputs"),
                exist_ok=True)
    out_dir = os.path.join(os.path.dirname(__file__), "..", "runtime", "outputs")
    research_file = os.path.join(out_dir, f"{crew_name}-research.md")
    brief_file = os.path.join(out_dir, f"{crew_name}-brief.md")

    if real:
        from ..a2a import A2AClient
        from ..neural import CogBrain
        a2a = A2AClient()
        researcher_brain, writer_brain = CogBrain(), CogBrain()
    else:
        _install_demo_stub()
        a2a = None
        researcher_brain = FakeBrain(steps=[
            {"action": "tool", "tool": "stamp", "args": "start"},
            {"action": "final",
             "final": f"Research on '{topic}': confirmed from the substrate that "
                      "reference_store is built with 10 passing tests and a valid "
                      "chain proof (24 unique cids); honest-failure llm gate verified."},
        ])
        writer_brain = FakeBrain(steps=[
            {"action": "final",
             "final": f"# Brief: {topic}\n\nResearch confirms the mem20 cleanroom "
                      "surface (Agent/Task/Crew/Flow) is backed by live substrate "
                      "primitives: roadmap-ledger runs, procedural-skills tools, "
                      "epistemic guardrails, and A2A delegation."},
        ])

    researcher = Agent(
        role="Researcher",
        goal=f"Produce an outline of verifiable facts about {topic}",
        backstory="A careful analyst that only reports what the substrate confirms.",
        tools=[stamp, "mem20-tool-file-safe-fix"],
        max_iter=6,
        brain=researcher_brain,
        a2a=a2a,
    )
    writer = Agent(
        role="Writer",
        goal=f"Write a concise markdown brief about {topic}",
        backstory="A precise technical writer. Never fabricates facts.",
        tools=[],
        max_iter=6,
        brain=writer_brain,
    )

    from ..tasks import Task
    research = Task(
        name="research_step",
        description="Research {topic} and route verifiable facts.",
        expected_output="An outline of 3-5 facts about {topic}",
        agent="Researcher",
        output_file=research_file,
    )
    brief = Task(
        name="write_step",
        description="Write the final markdown brief from the research steps.",
        expected_output="A markdown brief about {topic}",
        agent="Writer",
        context=[research.name],
        output_file=brief_file,
    )

    crew = Crew(name=crew_name, agents=[researcher, writer], tasks=[research, brief],
                a2a=a2a)
    crew_result = crew.kickoff(inputs={"topic": topic})

    flow = _BriefFlow(name=f"{crew_name}-flow")
    flow_result = flow.run(inputs={"topic": topic})

    lines = [
        f"demo crew '{crew.name}' ({'REAL' if real else 'FAKE [deterministic]'} backend)",
        "—" * 60,
    ]
    for o in crew_result.outcomes:
        lines.append(f"[{'OK ' if o.ok else 'FAIL'}] {o.agent} :: {o.task_name} "
                     f"({o.iterations} iters)")
        if o.blocked:
            lines.append(f"    BLOCKED: {o.blocked_reason}")
        lines.append(f"    {o.output[:300]}")
        if o.saved_to:
            lines.append(f"    saved -> {o.saved_to}")
    lines.append("—" * 60)
    lines.append(f"flow '{flow.name}': {flow_result.runs}")
    lines.append(f"roadmaps: {crew_result.roadmap.path if crew_result.roadmap else 'n/a'}, "
                 f"{flow_result.roadmap.path if flow_result.roadmap else 'n/a'}")
    return "\n".join(lines), crew_result, flow_result


class _BriefFlow(Flow):
    """Class-level @start / @listen usage of the cleanroom Flow."""

    @start
    def begin(self, ctx, state):
        return "researched"

    @listen("researched")
    def compose(self, ctx, state):
        return "written"

    @listen("written")
    def done(self, ctx, state):
        self.state["_done"] = True
        return ""