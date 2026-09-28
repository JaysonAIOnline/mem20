"""mem20owebz CLI — gateway, chat web, model listing, doctor."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from .config import load_env_files, parse_config
from .gateway import DEFAULT_CONFIG_PATH

import functools

try:
    from mem20cliz import json_main
except ImportError as _exc:  # never fail silently: a hidden fallback looks like success
    import sys as _sys

    def json_main(func):
        @functools.wraps(func)
        def _warn(*a, **k):
            _sys.stderr.write(
                "warning: mem20cliz unavailable, --json disabled for this CLI (%s)\n" % _exc
            )
            return func(*a, **k)

        return _warn


def _cmd_models(args) -> int:
    load_env_files()
    cfg = parse_config(args.config)
    keyed = cfg.keyed()
    print(f"routes: {len(cfg.routes)}  |  router groups: {sorted(cfg.router_groups)}")
    print(f"keyed (usable): {len(keyed)}")
    for r in keyed:
        print(f"  {r.display_name():34s} -> {r.upstream_model}")
    return 0


def _cmd_doctor(args) -> int:
    from .config import ENV_FILE, ENV_FALLBACK_FILE, env

    ok = True
    # global mem20 llm.py first, so its resolved keys are visible too
    for path in ("/opt/mem20/llm.py",):
        import importlib.util  # noqa: F401 - llm.py loads itself on import

    load_env_files()
    sys.path.insert(0, "/opt/mem20")
    try:
        import llm as _llm  # noqa: F401 - side-effect: loads secrets chain

        primary = _llm._config()
        print(f"primary: base={primary[0]} model={primary[2]} key={'set' if primary[1] else 'MISSING'}")
    except Exception as exc:
        print(f"mem20 llm.py load failed: {exc}")
        ok = False

    print(f"secrets home: {ENV_FILE} exists={os.path.exists(ENV_FILE)} fallback={os.path.exists(ENV_FALLBACK_FILE)}")
    cfg = parse_config(args.config)
    print(f"config: {args.config} routes={len(cfg.routes)} keyed={len(cfg.keyed())}")
    missing = []
    for r in cfg.routes:
        if r.key_env and not env(r.key_env):
            if r.key_env not in missing:
                missing.append(r.key_env)
    if missing:
        print(f"keys NOT present (routes will be skipped honestly): {missing}")
    else:
        print("all referenced keys present")
    return 0 if ok else 1


def _cmd_serve(args) -> int:
    from .gateway import run_serve as run_gateway

    try:
        asyncio.run(run_gateway(args.config, args.host, args.port))
    except KeyboardInterrupt:
        pass
    return 0


def _cmd_chat(args) -> int:
    from .server import run_serve as run_chat

    try:
        asyncio.run(run_chat(args.config, args.host, args.port))
    except KeyboardInterrupt:
        pass
    return 0


@json_main
def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="mem20owebz", description="mem20 chat + model gateway (native)")
    p.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="route config YAML")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("models", help="list routes and which are keyed").set_defaults(func=_cmd_models)
    sub.add_parser("doctor", help="health check of config + keys").set_defaults(func=_cmd_doctor)
    s = sub.add_parser("serve", help="run the model gateway proxy")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=4000)
    s.set_defaults(func=_cmd_serve)
    c = sub.add_parser("chat", help="run the chat web app + gateway")
    c.add_argument("--host", default="0.0.0.0")
    c.add_argument("--port", type=int, default=3000)
    c.set_defaults(func=_cmd_chat)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
