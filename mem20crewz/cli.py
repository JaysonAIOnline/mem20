"""CLI — python -m mem20crewz.

subcommands:
  init          write example agents.yaml/tasks.yaml into a dir
  run           load agents.yaml/tasks.yaml and kickoff a crew
  demo          run the bundled demo (--real uses CogBrain + live A2A)
  peers         list configured A2A peers
  version       print version
"""

from __future__ import annotations

import argparse
import os
import sys

from . import __version__

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


def _agent_files(args) -> tuple[str, str]:
    agents_yaml = args.agents or os.environ.get("MEM20CREWZ_AGENTS_YAML",
                                                "agents.yaml")
    tasks_yaml = args.tasks or os.environ.get("MEM20CREWZ_TASKS_YAML",
                                              "tasks.yaml")
    return agents_yaml, tasks_yaml


def cmd_init(args) -> int:
    from .config import write_example
    writes = write_example(args.dir)
    for w in writes:
        print(f"wrote {w}")
    return 0


def cmd_run(args) -> int:
    from .config import build_crew_from_yaml
    import json
    agents_yaml, tasks_yaml = _agent_files(args)
    if not os.path.exists(agents_yaml) or not os.path.exists(tasks_yaml):
        print(f"missing yaml: {agents_yaml} or {tasks_yaml} (run 'init' first)")
        return 2
    crew = build_crew_from_yaml(agents_yaml, tasks_yaml)
    result = crew.kickoff(inputs={"topic": args.topic or "mem20"})
    for o in result.outcomes:
        flag = "OK " if o.ok else "FAIL"
        print(f"[{flag}] {o.agent} :: {o.task_name} ({o.iterations} iters)")
        print(f"    {o.output[:200]}")
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.ok() else 1


def cmd_demo(args) -> int:
    from .demo import demo_crew
    if getattr(args, "real", False):
        import os
        os.environ.setdefault("MEM20CREWZ_BACKEND", "native")
    resp, crew_result, flow_result = demo_crew.run(real=bool(getattr(args, "real", False)),
                                                   topic=args.topic or "mem20 substrate")
    print(resp)
    return 0 if crew_result.ok() else 1


def cmd_peers(args) -> int:
    from .a2a import A2AClient
    client = A2AClient()
    for name in client.peer_names():
        entry = client.peers()[name]
        print(f"{name:20s} {entry.get('url')}")
    return 0


@json_main
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="mem20crewz",
                                     description="cleanroom mem20 crews on mem20")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("init", help="write example agents.yaml/tasks.yaml")
    p.add_argument("dir", nargs="?", default=".")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("run", help="run a crew from agents.yaml/tasks.yaml")
    p.add_argument("--agents", default="")
    p.add_argument("--tasks", default="")
    p.add_argument("--topic", default="")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("demo", help="run the bundled demo crew")
    p.add_argument("--real", action="store_true",
                   help="use CogBrain (llm.chat) + live A2A instead of FakeBrain")
    p.add_argument("--topic", default="")
    p.set_defaults(fn=cmd_demo)

    p = sub.add_parser("peers", help="list configured A2A peers")
    p.set_defaults(fn=cmd_peers)

    p = sub.add_parser("version", help="print version")
    p.set_defaults(fn=lambda args: (print(__version__), 0)[1])

    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return int(args.fn(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
