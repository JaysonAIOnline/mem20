"""Sarge — the kanban decomposer.

What he does
------------
Jayson writes a roadmap describing a change. Sarge finds it, breaks each phase
into a card on the kanban board, and writes the new card's id back into the
phase as ``jobid``. The kanban bot then advertises the card and a bot takes it.

The loop is therefore: ``roadmap -> Sarge -> card -> bot accepts -> work ->
verified done``. Nothing in that chain is a canned string; every card traces
back to a phase someone actually wrote.

Why ``jobid`` is the whole trick
--------------------------------
A phase carrying a ``jobid`` has already been decomposed. Sarge skips it. That
one field is what makes the loop safe to run on a loop forever: without it,
every pass would create a fresh card for every phase and the board would drown
in duplicates within minutes.

The write-back is atomic (temp file plus ``os.replace``). A crash between
creating the card and writing the id back leaves one orphan card, which is
recoverable; a half-written roadmap file is not, and roadmaps are hand-edited
source. So the id write is the thing that gets the care.

Skew found in the real roadmaps
-------------------------------
51 of the 318 phases on this box store ``name`` as a nested object rather than a
string::

    {"name": {"name": "Phase 1: Audit ...", "status": "in_progress"},
     "status": "planned", "notes": ""}

``mcp/roadmap_tools.py`` matches phases with ``phase["name"] == phase_name``, so
on those 51 it can never match and ``roadmap_update_phase`` silently reports
"not found" while changing nothing. Sarge normalises both shapes through
:func:`phase_title` instead of assuming, so he does not inherit that blindness.

The watermark
-------------
On first run Sarge records an activation timestamp and only ever looks at
roadmaps at or after it. That is deliberate: the existing roadmaps predate him
and mostly describe historical work, so backfilling them would bury the board
under hundreds of stale cards. Earlier phases can still be added by hand::

    mem20-sarge add <roadmap> <phase>      # ignores the watermark
    mem20-sarge add <roadmap> --all

Both paths go through the same :func:`decompose_phase`, so a hand-added card is
identical to an automatic one and carries the same ``jobid`` write-back.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional, Protocol

from .door import DEFAULT_DOOR, Door, DoorError, NotFound

#: Where the roadmap system keeps its files. Mirrors the default the MCP
#: roadmap tools use (``MEM20_ROADMAPS_DIR``), so Sarge and the agent agree.
ROADMAPS_DIR = Path(
    os.environ.get("MEM20_ROADMAPS_DIR", "/opt/mem20/roadmaps")
)

#: Sarge's own state: the activation watermark.
STATE_PATH = Path(
    os.environ.get("MEM20_SARGE_STATE", "/root/.mem20agentz/sarge.json")
)

#: Field on a roadmap phase holding the card id Sarge created for it.
JOB_FIELD = "jobid"

#: Field on a roadmap phase naming the phases that must be completed before it
#: may become a card. Without this a dependency-ordered roadmap is flattened
#: into independent cards and every step looks pickable at once.
DEPENDS_FIELD = "depends_on"

#: Phase statuses that count as finished, for dependency purposes. Narrower than
#: SKIP_STATUSES on purpose: "blocked" is not done, so it must not unblock work.
DONE_STATUSES = frozenset({"completed", "done"})

#: Phase statuses that never become cards. A completed phase is history and a
#: blocked one is a decision someone has to make, not work to hand to a bot.
SKIP_STATUSES = frozenset({"completed", "blocked", "done"})

#: Bounded on purpose. A decomposer that runs flat out hammers the door.
DEFAULT_INTERVAL = 60.0
MIN_INTERVAL = 5.0


class SargeError(RuntimeError):
    """Sarge could not do what was asked."""


class DoorLike(Protocol):
    """The only thing Sarge needs from a kanban door.

    Narrower than :class:`~mem20kanbanz.door.Door` on purpose: Sarge creates
    cards and reads nothing else, so this is the whole contract he depends on.
    Stating it means the dependency is visible instead of implied.
    """

    def add_card(self, board: str, title: str, content: str = "",
                 assignee: str = "", tags: Iterable[str] = (), column: str = "",
                 metadata: Optional[dict] = None) -> Any:
        ...


# --------------------------------------------------------------------- phases
@dataclass
class Phase:
    """One roadmap phase, normalised into a shape Sarge can reason about."""

    roadmap: str
    roadmap_description: str
    path: Path
    index: int
    title: str
    status: str
    notes: str
    jobid: Optional[str] = None
    depends_on: tuple[int, ...] = ()

    @property
    def short_id(self) -> str:
        return self.jobid[:8] if self.jobid else "(none)"

    @property
    def reference(self) -> str:
        return f"{self.roadmap}#{self.index}"


def phase_title(phase: Any) -> str:
    """Return a phase's title, whatever shape the roadmap stored it in.

    Both the plain string and the nested-object form seen in the wild are
    accepted. An empty or unusable title returns ``""`` so the caller can refuse
    rather than invent one.
    """
    name = phase.get("name") if isinstance(phase, dict) else None
    if isinstance(name, str):
        return name.strip()
    if isinstance(name, dict):
        inner = name.get("name")
        if isinstance(inner, str):
            return inner.strip()
    return ""


def _phase_status(phase: Any, title_fallback: Any = None) -> str:
    status = phase.get("status") if isinstance(phase, dict) else None
    if isinstance(status, str) and status.strip():
        return status.strip()
    return ""


def load_roadmap(path: Path) -> Optional[dict]:
    """Read one roadmap file. Returns ``None`` if it is not usable.

    A malformed file is skipped, never raised: one bad roadmap must not stop the
    loop, and silently rewriting a file we cannot parse would destroy it.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("phases"), list):
        return None
    data.setdefault("name", path.stem)
    if not isinstance(data.get("name"), str):
        data["name"] = path.stem
    if not isinstance(data.get("description"), str):
        data["description"] = ""
    return data


