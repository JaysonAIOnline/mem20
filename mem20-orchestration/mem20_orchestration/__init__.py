"""mem20-orchestration — Blender operator orchestration for the mem20 estate.

Queries the real captured `bpy.ops` surface and validates op sequences against
it, so a wrong operator is a clear report instead of a runtime AttributeError
inside a live Blender session.
"""

from .catalog import Catalog, CatalogError, Op, load
from .planner import Finding, Report, load_plan, save_plan, validate

__all__ = [
    "Catalog", "CatalogError", "Op", "load",
    "Finding", "Report", "validate", "load_plan", "save_plan",
]
__version__ = "0.1.0"
