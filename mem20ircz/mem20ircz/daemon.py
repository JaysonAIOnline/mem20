"""The systemd entrypoint: own the connections, serve the socket, stay up."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading

from .hub import Hub
from .ipc import DEFAULT_SOCKET, HubError, HubServer

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 6667
DEFAULT_CHANNEL = "#mem20"
DEFAULT_NICK = "mem20agents"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def serve(socket_path: str = DEFAULT_SOCKET, host: str = DEFAULT_HOST,
          port: int = DEFAULT_PORT, channel: str = DEFAULT_CHANNEL,
          nick: str = DEFAULT_NICK, buffer_size: int = 500) -> int:
    hub = Hub(host=host, port=port, channels=(channel,), default_nick=nick,
              buffer_size=buffer_size)

    # Bind the socket *before* connecting, so an agent that asks "is the hub
    # up" gets a real answer instead of a refused connection during the window
    # where the daemon is still dialling.
    try:
        server = HubServer(socket_path, hub)
    except HubError as exc:
        # Another hub owns the socket. Say so plainly and exit non-zero rather
        # than dying with a traceback -- this is a normal, expected refusal.
        sys.stderr.write(f"mem20ircz: {exc}\n")
        return 1
    threading.Thread(target=server.serve_forever, daemon=True,
                     name="hub-ipc").start()

    hub.join(nick)
    sys.stderr.write(
        f"mem20ircz: hub on {socket_path}, watching {channel} on "
        f"{host}:{port} as {nick}\n")
    sys.stderr.flush()

    stopping = threading.Event()

    def _shutdown(signum, _frame):  # noqa: ANN001
        sys.stderr.write(f"mem20ircz: signal {signum}, shutting down\n")
        stopping.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _shutdown)

    try:
        while not stopping.is_set():
            stopping.wait(1.0)
    finally:
        server.shutdown()
        server.server_close()
        hub.stop()
    return 0


def main(argv=None) -> int:  # noqa: ANN001
    """Entry point for ``mem20ircz-daemon``.

    Argument parsing is not decoration here. The fleet control plane
    (mem20controlz) discovers every console script in the venv and health-probes
    it with ``<binary> --json health``. An entry point that ignored argv and
    started a server unconditionally turned that routine probe into a second hub
    fighting the first one for the socket. So: ``health`` reports and exits,
    ``serve`` is the long-lived path, and anything unrecognised says so rather
    than quietly becoming a daemon.
    """
    parser = argparse.ArgumentParser(
        prog="mem20ircz-daemon",
        description="Own the persistent IRC connection and serve the hub socket.")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="machine-readable output")
    parser.add_argument("--socket", default=None,
                        help=f"hub socket path (default {DEFAULT_SOCKET})")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("serve", help="run the hub (default)")
    sub.add_parser("health", help="report hub status and exit")
    args = parser.parse_args(argv)

    socket_path = args.socket or os.environ.get("MEM20IRCZ_SOCKET",
                                                DEFAULT_SOCKET)

    if args.cmd == "health":
        from .ipc import HubClient, HubError
        try:
            status = HubClient(socket_path).status()
        except HubError as exc:
            if args.as_json:
                print(json.dumps({"ok": False, "healthy": False,
                                  "error": str(exc)}))
            else:
                print(f"unhealthy: {exc}", file=sys.stderr)
            return 1
        if args.as_json:
            print(json.dumps({"ok": True, "healthy": True, "status": status},
                             default=str))
        else:
            print(f"healthy: {len(status['connections'])} connection(s)")
            for nick, st in status["connections"].items():
                print(f"  {nick}: {'up' if st['connected'] else 'down'}")
        return 0

    if args.cmd not in (None, "serve"):
        parser.print_help()
        return 2

    return serve(
        socket_path=socket_path,
        host=os.environ.get("MEM20IRCZ_HOST", DEFAULT_HOST),
        port=_env_int("MEM20IRCZ_PORT", DEFAULT_PORT),
        channel=os.environ.get("MEM20IRCZ_CHANNEL", DEFAULT_CHANNEL),
        nick=os.environ.get("MEM20IRCZ_NICK", DEFAULT_NICK),
        buffer_size=_env_int("MEM20IRCZ_BUFFER", 500),
    )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())