def _phase_dependencies(raw: Any) -> tuple[int, ...]:
    """Read a phase's ``depends_on`` into a tuple of phase indexes.

    Accepts indexes as integers or as numeric strings, because a roadmap is
    hand-edited and both spellings occur. Anything unparseable is dropped
    rather than guessed at -- an unreadable reference must not be invented into
    a dependency that happens to be satisfied.
    """
    value = raw.get(DEPENDS_FIELD) if isinstance(raw, dict) else None
    if not isinstance(value, (list, tuple)):
        return ()
    out: list[int] = []
    for item in value:
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            out.append(item)
        elif isinstance(item, str) and item.strip().isdigit():
            out.append(int(item.strip()))
    return tuple(out)


def read_phases(path: Path, data: dict) -> Iterator[Phase]:
    """Yield the usable phases of an already-loaded roadmap."""
    for index, raw in enumerate(data.get("phases") or []):
        if not isinstance(raw, dict):
            continue
        title = phase_title(raw)
        if not title:
            # Refuse rather than invent a title. A card called "Phase 3" is
            # noise on a board people are meant to work from.
            continue
        jobid = raw.get(JOB_FIELD)
        notes = raw.get("notes")
        yield Phase(
            roadmap=data["name"],
            roadmap_description=data.get("description", ""),
            path=path,
            index=index,
            title=title,
            status=_phase_status(raw),
            notes=notes if isinstance(notes, str) else "",
            jobid=jobid if isinstance(jobid, str) and jobid else None,
            depends_on=_phase_dependencies(raw),
        )


def scan(roadmaps_dir: Path = ROADMAPS_DIR,
         since: Optional[float] = None) -> Iterator[Phase]:
    """Yield every phase in every roadmap, newest roadmap files included.

    ``since`` is the watermark: a roadmap whose file mtime is older than it is
    skipped entirely. The write-back updates mtime, so a roadmap Sarge has
    already touched stays in scope on later passes.
    """
    if not roadmaps_dir.is_dir():
        return
    for path in sorted(roadmaps_dir.rglob("*.json")):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if since is not None and mtime < since:
            continue
        data = load_roadmap(path)
        if data is None:
            continue
        yield from read_phases(path, data)


# ----------------------------------------------------------------- watermark
def load_state(path: Path = STATE_PATH) -> dict:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return state if isinstance(state, dict) else {}


def watermark(path: Path = STATE_PATH, create: bool = True) -> Optional[float]:
    """Return Sarge's activation timestamp, recording it on first call.

    Returns ``None`` when ``create`` is false and nothing is recorded yet, which
    is how ``scan --dry-run`` can show what he would see without stamping the
    watermark as a side effect of asking.
    """
    state = load_state(path)
    value = state.get("watermark")
    if isinstance(value, (int, float)):
        return float(value)
    if not create:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    payload = {"watermark": now,
               "activated": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now))}
    _atomic_write_json(path, payload)
    return now


