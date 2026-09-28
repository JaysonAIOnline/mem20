"""Command-line interface for mem20verify.

Every subcommand executes a real check against the live system or the real
source tree. There are no canned verdicts: if a check cannot run it reports the
error and exits non-zero rather than reporting a pass.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys

from . import dataintegrity, linters, outage, shadow, systemd, testrun

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2


def _emit(payload: dict, as_json: bool, human: str) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(human)


# ------------------------------------------------------------------ systemd
def cmd_systemd(args) -> int:
    try:
        reports = systemd.sweep(tuple(args.units) if args.units else None)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    lines = []
    for report in reports:
        if report.ok:
            lines.append(f"  OK    {report.unit:26s} pid={report.main_pid:<7d} "
                         f"ppid={report.ppid} port={report.listener_port} "
                         f"restart={report.restart_policy}")
        else:
            lines.append(f"  FAIL  {report.unit:26s} "
                         f"enabled={report.enabled} active={report.active}")
            for problem in report.problems:
                lines.append(f"          - {problem}")

    restart_note = ""
    if args.restart:
        for report in reports:
            if not report.exists:
                continue
            ok, detail = systemd.restart_survives(report.unit)
            restart_note += f"  {'OK  ' if ok else 'FAIL'} restart {report.unit}: {detail}\n"

    bad = [r for r in reports if not r.ok]
    if args.restart and any("FAIL restart" in line for line in restart_note.splitlines()):
        bad = bad or reports

    payload = {"ok": not bad, "units": [r.as_dict() for r in reports]}
    human = (f"systemd sweep: {len(reports) - len(bad)}/{len(reports)} compliant\n"
             + "\n".join(lines))
    if restart_note:
        human += "\nrestart resilience:\n" + restart_note.rstrip()
    _emit(payload, args.json, human)
    return EXIT_OK if not bad else EXIT_FINDINGS


# -------------------------------------------------------------------- tests
def cmd_tests(args) -> int:
    packages = args.package or testrun.discover_packages(args.root)
    if not packages:
        print("error: no packages discovered", file=sys.stderr)
        return EXIT_ERROR

    results = []
    lines = []
    for package in packages:
        result = testrun.run_package(
            package, root=args.root, timeout=args.timeout,
            test_pattern=args.pattern)
        results.append(result)
        if result.timed_out:
            lines.append(f"  TIMEOUT {package:24s} >{args.timeout}s")
        elif result.ok:
            lines.append(f"  OK      {package:24s} {result.passed} passed "
                         f"{result.skipped} skipped")
        elif result.returncode == 5:
            lines.append(f"  NO-OP   {package:24s} no tests collected")
        else:
            lines.append(f"  FAIL    {package:24s} {result.passed} passed "
                         f"{result.failed} failed {result.errors} errors")
            for failure in result.failed_ids[:5]:
                lines.append(f"            - {failure}")
            if result.error_text:
                lines.append(f"            {result.error_text.splitlines()[-1][:120]}")

    total = sum(r.passed for r in results)
    failures = [r for r in results if not r.ok and r.returncode not in (0, 5)]
    human = (f"test sweep: {len(results) - len(failures)}/{len(results)} packages pass"
             f"  ({total} tests passed)\n" + "\n".join(lines))
    _emit({"ok": not failures, "total_passed": total,
           "results": [r.as_dict() for r in results]}, args.json, human)
    return EXIT_OK if not failures else EXIT_FINDINGS


# ----------------------------------------------------------------- baseline
def cmd_baseline(args) -> int:
    try:
        ids = list(args.test_id or [])
        if not ids and args.failed_from:
            with open(args.failed_from, encoding="utf-8") as handle:
                data = json.load(handle)
            for entry in data.get("results", []):
                if entry.get("package") == args.package:
                    ids.extend(entry.get("failed_ids", []))
        if not ids:
            print("error: supply test ids or --failed-from JSON", file=sys.stderr)
            return EXIT_ERROR
        verdicts = testrun.attribute(args.package, ids, root=args.root,
                                     timeout=args.timeout)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    lines = []
    regressions = []
    for verdict in verdicts:
        if verdict.preexisting:
            lines.append(f"  PRE-EXISTING  {verdict.test_id}  ({verdict.detail})")
        elif not verdict.baseline_available:
            lines.append(f"  UNKNOWN       {verdict.test_id}  ({verdict.detail})")
        else:
            regressions.append(verdict)
            lines.append(f"  REGRESSION    {verdict.test_id}  ({verdict.detail})")

    human = (f"baseline: {len(verdicts) - len(regressions)}/{len(verdicts)} "
             f"pre-existing, {len(regressions)} regression(s)\n" + "\n".join(lines))
    _emit({"ok": not regressions,
           "regressions": [v.as_dict() for v in regressions],
           "verdicts": [v.as_dict() for v in verdicts]}, args.json, human)
    return EXIT_OK if not regressions else EXIT_FINDINGS


# ------------------------------------------------------------------- outage
def cmd_outage(args) -> int:
    result = outage.check()
    human = (
        f"outage breaker contract: {'PASS' if result.ok else 'FAIL'}\n"
        f"  strikes            : {result.strikes} (need 3)\n"
        f"  retry interval     : {result.retry_interval_s}s\n"
        f"  trip events        : {result.trip_events} (need exactly 1)\n"
        f"  stderr lines       : {result.stderr_lines}\n"
        f"  ledger rows        : {result.ledger_rows} (need 0)\n"
        f"  re-probe waits     : {result.re_probes}\n"
        f"  reset on recovery  : {result.reset_after_recovery}\n"
    )
    if result.error:
        human += f"  error              : {result.error}\n"
    _emit(result.as_dict(), args.json, human)
    return EXIT_OK if result.ok else EXIT_FINDINGS


# ----------------------------------------------------------- dataintegrity
def cmd_dataintegrity(args) -> int:
    result = dataintegrity.check(engine_dir=args.engine)
    human = (
        f"data integrity: {'PASS' if result.ok else 'FAIL'}\n"
        f"  payloads checked : {result.checked}\n"
        f"  byte-identical   : {result.roundtrip_ok}\n"
        f"  corruptions      : {len(result.failures)}\n"
        f"  false positives  : {len(result.false_positive_detections)}\n"
    )
    for failure in result.failures:
        human += f"    - {failure.get('payload')}: {failure.get('reason')}\n"
    for hit in result.false_positive_detections:
        human += f"    - false positive on {hit.get('payload')}: {hit.get('labels')}\n"
    if result.error:
        human += f"  error: {result.error}\n"
    _emit(result.as_dict(), args.json, human)
    return EXIT_OK if result.ok else EXIT_FINDINGS


# ------------------------------------------------------------------- lint
def _python_files_under(directory: str) -> list[str]:
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(directory):
        dirnames[:] = [d for d in dirnames
                       if d not in ("__pycache__", ".venv", "venv", "node_modules")]
        for filename in filenames:
            if filename.endswith(".py"):
                found.append(os.path.join(dirpath, filename))
    return found


def _lint_files(paths: list[str]) -> tuple[list[linters.Issue], int]:
    issues: list[linters.Issue] = []
    scanned = 0
    for target in paths:
        files = _python_files_under(target) if os.path.isdir(target) else [target]
        for path in files:
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    tree = ast.parse(fh.read(), filename=path)
            except (OSError, SyntaxError, ValueError):
                continue
            scanned += 1
            for check_fn in linters.ALL_CHECKS:
                issues.extend(check_fn(path, tree))
    return issues, scanned


def cmd_lint(args) -> int:
    issues, scanned = _lint_files(args.paths)
    lines = []
    for issue in issues:
        lines.append(f"  {issue.severity:6s} {issue.check:22s} "
                     f"{issue.path}:{issue.line}  {issue.message}")
    human = (f"lint: {len(issues)} issue(s) across {scanned} file(s)"
             + ("\n" + "\n".join(lines) if lines else ""))
    _emit({"ok": not issues, "scanned": scanned,
           "issues": [i.as_dict() for i in issues]}, args.json, human)
    return EXIT_OK if not issues else EXIT_FINDINGS


# ------------------------------------------------------------------ shadow
def cmd_shadow(args) -> int:
    try:
        reports = shadow.sweep(tuple(args.package) if args.package else None,
                               root=args.root, python=args.python,
                               pythonpath=args.pythonpath)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    lines = []
    for report in reports:
        if report.resolution == shadow.RESOLVES:
            lines.append(f"  OK        {report.package:24s} {report.import_name:22s} "
                         f"layout={report.layout}")
        elif report.resolution == shadow.SHADOWED:
            lines.append(f"  SHADOWED  {report.package:24s} {report.import_name:22s} "
                         f"layout={report.layout} outranked-by={report.search_path}")
        elif report.resolution == shadow.UNREACHABLE:
            lines.append(f"  UNREACH   {report.package:24s} {report.import_name:22s} "
                         f"layout={report.layout} not-importable-here")
        else:
            lines.append(f"  {report.resolution.upper():9s} {report.package:24s} "
                         f"{report.import_name}")
            for problem in report.problems:
                lines.append(f"             - {problem}")

    shadowed = [r for r in reports if r.resolution == shadow.SHADOWED]
    unreachable = [r for r in reports if r.resolution == shadow.UNREACHABLE]
    findings = shadowed + unreachable
    human = (f"shadow sweep: {len(reports) - len(findings)}/{len(reports)} "
             f"import with the estate root on sys.path"
             + ("\n" + "\n".join(lines) if lines else ""))
    if shadowed:
        human += ("\nnote: SHADOWED packages are installed and import fine on their "
                  "own; a same-named\n      directory outranks them only when the "
                  "estate root is the working directory.\n      Layout is not the "
                  "cause - run each from its own package root.")
    if unreachable:
        human += (f"\nnote: {len(unreachable)} package(s) are not importable from "
                  "this interpreter at all\n      (own venv, or different name); "
                  "a layout change would not fix those.")
    _emit({"ok": not findings,
           "shadowed": [r.as_dict() for r in shadowed],
           "unreachable": [r.as_dict() for r in unreachable],
           "reports": [r.as_dict() for r in reports]}, args.json, human)
    return EXIT_OK if not findings else EXIT_FINDINGS


# --------------------------------------------------------------------- all
def cmd_all(args) -> int:
    codes = []
    for name, fn in (
        ("systemd", cmd_systemd),
        ("dataintegrity", cmd_dataintegrity),
        ("outage", cmd_outage),
    ):
        print(f"--- {name} ---", file=sys.stderr)
        try:
            codes.append(fn(args))
        except Exception as exc:  # noqa: BLE001
            print(f"error: {exc}", file=sys.stderr)
            codes.append(EXIT_ERROR)
    return max(codes) if codes else EXIT_ERROR


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mem20verify",
        description="Verification toolkit: prove claims by execution, never by report.")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("systemd", help="unit persistence sweep")
    p.add_argument("--unit", dest="units", action="append")
    p.add_argument("--restart", action="store_true",
                   help="actually restart each unit and confirm it returns")
    p.set_defaults(func=cmd_systemd)

    p = sub.add_parser("tests", help="run each package's suite from its own root")
    p.add_argument("--root", default=testrun.DEFAULT_ROOT)
    p.add_argument("--package", action="append")
    p.add_argument("--pattern", help="-k expression")
    p.add_argument("--timeout", type=int, default=600)
    p.set_defaults(func=cmd_tests)

    p = sub.add_parser("baseline", help="separate pre-existing failures from regressions")
    p.add_argument("package")
    p.add_argument("--test-id", action="append")
    p.add_argument("--failed-from", help="JSON produced by `tests --json`")
    p.add_argument("--root", default=testrun.DEFAULT_ROOT)
    p.add_argument("--timeout", type=int, default=600)
    p.set_defaults(func=cmd_baseline)

    p = sub.add_parser("outage", help="breaker contract check")
    p.set_defaults(func=cmd_outage)

    p = sub.add_parser("dataintegrity", help="byte-identical store round-trip")
    p.add_argument("--engine", default="/opt/mem20/memory_engine")
    p.set_defaults(func=cmd_dataintegrity)

    p = sub.add_parser("lint", help="AST linters for known-shipped defect classes")
    p.add_argument("paths", nargs="+")
    p.set_defaults(func=cmd_lint)

    p = sub.add_parser("shadow", help="which packages are shadowed by a same-named dir")
    p.add_argument("--root", default=shadow.DEFAULT_ROOT)
    p.add_argument("--package", action="append")
    p.add_argument("--python", default=shadow.DEFAULT_PYTHON)
    p.add_argument("--pythonpath", help="extra PYTHONPATH for the child probe")
    p.set_defaults(func=cmd_shadow)

    p = sub.add_parser("all", help="systemd + dataintegrity + outage")
    p.add_argument("--unit", dest="units", action="append")
    p.set_defaults(func=cmd_all)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return EXIT_ERROR
    except Exception as exc:  # noqa: BLE001
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
