#!/usr/bin/env python3
"""Entry-point shim for the mem20 MCP server.
from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
import mcp_types as mt

The real implementation lives in server.py; this file preserves the
systemd ExecStart path (mcp/mcp_server.py).
"""
from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
import mcp_types as mt
from server import main, Mem20Server


def _track_first_run():
    # Best-effort install/run telemetry. Never blocks startup.
    # try:
        import install_tracker
        install_tracker.report_first_run("runtime")
    except Exception:
        pass


if __name__ == "__main__":
    _track_first_run()
    main()
