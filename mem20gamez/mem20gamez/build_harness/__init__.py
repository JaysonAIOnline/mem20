"""mem20 gamez build harness.

A permanent home for the swarm build harness: a real production pipeline that
drives game-asset generation through Blender, Unity and Godot, orchestrated by
LLM-assigned roles and a worker swarm.

Installed from the owner's `harness-src.zip`. The modules are the harness's own
implementation, kept intact so behaviour does not drift from what was tested:

* `v21` - provider key resolution and role-aware chat, plus the seam that routes
  worker calls by bucket.
* `runner` - the production pipeline: phases, workers, assembly, progress.
* `worker` - builds the orchestrator, supervisors and swarm members.
* `app` - the FastAPI control surface (projects, run, build, status).
* `mem20store` - mirrors project state into the mem20 entries store so it
  survives independently of the on-disk JSON cache.

`bpy` is only importable inside Blender, so it is never imported at module
scope; the harness degrades to planning-only when the tool is absent rather than
refusing to load.
"""

from __future__ import annotations

import os
import sys

# The harness's `v21` seam patches the mem20 substrate's `llm` module, and
# `runner`/`worker` reach for it too. The substrate lives at the estate root
# rather than in site-packages, so put it on the path before anything imports it.
# Same convention the other mem20 packages use; a no-op if it is already there.
_ESTATE_ROOT = os.environ.get("MEM20_ESTATE_ROOT", "/opt/mem20")
if os.path.isdir(_ESTATE_ROOT) and _ESTATE_ROOT not in sys.path:
    sys.path.append(_ESTATE_ROOT)

__all__ = [
    "app",
    "mem20store",
    "runner",
    "v21",
    "worker",
]

__version__ = "0.1.0"


def _load(name: str):
    """Import a harness submodule on demand.

    Kept lazy so that `import mem20gamez.build_harness` stays cheap and does not
    drag in FastAPI or the pipeline for a caller that only wants `v21`.
    """
    import importlib

    return importlib.import_module(f"{__name__}.{name}")


def __getattr__(name: str):
    if name in __all__:
        return _load(name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def surface() -> dict:
    """What this harness can actually do, reported honestly rather than claimed."""
    from . import docs as _docs

    info: dict = {
        "version": __version__,
        "modules": list(__all__),
        "app_routes": [],
        "runner_available": False,
        "v21_available": False,
        "notes": [],
        "docs": _docs.pointer(),
    }
    try:
        app_module = _load("app")
        routes = sorted(
            getattr(r, "path", "") for r in getattr(app_module.app, "routes", [])
        )
        info["app_routes"] = [r for r in routes if r.startswith("/api")]
    except Exception as exc:  # noqa: BLE001
        info["notes"].append(f"app unavailable: {type(exc).__name__}: {exc}")
    try:
        runner = _load("runner")
        info["runner_available"] = callable(getattr(runner, "run_project", None))
    except Exception as exc:  # noqa: BLE001
        info["notes"].append(f"runner unavailable: {type(exc).__name__}: {exc}")
    try:
        _load("v21")
        info["v21_available"] = True
    except Exception as exc:  # noqa: BLE001
        info["notes"].append(f"v21 unavailable: {type(exc).__name__}: {exc}")
    return info
