"""Index the on-disk agent skills into the mem20 catalog.

Why this exists
---------------
``mem20agentz skills catalog`` reads mem20's *procedural* skill store, which on
this box held four entries -- one of which was a ``test_skill`` fixture. That is
not the same thing as the skills an agent can actually use. The real inventory
is on disk: one directory per skill, each with a ``SKILL.md`` carrying YAML
frontmatter (``name`` and ``description``). There are hundreds of those, they
are first class, and the catalog could not see a single one.

So the catalog now reports two provenances, and says which is which:

* ``procedural`` -- mem20's own procedural store.
* ``skill``      -- a ``SKILL.md`` on disk, with the path it was read from.

Nothing is copied into another store and nothing is rewritten. This reads the
files the agent platform already loads and reports them alongside the procedural
entries, so ``!skills blender`` finds the real Blender skill instead of nothing.

Cache
-----
The on-disk scan is cached against the newest ``SKILL.md`` mtime and the set of
directories, so repeated searches do not re-read hundreds of files, while adding
a skill still shows up without a restart.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable, Optional

#: Where agent skills live. Both are searched; a name in both is reported once.
DEFAULT_ROOTS = tuple(
    Path(p) for p in os.environ.get(
        "MEM20_SKILL_ROOTS",
        "/root/.config/opencode/skills:/opt/mem20-skills/skills",
    ).split(":") if p
)

#: A skill is a directory containing this file.
MARKER = "SKILL.md"

#: Only the frontmatter is read, and only these two keys matter. Parsing the
#: whole document would mean reading every skill body on every cold scan.
_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.S)
_NAME = re.compile(r"^name:\s*(.+?)\s*$", re.M)
_DESC = re.compile(r"^description:\s*(.+?)\s*$", re.M | re.S)


def parse_frontmatter(text: str) -> tuple[str, str]:
    """Return ``(name, description)`` from a SKILL.md's frontmatter.

    Only the leading ``---`` block is considered, and only ``name`` and
    ``description``. A skill with no frontmatter yields empty strings and is
    skipped by the caller rather than indexed with a blank name.
    """
    match = _FRONT.match(text)
    if not match:
        return "", ""
    block = match.group(1)
    name = _NAME.search(block)
    desc = _DESC.search(block)
    name_val = name.group(1).strip().strip("\"'") if name else ""
    desc_val = desc.group(1).strip().strip("\"'") if desc else ""
    # A description can wrap onto following lines; keep it to one line so a
    # channel reply stays readable.
    desc_val = " ".join(desc_val.split())
    return name_val, desc_val


class DiskSkillIndex:
    """Lazily scans skill roots, cached against the filesystem."""

    def __init__(self, roots: Optional[Iterable[Path]] = None) -> None:
        self.roots = tuple(roots if roots is not None else DEFAULT_ROOTS)
        self._cache: Optional[tuple[tuple, list[dict]]] = None

    # ------------------------------------------------------------------ scan
    def _signature(self) -> tuple:
        """Cheap fingerprint of the roots: which skills, and how new they are.

        Used only to decide whether the cache is stale, so it must not read file
        contents.
        """
        sig = []
        for root in self.roots:
            if not root.is_dir():
                continue
            for entry in sorted(root.iterdir()):
                marker = entry / MARKER
                if marker.is_file():
                    try:
                        sig.append((str(entry), marker.stat().st_mtime))
                    except OSError:
                        continue
        return tuple(sig)

    def all(self) -> list[dict]:
        """Every on-disk skill, as dicts with name/description/source/path."""
        sig = self._signature()
        if self._cache is not None and self._cache[0] == sig:
            return list(self._cache[1])

        found: dict[str, dict] = {}
        for root in self.roots:
            if not root.is_dir():
                continue
            for entry in sorted(root.iterdir()):
                marker = entry / MARKER
                if not marker.is_dir() and not marker.is_file():
                    continue
                try:
                    text = marker.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                name, desc = parse_frontmatter(text)
                if not name:
                    # No usable name means no way to search or invoke it.
                    continue
                found.setdefault(name, {
                    "name": name,
                    "description": desc,
                    "source": "skill",
                    "path": str(entry),
                })
        rows = sorted(found.values(), key=lambda r: r["name"])
        self._cache = (sig, rows)
        return list(rows)