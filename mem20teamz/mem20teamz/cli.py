"""Teamz CLI: rooms, chat, roster, export, loopback serve."""

from __future__ import annotations

import argparse
import html
import http.server
import json
import os
import sys
import threading
import urllib.parse
from pathlib import Path
from typing import Optional, Sequence

from . import __version__
from .memory import Memory
from .router import route
from .store import Store, StoreError
from .studio import export_markdown


def _home() -> Path:
    root = Path(os.environ.get("MEM20TEAMZ_HOME",
                               Path.home() / ".mem20teamz"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _store(home: Optional[Path] = None) -> Store:
    return Store((home or _home()) / "teamz.sqlite")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mem20teamz",
        description="Mem20Teamz — humans and AI agents side by side.",
    )
    parser.add_argument("--version", action="store_true")
    sub = parser.add_subparsers(dest="command")

    create = sub.add_parser("create", help="Create a room.")
    create.add_argument("room")
    create.add_argument("--topic", default="")

    sub.add_parser("rooms", help="List rooms.")

    join = sub.add_parser("join", help="Join a profile to a room.")
    join.add_argument("room")
    join.add_argument("profile")
    join.add_argument("--kind", default="agent", choices=("human", "agent"))

    post = sub.add_parser("post", help="Post and route a message.")
    post.add_argument("room")
    post.add_argument("sender")
    post.add_argument("text")

    history = sub.add_parser("history", help="Show a transcript.")
    history.add_argument("room")
    history.add_argument("--limit", type=int, default=20)

    export = sub.add_parser("export", help="Export a transcript to markdown.")
    export.add_argument("room")
    export.add_argument("out")

    serve = sub.add_parser("serve", help="Loopback chat server.")
    serve.add_argument("--port", type=int, default=0)
    serve.add_argument("--host", default="127.0.0.1")
    return parser


class _Handler(http.server.BaseHTTPRequestHandler):
    backend: object = None

    def log_message(self, *args) -> None:  # noqa: D102
        pass

    def _json(self, obj: object, status: int = 200) -> None:
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/rooms":
            assert self.backend is not None
            self._json({"ok": True, "rooms": self.backend.rooms()})
        elif parsed.path == "/history":
            query = urllib.parse.parse_qs(parsed.query)
            room = query.get("room", [""])[0]
            assert self.backend is not None
            try:
                self._json({"ok": True,
                            "messages": self.backend.history(room)})
            except StoreError as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
        else:
            self._json({"ok": False, "error": "unknown route"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0) or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            self._json({"ok": False, "error": "bad json"}, 400)
            return
        assert self.backend is not None
        if parsed.path == "/post":
            try:
                record = route(self.backend, payload.get("room", ""),
                               payload.get("sender", ""),
                               payload.get("text", ""))
            except StoreError as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
                return
            self._json({"ok": True, "routing": record["kind"],
                        "woken": [w["profile"] for w in record["woken"]]})
        else:
            self._json({"ok": False, "error": "unknown route"}, 404)


def serve(store: Store, host: str = "127.0.0.1",
          port: int = 0) -> tuple[str, object]:
    httpd = http.server.ThreadingHTTPServer((host, port), _Handler)
    _Handler.backend = store
    actual = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return f"http://{host}:{actual}", httpd


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.version:
        print(f"mem20teamz {__version__}")
        return 0
    if not args.command:
        build_parser().print_help()
        return 0
    store = _store()
    memory = Memory()
    try:
        if args.command == "create":
            record = store.create_room(args.room, args.topic)
            print(json.dumps(record))
        elif args.command == "rooms":
            for room in store.rooms():
                print(f'{room["name"]}: {room["topic"]}')
        elif args.command == "join":
            print(json.dumps(store.join(args.room, args.profile, args.kind)))
        elif args.command == "post":
            record = route(store, args.room, args.sender, args.text)
            memory.remember(args.room, args.sender, args.text)
            print(json.dumps({"kind": record["kind"],
                              "woken": [w["profile"]
                                        for w in record["woken"]],
                              "plan": record["plan"]}, indent=1))
        elif args.command == "history":
            for msg in store.history(args.room, args.limit):
                print(f'[{msg["id"]}] {msg["sender"]}: {msg["text"]}')
        elif args.command == "export":
            rooms = {r["name"]: r for r in store.rooms()}
            if args.room not in rooms:
                print(f"error: unknown room {args.room!r}", file=sys.stderr)
                return 2
            path = export_markdown(args.room, rooms[args.room]["topic"],
                                   store.history(args.room, limit=500),
                                   args.out)
            print(f"wrote {path}")
        elif args.command == "serve":
            base, httpd = serve(store, args.host, args.port)
            print(base, flush=True)
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                httpd.shutdown()
                httpd.server_close()
    except StoreError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
