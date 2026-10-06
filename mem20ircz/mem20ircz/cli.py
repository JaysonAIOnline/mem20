"""mem20ircz CLI.

    mem20ircz who                     who is in the room
    mem20ircz status                  connections + what the filter swallowed
    mem20ircz join [nick]             take a nick, get the backlog depth
    mem20ircz read [--since N]        only messages newer than your cursor
    mem20ircz say <text>              send, without waiting for a reply

Output is deliberately one short line per message. The reason this tool exists
is token cost, so a verbose default would defeat it; ``--json`` is there when a
caller genuinely needs the structure.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional, Sequence

from . import __version__
from .ipc import DEFAULT_SOCKET, HubClient, HubError


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mem20ircz",
        description="Agent-side IRC client for the mem20 #mem20 room.",
    )
    p.add_argument("--version", action="store_true",
                   help="print version and exit")
    p.add_argument("--socket", default=DEFAULT_SOCKET,
                   help=f"hub socket path (default {DEFAULT_SOCKET})")
    p.add_argument("--nick", default=None,
                   help="act as this nick (default: the hub's own)")
    p.add_argument("--json", action="store_true", dest="as_json",
                   help="machine-readable output")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("who", help="who else is in the room")
    sub.add_parser("status", help="connections and swallowed-noise counts")
    # The fleet control plane probes every console script it discovers with
    # `<binary> --json health`, so this verb exists to answer that sanely.
    sub.add_parser("health", help="is the hub up and in the room")

    s = sub.add_parser("join", help="take a nick and get the backlog depth")
    # A distinct dest, because a positional called "nick" would overwrite the
    # global --nick value with its own None default and silently drop it.
    s.add_argument("join_nick", nargs="?", default=None, metavar="nick")

    s = sub.add_parser("read", help="messages newer than your cursor")
    s.add_argument("--since", type=int, default=0,
                   help="return only messages after this sequence number")
    s.add_argument("--limit", type=int, default=50)
    s.add_argument("--wait", type=float, default=0.0,
                   help="seconds to wait for the first new message "
                        "(bounded on purpose)")

    s = sub.add_parser("say", help="send a message to the room")
    s.add_argument("text", nargs="+")
    return p


def _wait_for(client: HubClient, since: int, limit: int, nick: Optional[str],
              seconds: float) -> dict:
    """Read now, or block a bounded time for something new.

    Bounded because a client that can wait forever is a client that can hang a
    shell or an agent turn with no way out and no output.
    """
    import time
    deadline = time.time() + max(0.0, seconds)
    while True:
        reply = client.read(since=since, limit=limit, nick=nick)
        if reply.get("count") or time.time() >= deadline:
            return reply
        time.sleep(0.25)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.version:
        print(f"mem20ircz {__version__}")
        return 0
    if not args.cmd:
        build_parser().print_help()
        return 2

    client = HubClient(args.socket)

    try:
        if args.cmd == "health":
            # Healthy means every connection is not merely up but *in the
            # room*. A socket that is connected but has not joined yet cannot
            # hear anything, and reporting that as healthy would be a lie an
            # operator has to debug by hand.
            data = client.status()
            conns = data.get("connections", {})
            healthy = bool(conns) and all(c.get("ready") for c in conns.values())
            if args.as_json:
                print(json.dumps({"ok": healthy, "healthy": healthy,
                                  "connections": {
                                      n: {"connected": c.get("connected"),
                                          "ready": c.get("ready")}
                                      for n, c in conns.items()}},
                                 indent=2, default=str))
            else:
                print("healthy" if healthy else "unhealthy")
                for nick, st in conns.items():
                    print(f"  {nick}: connected={st.get('connected')} "
                          f"ready={st.get('ready')}")
            return 0 if healthy else 1

        if args.cmd == "status":
            data = client.status()
            if args.as_json:
                print(json.dumps(data, indent=2))
                return 0
            print(f"hub: {data['host']}:{data['port']} "
                  f"channels={','.join(data['channels'])}")
            for nick, st in data["connections"].items():
                mark = "up" if st["connected"] else "DOWN"
                print(f"  {nick:<16} {mark:<5} buffered={st['buffered']:<5} "
                      f"seq={st['latest_seq']:<6} "
                      f"reconnects={st['disconnects']}")
                noise = st["noise"]
                if noise["lines_seen"]:
                    print(f"  {'':<16} wire lines={noise['lines_seen']} "
                          f"kept={noise['kept']} "
                          f"swallowed={noise['swallowed']} "
                          f"({noise['waste_ratio'] * 100:.1f}% waste)")
                    for reason, count in sorted(noise["by_reason"].items(),
                                                key=lambda kv: -kv[1]):
                        print(f"  {'':<18}{reason:<14} {count}")
                if st["last_error"]:
                    print(f"  {'':<16} last error: {st['last_error']}")
            return 0

        if args.cmd == "who":
            data = client.who(args.nick)
            if args.as_json:
                print(json.dumps(data, indent=2))
            else:
                print(" ".join(data["nicks"]) or "(nobody seen yet)")
            return 0

        if args.cmd == "join":
            data = client.join(args.join_nick or args.nick)
            if not data.get("ok"):
                print(f"error: {data.get('error')}", file=sys.stderr)
                return 1
            if args.as_json:
                print(json.dumps(data, indent=2))
            else:
                print(f"joined as {data['nick']} "
                      f"(ready={data.get('ready')}, "
                      f"{data['backlog']} messages in backlog, "
                      f"latest seq {data['latest_seq']})")
            # Not ready after waiting means we are in the channel's seat but
            # have not heard its roster yet, so a message sent now could be
            # dropped. Say so rather than implying the join fully succeeded.
            return 0 if data.get("ready") else 1

        if args.cmd == "read":
            data = _wait_for(client, args.since, args.limit, args.nick,
                             args.wait)
            if not data.get("ok"):
                print(f"error: {data.get('error')}", file=sys.stderr)
                return 1
            if args.as_json:
                print(json.dumps(data, indent=2))
                return 0
            if data["truncated"]:
                print(f"note: messages before seq {data['oldest_seq']} have "
                      f"aged out of the buffer", file=sys.stderr)
            if data["disconnects"]:
                print(f"note: connection dropped {data['disconnects']}x; "
                      f"messages during a drop were not received",
                      file=sys.stderr)
            for msg in data["messages"]:
                who = f"{msg['nick']}" if not msg["mine"] else f"{msg['nick']} (me)"
                print(f"<{who}> {msg['text']}")
            print(f"-- {data['count']} new, latest seq {data['latest_seq']}",
                  file=sys.stderr)
            return 0

        if args.cmd == "say":
            data = client.say(" ".join(args.text), nick=args.nick)
            if not data.get("ok"):
                print(f"error: {data.get('error')}", file=sys.stderr)
                return 1
            if args.as_json:
                print(json.dumps(data, indent=2))
            else:
                print(f"sent to {data['nick']}: {data['sent']}")
            return 0

    except HubError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    build_parser().print_help()
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())