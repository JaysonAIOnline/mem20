"""Expose mem20 console scripts on the default PATH.

Why this exists
---------------
Every mem20 subsystem installs its console script into the shared virtualenv
at ``/root/.venv/bin``. That directory is on the PATH of an interactive login
shell, because ``/etc/profile.d/thestack-env.sh`` adds it - so ``sitemap`` and
friends work when you type them at a prompt.

They do **not** resolve anywhere else: a systemd unit, a cron job, a script
invoked with ``sh -c``, or ``ssh host 'somecommand'`` all get the default
system PATH, which has never included the venv. That is a real gap, and it is
silent - the tool exists, it is installed, and it is simply not found.

This links the mem20-owned scripts into ``/root/.local/bin``, which *is* on the
default PATH, so the same command works in every context.

What it deliberately does not do
--------------------------------
Only distributions mem20 owns are linked. Third-party console scripts that
happen to sit in the same venv (chroma from chromadb, pytest, uvicorn and so on)
are left alone: promoting those estate-wide is a decision for the owner, not a
side effect of installing mem20 tools.

A script that is not a command-line tool is also left alone. ``mem20-metrics``
is a blocking HTTP server whose ``main()`` calls ``serve_forever`` and ignores
argv, so linking it would put something that never returns on the PATH.

Re-runnable by design: running it again after a package upgrade repairs the
links, and it never overwrites a real file it did not create.
"""

from __future__ import annotations

import argparse
import email
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

VENV_BIN = Path(os.environ.get("MEM20_VENV_BIN", "/root/.venv/bin"))
SITE_PACKAGES = Path(
    os.environ.get(
        "MEM20_SITE_PACKAGES", "/root/.venv/lib/python3.14/site-packages"
    )
)
DEFAULT_TARGET = Path(os.environ.get("MEM20_PATH_DIR", "/root/.local/bin"))

#: Distributions mem20 owns. Matched on the normalised distribution name, which
#: is metadata rather than a directory name, so an underscore/hyphen difference
#: cannot silently drop a tool.
OWNED_PREFIXES = ("mem20",)
OWNED_EXACT = frozenset({"braid", "braid-python"})

#: Console scripts that are real programs but not commands. Each entry is the
#: reason, so this list can be argued with rather than trusted.
EXCLUDED = {
    "mem20-metrics": "blocking HTTP server; main() calls serve_forever and ignores argv",
}


@dataclass
class Finding:
    script: str
    distribution: str
    target: Path
    status: str
    detail: str = ""


def _is_owned(name: str) -> bool:
    normalised = name.lower().replace("_", "-")
    return normalised.startswith(OWNED_PREFIXES) or normalised in OWNED_EXACT


def discover_scripts(site_packages: Path = SITE_PACKAGES) -> dict[str, str]:
    """Map console script name -> owning distribution, for mem20 packages only.

    Reads the installed metadata rather than guessing from file names, because
    the distribution name is what tells us who owns a command.
    """
    found: dict[str, str] = {}
    if not site_packages.is_dir():
        return found
    for info in sorted(site_packages.glob("*.dist-info")):
        metadata = info / "METADATA"
        entry_points = info / "entry_points.txt"
        if not metadata.is_file() or not entry_points.is_file():
            continue
        try:
            distribution = email.message_from_string(
                metadata.read_text(errors="replace")
            ).get("Name", "")
        except Exception:  # noqa: BLE001 - a malformed METADATA must not stop the sweep
            continue
        if not distribution or not _is_owned(distribution):
            continue
        for line in entry_points.read_text(errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("[") or "=" not in line:
                continue
            script = line.split("=", 1)[0].strip()
            if script and script not in EXCLUDED:
                found[script] = distribution
    return found


def plan(
    venv_bin: Path = VENV_BIN,
    site_packages: Path = SITE_PACKAGES,
    target_dir: Path = DEFAULT_TARGET,
) -> list[Finding]:
    """Decide what should be linked, without touching the filesystem."""
    scripts = discover_scripts(site_packages)
    findings: list[Finding] = []
    for script, distribution in sorted(scripts.items()):
        source = venv_bin / script
        target = target_dir / script
        if not source.is_file():
            findings.append(Finding(script, distribution, target, "missing", f"no {source}"))
            continue
        if target.is_symlink() and target.resolve() == source.resolve():
            findings.append(Finding(script, distribution, target, "current"))
            continue
        if target.exists() and not target.is_symlink():
            # A real file that we did not create. Never clobber it.
            findings.append(
                Finding(script, distribution, target, "conflict", "real file, not a symlink; left alone")
            )
            continue
        findings.append(Finding(script, distribution, target, "link"))
    for script, why in sorted(EXCLUDED.items()):
        findings.append(Finding(script, "-", target_dir / script, "excluded", why))
    return findings


def verify(
    site_packages: Path = SITE_PACKAGES, target_dir: Path = DEFAULT_TARGET
) -> list[str]:
    """Return the names that should resolve but do not, seen from a bare PATH."""
    default_path = "/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    missing: list[str] = []
    for name in sorted(discover_scripts(site_packages)):
        if not shutil.which(name, path=default_path):
            missing.append(name)
    return missing


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mem20-path",
        description=(
            "Link mem20 console scripts into a default-PATH directory so they "
            "resolve outside an interactive login shell."
        ),
    )
    parser.add_argument(
        "--apply", action="store_true", help="create the links (default is a dry run)"
    )
    parser.add_argument(
        "--target", default=str(DEFAULT_TARGET), help=f"directory to link into (default {DEFAULT_TARGET})"
    )
    parser.add_argument(
        "--site", dest="site", default=str(SITE_PACKAGES),
        help="site-packages directory to read installed metadata from",
    )
    parser.add_argument(
        "--venv", dest="venv", default=str(VENV_BIN),
        help="directory holding the real console scripts",
    )
    parser.add_argument(
        "--verify", action="store_true", help="exit non-zero if any tool still does not resolve"
    )
    args = parser.parse_args(argv)

    target_dir = Path(args.target)
    venv_bin = Path(args.venv)
    site_packages = Path(args.site)
    findings = plan(venv_bin=venv_bin, site_packages=site_packages, target_dir=target_dir)

    if args.verify:
        missing = verify(site_packages=site_packages, target_dir=target_dir)
        for name in missing:
            print(f"MISSING {name}", file=sys.stderr)
        print(f"verify: {len(missing)} tool(s) unresolvable from the default PATH")
        return 1 if missing else 0

    to_link = [f for f in findings if f.status == "link"]
    if args.apply:
        target_dir.mkdir(parents=True, exist_ok=True)
        created = 0
        for finding in findings:
            if finding.status != "link":
                continue
            source = venv_bin / finding.script
            if finding.target.is_symlink() or finding.target.exists():
                finding.target.unlink()
            finding.target.symlink_to(source)
            os.chmod(finding.target, 0o755)
            created += 1
        print(f"linked {created} tool(s) into {target_dir}")
    else:
        print(f"dry run: {len(to_link)} link(s) would be created in {target_dir}")

    for status in ("missing", "conflict", "excluded"):
        rows = [f for f in findings if f.status == status]
        if not rows:
            continue
        print(f"\n{status} ({len(rows)}):")
        for finding in rows:
            print(f"  {finding.script:20} {finding.detail}")

    current = sum(1 for f in findings if f.status == "current")
    if current:
        print(f"\nalready current: {current}")
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
