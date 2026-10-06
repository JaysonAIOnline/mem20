"""Skills store — catalog, bundles, curator, sync (sub-phase 2.3).

Skills are mem20 procedural skills; the store layers bundles + curation + sync
on top of them. Bundles are named skill groups persisted on disk (YAML, one
file per bundle under <runtime>/skills/bundles/) so they survive restarts and
can be shared.

- catalog     list/search the full mem20 procedural-skill inventory
- bundle      group skills by name
- curator     prune skills a bundle references but mem20 no longer has
- sync        reconcile a bundle on disk with the live inventory (report only)
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from typing import Optional

import yaml

from ._substrate import Backend, get_backend
from .skill_index import DiskSkillIndex
from .config import config_dir

BUNDLES_DIR = "skills/bundles"


def _bundles_dir() -> pathlib.Path:
    return config_dir() / BUNDLES_DIR


def _safe_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "-" for c in name)


@dataclass
class SkillInfo:
    name: str
    description: str = ""
    #: "procedural" (mem20's own store) or "skill" (a SKILL.md on disk).
    source: str = ""
    #: Where a disk skill was read from, so a reader can go and look.
    path: str = ""


#: One process-wide scan of the on-disk skills, shared by every store instance.
_DISK_INDEX = DiskSkillIndex()


class SkillsStore:
    def __init__(self, backend: Optional[Backend] = None,
                 root: Optional[pathlib.Path] = None) -> None:
        self._b = backend or get_backend()
        self.root = root or _bundles_dir()

    # -------------------------------------------------------------- catalog
    def catalog(self, query: str = "", include_disk: bool = True) -> list[SkillInfo]:
        """Every skill an agent can actually use, from both provenances.

        ``procedural`` entries come from mem20's own store. ``skill`` entries
        are read from the on-disk ``SKILL.md`` files the agent platform already
        loads -- see :mod:`mem20agentz.skill_index` for why the catalog used to
        be four entries while hundreds of real skills sat invisible.

        Set ``include_disk=False`` for the procedural store alone, which is what
        bundle reconciliation wants: a bundle names procedural skills, and
        treating an unrelated on-disk skill of the same name as a bundle member
        would make ``curator`` prune things it should never have looked at.
        """
        rows: list[dict] = []
        for s in self._b.procedural_list(category=""):
            rows.append({
                "name": s.get("name") or s.get("skill") or "",
                "description": s.get("description") or "",
                "source": "procedural",
            })
        if include_disk:
            rows.extend(_DISK_INDEX.all())

        out: list[SkillInfo] = []
        q = query.lower().strip()
        seen: set[str] = set()
        for row in rows:
            name = row.get("name") or ""
            desc = row.get("description") or ""
            if not name:
                continue
            # A name in both provenances is one skill, reported once. The
            # procedural row wins because that is the store bundles reconcile
            # against.
            if name in seen:
                continue
            if q and q not in name.lower() and q not in desc.lower():
                continue
            seen.add(name)
            out.append(SkillInfo(name=name, description=desc,
                                 source=row.get("source", ""),
                                 path=row.get("path", "")))
        return sorted(out, key=lambda s: s.name)

    # -------------------------------------------------------------- bundles
    def bundles(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        if not self.root.exists():
            return out
        for path in sorted(self.root.glob("*.yaml")):
            name = _safe_name(path.stem)
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            out[name] = list(data.get("skills") or [])
        return out

    def bundle(self, name: str) -> list[str]:
        return self.bundles().get(_safe_name(name), [])

    def bundle_add(self, name: str, skills: list[str],
                   create: bool = True) -> dict:
        name_s = _safe_name(name)
        current = set(self.bundle(name_s))
        added = [s for s in skills if s not in current]
        if not current and not create:
            return {"bundle": name_s, "added": [], "created": False}
        self._write_bundle(name_s, sorted(current | set(skills)))
        return {"bundle": name_s, "added": added, "created": True}

    def bundle_remove(self, name: str, skills: list[str]) -> dict:
        name_s = _safe_name(name)
        current = set(self.bundle(name_s))
        removed = [s for s in skills if s in current]
        self._write_bundle(name_s, sorted(current - set(skills)))
        return {"bundle": name_s, "removed": removed}

    # -------------------------------------------------------------- sync
    def sync(self, name: str) -> dict:
        """Report how a bundle on disk diverges from the live inventory."""
        name_s = _safe_name(name)
        wanted = set(self.bundle(name_s))
        # Procedural inventory only: a bundle names mem20 skills, so folding in
        # unrelated on-disk skills would report them as members mem20 never had.
        installed = {s.name for s in self.catalog(include_disk=False)}
        return {
            "bundle": name_s,
            "missing_from_mem20": sorted(wanted - installed),
            "not_in_bundle": sorted(installed - wanted) if self.root.exists()
            else [],
        }

    # ------------------------------------------------------------- curator
    def curator(self, min_members: int = 1) -> dict:
        """Prune bundle files that reference only skills mem20 no longer has,
        and nudge empty bundles. Returns a report (no silent deletion)."""
        # Procedural only, for the same reason as sync(): pruning must never be
        # decided by what happens to be installed on disk.
        installed = {s.name for s in self.catalog(include_disk=False)}
        report = {"candidates_for_removal": [], "checked": 0}
        if not self.root.exists():
            return report
        for name, members in self.bundles().items():
            report["checked"] += 1
            missing = [m for m in members if m not in installed]
            if len(members) < min_members or len(missing) == len(members):
                report["candidates_for_removal"].append(
                    {"bundle": name, "missing": missing,
                     "proposal": "delete bundle"})
        return report

    # -------------------------------------------------------------- helper
    def _write_bundle(self, name: str, skills: list[str]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{_safe_name(name)}.yaml"
        path.write_text(yaml.safe_dump({"skills": skills}, sort_keys=False),
                        encoding="utf-8")

    def export_bundle(self, name: str, path: pathlib.Path) -> None:
        path = pathlib.Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump({"name": _safe_name(name),
                                        "skills": self.bundle(name)},
                                       sort_keys=False), encoding="utf-8")

    def import_bundle(self, path: pathlib.Path) -> dict:
        data = yaml.safe_load(pathlib.Path(path).read_text(encoding="utf-8"))
        name = _safe_name(data.get("name") or pathlib.Path(path).stem)
        skills = list(data.get("skills") or [])
        self._write_bundle(name, sorted(set(skills)))
        return {"bundle": name, "skills": sorted(set(skills))}