"""Shared read-only forwarder used by every mem20_mcp shim module.

The canonical, *running* mem20 MCP server lives at /opt/mem20/mcp. That fact is
independently proven by the live process table (``/root/.venv/bin/python
/opt/mem20/mcp/mcp_server.py``), by ``mcp-server.service`` (WorkingDirectory and
ExecStart) and by ``/root/.config/opencode/opencode.jsonc``. The mem20_mcp
package is a thin loader that forwards to that single source of truth, so this
package boots the identical real tools instead of stale drift.

Nothing in this package reimplements or caches tool logic: every module here
re-exports the canonical module of the same name. Set ``MEM20_CANONICAL_MCP_ROOT``
to point the forwarder at a different canonical tree (used only in tests).
"""

import importlib.util
import os
import sys

DEFAULT_CANONICAL_ROOT = "/opt/mem20/mcp"


def canonical_root() -> str:
    """Resolve and validate the canonical MCP root, keeping it at sys.path[0].

    Raises ImportError if the canonical tree is missing its server/tools
    layout, so a broken MEM20_CANONICAL_MCP_ROOT fails loudly instead of
    silently importing stale local copies.
    """
    root = os.path.abspath(os.environ.get("MEM20_CANONICAL_MCP_ROOT", DEFAULT_CANONICAL_ROOT))
    if not os.path.isfile(os.path.join(root, "server.py")) or not os.path.isdir(os.path.join(root, "tools")):
        raise ImportError(
            f"mem20_mcp forwards to the canonical server tree at {root} "
            f"(override with MEM20_CANONICAL_MCP_ROOT), but that path has no "
            f"server.py/tools layout. Refusing to load stale local copies."
        )
    if root not in sys.path:
        sys.path.insert(0, root)
    return root


def load(rel_file: str, module_key: str):
    """Load the canonical module at ``<root>/<rel_file>`` under ``module_key``.

    Reuses ``sys.modules[module_key]`` when it is already the canonical file so
    top-level canonical imports and the mem20_mcp forwarding modules share one
    class object. If the key is held by a stale or in-progress module (e.g. a
    bare ``import tools.world_tools`` that resolved to the old local file), the
    canonical file is loaded under a distinct private key instead, so
    forwarding never self-imports.
    """
    root = canonical_root()
    path = os.path.join(root, rel_file)
    existing = sys.modules.get(module_key)
    if existing is not None:
        existing_file = getattr(existing, "__file__", None)
        if existing_file and os.path.abspath(existing_file) == path:
            return existing
        module_key = f"mem20_mcp._fwd.{module_key}"
        existing = sys.modules.get(module_key)
        if existing is not None:
            return existing
    spec = importlib.util.spec_from_file_location(module_key, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load canonical module {module_key} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_key] = module
    spec.loader.exec_module(module)
    return module