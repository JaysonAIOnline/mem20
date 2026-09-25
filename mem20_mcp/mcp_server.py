#!/usr/bin/env python3
"""Entry-point shim for the mem20 MCP server.

server.py in this package is a read-only forwarder to the canonical,
running server implementation at /opt/mem20/mcp (see mem20_mcp._forward),
so ``main`` here is the exact real main. This file preserves the familiar
entry-point shape (mcp/mcp_server.py).
"""
from server import main


def _track_first_run():
    # Best-effort install/run telemetry. Never blocks startup.
    try:
        import install_tracker
        install_tracker.report_first_run("runtime")
    except Exception:
        pass


if __name__ == "__main__":
    _track_first_run()
    main()
