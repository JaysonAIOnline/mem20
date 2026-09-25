"""AgentSwarmTool — port of kimi-code's AgentSwarm tool contract.

Validates fan-out inputs, expands the prompt template over items, merges
resume_agent_ids, runs the swarm batch, and renders the ordered XML result with
summary + resume hints. No sub-agents are launched here; the caller passes a
swarm-run function so the tool stays hermetic in tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional

from .types import SessionSwarmSpawnTask, SessionSwarmResumeTask, SessionSwarmRunResult, escape_xml

PROMPT_TEMPLATE_PLACEHOLDER = "{{item}}"
MAX_AGENT_SWARM_SUBAGENTS = 128
DEFAULT_SUBAGENT_TYPE = "coder"


class AgentSwarmError(Exception):
    pass


@dataclass
class AgentSwarmSpecs:
    spawn: list[dict[str, Any]] = field(default_factory=list)
    resume: list[dict[str, Any]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.spawn) + len(self.resume)


@dataclass
class AgentSwarmSpec:
    kind: Literal["spawn", "resume"]
    index: int
    item: Optional[str] = None
    prompt: str = ""
    agentId: Optional[str] = None


@dataclass
class SwarmRunResult:
    spec: AgentSwarmSpec
    agentId: Optional[str] = None
    status: Literal["completed", "failed", "aborted"] = "failed"
    state: Optional[Literal["started", "not_started"]] = None
    result: Optional[str] = None
    stopReason: Optional[str] = None
    error: Optional[str] = None


@dataclass
class AgentSwarmTool:
    description: str = ""
    subagent_type: Optional[str] = None
    prompt_template: Optional[str] = None
    items: Optional[list[str]] = None
    fork: bool = False
    resume_agent_ids: Optional[dict[str, str]] = None
    model: Optional[str] = None
    swarm_run: Callable[..., list[SessionSwarmRunResult]] | None = None

    def __post_init__(self) -> None:
        self.items = [i.strip() for i in (self.items or []) if i and i.strip()]
        self.resume_agent_ids = {str(k).strip(): str(v).strip() for k, v in (self.resume_agent_ids or {}).items()}

    # ------------------------------------------------------------- validation
    def validate_specs(self, get_resume_item: Callable[[str], Optional[str]] | None = None) -> AgentSwarmSpec:
        """Reject invalid input before any sub-agent starts (mirror kimi's rules)."""
        items = self.items or []
        resume = self.resume_agent_ids or {}
        if not resume and len(items) < 2:
            raise AgentSwarmError("AgentSwarm requires at least 2 items unless resume_agent_ids is provided.")
        total = len(items) + len(resume)
        if total > MAX_AGENT_SWARM_SUBAGENTS:
            raise AgentSwarmError(
                f"AgentSwarm supports at most {MAX_AGENT_SWARM_SUBAGENTS} subagents "
                f"(got {total})."
            )
        template = _normalize(self.prompt_template)
        if items and template is None:
            raise AgentSwarmError("prompt_template is required when items are provided.")
        if template is not None and PROMPT_TEMPLATE_PLACEHOLDER not in template:
            raise AgentSwarmError(
                f"prompt_template must include the {PROMPT_TEMPLATE_PLACEHOLDER} placeholder."
            )
        if self.fork and (resume or len(items) == 0):
            raise AgentSwarmError("fork requires items and cannot be combined with resume_agent_ids.")

        seen_prompts: dict[str, int] = {}
        resume_specs: list[AgentSwarmSpec] = []
        for idx, (agent_id, prompt) in enumerate(resume.items()):
            resume_specs.append(
                AgentSwarmSpec(
                    kind="resume",
                    index=idx + 1,
                    agentId=agent_id,
                    item=(get_resume_item(agent_id) if get_resume_item else None),
                    prompt=prompt,
                )
            )
        spawn_specs: list[AgentSwarmSpec] = []
        base = len(resume_specs)
        for i, item in enumerate(items):
            prompt = template.replace(PROMPT_TEMPLATE_PLACEHOLDER, item) if template else ""
            previous = seen_prompts.get(prompt)
            if previous is not None:
                raise AgentSwarmError(
                    f"Duplicate subagent prompts from items {previous} and {i + 1}. "
                    "AgentSwarm requires distinct subagents."
                )
            seen_prompts[prompt] = i + 1
            spawn_specs.append(AgentSwarmSpec(kind="spawn", index=base + i + 1, item=item, prompt=prompt))
        return AgentSwarmSpecs(spawn=spawn_specs, resume=resume_specs)

    # ------------------------------------------------------------------- tasks
    def to_tasks(
        self,
        caller_agent_id: str,
        profile_name: Optional[str] = None,
        parent_tool_call_id: str = "",
        spec_source: AgentSwarmSpecs | None = None,
    ) -> list[SessionSwarmSpawnTask | SessionSwarmResumeTask]:
        specs = spec_source or self.validate_specs()
        profile = profile_name or self.subagent_type or DEFAULT_SUBAGENT_TYPE
        tasks: list[SessionSwarmSpawnTask | SessionSwarmResumeTask] = []
        for s in specs.resume:
            tasks.append(
                SessionSwarmResumeTask(
                    kind="resume",
                    data=s.__dict__,
                    profileName="subagent",
                    parentToolCallId=parent_tool_call_id,
                    prompt=s.prompt,
                    description=child_description(self.description, s.index, "resume"),
                    swarmIndex=s.index,
                    swarmItem=s.item,
                    resumeAgentId=s.agentId or "",
                )
            )
        for s in specs.spawn:
            tasks.append(
                SessionSwarmSpawnTask(
                    kind="spawn",
                    data=s.__dict__,
                    profileName=profile,
                    parentToolCallId=parent_tool_call_id,
                    prompt=s.prompt,
                    description=child_description(self.description, s.index, profile),
                    swarmIndex=s.index,
                    swarmItem=s.item,
                    plan={"profileName": profile, "model": self.model},
                )
            )
        return tasks

    # ------------------------------------------------------------ result render
    def render_results(self, results: list[SessionSwarmRunResult], specs: AgentSwarmSpecs) -> str:
        completed = sum(1 for r in results if r.status == "completed")
        failed = sum(1 for r in results if r.status == "failed")
        aborted = sum(1 for r in results if r.status == "aborted")

        merged: list[SwarmRunResult] = []
        for spec, result in zip(specs.spawn + specs.resume, results):
            merged.append(
                SwarmRunResult(
                    spec=spec,
                    agentId=result.agentId,
                    status=result.status,
                    state=result.state,
                    result=result.result if result.status == "completed" else None,
                    stopReason=result.stopReason,
                    error=result.error if result.status != "completed" else None,
                )
            )

        should_render_resume_hint = any(
            (r.status != "completed" or r.stopReason is not None) and r.agentId is not None
            for r in merged
        )

        lines = ["<agent_swarm_result>", f"<summary>{_summary(completed, failed, aborted)}</summary>"]
        if should_render_resume_hint:
            lines.append(
                "<resume_hint>Call AgentSwarm with resume_agent_ids using the agent_id values "
                "in this result to continue unfinished work.</resume_hint>"
            )
        for r in merged:
            agent_id = f' agent_id="{escape_xml(r.agentId)}"' if r.agentId else ""
            mode = ' mode="resume"' if r.spec.kind == "resume" else ""
            item = f' item="{escape_xml(r.spec.item)}"' if r.spec.item is not None else ""
            state = f' state="{r.state}"' if r.state else ""
            stop = f' stop_reason="{escape_xml(r.stopReason)}"' if r.stopReason else ""
            body = r.result if r.status == "completed" else (r.error or "unknown error")
            lines.append(
                f"<subagent{mode}{agent_id}{item}{state} outcome=\"{r.status}\"{stop}>"
                f"{escape_xml(body)}</subagent>"
            )
        lines.append("</agent_swarm_result>")
        return "\n".join(lines)


def child_description(swarm_description: str, index: int, profile_name: str) -> str:
    return f"{swarm_description} #{index} ({profile_name})"


def _summary(completed: int, failed: int, aborted: int = 0) -> str:
    parts = []
    if completed > 0:
        parts.append(f"completed: {completed}")
    if failed > 0:
        parts.append(f"failed: {failed}")
    if aborted > 0:
        parts.append(f"aborted: {aborted}")
    return ", ".join(parts) if parts else "none"


def _normalize(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return value.strip() or None