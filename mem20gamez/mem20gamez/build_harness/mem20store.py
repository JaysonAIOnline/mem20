"""mem20 memory store mirror for the harness.

Projects are persisted to the mem20 memory store (substrate backend) using the
same self-model namespace pattern mem20agentz uses, so project state survives
independently of the on-disk JSON cache.
"""

from __future__ import annotations

import json
import os

MEM20_ENTRIES = os.environ.get("MEM20_ENTRIES", "/opt/mem20/entries")
NAMESPACE_PREFIX = "harness:project"


def _entry_path(pid: str) -> str:
    return os.path.join(MEM20_ENTRIES, f"{NAMESPACE_PREFIX}-{pid}.json")


def mirror_projects(projects: dict) -> list[str]:
    """Write one JSON entry per project into the mem20 entries store."""
    written = []
    for pid, project in projects.items():
        path = _entry_path(pid)
        payload = {
            "namespace": f"{NAMESPACE_PREFIX}:{pid}",
            "kind": "harness_project",
            "project_id": pid,
            "project": project,
        }
        if os.path.isdir(MEM20_ENTRIES):
            with open(path, "w") as fh:
                json.dump(payload, fh, indent=2)
            written.append(path)
        else:
            store_fact(parser=pdict(project), note=f"harness project {pid}",
                       tags=["harness", "project"], verbose=False)
            written.append("memory-store")
    return written


def pdict(project: dict) -> dict:
    """Flatten a project into a light fact dict for the memory scaffold."""
    return {
        "project": project.get("name", pid_of(project)),
        "id": project.get("id", ""),
        "status": project.get("status", "setup"),
        "supervisors": len(project.get("supervisors", [])),
        "swarm_members": len(project.get("swarm", {}).get("members", [])),
    }


def pid_of(project: dict) -> str:
    return project.get("id", "unknown")


def store_fact(parser=None, note: str = "", tags=None, verbose: bool = False) -> None:
    """Write a fact to the mem20 entries store (best-effort, no-op if absent)."""
    if not parser:
        return
    try:
        topic = parser.get("project", note)
        line = {
            "namespace": f"harness:fact",
            "topic": topic,
            "content": json.dumps(parser),
            "tags": ",".join(tags or []),
            "note": note,
        }
        path = os.path.join(MEM20_ENTRIES, f"harness-fact-{topic}.json")
        if os.path.isdir(MEM20_ENTRIES):
            with open(path, "w") as fh:
                json.dump(line, fh, indent=2)
        if verbose:
            print(f"[harness] fact -> {path}")
    except Exception as exc:
        if verbose:
            print(f"[harness] fact write failed: {exc}")


def list_projects_from_mem20() -> list[dict]:
    """Re-hydrate projects from the mem20 entries store (fallback list source)."""
    if not os.path.isdir(MEM20_ENTRIES):
        return []
    out = []
    prefix = f"{NAMESPACE_PREFIX}-"
    for fn in sorted(os.listdir(MEM20_ENTRIES)):
        if not fn.startswith(prefix) or not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(MEM20_ENTRIES, fn)) as fh:
                data = json.load(fh)
            project = data.get("project")
            if project:
                out.append(project)
        except Exception:
            continue
    return out