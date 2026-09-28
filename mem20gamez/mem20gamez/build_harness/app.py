"""Swarm Harness — frontend for building mem20 multi-agent projects.

Flow: project picker -> orchestrator prompt -> supervisor prompts (up to 15)
-> agent prompts per supervisor -> orchestrator build (supervisors via
mem20agentz, swarms via mem20crewz/mem20kimiz).

All state persists through the mem20 memory store (substrate backend).
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

PROJECT_DIR = Path(
    os.environ.get("HARNESS_PROJECT_DIR", "/opt/mem20/store/harness")
).expanduser()
STATIC_DIR = Path(
    os.environ.get("HARNESS_STATIC_DIR", str(Path(__file__).resolve().parent / "static"))
)
DATA_FILE = PROJECT_DIR / "projects.json"


# ---------------------------------------------------------------------------
# Sibling-module resolution
# ---------------------------------------------------------------------------
# The harness originally ran as a loose `harness/src/` directory and imported its
# siblings flat (`import src.runner`). Installed inside mem20gamez that form
# does not exist, so resolve a sibling by trying each layout in turn rather than
# hard-coding one and failing silently at call time.
def _sibling(name: str):
    import importlib
    for candidate in (
        f"{__package__}.{name}",   # installed: mem20gamez.build_harness.<name>
        f"src.{name}",              # original layout: src/runner.py
        name,                       # flat: runner.py beside sys.path
    ):
        try:
            return importlib.import_module(candidate)
        except ImportError:
            continue
    raise ImportError(f"harness module {name!r} not found in any known layout")


app = FastAPI(title="Swarm Harness")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Persistence: JSON on disk, mirrored into mem20 memory store on write
# ---------------------------------------------------------------------------

def _load_projects() -> dict:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def _save_projects(projects: dict) -> None:
    # The project directory is configuration, not something a caller should have
    # to remember to create: a fresh HARNESS_PROJECT_DIR used to make the very
    # first write fail with FileNotFoundError.
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(projects, indent=2))
    _mirror_to_mem20(projects)


def _mirror_to_mem20(projects: dict) -> None:
    """Best-effort mirror: each project logged as a memory fact."""
    try:
        mem20store = _sibling('mem20store')
        mem20store.mirror_projects(projects)
    except Exception as exc:  # never block the UI on mirror failure
        print(f"[harness] mem20 mirror skipped: {exc}")


# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _new_project(name: str, description: str = "") -> dict:
    return {
        "id": uuid.uuid4().hex[:12],
        "name": name,
        "description": description,
        "created_at": _now(),
        "updated_at": _now(),
        "orchestrator": {"prompt": "", "name": name + " Orchestrator", "ready": False},
        "supervisors": [],
        "swarm": {"members": [], "ready": False},
        "status": "setup",
        "run_log": [],
    }


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ProjectCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""


class OrchestratorPrompt(BaseModel):
    prompt: str = Field(min_length=1)
    name: str = ""


class SupervisorPrompt(BaseModel):
    name: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    capabilities: list[str] = Field(default_factory=list)
    values: list[str] = Field(default_factory=list)


class AgentPrompt(BaseModel):
    name: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    supervisor: str = ""


# ---------------------------------------------------------------------------
# Routes: projects
# ---------------------------------------------------------------------------

@app.get("/api/projects")
def list_projects():
    projects = _load_projects()
    return [
        {
            "id": p["id"],
            "name": p["name"],
            "status": p.get("status", "setup"),
            "description": p.get("description", ""),
            "created_at": p.get("created_at", ""),
            "supervisor_count": len(p.get("supervisors", [])),
            "swarm_count": len(p.get("swarm", {}).get("members", [])),
        }
        for p in sorted(projects.values(), key=lambda x: x.get("updated_at", ""), reverse=True)
    ]


@app.post("/api/projects")
def create_project(body: ProjectCreate):
    projects = _load_projects()
    project = _new_project(body.name, body.description)
    projects[project["id"]] = project
    _save_projects(projects)
    return project


@app.get("/api/projects/{pid}")
def get_project(pid: str):
    projects = _load_projects()
    project = projects.get(pid)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


# ---------------------------------------------------------------------------
# Routes: prompts
# ---------------------------------------------------------------------------

@app.put("/api/projects/{pid}/orchestrator")
def set_orchestrator(pid: str, body: OrchestratorPrompt):
    projects = _load_projects()
    project = projects.get(pid)
    if not project:
        raise HTTPException(404, "Project not found")
    project["orchestrator"] = {
        "prompt": body.prompt,
        "name": body.name or project.get("name", "Project") + " Orchestrator",
        "ready": True,
    }
    project["updated_at"] = _now()
    _save_projects(projects)
    return project["orchestrator"]


@app.put("/api/projects/{pid}/supervisors")
def set_supervisors(pid: str, body: list[SupervisorPrompt]):
    projects = _load_projects()
    project = projects.get(pid)
    if not project:
        raise HTTPException(404, "Project not found")
    normalized = []
    for i, s in enumerate(body):
        normalized.append({
            "id": s.name.lower().replace(" ", "-") or f"supervisor-{i + 1}",
            "name": s.name,
            "prompt": s.prompt,
            "capabilities": s.capabilities or _default_supervisor_caps(s.name, i),
            "values": s.values or ["accountability", "quality", "no-placeholders"],
            "status": "defined",
            "swarm": [],  # agent swarm members assigned later
        })
    project["supervisors"] = normalized
    project["updated_at"] = _now()
    _save_projects(projects)
    return {"count": len(normalized), "supervisors": normalized}


def _default_supervisor_caps(name: str, index: int) -> list[str]:
    generic = ["coordination", "delegation", "verification", "reporting"]
    hints = {
        "bootstrap": ["scaffolding", "setup", "architecture"],
        "dialogue": ["dialogue", "narrative", "conversation"],
        "office": ["environment", "assets", "level-design"],
        "character": ["characters", "population", "lod"],
        "flow": ["systems", "gameplay", "logic"],
        "polish": ["audio", "vfx", "optimization"],
        "stress": ["qa", "testing", "performance", "adversarial"],
    }
    for key, caps in hints.items():
        if key in name.lower():
            return list(dict.fromkeys(generic + caps))
    return generic


@app.put("/api/projects/{pid}/swarm")
def set_swarm(pid: str, body: list[AgentPrompt]):
    projects = _load_projects()
    project = projects.get(pid)
    if not project:
        raise HTTPException(404, "Project not found")
    supervisors = {s["name"]: s for s in project.get("supervisors", [])}
    members = []
    for a in body:
        supervisor = a.supervisor or ""
        sv = supervisors.get(supervisor)
        if not sv:
            raise HTTPException(400, f"Unknown supervisor '{supervisor}'")
        members.append({
            "id": a.name.lower().replace(" ", "-"),
            "name": a.name,
            "prompt": a.prompt,
            "skills": a.skills,
            "tools": a.tools,
            "supervisor": supervisor,
        })
    project["swarm"] = {"members": members, "ready": True}
    for s in project.get("supervisors", []):
        s["swarm"] = [m for m in members if m["supervisor"] == s["name"]]
    project["updated_at"] = _now()
    _save_projects(projects)
    return {"count": len(members), "members": members}


# ---------------------------------------------------------------------------
# Route: orchestrated build
# ---------------------------------------------------------------------------

# In-memory run registry for async run state (per pid)
_RUNS: dict[str, dict] = {}
_RUN_ACTIVE: dict[str, bool] = {}
_RUN_THREADS: dict[str, object] = {}


def _start_run(pid: str, project: dict, dry_run: bool, phase: str,
               retry_workers: list[str] | None = None) -> dict:
    """Launch run_project in a background thread, tracking state in _RUNS."""
    runner = _sibling('runner')

    run_id = uuid.uuid4().hex[:12]
    _RUNS[pid] = {
        "run_id": run_id, "pid": pid, "status": "running", "phase": "",
        "started": _now(), "finished": "", "phases": {}, "errors": [],
        "summary": {}, "dry_run": dry_run, "phase_filter": phase or "",
        "log": [],
    }
    _RUN_ACTIVE[pid] = True

    def _progress(phase_name, event, data):
        entry = _RUNS.get(pid)
        if not entry:
            return
        entry["phase"] = phase_name
        entry["log"].append({"ts": _now(), "phase": phase_name,
                             "event": event, "data": data})
        if len(entry["log"]) > 2000:
            entry["log"] = entry["log"][-2000:]

    import threading as _th

    def run():
        try:
            result = runner.run_project(
                project, dry_run=dry_run, phase_filter=phase or None,
                retry_workers=retry_workers,
                progress_callback=_progress)
            entry = _RUNS.get(pid)
            if entry:
                entry["status"] = result.get("status", "done")
                entry["phase"] = result.get("phase", "")
                entry["summary"] = result.get("summary", {})
                entry["errors"] = result.get("errors", [])
                entry["finished"] = result.get("finished", "")
                entry["result"] = result  # full run/plan detail
        except Exception as exc:
            entry = _RUNS.get(pid)
            if entry:
                entry["status"] = "error"
                entry["errors"] = [str(exc)]
                entry["finished"] = _now()
        finally:
            _RUN_ACTIVE[pid] = False

    thread = _th.Thread(target=run, daemon=True, name=f"run-{pid}")
    _RUN_THREADS[pid] = thread
    thread.start()
    return _RUNS[pid]


class RunRequest(BaseModel):
    dry_run: bool = False
    phase: str = ""
    retry_workers: list[str] | None = None


@app.post("/api/projects/{pid}/run")
def run_project(pid: str, body: RunRequest):
    projects = _load_projects()
    project = projects.get(pid)
    if not project:
        raise HTTPException(404, "Project not found")
    if not project.get("orchestrator", {}).get("ready"):
        raise HTTPException(400, "Orchestrator prompt not set")
    if not project.get("supervisors"):
        raise HTTPException(400, "No supervisors defined")
    if _RUN_ACTIVE.get(pid):
        raise HTTPException(409, "Run already in progress")
    run_info = _start_run(pid, project, dry_run=body.dry_run, phase=body.phase,
                          retry_workers=body.retry_workers)
    project["status"] = "running"
    project["run_log"].append({
        "ts": _now(), "event": "run_started", "dry_run": body.dry_run,
        "phase_filter": body.phase,
    })
    project["updated_at"] = _now()
    _save_projects(projects)
    return run_info


@app.get("/api/projects/{pid}/run/status")
def run_status(pid: str):
    if pid not in _RUNS:
        return {"run_id": "", "status": "idle", "pid": pid}
    return _RUNS[pid]


# ---------------------------------------------------------------------------
# Static / desktop launch
# ---------------------------------------------------------------------------

@app.post("/api/projects/{pid}/build")
def build_project(pid: str):
    projects = _load_projects()
    project = projects.get(pid)
    if not project:
        raise HTTPException(404, "Project not found")
    if not project.get("orchestrator", {}).get("ready"):
        raise HTTPException(400, "Orchestrator prompt not set")
    if not project.get("supervisors"):
        raise HTTPException(400, "No supervisors defined")

    try:
        worker = _sibling('worker')
        report = worker.build_project(project, dry_run=os.environ.get(
            "HARNESS_DRY_RUN", "1") == "1")
    except Exception as exc:
        raise HTTPException(500, f"Build failed: {exc}")

    project["status"] = "building" if not report.get("dry_run") else "dry-run-ok"
    project["run_log"].append({
        "ts": _now(),
        "event": "build",
        "dry_run": report.get("dry_run", False),
        "supervisors_built": report.get("supervisors_built", []),
        "swarm_built": report.get("swarm_built", []),
    })
    project["updated_at"] = _now()
    _save_projects(projects)
    return report


# ---------------------------------------------------------------------------
# Static / desktop launch
# ---------------------------------------------------------------------------

STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/guide")
@app.get("/api/docs")
def harness_docs(request: Request):
    """The harness guide, rendered. Kept findable from the control surface itself.

    Served at /guide, not /docs: FastAPI already owns /docs for its Swagger UI,
    and shadowing the API reference would be a poor trade. Both are reachable.
    """
    from . import docs as _docs

    if request.url.path.startswith("/api/"):
        return JSONResponse(
            {
                "guide": _docs.pointer(),
                "markdown": _docs.read(),
            }
        )
    return HTMLResponse(_docs.as_html())


@app.get("/")
def index():
    index = STATIC_DIR / "index.html"
    if not index.is_file():
        return JSONResponse(
            {
                "harness": "mem20gamez build harness",
                "static_dir": str(STATIC_DIR),
                "note": "no index.html yet; the API under /api is live",
                "api": sorted(
                    r.path for r in app.routes if getattr(r, "path", "").startswith("/api")
                ),
            }
        )
    return FileResponse(str(index))


def launch() -> None:
    import uvicorn
    uvicorn.run("src.app:app", host="127.0.0.1", port=int(os.environ.get(
        "HARNESS_PORT", "8085")), reload=False)


if __name__ == "__main__":
    launch()