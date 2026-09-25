"""mem20crewz — cleanroom mem20 crews (Agent/Task/Crew/Flow) on mem20 primitives.

Zero dependency on the `mem20 crews` package. See README.md for the mapping.
"""

from __future__ import annotations

__version__ = "0.1.0"

from .agents import Agent
from .a2a import A2AClient, A2AError
from .config import (build_crew, build_crew_from_yaml, load_agents_yaml,
                     load_tasks_yaml, write_example)
from .context import TaskContext, assemble
from .crew import Crew, CrewResult
from .flow import Flow, FlowResult, listen, listen_once, router, start
from .guardrails import Guards, GuardrailBlocked
from .loop import ToolLoop
from .neural import Brain, CogBrain, FakeBrain
from .roadmap import Roadmap
from .skills import Skill, Skills
from ._substrate import backend
from .tasks import Task, TaskOutcome

__all__ = [
    "A2AClient", "A2AError", "Agent", "Brain", "CogBrain", "Crew",
    "CrewResult", "FakeBrain", "Flow", "FlowResult", "Guards",
    "GuardrailBlocked", "Roadmap", "Skill", "Skills", "Task", "TaskContext",
    "TaskOutcome", "ToolLoop", "assemble", "backend", "build_crew",
    "build_crew_from_yaml", "listen", "listen_once", "load_agents_yaml",
    "load_tasks_yaml", "router", "start", "write_example",
]