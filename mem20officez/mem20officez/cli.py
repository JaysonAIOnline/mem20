"""mem20officez CLI — native office server + utilities."""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path

from .config import DEFAULT_CONFIG, OfficeConfig
from .server import run_server

HERE = Path(__file__).parent.parent
HARVEST = HERE / "src_harvest"


def _cmd_serve(args) -> int:
    cfg = OfficeConfig.load(args.config) if args.config else DEFAULT_CONFIG
    if args.host:
        cfg.host = args.host
    if args.port:
        cfg.port = args.port
    if args.gateway:
        cfg.gateway_url = args.gateway
    try:
        asyncio.run(run_server(cfg))
    except KeyboardInterrupt:
        pass
    return 0


def _cmd_build(args) -> int:
    """Build the Next.js frontend for production."""
    print(f"Building Next.js app in {HARVEST}...")
    try:
        # Use existing node_modules if present, otherwise install
        if not (HARVEST / "node_modules").exists():
            print("Installing dependencies...")
            subprocess.run(["npm", "install"], cwd=HARVEST, check=True)
        subprocess.run(["npm", "run", "build"], cwd=HARVEST, check=True)
        # Copy build output to build_dir
        build_dir = DEFAULT_CONFIG.build_dir
        build_dir.mkdir(parents=True, exist_ok=True)
        import shutil
        src_next = HARVEST / ".next"
        dst_next = build_dir / ".next"
        if dst_next.exists():
            shutil.rmtree(dst_next)
        shutil.copytree(src_next, dst_next)
        # Copy public assets
        public_src = HARVEST / "public"
        public_dst = build_dir / "public"
        if public_dst.exists():
            shutil.rmtree(public_dst)
        shutil.copytree(public_src, public_dst)
        print(f"Build complete: {build_dir}")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"Build failed: {e}")
        return 1
    except FileNotFoundError:
        print("npm not found. Install Node.js to build the frontend.")
        return 1


def _cmd_dev(args) -> int:
    """Run Next.js dev server (for development)."""
    print(f"Starting Next.js dev server in {HARVEST}...")
    try:
        os.execvpe("npm", ["npm", "run", "dev"], os.environ)
    except FileNotFoundError:
        print("npm not found. Install Node.js.")
        return 1


def _cmd_doctor(args) -> int:
    """Health check."""
    ok = True
    print(f"Harvest root: {HARVEST} {'OK' if HARVEST.exists() else 'MISSING'}")
    print(f"Harvest package.json: {HARVEST / 'package.json'} {'OK' if (HARVEST / 'package.json').exists() else 'MISSING'}")
    print(f"Gateway URL: {DEFAULT_CONFIG.gateway_url}")
    # Check gateway
    try:
        import httpx
        with httpx.Client(timeout=5) as client:
            resp = client.get(f"{DEFAULT_CONFIG.gateway_url}/health")
            print(f"Gateway health: {resp.status_code} {'OK' if resp.status_code == 200 else 'FAIL'}")
            if resp.status_code != 200:
                ok = False
    except Exception as e:
        print(f"Gateway health: ERROR - {e}")
        ok = False
    # Check wellness files
    for f in ["wellness-checkin.html", "wellness-checkin-demo.html", "wellness-checkin-embed.js", "mem20-dashboard.html"]:
        p = HARVEST / f
        print(f"  {f}: {'OK' if p.exists() else 'MISSING'}")
    return 0 if ok else 1


def _cmd_test(args) -> int:
    """Run tests (vitest + playwright)."""
    print("Running vitest...")
    try:
        subprocess.run(["npm", "run", "test"], cwd=HARVEST, check=True)
    except subprocess.CalledProcessError:
        return 1
    except FileNotFoundError:
        print("npm not found")
        return 1
    print("Running playwright...")
    try:
        subprocess.run(["npm", "run", "test:e2e"], cwd=HARVEST, check=True)
    except subprocess.CalledProcessError:
        return 1
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="mem20officez", description="mem20 native office (3D, agents, wellness, dashboard)")
    p.add_argument("--config", help="Config YAML path")
    p.add_argument("--gateway", help="Gateway URL (default: http://127.0.0.1:4000)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="Run the office server")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=3000)
    s.set_defaults(func=_cmd_serve)

    sub.add_parser("build", help="Build Next.js frontend for production").set_defaults(func=_cmd_build)
    sub.add_parser("dev", help="Run Next.js dev server").set_defaults(func=_cmd_dev)
    sub.add_parser("doctor", help="Health check").set_defaults(func=_cmd_doctor)
    sub.add_parser("test", help="Run vitest + playwright tests").set_defaults(func=_cmd_test)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())