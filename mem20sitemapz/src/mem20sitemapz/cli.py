"""Command line entry point: /sitemap and friends."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from . import report, search as search_mod, snapshot as snapshot_mod, watch as watch_mod
from .index import scan
from .policy import SCHEMA

DEFAULT_ROOT = Path("/opt/mem20")
DEFAULT_INDEX_DIR = Path("/opt/mem20/.sitemap")
DEFAULT_DB = Path("/root/.local/share/opencode/opencode.db")


def _index_paths(index_dir: Path) -> tuple[Path, Path, Path]:
    return (
        index_dir / "sitemap.json",
        index_dir / "SITEMAP.md",
        index_dir / "snapshot.json",
    )


def _load_index(index_dir: Path, quiet: bool = False) -> dict:
    json_path, md_path, _ = _index_paths(index_dir)
    if not json_path.is_file():
        if not quiet:
            print(f"no index at {json_path}; run: sitemap build", file=sys.stderr)
        raise SystemExit(2)
    return json.loads(json_path.read_text(encoding="utf-8"))


def _autodetect_targets() -> list[int]:
    from . import procinfo

    table = procinfo.process_table()
    mine = procinfo.ancestor_matching(os.getpid(), watch_mod.AGENT_COMM_NAMES)
    chain = set(procinfo.ppid_chain(os.getpid()))
    found = []
    for pid, info in sorted(table.items()):
        if info.comm not in watch_mod.AGENT_COMM_NAMES:
            continue
        if pid in chain:
            continue
        if not info.tty_path():
            continue
        try:
            cmdline = (Path("/proc") / str(pid) / "cmdline").read_bytes().decode(
                "utf-8", "replace"
            )
        except OSError:
            continue
        if "serve" in cmdline.split("\0"):
            continue
        found.append(pid)
    return found


def cmd_build(args: argparse.Namespace) -> int:
    root = Path(args.root)
    if not root.is_dir():
        print(f"root not found: {root}", file=sys.stderr)
        return 2
    index = scan(root, max_depth=args.depth)
    index_dir = Path(args.index_dir)
    index_dir.mkdir(parents=True, exist_ok=True)
    json_path, _, _ = _index_paths(index_dir)
    json_path.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")
    root_md = root / "SITEMAP.md"
    root_md.write_text(report.render_markdown(index), encoding="utf-8")
    print(report.render_terminal(index))
    print(f"wrote {json_path}")
    print(f"wrote {root_md}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    index = _load_index(Path(args.index_dir))
    hits = search_mod.search(index, args.query, limit=args.limit)
    if not hits:
        print(f"no match for {args.query!r}")
        return 1
    if args.json:
        print(json.dumps([{"score": h["score"], **{k: v for k, v in h["entry"].items()}} for h in hits], indent=2, sort_keys=True))
        return 0
    print(f"{len(hits)} match(es) for {args.query!r}\n")
    for hit in hits:
        entry = hit["entry"]
        print(f"[{hit['score']:>6}] {search_mod.brief(entry)}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    index = _load_index(Path(args.index_dir))
    entry = search_mod.find(index, args.name)
    if entry is None:
        print(f"no subsystem matching {args.name!r}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(entry, indent=2, sort_keys=True))
        return 0
    print(f"name         {entry['name']}")
    print(f"dir          {entry['dir']}")
    print(f"category     {entry['category']}")
    print(f"packaged     {entry['packaged']}")
    print(f"version      {entry.get('version')}")
    print(f"license      {entry.get('license')}")
    print(f"description  {entry.get('description') or '-'}")
    print(f"readme       {entry.get('readme_summary') or '-'}")
    print(f"files        {entry['file_count']}  lines {entry['line_count']}  tests {entry['test_files']}")
    print(f"languages    " + ", ".join(f"{k}:{v}" for k, v in entry.get("languages", {}).items()))
    print(f"keywords     {', '.join(entry.get('keywords') or []) or '-'}")
    print(f"entry_points " + (", ".join(f"{k}={v}" for k, v in sorted(entry.get("entry_points", {}).items())) or "-"))
    print(f"deps         {', '.join(entry.get('dependencies') or []) or '-'}")
    print(f"subdirs      {', '.join(entry.get('subdirs') or []) or '-'}")
    print(f"docs         {', '.join(entry.get('docs') or []) or '-'}")
    print(f"modules      {', '.join(entry.get('modules') or []) or '-'}")
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    root = Path(args.root)
    out = Path(args.out)
    result = snapshot_mod.create_snapshot(
        root,
        out,
        extra_skip_dirs=tuple(args.skip_dir or ()),
        extra_skip_suffixes=tuple(args.skip_suffix or ()),
        dry_run=args.dry_run,
        on_progress=lambda r: print(f"  ... {r.files} files, {r.raw_bytes/1e6:.1f} MB raw", file=sys.stderr),
    )
    if args.json:
        print(result.to_json())
    else:
        print(f"out          {result.out}")
        print(f"files        {result.files}")
        print(f"skipped      {result.skipped} (secrets: {result.skipped_secrets})")
        print(f"raw bytes    {result.raw_bytes}")
        print(f"zip bytes    {result.zip_bytes}")
        print(f"seconds      {result.seconds}")
    if not args.dry_run:
        check = snapshot_mod.verify_zip(out)
        if not args.json:
            print(f"verify       {check}")
        if not check["ok"]:
            print("VERIFY FAILED", file=sys.stderr)
            return 1
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    out = Path(args.out)
    check = snapshot_mod.verify_zip(out)
    print(json.dumps(check, indent=2, sort_keys=True))
    return 0 if check.get("ok") else 1


def cmd_watch(args: argparse.Namespace) -> int:
    db = Path(args.db)
    self_pid = None
    self_sessions = list(args.self_session or [])
    if not self_sessions:
        from . import procinfo

        self_pid = procinfo.ancestor_matching(os.getpid(), watch_mod.AGENT_COMM_NAMES)
        inferred, self_pid = watch_mod.infer_self_sessions(
            db, self_pid, args.directory or str(Path.cwd())
        )
        self_sessions.extend(inferred)
        print(f"watch: self agent pid={self_pid} self sessions={self_sessions}", file=sys.stderr)

    targets = [int(p) for p in (args.targets or "").replace(",", " ").split()] if args.targets else []
    if not targets and args.autodetect:
        targets = _autodetect_targets()
    if not targets:
        print("no target pids; pass --targets or --autodetect", file=sys.stderr)
        return 2

    state_path = Path(args.state)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    def emit(state) -> None:
        state_path.write_text(state.to_json(), encoding="utf-8")
        print(f"[{time.strftime('%H:%M:%S')}] {watch_mod.format_status(state)}", flush=True)

    monitor = watch_mod.Monitor(
        targets,
        self_sessions=self_sessions,
        self_agent_pid=self_pid,
        window=args.window,
        streak_required=args.streak,
        max_wait=args.max_wait,
        db=db,
        sleeper=time.sleep,
    )
    print(
        f"watch: targets={targets} window={args.window}s streak={args.streak} "
        f"max_wait={int(args.max_wait)}s out={args.out}",
        file=sys.stderr,
    )
    quiescent = monitor.run(on_tick=emit)
    state_path.write_text(monitor.state.to_json(), encoding="utf-8")
    print(f"watch: finished reason={monitor.state.reason} quiescent={quiescent}")

    if not quiescent:
        print(f"watch: giving up ({monitor.state.reason})", file=sys.stderr)
        return 3
    if args.no_snapshot:
        return 0

    result = snapshot_mod.create_snapshot(
        Path(args.root),
        Path(args.out),
        extra_skip_suffixes=tuple(args.skip_suffix or ()),
        on_progress=lambda r: print(f"  ... {r.files} files", file=sys.stderr),
    )
    state_path.with_name("snapshot.json").write_text(result.to_json(), encoding="utf-8")
    check = snapshot_mod.verify_zip(Path(args.out))
    print(json.dumps({**result.__dict__, "verify": check}, indent=2, sort_keys=True, default=str))
    return 0 if check.get("ok") else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sitemap",
        description="Machine-readable sitemap of the mem20 monorepo, plus quiescence poller and source snapshotter.",
    )
    parser.add_argument("--version", action="version", version=f"{SCHEMA} mem20sitemapz")
    sub = parser.add_subparsers(dest="command")

    p_build = sub.add_parser("build", help="scan the tree and write the index")
    p_build.add_argument("--root", default=str(DEFAULT_ROOT))
    p_build.add_argument("--index-dir", default=str(DEFAULT_INDEX_DIR))
    p_build.add_argument("--depth", type=int, default=2)
    p_build.set_defaults(func=cmd_build)

    p_search = sub.add_parser("search", help="search the index")
    p_search.add_argument("query")
    p_search.add_argument("--index-dir", default=str(DEFAULT_INDEX_DIR))
    p_search.add_argument("--limit", type=int, default=15)
    p_search.add_argument("--json", action="store_true")
    p_search.set_defaults(func=cmd_search)

    p_show = sub.add_parser("show", help="show one subsystem in full")
    p_show.add_argument("name")
    p_show.add_argument("--index-dir", default=str(DEFAULT_INDEX_DIR))
    p_show.add_argument("--json", action="store_true")
    p_show.set_defaults(func=cmd_show)

    p_snap = sub.add_parser("snapshot", help="write a source-only zip of the tree")
    p_snap.add_argument("--root", default=str(DEFAULT_ROOT))
    p_snap.add_argument("--out", default=str(snapshot_mod.DEFAULT_OUT))
    p_snap.add_argument("--skip-dir", action="append")
    p_snap.add_argument("--skip-suffix", action="append")
    p_snap.add_argument("--dry-run", action="store_true")
    p_snap.add_argument("--json", action="store_true")
    p_snap.set_defaults(func=cmd_snapshot)

    p_verify = sub.add_parser("verify", help="verify a zip and scan it for secret paths")
    p_verify.add_argument("--out", default=str(snapshot_mod.DEFAULT_OUT))
    p_verify.set_defaults(func=cmd_verify)

    p_watch = sub.add_parser("watch", help="wait until every target agent stops working, then snapshot")
    p_watch.add_argument("--targets", default="", help="comma or space separated pids")
    p_watch.add_argument("--autodetect", action="store_true", help="find other opencode processes")
    p_watch.add_argument("--root", default=str(DEFAULT_ROOT))
    p_watch.add_argument("--out", default=str(snapshot_mod.DEFAULT_OUT))
    p_watch.add_argument("--db", default=str(DEFAULT_DB))
    p_watch.add_argument("--window", type=float, default=watch_mod.DEFAULT_WINDOW)
    p_watch.add_argument("--streak", type=int, default=watch_mod.DEFAULT_STREAK)
    p_watch.add_argument("--max-wait", type=float, default=watch_mod.DEFAULT_MAX_WAIT)
    p_watch.add_argument("--self-session", action="append")
    p_watch.add_argument("--directory", default="")
    p_watch.add_argument("--state", default="/opt/mem20/.sitemap/watch-state.json")
    p_watch.add_argument("--skip-suffix", action="append")
    p_watch.add_argument("--no-snapshot", action="store_true", help="report quiescence, write nothing")
    p_watch.set_defaults(func=cmd_watch)

    common(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if not argv or argv[0].startswith("-"):
        argv = ["build", *argv]
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
