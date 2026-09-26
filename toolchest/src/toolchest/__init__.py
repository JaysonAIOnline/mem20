"""toolchest — mem20 tool inventory registry.

Real discovery over real on-box sources:

- the mem20 MCP server's canonical tool table (``Mem20MCPServer.tools``),
- executable CLI binaries on the box (``/usr/local/bin``, ``/root/.venv/bin``),
- native mem20*z subsystems (``pyproject.toml`` + runtime install checks).

The generated machine-readable inventory is ``inventory.json``; query it with
``python -m toolchest list|search|show``.
"""

__version__ = "0.1.0"