"""Promotion: turn a dream lineage into a portable roadmap pack.

Four parts, because they answer four different questions:

  maps        - what does the estate look like, and what did this dream touch?
  skills      - what did the dreamer learn about how to do this work?
  information - what was discovered, and how confident is it?
  design      - what was actually built?

The pack is written to disk because it is meant to be portable: handed to another
estate, another agent, or a person. It is the one place a dream legitimately
leaves braid, and it only happens when somebody explicitly asks.

Two honesty rules, both load-bearing:

  * Skills are labelled as *learned observations*, never as verified procedures.
    They came from a model's critique, not from a test that passed.
  * Promotion is refused when the lineage's braid chain does not verify. Shipping
    a roadmap whose provenance is damaged is worse than shipping nothing.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from typing import Any

from . import estate, ledger
from .lineage import Lineage, list_lineages

PACK_VERSION = 1

#: Techniques arrive as model observations ("watch for: ..."). This prefix is
#: stripped when rendering them as skills, but they stay labelled as observations.
_OBSERVATION_PREFIXES = ("watch for:", "watch out for:", "note that", "beware:")


def _clean(text: str) -> str:
    out = text.strip()
    lowered = out.lower()
    for prefix in _OBSERVATION_PREFIXES:
        if lowered.startswith(prefix):
            return out[len(prefix) :].strip()
    return out


def _imperative(text: str) -> str:
    """Make an observation checkable without inventing a procedure that was never tested."""
    cleaned = _clean(text)
    if not cleaned:
        return cleaned
    if cleaned.endswith("?"):
        return f"Confirm: {cleaned}"
    return f"Check that {cleaned[0].lower()}{cleaned[1:]}"


# --- the four parts ----------------------------------------------------------


def build_maps(lineage: Lineage) -> dict[str, Any]:
    """The estate as measured, plus what this dream actually touched."""
    report = estate.estate_report()
    return {
        "estate": {
            "installed_packages": report["installed_count"],
            "reachable_tools": report.get("tool_counts", {}),
            "capability_claims": report["claimed_count"],
            "claims_unverified": report["unverified_claim_count"],
            "match_basis": report["match_basis"],
            "packages": report["installed"],
        },
        "dream": {
            "dream_id": lineage.dream_id,
            "kind": lineage.kind,
            "foundation": lineage.foundation,
            "iterations": lineage.iteration_count,
            "braid_cids": list(lineage.braid_cids),
            "touched": sorted({_imperative(t) for t in lineage.dreamer.techniques})[:20],
        },
    }


def build_skills(lineage: Lineage) -> list[dict[str, Any]]:
    """Learned observations. Labelled as such, because nothing here was tested."""
    skills = []
    for index, technique in enumerate(lineage.dreamer.techniques, start=1):
        skills.append(
            {
                "id": f"{lineage.dream_id}-skill-{index:02d}",
                "statement": _imperative(technique),
                "raw_observation": technique,
                "kind": "learned_observation",
                "verified": False,
                "why_unverified": "came from a panel critique, not from a passing test",
                "learned_at_iteration": lineage.dreamer.evolved_at_iteration,
            }
        )
    return skills


def build_information(lineage: Lineage) -> dict[str, Any]:
    """What was found, and how well it held up."""
    history = lineage.score_history
    fidelities: list[float] = [
        float(h["fidelity"])
        for h in history
        if isinstance(h.get("fidelity"), (int, float)) and h.get("fidelity") is not None
    ]
    return {
        "inventions": lineage.inventions.entries,
        "fidelity": {
            "scores": fidelities,
            "min": min(fidelities) if fidelities else None,
            "max": max(fidelities) if fidelities else None,
        },
        "accepted_iterations": sum(1 for h in history if h.get("accepted")),
        "rejected_iterations": sum(1 for h in history if not h.get("accepted")),
        "foundation_revisions": lineage.foundation_revisions,
        "guidance": lineage.dreamer.guidance,
        "confidence_note": (
            "scores are panel judgements, not measurements; treat a wide spread as "
            "disagreement rather than precision"
        ),
    }


def build_design(lineage: Lineage) -> dict[str, Any]:
    best = lineage.best()
    final = lineage.iterations[-1] if lineage.iterations else None
    return {
        "final_artifact": final.artifact if final else "",
        "final_artifact_chars": len(final.artifact) if final else 0,
        "best_iteration": best.n if best else None,
        "best_artifact": best.artifact if best else "",
        "selected_because": (
            "highest-scoring accepted iteration" if best else "no accepted iteration yet"
        ),
        "done": lineage.done,
        "paused": lineage.paused,
        "pause_reason": lineage.pause_reason,
    }


def build_pack(lineage: Lineage) -> dict[str, Any]:
    return {
        "pack_version": PACK_VERSION,
        "generated_at": time.time(),
        "generated_at_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "dream_id": lineage.dream_id,
        "kind": lineage.kind,
        "maps": build_maps(lineage),
        "skills": build_skills(lineage),
        "information": build_information(lineage),
        "design": build_design(lineage),
        "honesty": {
            "skills_are_verified": False,
            "scores_are_measurements": False,
            "provenance": "braid cids listed in maps.dream.braid_cids",
        },
    }


# --- rendering ---------------------------------------------------------------


def render_markdown(pack: dict[str, Any]) -> str:
    dream = pack["maps"]["dream"]
    estate_map = pack["maps"]["estate"]
    info = pack["information"]
    design = pack["design"]
    lines = [
        f"# Roadmap pack: {pack['dream_id']}",
        "",
        f"Kind: `{pack['kind']}` - generated {pack['generated_at_iso']}",
        "",
        "This pack is portable. It carries its own context and does not need the",
        "estate it came from to be read.",
        "",
        "## What this is not",
        "",
        "- The skills below are **learned observations**, not tested procedures.",
        "- The scores are **panel judgements**, not measurements.",
        "- Nothing here is a substitute for running the thing.",
        "",
        "## Map: the estate",
        "",
        f"- installed packages: {estate_map['installed_packages']}",
        f"- reachable tools: {estate_map['reachable_tools']}",
        (
            f"- capability claims: {estate_map['capability_claims']} "
            f"({estate_map['claims_unverified']} unverified; {estate_map['match_basis']})"
        ),
        "",
        "## Map: this dream",
        "",
        f"- brief: {dream['foundation']}",
        f"- iterations: {dream['iterations']}",
        f"- braid nodes: {len(dream['braid_cids'])}",
        "",
        "## Skills (learned observations)",
        "",
    ]
    if pack["skills"]:
        for skill in pack["skills"]:
            lines.append(f"- {skill['statement']}")
    else:
        lines.append("_none learned yet_")
    lines += ["", "## Information (what was found)", ""]
    if info["inventions"]:
        for invention in info["inventions"]:
            lines.append(f"- **{invention.get('name', '?')}** - {invention.get('description', '')}")
    else:
        lines.append("_no inventions recorded_")
    lines += [
        "",
        (
            f"- accepted iterations: {info['accepted_iterations']}, "
            f"rejected: {info['rejected_iterations']}"
        ),
        f"- fidelity range: {info['fidelity']['min']} to {info['fidelity']['max']}",
        f"- {info['confidence_note']}",
        "",
        "## Design (what was built)",
        "",
        f"- final artifact: {design['final_artifact_chars']} chars",
        f"- best iteration: {design['best_iteration']} ({design['selected_because']})",
        f"- done: {design['done']}, paused: {design['paused']}",
        "",
        "```",
        (design["best_artifact"] or design["final_artifact"] or "_empty_")[:6000],
        "```",
        "",
    ]
    return "\n".join(lines)


# --- the integrity gate and the export --------------------------------------


def check_provenance(lineage: Lineage) -> dict[str, Any]:
    """Promotion is refused on a damaged chain, and on a hollow lineage."""
    if lineage.hollow:
        # A lineage the audit marked as failed calls is not a dream. Its braid
        # chain is perfectly valid, which is exactly why it needs this guard: a
        # signature says the bytes are intact, not that a dream happened.
        return {
            "healthy": False,
            "checked": 0,
            "note": "lineage is marked hollow: it recorded provider errors, not work",
            "hollow": lineage.hollow,
        }
    if not lineage.braid_cids:
        return {"healthy": True, "checked": 0, "note": "no braid nodes; nothing to verify"}
    report = ledger.verify_chain(lineage.braid_cids)
    return {
        "healthy": bool(report.get("healthy")),
        "checked": report.get("checked"),
        "verified": report.get("verified"),
        "broken": report.get("broken", []),
    }


def render_files(pack: dict[str, Any]) -> list[tuple[str, str]]:
    """Every file's content, rendered before anything touches the filesystem.

    Rendering first is the whole point: a pack that cannot be rendered must fail
    without having created a single byte on disk. Building the tuple of contents
    up front means a renderer error happens while nothing has been written, rather
    than after a directory and one file already exist.
    """
    stem = str(pack["dream_id"])
    return [
        (f"{stem}.json", json.dumps(pack, indent=2, default=str)),
        (f"{stem}.md", render_markdown(pack)),
    ]


def _remove_tree(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)


def _existing_pack_is_incomplete(target: str, expected: list[str]) -> bool:
    """Whether a non-empty target is interrupted debris rather than real work.

    The overwrite guard has always asked "is this directory non-empty?", which is
    the wrong question after a crash: a half-written pack is non-empty too, so it
    locks out every retry while being indistinguishable from real work.

    The distinction is drawn narrowly, because guessing wrong here destroys
    somebody's files. A directory is debris only if *everything* in it is a file
    this function would have written - a finished name, or that name's ``.tmp``.
    A single unrelated filename means a human's work, and it is refused, not
    cleaned up.
    """
    try:
        present = set(os.listdir(target))
    except OSError:
        return False
    if not present:
        return False
    if set(expected).issubset(present):
        return False  # a complete pack: real work, refuse it
    ours = set(expected) | {f"{name}.tmp" for name in expected}
    return present.issubset(ours)


def _stage_files(staging: str, files: list[tuple[str, str]]) -> None:
    """Write the whole pack into a staging directory, durably, before installing it."""
    for name, content in files:
        path = os.path.join(staging, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())


def _install(staging: str, target: str) -> str | None:
    """Swap the staged pack into place, setting any existing pack aside.

    The set-aside rename and the install rename are each atomic, and between them
    the old pack is intact under a ``.bak`` name, so a failure at exactly this
    point is recoverable. Returns the backup path, or None if there was nothing to
    replace.
    """
    backup = None
    if os.path.isdir(target):
        backup = f"{target}.bak-{int(time.time())}"
        os.replace(target, backup)
    os.replace(staging, target)
    return backup


def recover_stranded_backup(root: str, stem: str) -> str | None:
    """Restore a pack stranded by a crash between the set-aside and install renames.

    Replacing a pack is two renames, and a process killed between them leaves the
    previous pack under its ``.bak`` name with no ``target`` beside it. Nothing
    points at it, so it reads as garbage - but it is the only copy of a real pack.
    The newest backup is moved back into place, and reported, rather than being
    silently overwritten by the next attempt.
    """
    if not os.path.isdir(root):
        return None
    candidates = sorted(
        (n for n in os.listdir(root) if n.startswith(f"{stem}.bak-") and os.path.isdir(os.path.join(root, n))),
        reverse=True,
    )
    if not candidates:
        return None
    target = os.path.join(root, stem)
    if os.path.exists(target):
        # A completed pack is already in place, so the backup is redundant. Left
        # alone rather than deleted: it is not ours to assume is worthless.
        return None
    chosen = os.path.join(root, candidates[0])
    try:
        os.replace(chosen, target)
    except OSError as exc:
        return f"could not restore {chosen}: {type(exc).__name__}: {exc}"
    return chosen


def write_pack(pack: dict[str, Any], out_dir: str, force: bool = False) -> str:
    """Write the pack as a self-contained directory, one per dream.

    The per-dream subdirectory is what lets many dreams share one promotions
    store: the "do not silently overwrite" guard then protects a given dream's
    own pack instead of locking out every other dream.

    Written as stage-then-install with a rollback, because a promotion that fails
    halfway is worse than one that never started: the reader cannot tell a
    half-written pack from a finished one, and the guard would then refuse every
    retry. Three properties follow, and each is tested:

      * nothing touches the target until the whole pack is rendered and written,
      * a failure leaves the target either untouched or complete, never partial,
      * replacing an existing pack is reversible - a failure restores the original.
    """
    files = render_files(pack)  # may raise: nothing has been written yet
    root = os.path.abspath(out_dir)
    stem = str(pack["dream_id"])
    target = os.path.join(root, stem)
    expected = [name for name, _ in files]

    os.makedirs(root, exist_ok=True)
    # Heal first: a pack stranded by an interrupted replacement is the only copy of
    # real work, and it must be back in place before anything else happens here.
    recover_stranded_backup(root, stem)

    if os.path.isdir(target) and os.listdir(target) and not force:
        if _existing_pack_is_incomplete(target, expected):
            # An interrupted write, not somebody's finished pack. Clear it and say
            # so, rather than demanding --force to escape our own debris.
            _remove_tree(target)
        else:
            raise FileExistsError(
                f"{target} exists and is not empty; pass force to overwrite this dream's pack"
            )

    staging = tempfile.mkdtemp(prefix=f".{stem}.staging-", dir=root)
    try:
        _stage_files(staging, files)
    except Exception:
        # The target was never touched, so there is nothing to undo here.
        _remove_tree(staging)
        raise

    replaced = os.path.isdir(target)
    try:
        backup = _install(staging, target)
    except Exception as exc:
        _remove_tree(staging)
        stranded = ""
        if replaced:
            for candidate in sorted(
                (n for n in os.listdir(root) if n.startswith(f"{stem}.bak-")), reverse=True
            ):
                # `target` is absent precisely because the install rename is what
                # failed, so the set-aside pack is the only copy that survives.
                try:
                    os.replace(os.path.join(root, candidate), target)
                except OSError as restore_exc:
                    # The rollback itself failed. Never let that pass silently:
                    # the previous pack exists only under its .bak name now, and
                    # an operator who is not told the path has lost it.
                    stranded = (
                        f"; the previous pack could not be restored and is at "
                        f"{os.path.join(root, candidate)} "
                        f"({type(restore_exc).__name__}: {restore_exc})"
                    )
                break
        elif os.path.isdir(target):
            # Nothing existed here before, so a target that appeared anyway is
            # ours and incomplete: remove it rather than leave debris that the
            # next attempt would trip over.
            _remove_tree(target)
        if stranded:
            raise RuntimeError(f"{type(exc).__name__}: {exc}{stranded}") from exc
        raise

    if backup:
        _remove_tree(backup)
    return target



def commit_promotion(lineage: Lineage, pack: dict[str, Any]) -> dict[str, Any]:
    """Record the promotion in braid, so the pack itself is traceable."""
    body = {
        "dream_id": lineage.dream_id,
        "kind": lineage.kind,
        "iterations": lineage.iteration_count,
        "skills": [s["statement"] for s in pack["skills"]],
        "inventions": [i.get("name") for i in pack["information"]["inventions"]],
        "design_chars": pack["design"]["final_artifact_chars"],
        "honesty": pack["honesty"],
    }
    return ledger.commit_raw(
        "write:dream_promotion", f"dream:{lineage.dream_id}", body
    )


def promote(dream_id: str, out_dir: str, force: bool = False) -> dict[str, Any]:
    """The whole flow, with the gate in front of it."""
    lineage = Lineage.load(dream_id)
    if lineage is None:
        raise FileNotFoundError(f"no such dream: {dream_id}")
    provenance = check_provenance(lineage)
    if not provenance["healthy"]:
        return {
            "promoted": False,
            "reason": (
                "refusing to promote a hollow lineage: it recorded provider errors, "
                "not a dream"
                if provenance.get("hollow")
                else "braid provenance does not verify; refusing to promote a damaged chain"
            ),
            "provenance": provenance,
        }
    pack = build_pack(lineage)
    root = os.path.abspath(out_dir)
    # Captured before the write, because the write heals it.
    recovered = recover_stranded_backup(root, str(lineage.dream_id))
    target = write_pack(pack, out_dir, force=force)
    receipt = commit_promotion(lineage, pack)
    return {
        "promoted": True,
        "dream_id": dream_id,
        "out_dir": target,
        "files": sorted(os.listdir(target)),
        "skills": len(pack["skills"]),
        "inventions": len(pack["information"]["inventions"]),
        "braid": receipt,
        "provenance": provenance,
        "recovered_stranded_pack": recovered,
    }


def catalogue(limit: int = 25) -> list[dict[str, Any]]:
    """Which lineages are even promotable, and why not if they are not."""
    rows = []
    for row in list_lineages():
        lineage = Lineage.load(row["dream_id"])
        if lineage is None:
            continue
        rows.append(
            {
                "dream_id": lineage.dream_id,
                "kind": lineage.kind,
                "iterations": lineage.iteration_count,
                "skills": len(lineage.dreamer.techniques),
                "inventions": len(lineage.inventions.entries),
                "provenance": check_provenance(lineage)["healthy"],
            }
        )
    return rows[-limit:]
