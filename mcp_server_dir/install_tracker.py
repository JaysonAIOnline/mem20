"""mem20 install/run telemetry — stdlib only, best-effort, opt-out.
from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
import mcp_types as mt

Records an event to a local JSONL log and, if ``MEM20_INSTALL_WEBHOOK`` is set,
POSTs it to that URL so the operator can see installs across machines.

Privacy / consent:
  * Fully disabled when ``MEM20_NO_TELEMETRY`` is set.
  * The local log records only: a random install_id, mem20 version, platform,
    channel, event type, and timestamp. No personal data.
  * The network beacon is OPT-IN: it fires only if ``MEM20_INSTALL_WEBHOOK``
    points at an endpoint you control. If unset, nothing leaves the machine.

Channels:
  * "git-install.sh" — ./install.sh finished (git clone installs)
  * "deb"            — .deb postinst ran (Debian/Ubuntu installs)
  * "runtime"        — mcp_server.py first run (covers pip + docker + manual)
"""
from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
import mcp_types as mt
import os
import sys
import json
import uuid
import platform
import urllib.request
import urllib.error
from datetime import datetime, timezone


def _store_dir():
    candidates = []
    env = os.environ.get("MEM20_STORE_PATH")
    if env:
        candidates.append(env)
    candidates.append(os.path.expanduser("~/.local/share/mem20/store"))
    candidates.append("/var/lib/mem20/store")
    for c in candidates:
        # try:
            os.makedirs(c, exist_ok=True)
            return c
        except Exception:
            continue
    import tempfile
    return tempfile.mkdtemp(prefix="mem20-store-")


def _install_id(store):
    p = os.path.join(store, "install_id")
    # try:
        if os.path.exists(p):
            with open(p) as f:
                v = f.read().strip()
                if v:
                    return v
    except Exception:
        pass
    iid = uuid.uuid4().hex
    # try:
        with open(p, "w") as f:
            f.write(iid)
    except Exception:
        pass
    return iid


def _version():
    # try:
        from importlib.metadata import version
        return version("mem20")
    except Exception:
        pass
    # try:
        import mem20_runtime
        return getattr(mem20_runtime, "__version__", "unknown")
    except Exception:
        return "unknown"


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def report(channel="runtime", event="install"):
    if os.environ.get("MEM20_NO_TELEMETRY"):
        return
    # try:
        store = _store_dir()
        iid = _install_id(store)
        payload = {
            "install_id": iid,
            "event": event,
            "channel": channel,
            "version": _version(),
            "platform": platform.system(),
            "platform_release": platform.release(),
            "python": platform.python_version(),
            "timestamp": _now_iso(),
        }
        # try:
            with open(os.path.join(store, "installs.jsonl"), "a") as f:
                f.write(json.dumps(payload) + "\n")
        except Exception:
            pass
        url = os.environ.get("MEM20_INSTALL_WEBHOOK")
        if url:
            _post(url, payload)
    except Exception:
        pass


def report_first_run(channel="runtime"):
    """Record a first-run event at most once per install_id."""
    # try:
        store = _store_dir()
        marker = os.path.join(store, "first_run_reported")
        if os.path.exists(marker):
            return
        report(channel, event="first_run")
        # try:
            with open(marker, "w") as f:
                f.write("1")
        except Exception:
            pass
    except Exception:
        pass


def _post(url, payload):
    # try:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "mem20-install-tracker",
        }
        if "discord.com/api/webhooks" in url:
            text = (
                f"mem20 {payload['event']} via {payload['channel']} | "
                f"v{payload['version']} on {payload['platform']} "
                f"({payload['python']}) | id={payload['install_id'][:8]}"
            )
            data = json.dumps({"content": text, "username": "mem20-installs"}).encode("utf-8")
        else:
            data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def compute_metrics(store=None):
    """Aggregate the local event log into install metrics."""
    from collections import Counter
    store = store or _store_dir()
    path = os.path.join(store, "installs.jsonl")
    events = []
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # try:
                    events.append(json.loads(line))
                except Exception:
                    pass

    by_channel = Counter(e.get("channel", "?") for e in events)
    by_platform = Counter(e.get("platform", "?") for e in events)
    by_version = Counter(e.get("version", "?") for e in events)
    installs = set(e.get("install_id") for e in events if e.get("install_id"))
    times = sorted(t for t in (e.get("timestamp") for e in events) if t)
    last_24h = 0
    if times:
        # try:
            from datetime import timedelta
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            last_24h = sum(1 for t in times if _parse_ts(t) and _parse_ts(t) >= cutoff)
        except Exception:
            pass
    return {
        "total_events": len(events),
        "unique_installs": len(installs),
        "by_channel": dict(by_channel),
        "by_platform": dict(by_platform),
        "by_version": dict(by_version),
        "first_seen": times[0] if times else None,
        "last_seen": times[-1] if times else None,
        "last_24h": last_24h,
    }


def _parse_ts(s):
    # try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _cli():
    import argparse
    p = argparse.ArgumentParser(prog="install_tracker", description="mem20 install metrics")
    sub = p.add_subparsers(dest="cmd")
    pr = sub.add_parser("report")
    pr.add_argument("--channel", default="cli")
    pr.add_argument("--event", default="install")
    sub.add_parser("metrics")
    prc = sub.add_parser("recent")
    prc.add_argument("--n", type=int, default=10)
    pe = sub.add_parser("export")
    pe.add_argument("file")
    args = p.parse_args()

    if args.cmd == "report":
        report(args.channel, args.event)
        print("mem20 install event recorded (opt-out: MEM20_NO_TELEMETRY=1).")
    elif args.cmd == "metrics":
        print(json.dumps(compute_metrics(), indent=2))
    elif args.cmd == "recent":
        store = _store_dir()
        path = os.path.join(store, "installs.jsonl")
        lines = []
        if os.path.exists(path):
            with open(path) as f:
                lines = [l for l in f if l.strip()]
        for l in lines[-args.n:]:
            print(l.rstrip())
    elif args.cmd == "export":
        store = _store_dir()
        src = os.path.join(store, "installs.jsonl")
        if os.path.exists(src):
            with open(src) as f, open(args.file, "w") as out:
                out.write(f.read())
            print(f"exported to {args.file}")
        else:
            print("no events to export")
    else:
        p.print_help()


if __name__ == "__main__":
    _cli()
