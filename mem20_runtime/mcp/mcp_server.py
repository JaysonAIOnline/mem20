#!/usr/bin/env python3
"""Entry-point shim for the mem20 MCP server.

The real implementation lives in server.py; this file preserves the
systemd ExecStart path (mcp/mcp_server.py).
"""
from server import main

if __name__ == "__main__":
    main()