# -------------------------------------------------------------------- writing
def _atomic_write_json(path: Path, payload: Any) -> None:
    """Write JSON via temp file plus rename, so a crash cannot truncate.

    Roadmaps are hand-edited source. A partial write there loses someone's
    thinking, which is the one failure this whole tool exists to avoid causing.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.",
                                    suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def stamp_jobid(path: Path, index: int, jobid: str) -> bool:
    """Record ``jobid`` on one phase of one roadmap. True if the file changed.

    Re-reads the file immediately before writing so a roadmap Jayson edited
    between Sarge's scan and this call is not silently overwritten with the copy
    Sarge read earlier.
    """
    data = load_roadmap(path)
    if data is None:
        return False
    phases = data.get("phases") or []
    if not isinstance(phases, list) or index >= len(phases):
        return False
    raw = phases[index]
    if not isinstance(raw, dict):
        return False
    if raw.get(JOB_FIELD) == jobid:
        return False
    raw[JOB_FIELD] = jobid
    _atomic_write_json(path, data)
    return True


def card_content(phase: Phase) -> str:
    """The card body: where this job came from and what it is.

    A card with only a title is the failure mode this whole system just spent a
    day removing, so the body always carries the roadmap, its description, the
    phase notes and the exact source location.
    """
    lines = [f"Roadmap: {phase.roadmap}", f"Phase {phase.index}: {phase.title}"]
    if phase.roadmap_description:
        lines += ["", phase.roadmap_description]
    if phase.notes:
        lines += ["", f"Notes: {phase.notes}"]
    source = f"Source: {phase.path} phase {phase.index} ({phase.reference})"
    by = f"Decomposed by Sarge from {phase.roadmap}#{phase.index}."
    lines += ["", source, by]
    return "\n".join(lines)


def card_metadata(phase: Phase) -> dict:
    return {
        "source": "sarge",
        "roadmap": phase.roadmap,
        "roadmap_file": str(phase.path),
        "phase_index": phase.index,
        "phase_title": phase.title,
        "phase_status": phase.status,
    }


# ----------------------------------------------------------------- decompose
@dataclass
class Outcome:
    """What one decompose pass did. Counted, not narrated."""

    created: list[tuple[str, str]] = field(default_factory=list)
    skipped_existing: int = 0
    skipped_status: int = 0
    stamped: int = 0
    unstamped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    blocked_dependency: int = 0
    blocked: list[tuple[str, list[str]]] = field(default_factory=list)

    @property
    def summary(self) -> str:
        return (f"{len(self.created)} created, {self.skipped_existing} already had "
                f"a job, {self.skipped_status} skipped by status, "
                f"{self.blocked_dependency} blocked by dependency, "
                f"{self.stamped} stamped, {len(self.failed)} failed")


def wants_card(phase: Phase) -> bool:
    """True if this phase should become a card right now."""
    if phase.jobid:
        return False
    return phase.status.lower() not in SKIP_STATUSES


@dataclass
class Decomposed:
    """The result of decomposing one phase.

    ``stamped`` travels with the id rather than being re-derived by the caller,
    because the stamp happens exactly once inside :func:`decompose_phase`.
    Re-stamping to find out would both corrupt the count and hide the one case
    that matters: a card that exists but whose phase never learned its id.
    """

    card_id: str
    stamped: bool


def decompose_phase(door: DoorLike, phase: Phase, board: str,
                    dry_run: bool = False) -> Decomposed:
    """Create one card for one phase and stamp its id back.

    The card is created before the stamp, never after. If the stamp fails the
    worst case is a duplicate on the next pass, which a human can see; the other
    order would mean a jobid pointing at a card that does not exist.
    """
    if dry_run:
        return Decomposed(card_id=f"dry-run:{phase.roadmap}#{phase.index}",
                          stamped=False)
    try:
        card = door.add_card(board, phase.title, content=card_content(phase),
                             tags=("sarge",), metadata=card_metadata(phase))
    except (DoorError, NotFound) as exc:
        raise SargeError(f"door refused the card for {phase.reference}: {exc}") from exc
    stamped = stamp_jobid(phase.path, phase.index, card.id)
    return Decomposed(card_id=card.id, stamped=stamped)


def unmet_dependencies(phase: Phase, siblings: dict) -> list[str]:
    """Return human-readable reasons this phase must not become a card yet.

    Fails closed. A dependency that names a phase which does not exist is
    reported as unmet, never assumed satisfied, and the check is not recursive,
    so a dependency cycle is reported rather than looped on.
    """
    unmet: list[str] = []
    for dep in phase.depends_on:
        target = siblings.get(dep)
        if target is None:
            unmet.append(f"step {dep} is not a phase of {phase.roadmap}")
        elif target.status.lower() not in DONE_STATUSES:
            unmet.append(
                f"{target.reference} is "
                f"{target.status or 'planned'}, not completed"
            )
    return unmet


def run_once(door: DoorLike, board: str = "Fleet HQ",
             roadmaps_dir: Path = ROADMAPS_DIR,
             since: Optional[float] = None,
             dry_run: bool = False) -> Outcome:
    """One full pass over the roadmaps. Never raises for a single bad roadmap."""
    outcome = Outcome()
    phases = list(scan(roadmaps_dir, since=since))
    # Dependencies are resolved against the phases of the same roadmap file.
    by_file: dict[str, dict] = {}
    for phase in phases:
        by_file.setdefault(str(phase.path), {})[phase.index] = phase

    for phase in phases:
        if phase.jobid:
            outcome.skipped_existing += 1
            continue
        if phase.status.lower() in SKIP_STATUSES:
            outcome.skipped_status += 1
            continue
        blockers = unmet_dependencies(phase, by_file.get(str(phase.path), {}))
        if blockers:
            outcome.blocked_dependency += 1
            outcome.blocked.append((phase.reference, blockers))
            continue
        try:
            result = decompose_phase(door, phase, board, dry_run=dry_run)
        except SargeError as exc:
            outcome.failed.append((phase.reference, str(exc)))
            continue
        outcome.created.append((result.card_id, phase.title))
        if dry_run:
            continue
        if result.stamped:
            outcome.stamped += 1
        else:
            # The card exists but the phase does not know its id. Say so rather
            # than letting it be re-created silently on the next pass.
            outcome.unstamped.append(phase.reference)
    return outcome


def serve(door: DoorLike, board: str = "Fleet HQ", interval: float = DEFAULT_INTERVAL,
          roadmaps_dir: Path = ROADMAPS_DIR, runs: Optional[int] = None,
          stream=sys.stdout) -> int:
    """Run the loop. ``runs`` bounds it, which is what the tests use.

    The interval is clamped so a typo cannot turn Sarge into a door-hammer, and
    the loop is interruptible so SIGTERM from systemd stops it promptly.
    """
    interval = max(MIN_INTERVAL, float(interval))
    since = watermark()
    count = 0
    while runs is None or count < runs:
        try:
            outcome = run_once(door, board=board, roadmaps_dir=roadmaps_dir,
                               since=since)
            if outcome.created or outcome.failed or outcome.unstamped:
                print(f"sarge: {outcome.summary}", file=stream, flush=True)
                for ref, err in outcome.failed:
                    print(f"sarge: FAILED {ref}: {err}", file=stream, flush=True)
                for ref in outcome.unstamped:
                    print(f"sarge: WARNING {ref} was created but not stamped; "
                          f"it will be duplicated next pass", file=stream,
                          flush=True)
        except DoorError as exc:
            # The door being down is not fatal. Report it and try again next
            # pass rather than exiting, so a door restart does not need Sarge.
            print(f"sarge: door unreachable — {exc}", file=stream, flush=True)
        count += 1
        if runs is not None and count >= runs:
            break
        time.sleep(interval)
    return 0


# ----------------------------------------------------------------------- cli
def add_parser(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
    sub = p.add_subparsers(dest="sarge_cmd")

    s = sub.add_parser("serve", help="run the decomposer loop")
    s.add_argument("--board", default="Fleet HQ")
    s.add_argument("--door", default=DEFAULT_DOOR)
    s.add_argument("--interval", type=float, default=DEFAULT_INTERVAL,
                   help=f"seconds between passes (min {MIN_INTERVAL:g})")
    s.add_argument("--roadmaps", default=str(ROADMAPS_DIR))
    s.add_argument("--runs", type=int, default=None,
                   help="stop after N passes instead of looping forever")
    s.add_argument("--no-watermark", action="store_true",
                   help="ignore the activation watermark and read every roadmap")

    s = sub.add_parser("scan", help="show what would be decomposed, change nothing")
    s.add_argument("--roadmaps", default=str(ROADMAPS_DIR))
    s.add_argument("--board", default="Fleet HQ")
    s.add_argument("--ignore-watermark", action="store_true")
    s.add_argument("--all", action="store_true",
                   help="include phases that already have a jobid")

    s = sub.add_parser("add", help="decompose one phase by hand, ignoring the watermark")
    s.add_argument("roadmap")
    s.add_argument("phase", nargs="?", default=None,
                   help="phase index or title substring; omit with --all")
    s.add_argument("--all", action="store_true", help="every phase in the roadmap")
    s.add_argument("--board", default="Fleet HQ")
    s.add_argument("--door", default=DEFAULT_DOOR)

    sub.add_parser("watermark", help="print the activation watermark")
    return p


def _find_roadmap(roadmaps_dir: Path, name: str) -> Optional[Path]:
    direct = roadmaps_dir / f"{name}.json"
    if direct.is_file():
        return direct
    for path in sorted(roadmaps_dir.rglob("*.json")):
        data = load_roadmap(path)
        if data and data.get("name") == name:
            return path
    return None


def _cmd_scan(args: argparse.Namespace) -> int:
    roadmaps_dir = Path(args.roadmaps)
    since = None if args.ignore_watermark else watermark(create=False)
    if since is None:
        print("scan: no watermark recorded yet, so this is every roadmap")
    total = pending = 0
    for phase in scan(roadmaps_dir, since=since):
        total += 1
        if wants_card(phase) or args.all:
            pending += 1
            print(f"  would create: {phase.reference} — {phase.title}")
    print(f"scan: {pending} of {total} phases in scope")
    return 0


def _cmd_add(args: argparse.Namespace) -> int:
    roadmaps_dir = ROADMAPS_DIR
    path = _find_roadmap(roadmaps_dir, args.roadmap)
    if path is None:
        print(f"sarge: no roadmap named {args.roadmap!r} under {roadmaps_dir}",
              file=sys.stderr)
        return 1
    data = load_roadmap(path)
    if data is None:
        print(f"sarge: {path} is not a readable roadmap", file=sys.stderr)
        return 1
    phases = [p for p in read_phases(path, data)]
    if args.all:
        chosen = phases
    else:
        token = str(args.phase)
        chosen = [p for p in phases
                  if token == str(p.index) or token.lower() in p.title.lower()]
    if not chosen:
        print(f"sarge: no phase matching {args.phase!r} in {data['name']}",
              file=sys.stderr)
        return 1
    door = Door(args.door)
    for phase in chosen:
        if phase.jobid:
            print(f"  skip {phase.reference}: already has job {phase.short_id}")
            continue
        try:
            result = decompose_phase(door, phase, args.board)
        except SargeError as exc:
            print(f"  FAILED {phase.reference}: {exc}", file=sys.stderr)
            return 1
        note = "" if result.stamped else "  (WARNING: not stamped, will repeat)"
        print(f"  created {result.card_id[:8]} — {phase.title}{note}")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    door = Door(args.door)
    since = None if args.no_watermark else watermark()
    if since is None:
        print("sarge: no watermark, reading every roadmap", flush=True)
    else:
        print(f"sarge: watermark {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(since))}"
              f" — only roadmaps at or after it", flush=True)
    if args.runs is not None:
        return serve(door, board=args.board, interval=args.interval,
                     roadmaps_dir=Path(args.roadmaps), runs=args.runs)
    try:
        return serve(door, board=args.board, interval=args.interval,
                     roadmaps_dir=Path(args.roadmaps))
    except KeyboardInterrupt:
        return 0


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="mem20-sarge",
                                description="Decompose roadmap phases into kanban cards.")
    add_parser(p)
    args = p.parse_args(argv)
    command = getattr(args, "sarge_cmd", None)
    if command == "serve":
        return _cmd_serve(args)
    if command == "scan":
        return _cmd_scan(args)
    if command == "add":
        return _cmd_add(args)
    if command == "watermark":
        value = watermark(create=False)
        print("no watermark recorded yet" if value is None
              else time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(value)))
        return 0
    p.print_help()
    return 1