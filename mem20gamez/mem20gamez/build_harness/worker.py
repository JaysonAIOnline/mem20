"""Orchestrated build for the Swarm Harness.

Pipeline (exactly one logical sequence):
  1. Build the ORCHESTRATOR as a mem20agentz profile (the project's master
     prompt) + A2A capability.
  2. Build SUPERVISORS (<= 15) one at a time in sequence via mem20agentz
     Profiles.create(); give each A2A capability so orchestrator <-> supervisor
     and supervisor -> orchestrator reporting is a real peer link.
  3. Build the SWARM under mem20crewz: one Agent per worker, bound to its
     skills/tools, assigned to its supervisor.
  4. Log the roster + project into the mem20 memory store.

A2A is reserved for orchestrator + supervisors. Swarm workers get skills/tools
only (no peer slots). dry_run (default) plans without mutating mem20agentz.
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

# --- mem20 agent platform (supervisors) ---
A2A_CAPABILITY = "a2a"
A2A_VALUES = ["accountability", "reporting", "no-workarounds"]

# --- supervisor job packages: match role -> concrete skills + tools --------
# Each package carries the procedural skills that get REGISTERED into mem20
# (so the supervisor can actually execute them) plus the tool inventory bound
# to the profile. Match is scored against name + prompt + capabilities, so a
# supervisor always receives its job-appropriate toolkit, never a generic one.
JOB_PACKAGES = {
    "bootstrap": {
        "match": ["bootstrap", "scaffold", "foundation", "phase 0", "setup", "xr base", "project init"],
        "skills": [
            {"name": "scaffold_xr_project", "description": "Create the Unity/XR project skeleton (folders, git, build target).",
             "steps": ["Create project structure", "Configure XR plugin", "Add build target", "Verify import"]},
            {"name": "bootstrap_config", "description": "Write bootstrap config: budgets, naming, scene list.",
             "steps": ["Define scene list", "Write budgets", "Apply naming rules"]},
        ],
        "tools": ["scaffold-project", "write-config", "setup-build-target", "verify-bootstrap"],
    },
    "dialogue": {
        "match": ["dialogue", "dialog", "conversation", "narrative", "phase 1", "voice", "script"],
        "skills": [
            {"name": "dialogue_data_authoring", "description": "Author DialogueData ScriptableObject content with speaker, eventIds, branching.",
             "steps": ["Define characters", "Write linear dialogue", "Add branches", "Map eventIds", "Export DialogueData"]},
            {"name": "dialogue_interactable_config", "description": "Configure XRBaseInteractable + DialogueInteractable per talkable character.",
             "steps": ["Assign agentId", "Set cooldown", "Wire Interaction Toolkit", "Test spam-free"]},
        ],
        "tools": ["write-dialogue-data", "validate-eventids", "config-dialogue-interactable", "branch-check"],
    },
    "environment": {
        "match": ["office", "environment", "scene", "phase 2", "fishtank", "award", "office", "level", "world"],
        "skills": [
            {"name": "env_asset_authoring", "description": "Build environment assets (fishtanks, awards, furniture) within budgets.",
             "steps": ["Model asset", "Add materials", "Check draw calls", "Verify collision"]},
            {"name": "environment_integration", "description": "Integrate environment pieces into the office scene cleanly.",
             "steps": ["Place in scene", "Verify lighting", "Run smoke test"]},
        ],
        "tools": ["build-fishtank", "build-awards-wall", "scene-integrate", "lighting-check"],
    },
    "characters": {
        "match": ["character", "agent", "population", "phase 3", "lod", "300", "npc", "crowd"],
        "skills": [
            {"name": "agent_prefab_factory", "description": "Build role-based agent prefabs with LOD groups and work animations.",
             "steps": ["Create base prefab", "Add LOD group", "Add role variants", "Wire animation states"]},
            {"name": "agent_population_lod", "description": "Make large agent populations (up to 300) Quest-viable via LOD + pooling.",
             "steps": ["Define LOD chain", "Add pooling", "Measure frame time", "Accept/iterate"]},
        ],
        "tools": ["build-agent-prefab", "lod-optimize", "population-pool", "perf-measure"],
    },
    "flow": {
        "match": ["flow", "gameplay", "systems", "phase 4", "elevator", "sequence", "logic", "game flow"],
        "skills": [
            {"name": "elevator_system", "description": "Build the elevator: doors, XR button panel, movement, floor indicator, tolerates 50 rides.",
             "steps": ["Build doors", "Add button panel", "Wire movement", "Add floor indicator", "Run 50-ride test"]},
            {"name": "player_flow_wiring", "description": "Maintain the Office->Secretary->Elevator->Main Floor->Car sequence.",
             "steps": ["Map flow nodes", "Wire transitions", "Verify no stuck states"]},
        ],
        "tools": ["build-elevator", "wire-flow", "flow-test", "50-ride-torture"],
    },
    "polish": {
        "match": ["polish", "phase 5", "phase 6", "audio", "vfx", "factory", "optimization", "refinement"],
        "skills": [
            {"name": "audio_design", "description": "Design spatialized audio (filter hum, ambient, announcements) within mixes.",
             "steps": ["Define bus layout", "Add spatialized sources", "Test levels", "Verify performance"]},
            {"name": "vfx_polish", "description": "Add VFX (bubbles, caustics, screens) without breaking budgets.",
             "steps": ["Add particle system", "Check draw calls", "Verify frame time"]},
        ],
        "tools": ["audio-mix", "vfx-add", "polish-pass", "budget-check"],
    },
    "stress": {
        "match": ["stress", "qa", "test", "performance", "phase 7", "adversarial", "ruthless", "verify", "break"],
        "skills": [
            {"name": "adversarial_stress_qa", "description": "Adversarial stress tests that intentionally try to break the build.",
             "steps": ["Pick stress target", "Run methodology", "Capture metrics", "Record failure repro"]},
            {"name": "performance_audit", "description": "Audit frame time, draw calls, memory, GC, exceptions vs published budgets.",
             "steps": ["Collect metrics", "Compare to budget", "Write pass/fail", "Report blockers"]},
        ],
        "tools": ["stress-test", "perf-metrics", "repro-report", "budget-verify"],
    },
    "integration": {
        "match": ["integrat", "assemble", "scene assembler", "smoke", "merge"],
        "skills": [
            {"name": "scene_assembly", "description": "Assemble accepted assets into final scenes, never inventing features.",
             "steps": ["Collect accepted assets", "Place in scene", "Verify collisions/lighting", "Smoke test"]},
            {"name": "handoff_verification", "description": "Verify every integrated piece ships with its handoff report and criteria.",
             "steps": ["Check handoff reports", "Verify acceptance criteria", "Report breakage"]},
        ],
        "tools": ["assemble-scene", "smoke-test", "verify-handoff", "report-breakage"],
    },
}
# Generic supervision toolkit every supervisor receives regardless of job.
BASE_SUPERVISOR_SKILLS = [
    {"name": "delegation", "description": "Issue precise task specs + acceptance criteria to swarm workers.",
     "steps": ["Write task spec", "Set acceptance criteria", "Dispatch to worker", "Await handoff"]},
    {"name": "handoff_report", "description": "Produce a structured handoff report to the orchestrator.",
     "steps": ["Collect results", "Check acceptance criteria", "Write performance notes", "Report blockers"]},
]
BASE_SUPERVISOR_TOOLS = ["delegate", "review", "verify", "handoff-report",
                         "probe-memory", "procedural-execute"]


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def slug(text: str) -> str:
    out = "".join(c if (c.isalnum() or c in "-_") else "-" for c in text.lower())
    return out.strip("-") or "agent"


def detect_job(sv: dict) -> str:
    """Score the supervisor's name + prompt + capabilities against the job
    packages and return the best-matching job id ('general' if none)."""
    text = " ".join([
        sv.get("name", ""),
        sv.get("prompt", ""),
        " ".join(sv.get("capabilities", [])),
    ]).lower()
    best, best_score = "general", 0
    for job, pkg in JOB_PACKAGES.items():
        score = 0
        for kw in pkg["match"]:
            if kw in text:
                score += 1
        if score > best_score:
            best, best_score = job, score
    return best


def supervisor_skills_tools(sv: dict) -> tuple[list[dict], list[str]]:
    """Job-appropriate skills (procedural specs) + tools for a supervisor."""
    job = detect_job(sv)
    pkg = JOB_PACKAGES.get(job)
    skills = list(BASE_SUPERVISOR_SKILLS)
    tools = list(BASE_SUPERVISOR_TOOLS)
    if pkg:
        skills += pkg.get("skills", [])
        tools = list(dict.fromkeys(tools + pkg.get("tools", [])))
    return skills, tools


def _register_skills(skill_specs: list[dict], scope: str, dry_run: bool) -> list[str]:
    """Register each skill as a procedural skill in the mem20 store.

    Returns the list of skill names registered (or planned in dry-run mode)."""
    registered: list[str] = []
    if dry_run:
        return [s["name"] for s in skill_specs]
    from mem20agentz._substrate import get_backend
    b = get_backend()
    for spec in skill_specs:
        name = spec["name"]
        try:
            b.procedural_register(
                name=name,
                description=spec.get("description", ""),
                steps=spec.get("steps", ["execute"]),
                category="harness_" + scope,
            )
            registered.append(name)
        except Exception as exc:
            print(f"[harness] skill register failed for {name}: {exc}")
    return registered


# ---------------------------------------------------------------------------
# Supervisor build (mem20agentz)
# ---------------------------------------------------------------------------

def _build_supervisor(sv: dict, project: dict, dry_run: bool) -> dict:
    """Create ONE supervisor as a mem20agentz profile, in sequence."""
    name = sv["name"]
    identity = f"{name} — Phase Supervisor for {project.get('name', 'project')} " \
               f"swarm. Prompt: {sv['prompt'][:200]}"
    capabilities = list(dict.fromkeys(sv.get("capabilities", []) + [A2A_CAPABILITY]))
    values = list(dict.fromkeys(sv.get("values", []) + A2A_VALUES))
    skills, tools = supervisor_skills_tools(sv)
    job = detect_job(sv)

    if not dry_run:
        from mem20agentz.profiles import Profiles
        Profiles().create(name=name, identity=identity,
                          capabilities=capabilities, values=values)
        # job-appropriate procedural skills actually registered in mem20
        _register_skills(skills, f"supervisor_{slug(name)}", dry_run=dry_run)
        # memory entry: supervisor roster fact
        _remember_roster(project.get("id", ""), "supervisor",
                         {"name": name, "prompt": sv.get("prompt"),
                          "capabilities": capabilities, "values": values,
                          "job": job, "skills": [s["name"] for s in skills],
                          "tools": tools})

    return {
        "type": "supervisor",
        "subsystem": "mem20agentz",
        "name": name,
        "identity": identity,
        "job": job,
        "capabilities": capabilities,
        "values": values,
        "skills": [s["name"] for s in skills],
        "tools": tools,
        "a2a": True,
        "status": "planned" if dry_run else "created",
    }


# ---------------------------------------------------------------------------
# Swarm build (mem20crewz)
# ---------------------------------------------------------------------------

def _tools_for_agent(agent: dict, skills: list[str]) -> list[str]:
    """A worker gets the tools bound to its declared skills."""
    tools: list[str] = []
    for skill in skills:
        for job, pkg in JOB_PACKAGES.items():
            if any(kw in skill.lower() for kw in pkg["match"]):
                for t in pkg.get("tools", []):
                    if t not in tools:
                        tools.append(t)
    return tools or ["procedural-execute"]


def _build_swarm_member(member: dict, dry_run: bool) -> dict:
    name = member["name"]
    skills = list(member.get("skills", []))
    tools = _tools_for_agent(member, skills)

    if not dry_run:
        from mem20crewz import Agent as CrewzAgent
        agent = CrewzAgent(
            role=name,
            goal=member.get("prompt", ""),
            capabilities=skills,
            tools=tools,
        )
        agent.persist_identity(actor=name)

    return {
        "type": "swarm_member",
        "subsystem": "mem20crewz",
        "name": name,
        "supervisor": member.get("supervisor", ""),
        "skills": skills,
        "tools": tools,
        "a2a": False,
        "status": "planned" if dry_run else "created",
    }


# ---------------------------------------------------------------------------
# Orchestrator build
# ---------------------------------------------------------------------------

def _build_orchestrator(project: dict, dry_run: bool) -> dict:
    orch = project.get("orchestrator", {})
    name = orch.get("name") or f"{project.get('name', 'project')}-orchestrator"
    identity = f"Top-Level Orchestrator for {project.get('name', 'project')}. " \
               f"Master prompt: {orch.get('prompt', '')[:200]}"
    caps = list(dict.fromkeys(["orchestrate", "supervision",
                               "delegate", "phase-gating"] + [A2A_CAPABILITY]))
    skills = [
        {"name": "phase_gating", "description": "Enforce phase gates: no phase advances until exit criteria pass.",
         "steps": ["Check phase exit criteria", "Review handoff reports", "Gate or advance phase"]},
        {"name": "risk_register", "description": "Maintain the production risk register and escalate blockers.",
         "steps": ["Log risk", "Assess severity", "Assign owner", "Track to closure"]},
        {"name": "orchestration", "description": "Conduct supervisors one at a time and synthesize their reports.",
         "steps": ["Select next supervisor", "Brief with phase context", "Receive handoff report", "Update project state"]},
    ]
    tools = ["delegate", "review", "verify", "handoff-report",
             "probe-memory", "procedural-execute", "phase-gate", "risk-log"]
    if not dry_run:
        from mem20agentz.profiles import Profiles
        Profiles().create(name=name, identity=identity,
                          capabilities=caps, values=list(A2A_VALUES))
        _register_skills(skills, f"orchestrator_{slug(name)}", dry_run=dry_run)
        _remember_roster(project.get("id", ""), "orchestrator",
                         {"name": name, "prompt": orch.get("prompt"),
                          "capabilities": caps,
                          "skills": [s["name"] for s in skills], "tools": tools})
    return {
        "type": "orchestrator",
        "subsystem": "mem20agentz",
        "name": name,
        "identity": identity,
        "capabilities": caps,
        "values": list(A2A_VALUES),
        "skills": [s["name"] for s in skills],
        "tools": tools,
        "a2a": True,
        "status": "planned" if dry_run else "created",
    }


# ---------------------------------------------------------------------------
# Roster logging (mem20 memory store)
# ---------------------------------------------------------------------------

def _remember_roster(project_id: str, kind: str, payload: dict) -> None:
    try:
        import os
        entries = os.environ.get("MEM20_ENTRIES", "/opt/mem20/entries")
        if os.path.isdir(entries):
            path = os.path.join(
                entries, f"harness-roster-{project_id}-{slug(str(payload.get('name', kind)))}.json")
            with open(path, "w") as fh:
                json.dump({"kind": f"roster:{kind}", "project_id": project_id,
                           "payload": payload, "ts": _now()}, fh, indent=2)
    except Exception as exc:
        print(f"[harness] roster log failed: {exc}")


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def build_project(project: dict, dry_run: bool = True) -> dict:
    # 1. orchestrator (a2a)
    orch = _build_orchestrator(project, dry_run)
    # 2. supervisors strictly in sequence, one at a time (a2a each)
    supervisors = [_build_supervisor(sv, project, dry_run)
                   for sv in project.get("supervisors", [])]
    # 3. swarm per supervisor (no a2a)
    swarm = [_build_swarm_member(m, dry_run)
             for m in project.get("swarm", {}).get("members", [])]

    return {
        "dry_run": dry_run,
        "project_id": project.get("id", ""),
        "project_name": project.get("name", ""),
        "orchestrator": orch,
        "supervisors_built": supervisors,
        "swarm_built": swarm,
        "summary": {
            "orchestrator": 1,
            "supervisors": len(supervisors),
            "swarm_members": len(swarm),
            "a2a_peers": 1 + len(supervisors),  # orchestrator + supervisors only
        },
        "ts": _now(),
    }