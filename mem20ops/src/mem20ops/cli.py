"""Command-line entry point for mem20ops.

Exit codes are stable so other tools can branch on them:
  0  success
  1  operation failed
  2  usage error (argparse)
  3  findings present (audit-style commands)
  4  missing credentials or environment
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import audit, clicheck, memchecks, runtime
from .cloudflare import CredentialError

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_FINDINGS = 3
EXIT_NO_CREDENTIALS = 4


def _emit(payload: dict[str, Any], as_json: bool, renderer) -> int:
    if as_json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        renderer(payload)
    return EXIT_OK


def _dns_audit(args, as_json: bool) -> int:
    result = audit.audit_dns(args.zone, pattern=args.pattern)
    findings = result["findings"]

    def render(data: dict[str, Any]) -> None:
        f = data["findings"]
        print(f"zone: {data['zone']}  records: {data['total_records']}")
        print(f"types: {data['type_counts']}")
        if args.pattern:
            print(f"matched by /{args.pattern}/: {data['matched_records']}")
            for row in data["records"]:
                print(f"  {row['type']:6} {row['name']:40} -> {row['content']}")
        if f["wildcards"]:
            for w in f["wildcards"]:
                print(f"  WILDCARD {w['name']} -> {w['content']} (proxied={w['proxied']})")
        print(f"email routing records: {f['email_routing_records']}")
        print(f"origin groups: {len(f['origin_groups'])}")

    _emit(result, as_json, render)
    return EXIT_FINDINGS if findings["wildcard_shadows_unlisted_hosts"] else EXIT_OK


def _pages_inspect(args, as_json: bool) -> int:
    result = audit.inspect_pages(
        account_id=args.account, project=args.project, fetch_live=not args.no_fetch
    )

    def render(data: dict[str, Any]) -> None:
        if "projects" in data:
            print(f"pages projects: {data['total']}")
            for p in data["projects"]:
                print(f"  {p['name']:24} {p['subdomain']}  last={p['latest_deployment']}")
        else:
            print(f"project: {data['name']}  subdomain={data['subdomain']}")
            print(f"domains: {data['domains']}")
            print(f"deployments: {data['deployment_count']}")
            live = data.get("live")
            if live:
                print(f"live: {live['url']} status={live['status']} bytes={live['bytes']}")
                print(f"  title: {live['title']}")
                for h in live.get("headings", []):
                    print(f"  heading: {h}")

    _emit(result, as_json, render)
    return EXIT_OK


def _pages_delete(args, as_json: bool) -> int:
    result = audit.delete_pages_project(args.project, account_id=args.account, confirm=args.confirm)

    def render(data: dict[str, Any]) -> None:
        print(f"deleted: {data['deleted']} (existed={data['existed']})")
        print(f"still present: {data['still_present']}")
        print(f"remaining: {data['remaining_projects']}")

    _emit(result, as_json, render)
    return EXIT_OK if not result["still_present"] else EXIT_FAIL


def _stale_code(args, as_json: bool) -> int:
    result = runtime.find_stale_processes(args.path, match=args.match, related=args.related)

    def render(data: dict[str, Any]) -> None:
        print(f"newest source: {data['newest_source']} @ {data['newest_mtime']}")
        print(f"processes checked: {data['processes_checked']}  stale: {data['stale_count']}")
        for row in data["processes"]:
            print(f"  [{row['verdict']:7}] pid={row['pid']} elapsed={row['elapsed_s']}s {row['cmd']}")
        if data["stale_count"]:
            print(data["interpretation"])

    _emit(result, as_json, render)
    return EXIT_FINDINGS if result["stale_count"] else EXIT_OK


def _service_status(args, as_json: bool) -> int:
    result = runtime.service_status(args.unit)

    def render(data: dict[str, Any]) -> None:
        print(f"unit: {data['unit']}  {data['active_state']}/{data['sub_state']}")
        print(f"main pid: {data['main_pid']}  active since: {data['active_enter']}")
        print(f"pid started: {data['main_pid_started']}")

    _emit(result, as_json, render)
    return EXIT_OK if result["active_state"] == "active" else EXIT_FAIL


def _verify(args, as_json: bool) -> int:
    result = runtime.verify_suite(
        repo=args.repo,
        python=args.python,
        lint_paths=args.lint or None,
        run_tests=not args.no_tests,
        run_lint=not args.no_lint,
    )

    def render(data: dict[str, Any]) -> None:
        for step in data["steps"]:
            print(f"--- {step['name']} exit={step['exit_code']}")
            if step["name"] == "pytest":
                print(f"    counts: {step.get('counts')}")
            if step["name"] == "ruff":
                print(f"    finding lines: {step.get('finding_lines')}")
            tail = (step.get("stdout_tail") or "").strip().splitlines()
            for line in tail[-5:]:
                print(f"    {line}")
        print(f"ok: {data['ok']}  failed: {data['failed_steps']}")

    _emit(result, as_json, render)
    return EXIT_OK if result["ok"] else EXIT_FAIL


def _identity(args, as_json: bool) -> int:
    result = memchecks.identity_check()

    def render(data: dict[str, Any]) -> None:
        print(f"store: {data['store_path']}")
        print(f"pinned blocks: {data['pinned_block_count']}")
        for block in data["pinned_blocks"]:
            print(f"  {block}")
        print(f"life/voice blocks: {data['life_voice_blocks']}")
        print(f"namespaces: {data['namespace_count']}")
        for ns in data["namespaces"][:20]:
            print(f"  {ns.get('namespace')} owner={ns.get('owner')} structured={ns.get('structured')}")

    _emit(result, as_json, render)
    return EXIT_OK


def _acl_probe(args, as_json: bool) -> int:
    result = memchecks.acl_probe(args.namespace, actors=args.actor or None, probe_query=args.query)

    def render(data: dict[str, Any]) -> None:
        print(f"scope: {data['scope']}")
        for row in data["actors"]:
            print(f"  {row}")
        print(data["note"])

    _emit(result, as_json, render)
    return EXIT_OK


def _lint_delta(args, as_json: bool) -> int:
    result = memchecks.lint_delta(args.path, revision=args.revision)

    def render(data: dict[str, Any]) -> None:
        if data.get("error"):
            print(f"error: {data['error']}")
            print(data.get("hint", ""))
            return
        print(f"{data['path']} vs {data['revision']}: {data['before_total']} -> {data['after_total']}")
        for code, entry in data["delta"].items():
            print(f"  {code}: {entry['before']} -> {entry['after']} ({entry['change']:+d})")

    _emit(result, as_json, render)
    if result.get("error"):
        return EXIT_FAIL
    return EXIT_FINDINGS if result["new_findings"] else EXIT_OK


def _cli_coverage(args, as_json: bool) -> int:
    report = clicheck.audit(timeout=args.timeout)

    def render(data: dict[str, Any]) -> None:
        totals = data["totals"]
        print(f"audited CLIs      : {totals['audited_clis']}")
        print(f"skipped (non-CLI) : {totals['skipped']} {data['skipped_non_cli']}")
        print(f"declared scripts  : {totals['declared_scripts']}")
        print(f"with --json       : {totals['with_json']}")
        print(f"missing --json    : {totals['audited_clis'] - totals['with_json']}")
        print(f"help failures     : {totals['with_help_failure']}")
        print(f"help timeouts     : {totals['with_help_timeout']}")
        print(f"naming            : {totals['fs_standard']} fs-* / {totals['mem20_native']} mem20* "
              "(not a contract; no subsystem is renamed)")
        if data["declared_but_not_installed"]:
            print(f"declared but missing: {', '.join(data['declared_but_not_installed'])}")
        if data["binaries_present_but_not_declared"]:
            print(f"installed, undeclared: {', '.join(data['binaries_present_but_not_declared'])}")
        print("\nmissing --json:")
        for row in data["results"]:
            if "no-json" in row["gaps"]:
                print(f"  {row['name']}")

    _emit(report, as_json, render)
    return EXIT_OK if report["totals"]["fully_compliant"] == report["totals"]["audited_clis"] else EXIT_FINDINGS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fs-ops",
        description="mem20 operational workflows: Cloudflare audits, stale-code detection, verification.",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    p_dns = sub.add_parser("dns-audit", help="inventory a Cloudflare zone and flag wildcard shadowing")
    p_dns.add_argument("zone")
    p_dns.add_argument("--pattern", help="only show records matching this regex")
    p_dns.set_defaults(func=_dns_audit)

    p_pages = sub.add_parser("pages-inspect", help="list or inspect Cloudflare Pages projects")
    p_pages.add_argument("--project")
    p_pages.add_argument("--account")
    p_pages.add_argument("--no-fetch", action="store_true", help="skip fetching the live site")
    p_pages.set_defaults(func=_pages_inspect)

    p_del = sub.add_parser("pages-delete", help="delete a Cloudflare Pages project")
    p_del.add_argument("project")
    p_del.add_argument("--account")
    p_del.add_argument("--confirm", action="store_true", help="required; refuses to delete otherwise")
    p_del.set_defaults(func=_pages_delete)

    p_stale = sub.add_parser("stale-code", help="find processes running code older than a source file")
    p_stale.add_argument("path", nargs="+")
    p_stale.add_argument("--match", help="only consider processes whose cmdline contains this")
    p_stale.add_argument(
        "--related",
        action="append",
        help="file whose mtime also decides staleness but need not appear in the cmdline "
        "(e.g. a module imported by a long-running server entry script)",
    )
    p_stale.set_defaults(func=_stale_code)

    p_svc = sub.add_parser("service-status", help="systemd unit status and main pid start time")
    p_svc.add_argument("unit")
    p_svc.set_defaults(func=_service_status)

    p_verify = sub.add_parser("verify", help="run the test suite and lint, reporting real counts")
    p_verify.add_argument("--repo", default="/opt/mem20")
    p_verify.add_argument("--python", default=runtime.DEFAULT_PYTHON)
    p_verify.add_argument("--lint", nargs="*", help="paths to lint")
    p_verify.add_argument("--no-tests", action="store_true")
    p_verify.add_argument("--no-lint", action="store_true")
    p_verify.set_defaults(func=_verify)

    p_ident = sub.add_parser("identity-check", help="report life models, pinned blocks, namespaces")
    p_ident.set_defaults(func=_identity)

    p_acl = sub.add_parser("acl-probe", help="probe namespace readability for a set of actors")
    p_acl.add_argument("namespace")
    p_acl.add_argument("--actor", action="append", help="repeatable actor name")
    p_acl.add_argument("--query", default="life model")
    p_acl.set_defaults(func=_acl_probe)

    p_lint = sub.add_parser("lint-delta", help="compare ruff findings for a file against a git revision")
    p_lint.add_argument("path")
    p_lint.add_argument("--revision", default="HEAD")
    p_lint.set_defaults(func=_lint_delta)

    p_cov = sub.add_parser(
        "cli-coverage", help="audit every fleet CLI against the fs-*/--json contract"
    )
    p_cov.add_argument("--timeout", type=int, default=clicheck.HELP_TIMEOUT)
    p_cov.set_defaults(func=_cli_coverage)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    as_json = getattr(args, "json", False)
    try:
        return args.func(args, as_json)
    except CredentialError as exc:
        print(f"credentials error: {exc}", file=sys.stderr)
        return EXIT_NO_CREDENTIALS
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAIL
    except Exception as exc:  # noqa: BLE001
        print(f"unexpected error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
