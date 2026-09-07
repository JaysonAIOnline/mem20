# mem20 packaging

This directory holds the build/packaging glue for the four distribution channels.
The MCP server runtime itself (`mcp/mcp_server.py`) is **never** modified by any
of this — it always runs as a script, exactly as `python mcp/mcp_server.py`.

```
packaging/
├── sync_runtime.sh     # copies mcp/  ->  mem20_runtime/mcp  (package data source)
├── deb/
│   └── build-deb.sh    # builds a .deb (venv + systemd unit + health probe)
└── README.md           # this file
```

## Layout rationale

The local `mcp/` directory must **not** become an importable package (doing so
would shadow the `mcp` SDK that `mcp/server.py` imports via
`from mcp.server import Server`). So:

- `mcp/` stays a *script* directory (no `__init__.py` at its root).
- `launcher.py` (repo root) is the console-script entry point (`mem20-mcp`). It
  locates the bundled server directory (shipped as package data inside
  `mem20_runtime/mcp/`) via `importlib.resources`, puts it on `sys.path`, and runs
  `mcp_server.py` with `runpy` — byte-for-byte equivalent to
  `python mcp/mcp_server.py`.
- `packaging/sync_runtime.sh` keeps `mem20_runtime/mcp/` in sync with the real
  `mcp/` so the packaged copy never drifts. Run it before building a wheel/release.

`memory_engine/` is the engine package, exposed as the top-level `memory` module
via the repo-root `memory.py` shim (`py-modules = ["memory"]`).

## Channels

| Channel | How to build | Output |
|---------|--------------|--------|
| pip     | `make install` (or `pip install .`) | `mem20-mcp` console script |
| docker  | `make docker` (or `docker build -t mem20 .`) | image, `docker-compose.yml` provided |
| npm     | `make npm` (or `cd dashboard && npm run build`) | static `dashboard/dist/` |
| apt     | `make deb` (or `bash packaging/deb/build-deb.sh`) | `packaging/deb/mem20_*.deb` |

The npm dashboard talks to the **optional** HTTP bridge (`bridge/server.py`),
which is shipped separately and does not affect the MCP server.

See the top-level `README.md` → **Installation** for end-user commands.
