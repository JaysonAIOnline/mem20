# mem20_mcp

Thin loader for the **canonical** mem20 MCP server.

The canonical, running server lives at `/opt/mem20/mcp`. That is proven
independently by:

- the live process table (`/root/.venv/bin/python /opt/mem20/mcp/mcp_server.py`)
- `mcp-server.service` (`WorkingDirectory=` and `ExecStart=`)
- `/root/.config/opencode/opencode.jsonc`

Every module in this package is a read-only forwarder to that tree. Nothing here
reimplements or caches tool logic: each module re-exports the canonical module
of the same name. This is why `mem20_mcp` boots the identical real tool set
instead of drifting away from it.

Set `MEM20_CANONICAL_MCP_ROOT` to point the forwarder at a different canonical
tree. That is used only by tests.

## Why this exists

`mem20_mcp` was originally a stale copy of the server whose
`tools/world_tools.py` had lost the `WorldToolsMixin` class, so
`server.py`'s import raised `ImportError` and the package could not boot. Rather
than maintaining a second implementation, the tree was reduced to a loader and
the canonical server became the single source of truth.

## What this package is not

- Not a second MCP server. Starting a server means running the canonical
  `/opt/mem20/mcp/mcp_server.py` (see `mcp-server.service`).
- Not a place to add tools. Add them to `/opt/mem20/mcp/tools/`, which this
  package forwards to.

## Verify

```bash
/root/.venv/bin/python -c "import mem20_mcp; print(mem20_mcp.__canonical_root__)"
```

That prints `/opt/mem20/mcp`.

## Related

- `/opt/mem20/mcp` — the canonical server and the real tool implementations
- `mem20-orchestration/` — **not packaged.** It currently contains a single file,
  `tools/blender_ops.json`, and no Python. It is an unfinished scaffold, not a
  subsystem, and is deliberately left unpackaged rather than shipped as an empty
  package.
