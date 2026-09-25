"""mem20orcaz CLI — run a deterministic Orchestrator workflow in-process.

Loads a workflow from YAML (or a dict-style ``workflow`` block), executes it
against a fake deterministic runtime, and prints the final response, per-agent
results, and metrics. Everything is pure stdlib; no model API is contacted.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, List, Optional

from .agents import AGENT_CLASSES
from .nodes import NODE_CLASSES
from .orchestrator import Orchestrator


def _fake_llm(prompt: str, **_: Any) -> str:
    # deterministic stand-in so llm/rag/binary agents run offline
    snippet = (prompt or "").strip().splitlines()[0] if prompt else ""
    return f"[deterministic] {snippet[:120]}"


def _run_file(path: str, user_input: str, show_outputs: bool = False) -> int:
    orch = Orchestrator(
        id=path,
        config={"workflow": {"yaml_file_path": path}},
    )
    needs_llm = any(
        str(cfg.get("type", "")).lower() in ("llm", "rag", "openai-answer", "openai-binary", "local_llm")
        for cfg in orch.agents_config_map.values()
    )
    if needs_llm or not orch.attributes.get("gateway_set"):
        orch.set_llm_gateway(_fake_llm)
    result = orch.run(user_input)
    final = result.get("response")
    print(f"# mem20orcaz run of {path}")
    print(f"# final response: {final!r}")
    metrics = result.get("metrics") or {}
    print(f"# executions: {metrics.get('total_executions', 0)} "
          f"statuses: {metrics.get('statuses', {})}")
    for aid, resp in (result.get("results") or {}).items():
        status = resp.get("status") if isinstance(resp, dict) else "?"
        value = resp.get("response") if isinstance(resp, dict) else resp
        if show_outputs:
            print(f"#   {aid}: [{status}] {value!r}")
        elif resp is not None and isinstance(resp, dict) and resp.get("error"):
            print(f"#   {aid}: [error] {resp.get('error')}")
    return 0


def _list_types() -> int:
    print("agent types:")
    for name in sorted(AGENT_CLASSES):
        print(f"  {name}")
    print("node types:")
    for name in sorted(NODE_CLASSES):
        print(f"  {name}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mem20orcaz",
        description="Run a deterministic OrKa-style orchestrator workflow (pure stdlib).",
    )
    parser.add_argument("workflow_yaml", nargs="?", default=None,
                        help="path to a workflow YAML file")
    parser.add_argument("--input", default="hello", help="user input sent to the workflow")
    parser.add_argument("--outputs", action="store_true",
                        help="print every agent's response")
    parser.add_argument("--list-types", action="store_true",
                        help="list known agent/node types and exit")
    parser.add_argument("--version", action="store_true",
                        help="print version and exit")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.version:
        import mem20orcaz as pkg
        print(pkg.__version__)
        return 0
    if args.list_types:
        return _list_types()
    if not args.workflow_yaml:
        print("error: workflow_yaml path is required (or --list-types/--version)", file=sys.stderr)
        return 2
    try:
        return _run_file(args.workflow_yaml, args.input, show_outputs=args.outputs)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # loader/validation errors
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())