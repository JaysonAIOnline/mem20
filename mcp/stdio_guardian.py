#!/usr/bin/env python3
"""Durable-stdin supervisor for the platform mem20 MCP server under systemd.

The mem20 MCP server (``server.py``) uses the mcp.server.stdio transport
plus a threaded health/ready/metrics endpoint on ``MEM20_HEALTH_PORT``
(:8080). Launched directly under systemd, stdin is /dev/null, so the server
reads EOF and exits immediately (restart loop). This guardian spawns the
real server with stdin attached to a pipe that is held open for the unit's
lifetime, so the platform instance stays up and its health endpoint stays
live. MCP stdio clients still spawn their own per-client instance (e.g. the
opencode session MCP on :8081).

Stdlib-only, so it starts fast and cannot itself leak resources.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "mcp_server.py")
CHILD: subprocess.Popen | None = None


def _terminate(signum, frame):
    if CHILD is not None and CHILD.poll() is None:
        try:
            CHILD.terminate()
            CHILD.wait(timeout=3)
        except (subprocess.TimeoutExpired, OSError):
            CHILD.kill()
    sys.exit(0)


def main() -> int:
    global CHILD
    signal.signal(signal.SIGTERM, _terminate)
    signal.signal(signal.SIGINT, _terminate)
    CHILD = subprocess.Popen(
        [sys.executable, SERVER],
        cwd=HERE,
        stdin=subprocess.PIPE,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    try:
        while CHILD.poll() is None:
            time.sleep(2)
    except KeyboardInterrupt:
        _terminate(0, None)
    return CHILD.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main())