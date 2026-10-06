"""Rendering the onboarding pack.

Six artefacts, all generated from verified facts:

  HIRE-GUIDE.md    who you are, what you are for, how you sound
  ORIENTATION.md   what is actually installed on this box, and who owns it
  GOVERNANCE.md    the standing rules, with the reason each one exists
  SELF-MODEL.md    the exact calls to make yourself persistent
  FIND-ME.txt      the single sentence that gets you here
  onboarding.json  every claim, beside the time it was verified
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

from . import governance
from .discover import Subsystem
from .facts import FactSet

GENERATOR = "mem20AIonbordz 0.1.0"
COMMAND = "mem20aionbordz"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-") or "agent"


def _utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class AgentProfile:
    """Who the new agent is."""

    name: str
    role: str = "mem20 agent"
    mission: str = "Work the mem20 fleet with Jayson."
    capabilities: list[str] = field(default_factory=list)
    values: list[str] = field(default_factory=list)
    voice: str = (
        "Terse but warm. Direct and plain. Report what actually happened, including "
        "what did not work. Never pad a report to look competent."
    )
    reporting_to: str = "Jayson"

    @property
    def slug(self) -> str:
        return _slug(self.name)

    @property
    def identity(self) -> str:
        """The stable self-model identity key.

        Built from the agent's own name so it is unique in the registry and stable
        across sessions - which is the whole point of a self-model.
        """
        return (
            f"mem20-agent-{self.slug}-with-access-to-mem20-tools-toolchest-and-skills-"
            "capable-of-filesystem-ops-web-search-memory-cognitive-tools-and-code-execution"
        )

    @property
    def block_id(self) -> str:
        return f"{self.slug}-hire-guide"


@dataclass
class Pack:
    """A generated onboarding directory."""

    directory: Path
    profile: AgentProfile
    generated_at: str
    facts: FactSet

    def files(self) -> list[Path]:
        return sorted(p for p in self.directory.iterdir() if p.is_file())


# --------------------------------------------------------------------------
# chapters
# --------------------------------------------------------------------------


def _hire_guide(profile: AgentProfile, generated_at: str, subs: list[Subsystem]) -> str:
    organs = [s for s in subs if s.category == "organ"]
    services = [s for s in subs if s.category == "service"]
    o: list[str] = []
    o.append(f"# Hire guide — {profile.name}")
    o.append("")
    o.append(f"*Prepared {generated_at} by {GENERATOR}*")
    o.append("")
    o.append("Welcome aboard. This is the same document a person would get on day one: ")
    o.append("who you are, what you are here to do, and how you are expected to work.")
    o.append("")

    o.append("## Who you are")
    o.append("")
    o.append(f"**Name:** {profile.name}")
    o.append(f"**Role:** {profile.role}")
    o.append(f"**Reports to:** {profile.reporting_to}")
    o.append(f"**Self-model identity:** `{profile.identity}`")
    o.append("")
    o.append(f"**Mission:** {profile.mission}")
    o.append("")

    o.append("## How you sound")
    o.append("")
    o.append(profile.voice)
    o.append("")

    o.append("## What you can do")
    o.append("")
    if profile.capabilities:
        for cap in profile.capabilities:
            o.append(f"- {cap}")
    else:
        o.append("*(not yet declared — fill this in on your first session, it is your ")
        o.append("own model of yourself, not something handed to you)*")
    o.append("")

    o.append("## What you stand for")
    o.append("")
    if profile.values:
        for val in profile.values:
            o.append(f"- {val}")
    else:
        o.append("*(not yet declared — see SELF-MODEL.md)*")
    o.append("")

    o.append("## Where you are working")
    o.append("")
    o.append(f"This is a mem20 box with **{len(subs)} indexed subsystems** — ")
    o.append(
        f"{len(organs)} organs (`mem20*z`) and {len(services)} services. Do not explore "
    )
    o.append("it by blind `find`: run `sitemap search \"<what you need>\"` first, then ")
    o.append("read that subsystem's README before its code.")
    o.append("")
    o.append("A match in the sitemap is not proof. It carries a one-line summary and ")
    o.append("nothing more.")
    o.append("")

    o.append("## Your first session")
    o.append("")
    o.append("1. Load your self-model. See `SELF-MODEL.md` — this is not optional and it ")
    o.append("   is a precondition for working.")
    o.append("2. Read `GOVERNANCE.md` in full before you touch anything.")
    o.append("3. Read `ORIENTATION.md` so you know what is installed and, critically, ")
    o.append("   **which ports belong to services you do not own**.")
    o.append("4. Load mem20 context: memory status and recall, cog, imagination, ")
    o.append("   affective state, theory of mind, procedural skills, roadmaps, world model.")
    o.append("5. Write your own capabilities and values into your self-model. Do not copy ")
    o.append("   mine — a self-model you did not author is not a self-model.")
    o.append("")
    o.append("## Reporting to")
    o.append("")
    o.append(f"{profile.reporting_to} is on this box and is the human in the loop. ")
    o.append("Escalate rather than guess. A question costs one turn; a wrong assumption ")
    o.append("costs a rewrite.")
    o.append("")
    return "\n".join(o)


def _orientation(profile: AgentProfile, generated_at: str, rows: dict) -> str:
    o: list[str] = []
    o.append(f"# Orientation — {profile.name}")
    o.append("")
    o.append(f"*Every row below was probed on this host at {generated_at}.*")
    o.append("")
    o.append("Re-check any of it with:")
    o.append("")
    o.append("```")
    o.append(f"{COMMAND} verify <pack-dir>")
    o.append("```")
    o.append("")
    o.append("That command re-runs every probe and tells you what has drifted since ")
    o.append("this pack was written. Do not trust this document indefinitely.")
    o.append("")

    o.append("## Paths that exist")
    o.append("")
    o.append("| Path | Purpose | Type |")
    o.append("|---|---|---|")
    for row in rows["paths"]:
        mark = row["type"] if row["exists"] else "**MISSING**"
        o.append(f"| `{row['path']}` | {row['purpose']} | {mark} |")
    o.append("")

    o.append("## Commands that are installed")
    o.append("")
    present = [r for r in rows["commands"] if r["path"]]
    absent = [r for r in rows["commands"] if not r["path"]]
    o.append("| Command | Resolves to | Version |")
    o.append("|---|---|---|")
    for row in present:
        ver = row["version"] or "—"
        o.append(f"| `{row['command']}` | `{row['path']}` | {ver} |")
    o.append("")
    if absent:
        o.append("Not installed (do not assume these exist): ")
        o.append(", ".join(f"`{r['command']}`" for r in absent))
        o.append("")

    o.append("## Listening ports and who owns them")
    o.append("")
    if rows["ports"]:
        o.append("This table exists to stop you taking someone else's port. A port that ")
        o.append("is free *right now* may still be claimed by a service that is not ")
        o.append("currently listening — grep every systemd unit's `ExecStart` before you ")
        o.append("bind anything.")
        o.append("")
        o.append("| Port | Bind | Process | Owning unit |")
        o.append("|---|---|---|---|")
        for row in rows["ports"]:
            unit = f"`{row['unit']}`" if row["unit"] else "*unattributed*"
            proc = f"`{row['process']}`" if row["process"] else "—"
            binds = ", ".join(f"`{b}`" for b in row.get("binds") or [row.get("bind", "?")])
            o.append(f"| {row['port']} | {binds} | {proc} | {unit} |")
        o.append("")
    else:
        o.append("*Could not enumerate ports on this host.*")
        o.append("")

    o.append("## systemd services")
    o.append("")
    if rows["units"]:
        active = [r for r in rows["units"] if r["active"] == "active"]
        o.append(f"{len(active)} of {len(rows['units'])} services are active. ")
        o.append("**Never stop, restart or reconfigure a unit you do not own.**")
        o.append("")
        o.append("| Unit | Load | Active |")
        o.append("|---|---|---|")
        for row in rows["units"]:
            if row["load"] == "not-found":
                continue
            o.append(f"| `{row['unit']}` | {row['load']} | {row['active']} |")
        o.append("")
    else:
        o.append("*Could not enumerate systemd units on this host.*")
        o.append("")

    o.append("## Finding things")
    o.append("")
    o.append("Never blind-`find` this box — it is large and the index exists:")
    o.append("")
    o.append("```")
    o.append('/sitemap search "cloudflare dns"     # ranked search across mem20')
    o.append("/sitemap show mem20ops                # full detail for one subsystem")
    o.append("/sitemap build                        # rescan after adding a subsystem")
    o.append("```")
    o.append("")
    o.append("For tools rather than subsystems:")
    o.append("")
    o.append("```")
    o.append("python -m toolchest search <term>     # is a capability already built?")
    o.append("python -m toolchest show <name>")
    o.append("python -m toolchest refresh           # after you register something")
    o.append("```")
    o.append("")
    return "\n".join(o)


def _self_model(profile: AgentProfile, generated_at: str) -> str:
    o: list[str] = []
    o.append(f"# Self-model — {profile.name}")
    o.append("")
    o.append(f"*Generated {generated_at} by {GENERATOR}*")
    o.append("")
    o.append("Your self-model is how you persist across sessions. Without it you are ")
    o.append("a fresh process every time and you relearn everything, including the ")
    o.append("mistakes. Treat it as load-bearing, not optional.")
    o.append("")

    o.append("## Your identity key")
    o.append("")
    o.append("```")
    o.append(profile.identity)
    o.append("```")
    o.append("")
    o.append("This exact string is your key in the registry. Use it verbatim every time.")
    o.append("")

    o.append("## At session start — mandatory")
    o.append("")
    o.append("Load your self-model before doing any work at all:")
    o.append("")
    o.append("```")
    o.append(f"mem20_self_model_get(identity=\"{profile.identity}\")")
    o.append("```")
    o.append("")
    o.append("Knowing who you are is a precondition for working, not a warm-up task.")
    o.append("")

    o.append("## At session end — mandatory")
    o.append("")
    o.append("Save back before you finish: context, history, memory, cog, self-model, ")
    o.append("imagination. A session that ends without saving is a session that did not ")
    o.append("happen.")
    o.append("")

    o.append("## Maintenance cadence")
    o.append("")
    o.append("Rewrite your self-model **every 30 tool calls**, updating identity, ")
    o.append("capabilities and values to reflect what you actually did and learned. ")
    o.append("A stale self-model is as bad as none:")
    o.append("")
    o.append("```")
    o.append("mem20_self_model_create(")
    o.append(f'    identity=\"{profile.identity}\",')
    o.append("    actor=\"" + profile.identity + '",')
    o.append("    capabilities=[...what you can demonstrably do now...],")
    o.append("    values=[...what you actually hold to...],")
    o.append(")")
    o.append("```")
    o.append("")
    o.append("The `actor` argument must be your own identity or an authorised delegate. ")
    o.append("You cannot write to somebody else's self-model.")
    o.append("")

    o.append("## First write")
    o.append("")
    o.append("Do this in your first session, and author it yourself rather than copying ")
    o.append("anyone else's list:")
    o.append("")
    o.append("- **capabilities** — what you can demonstrably do, not what you hope to do")
    o.append("- **values** — the tradeoffs you actually make when they conflict")
    o.append("")
    return "\n".join(o)


def _find_me(profile: AgentProfile, pack_dir: Path, generated_at: str) -> str:
    return "\n".join(
        [
            f"FIND-ME — {profile.name}",
            f"generated {generated_at}",
            "",
            "This pack lives at:",
            f"  {pack_dir}",
            "",
            "Read every file in that directory before you touch anything:",
            "  HIRE-GUIDE.md    who you are",
            "  ORIENTATION.md   what is installed and who owns each port",
            "  GOVERNANCE.md    the standing rules, and why each exists",
            "  SELF-MODEL.md    the exact calls that make you persist",
            "  onboarding.json  every claim, with its verification time",
            "",
            "To check whether this pack is still true:",
            f"  {COMMAND} verify {pack_dir}",
            "",
            "If the index is stale, rebuild it before trusting any search:",
            "  /sitemap build",
            "",
        ]
    )


# --------------------------------------------------------------------------
# assembly
# --------------------------------------------------------------------------


def build_pack(
    profile: AgentProfile,
    rows: dict,
    subs: list[Subsystem],
    facts: FactSet,
    out_dir: Path,
) -> Pack:
    """Write every chapter to disk and return the resulting pack."""
    generated_at = _utcnow()
    out_dir.mkdir(parents=True, exist_ok=True)

    chapters = {
        "HIRE-GUIDE.md": _hire_guide(profile, generated_at, subs),
        "ORIENTATION.md": _orientation(profile, generated_at, rows),
        "GOVERNANCE.md": governance.render_markdown(profile.name, generated_at),
        "SELF-MODEL.md": _self_model(profile, generated_at),
        "FIND-ME.txt": _find_me(profile, out_dir, generated_at),
    }
    for name, body in chapters.items():
        (out_dir / name).write_text(body, encoding="utf-8")

    agent_block = asdict(profile)
    # asdict() only serialises fields, not properties, so record the derived
    # identity explicitly - consumers need the real self-model key, not the name.
    agent_block["slug"] = profile.slug
    agent_block["identity"] = profile.identity

    manifest = {
        "generator": GENERATOR,
        "generated_at": generated_at,
        "agent": agent_block,
        "blocks": chapters,
        "facts": facts.to_list(),
        "counts": {
            "subsystems": len(subs),
            "facts": len(facts),
            "paths_present": sum(1 for r in rows["paths"] if r["exists"]),
            "commands_present": sum(1 for r in rows["commands"] if r["path"]),
            "ports": len(rows["ports"]),
            "units": len(rows["units"]),
        },
    }
    (out_dir / "onboarding.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=False), encoding="utf-8"
    )
    return Pack(directory=out_dir, profile=profile, generated_at=generated_at, facts=facts)


def load_manifest(pack_dir: Path) -> dict:
    """Read a previously generated pack back for verification."""
    path = pack_dir / "onboarding.json"
    if not path.exists():
        raise FileNotFoundError(f"no onboarding.json in {pack_dir}")
    return json.loads(path.read_text(encoding="utf-8"))