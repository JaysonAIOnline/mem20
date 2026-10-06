"""mem20botz CLI.

    mem20botz serve          run the crew in the foreground (the systemd path)
    mem20botz serve-dreamer  run only dreamer, on #dreamz
    mem20botz bots           list the bots and what each one is for
    mem20botz whoami         show who Jayson is, as a bot would report it
    mem20botz jobs [board]   open work, without joining IRC
    mem20botz watch          tail the channel as a plain client
    mem20botz version

``jobs`` and ``watch`` exist because "what is on the board" and "what did they
say" are questions you will ask from a shell, and forcing yourself into an IRC
client to answer them is a good way to never ask.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Optional, Sequence

from . import __version__
from .crew import Crew
from .identity import operator_card
from .irc import IRCClient
from .kanban_bot import KanbanBot


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mem20botz",
        description="mem20 IRC crew chat — agents orchestrated in the open.",
    )
    p.add_argument("--version", action="store_true",
                   help="print version and exit")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("serve", help="run the crew in the foreground")
    s.add_argument("--channel", default="#mem20")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=6667)
    s.add_argument("--board", default="Fleet HQ")
    s.add_argument("--advertise-every", type=int, default=60,
                   help="seconds between new-job notices (min 15)")
    s.add_argument("--no-relay", action="store_true",
                   help="run without the memory relay")

    s = sub.add_parser("serve-dreamer",
                       help="run only dreamer, on the dream channel")
    s.add_argument("--channel", default="#dreamz")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=6667)

    sub.add_parser("bots", help="list the bots and their sources of truth")

    s = sub.add_parser("whoami", help="who Jayson is")
    s.add_argument("--json", action="store_true", dest="as_json")

    s = sub.add_parser("jobs", help="open work on a board")
    s.add_argument("board", nargs="?", default="Fleet HQ")

    s = sub.add_parser("watch", help="tail the channel")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=6667)
    s.add_argument("--channel", default="#mem20")
    s.add_argument("--nick", default="watch")
    s.add_argument("--seconds", type=int, default=60,
                   help="how long to watch (bounded on purpose)")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.version:
        print(f"mem20botz {__version__}")
        return 0
    if not args.cmd:
        build_parser().print_help()
        return 2

    if args.cmd == "serve-dreamer":
        # Dreamer has her own channel and her own unit. She is not part of the
        # board crew, so she is served alone rather than added to Crew, which
        # would put her in #mem20 as well.
        from .dreamer_bot import DreamerBot

        dreamer = DreamerBot(channel=args.channel, host=args.host,
                             port=args.port)
        try:
            dreamer.run()
        except KeyboardInterrupt:
            dreamer.stop()
        return 0

    if args.cmd == "serve":
        crew = Crew(channel=args.channel, host=args.host, port=args.port,
                    board=args.board, advertise_every=args.advertise_every,
                    start_relay=not args.no_relay)
        try:
            crew.run()
        except KeyboardInterrupt:
            crew.stop()
        return 0

    if args.cmd == "bots":
        # Built without connecting, so this answers even when the daemon is
        # down — which is exactly when you want to know what should be running.
        # Crew is imported at module scope. Re-importing it here would make
        # `Crew` a function-local name for the whole of main(), which broke the
        # serve path with UnboundLocalError -- and no unit test calls main().
        # Built without connecting, so this answers even when the daemon is
        # down -- which is exactly when you want to know what should be running.
        # The list comes from Crew itself so it cannot drift from what is up.
        for cls in Crew.bot_classes():
            print(cls().describe())
            print()
        return 0

    if args.cmd == "whoami":
        import json
        from .identity import OPERATOR_PROFILE
        if args.as_json:
            print(json.dumps(OPERATOR_PROFILE, indent=2))
        else:
            print(operator_card())
        return 0

    if args.cmd == "jobs":
        bot = KanbanBot()
        try:
            print(bot.cmd_jobs(bot, None, args.board))  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001
            print(f"error: {exc}", file=sys.stderr)
            return 1
        return 0

    if args.cmd == "watch":
        # Bounded on purpose: a watch that never returns is a hang, and the
        # bounded form is also what makes this scriptable in CI.
        deadline = time.time() + max(1, args.seconds)
        seen = 0

        def show(msg):
            nonlocal seen
            if msg.command == "PRIVMSG" and msg.text:
                print(f"<{msg.nick}> {msg.text}")
                sys.stdout.flush()
                seen += 1

        client = IRCClient(host=args.host, port=args.port, nick=args.nick,
                           channels=(args.channel,), on_message=show,
                           realname="mem20botz watch")
        try:
            client.connect()
        except OSError as exc:
            print(f"error: cannot reach the IRC daemon: {exc}", file=sys.stderr)
            return 1
        try:
            while time.time() < deadline:
                msg = client.read_message()
                if msg is not None:
                    client.dispatch(msg)
        except Exception as exc:  # noqa: BLE001
            print(f"error: {exc}", file=sys.stderr)
            return 1
        finally:
            client.close()
        if not seen:
            print(f"(no messages on {args.channel} in "
                  f"{args.seconds}s — the channel is quiet)")
        return 0

    build_parser().print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
