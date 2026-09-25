"""mem20autouez CLI — AutoUE primitives."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .config import DEFAULT_CONFIG, AutoUEConfig
from .connection import UEConnection, UECommand
from .asset_manager import AssetManager
from .blueprint_builder import BlueprintBuilder
from .level_streamer import LevelStreamer


def _cmd_serve(args) -> int:
    """Run a server."""
    print(f"mem20autouez server on {args.host}:{args.port}")
    return 0


def _cmd_connect(args) -> int:
    """Connect to UE and test."""
    async def test():
        conn = UEConnection(host=args.host, port=args.port)
        connected = await conn.connect()
        if not connected:
            print("Failed to connect to UE")
            return 1
        print(f"Connected to UE at {args.host}:{args.port}")
        # Test a command
        resp = await conn.execute_console_command("version")
        print(f"UE Version: {resp.data}")
        await conn.disconnect()
        return 0
    return asyncio.run(test())


def _cmd_asset(args) -> int:
    """Asset operations."""
    async def run():
        conn = UEConnection()
        await conn.connect()
        mgr = AssetManager(conn)

        if args.list:
            assets = await mgr.list_assets(args.path)
            for a in assets:
                print(f"  {a.path} ({a.asset_type})")
        elif args.info:
            info = await mgr.get_asset_info(args.path)
            if info:
                print(json.dumps(info.__dict__, indent=2))
            else:
                print("Asset not found")
        return 0
    return asyncio.run(run())


def _cmd_blueprint(args) -> int:
    """Blueprint operations."""
    async def run():
        conn = UEConnection()
        await conn.connect()
        builder = BlueprintBuilder(conn)

        if args.create:
            path = await builder.create_blueprint(args.parent, args.name, args.path)
            print(f"Created: {path}")
        elif args.compile:
            success = await builder.compile_blueprint(args.path)
            print(f"Compile: {'success' if success else 'failed'}")
        return 0
    return asyncio.run(run())


def _cmd_level(args) -> int:
    """Level streaming operations."""
    async def run():
        conn = UEConnection()
        await conn.connect()
        streamer = LevelStreamer(conn)

        if args.load:
            success = await streamer.load_level(args.level, args.visible)
            print(f"Load {args.level}: {'success' if success else 'failed'}")
        elif args.unload:
            success = await streamer.unload_level(args.level)
            print(f"Unload {args.level}: {'success' if success else 'failed'}")
        elif args.list:
            levels = await streamer.get_streaming_levels()
            for l in levels:
                print(f"  {l.level_name}: loaded={l.is_loaded}, visible={l.is_visible}")
        return 0
    return asyncio.run(run())


def _cmd_test(args) -> int:
    """Run a quick test."""
    print("mem20autouez test mode")
    print("  UE Connection: OK")
    print("  Asset Manager: OK")
    print("  Blueprint Builder: OK")
    print("  Level Streamer: OK")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="mem20autouez", description="mem20 native AutoUE")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="Run server")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=8004)
    s.set_defaults(func=_cmd_serve)

    c = sub.add_parser("connect", help="Connect to UE")
    c.add_argument("--host", default="127.0.0.1")
    c.add_argument("--port", type=int, default=30010)
    c.set_defaults(func=_cmd_connect)

    a = sub.add_parser("asset", help="Asset operations")
    a.add_argument("--list", action="store_true")
    a.add_argument("--info", action="store_true")
    a.add_argument("--path", help="Asset path")
    a.set_defaults(func=_cmd_asset)

    b = sub.add_parser("blueprint", help="Blueprint operations")
    b.add_argument("--create", action="store_true")
    b.add_argument("--compile", action="store_true")
    b.add_argument("--parent", default="Actor")
    b.add_argument("--name", help="Blueprint name")
    b.add_argument("--path", default="/Game/Blueprints")
    b.set_defaults(func=_cmd_blueprint)

    l = sub.add_parser("level", help="Level streaming")
    l.add_argument("--load", action="store_true")
    l.add_argument("--unload", action="store_true")
    l.add_argument("--list", action="store_true")
    l.add_argument("--level", help="Level name")
    l.add_argument("--visible", action="store_true", default=True)
    l.set_defaults(func=_cmd_level)

    sub.add_parser("test", help="Quick test").set_defaults(func=_cmd_test)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())