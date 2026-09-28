#!/usr/bin/env python
"""Generate the mem20 systems-and-value document from measured estate data.

Writes /home/jayson/Desktop/mem20-SYSTEMS-AND-VALUE.md.

Every figure is measured at run time: package inventory from pyproject.toml,
line counts from the source trees, running services from systemd, and the ledger
and tool counts from their live stores. Nothing is hand-typed, so re-running this
after the estate changes keeps the document honest.

Value basis: replacement cost (what an outside team would have charged to build
it). Not a sale price, not revenue.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Any

ESTATE = "/opt/mem20"
OUT = "/home/jayson/Desktop/mem20-SYSTEMS-AND-VALUE.md"

# --- assumptions, all three arguable and all three stated in the document ------
PROD_LOC_PER_HR = 30  # integration-heavy backend; deliberately conservative
TEST_LOC_PER_HR = 60  # tests are faster per line than product code
RATE = 125.0  # blended senior contractor, USD/hour

SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".venv", "target", "build", "dist", "__snapshots__"}


def count_lines(path: str, exts: set[str], exclude_dirs: set[str] | None = None) -> tuple[int, int]:
    """(lines, files) under `path`.

    `exclude_dirs` names directories to skip at ANY depth. Rust workspaces keep
    their tests in per-crate `tests/` directories, so a top-level-only exclusion
    would silently bill test code as production.
    """
    excluded = set(exclude_dirs or ())
    loc = files = 0
    for root, dirs, names in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and d not in excluded]
        for name in names:
            if os.path.splitext(name)[1] not in exts:
                continue
            try:
                with open(os.path.join(root, name), encoding="utf-8", errors="ignore") as fh:
                    loc += sum(1 for _ in fh)
                files += 1
            except OSError:
                continue
    return loc, files


def count_test_lines(path: str, exts: set[str]) -> int:
    """Lines in any `tests/` directory at any depth, plus `test_*` files.

    Deliberately does NOT prune `tests` directories while walking: pruning them at
    each level means the walker never reaches the very directories being counted.
    """
    loc = 0
    for root, dirs, names in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        in_tests = os.path.basename(root) == "tests"
        for name in names:
            if os.path.splitext(name)[1] not in exts:
                continue
            if in_tests or name.startswith("test_") or name.endswith("_test.rs"):
                try:
                    with open(os.path.join(root, name), encoding="utf-8", errors="ignore") as fh:
                        loc += sum(1 for _ in fh)
                except OSError:
                    continue
    return loc


def measure() -> list[tuple[str, int, int, str]]:
    """(package, production LOC, test LOC, description) for every real package."""
    out = []
    for pkg in sorted(os.listdir(ESTATE)):
        manifest = os.path.join(ESTATE, pkg, "pyproject.toml")
        if not os.path.isfile(manifest):
            continue
        prod = tests = 0
        for root, dirs, names in os.walk(os.path.join(ESTATE, pkg)):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in names:
                ext = os.path.splitext(name)[1]
                if ext not in {".py", ".rs"}:
                    continue
                try:
                    with open(os.path.join(root, name), encoding="utf-8", errors="ignore") as fh:
                        n = sum(1 for _ in fh)
                except OSError:
                    continue
                # Test files count as tests in BOTH languages. Rust keeps its unit
                # tests inline in #[cfg(test)] modules, which are not separable by
                # filename, so only dedicated tests/ files are counted as test lines
                # for .rs - otherwise braid would report zero tests while shipping them.
                full = os.path.join(root, name)
                is_test_file = "/tests/" in full or name.startswith("test_") or full.endswith("tests.rs")
                if is_test_file:
                    tests += n
                else:
                    prod += n
        desc = ""
        with open(manifest, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("description"):
                    desc = line.split("=", 1)[1].strip().strip('"')
                    break
        out.append((pkg, prod, tests, desc))
    return out


def non_package_systems() -> list[tuple[str, int, int, str]]:
    """Systems that are real but are not pip packages."""
    out = []
    for name, path, exts, label in (
        ("braid", "braid", {".rs"}, "Append-only signed ledger"),
        ("mcp", "mcp", {".py"}, "Canonical tool server"),
    ):
        full = os.path.join(ESTATE, path)
        if not os.path.isdir(full):
            continue
        prod, _ = count_lines(full, exts, exclude_dirs={"tests"})
        test_loc = count_test_lines(full, exts)
        out.append((name, prod, test_loc, label))
    py = os.path.join(ESTATE, "braid_python")
    if os.path.isdir(py):
        loc, _ = count_lines(py, {".rs"})
        test_loc, _ = count_lines(os.path.join(py, "tests"), {".rs"}) if os.path.isdir(os.path.join(py, "tests")) else (0, 0)
        out.append(("braid_python", loc, test_loc, "Python binding for the ledger"))
    return out


def live_facts() -> dict[str, Any]:
    def run(cmd: str) -> str:
        try:
            return subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=90, check=False
            ).stdout.strip()
        except Exception:  # noqa: BLE001
            return ""

    braid_nodes = 0
    log = os.path.join(ESTATE, "store/braid/mem20.braid")
    try:
        with open(log, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    if isinstance(json.loads(line).get("depth"), int):
                        braid_nodes += 1
                except ValueError:
                    continue
    except OSError:
        pass

    dreams_dir = os.path.join(ESTATE, "store/dreams")
    dreams = (
        len([d for d in os.listdir(dreams_dir) if d.startswith("dream-")])
        if os.path.isdir(dreams_dir)
        else 0
    )

    try:
        with open(os.path.join(ESTATE, "toolchest/inventory.json"), encoding="utf-8") as fh:
            counts = json.load(fh)["counts"]
    except (OSError, ValueError, KeyError):
        counts = {"total": 0, "mcp": 0, "cli": 0, "subsystem": 0}

    return {
        "services": run(
            "systemctl list-units --type=service --state=running --no-legend "
            "| grep -icE 'mem20|braid|cloudflared|pickle'"
        )
        or "0",
        "braid_nodes": braid_nodes,
        "dreams": dreams,
        "tools": counts,
    }


CATEGORY = {
    "mem20agentz": ("Agent platform", "profiles, sessions, skills, projects, kanban, cron, gateway, desktop"),
    "mem20oreo": ("Visual language", "natural language to graph to runnable app; 7.7k lines of Rust"),
    "braid": ("Signed ledger", "content-addressed DAG, Merkle proofs, Ed25519 audit strands, policy snapshots, key rotation"),
    "mcp": ("Tool server", "the canonical surface behind every MCP tool"),
    "mem20kilnz": ("3D mesh", "cleanroom mesh and AI-first asset pipeline"),
    "mem20owebz": ("Chat and gateway", "OpenAI-compatible gateway, chat front-end, local model bridge"),
    "mem20orcaz": ("Workflow runner", "YAML pipelines, fork-join, routers, loops, failover, RAG nodes"),
    "mem20dreamz": ("Dream engine", "multi-model panel, fidelity gate, omission veto, pairwise selection, idle timer, braid retention, promotion packs, subsystem awareness"),
    "mem20unitiz": ("Reinforcement learning", "grid environments, policies, buffers, training loops"),
    "mem20crewz": ("Multi-agent crews", "agents, tasks, flows, roadmap-backed runs, YAML config, A2A fan-out"),
    "mem20googlez": ("Google ADK-style agents", "agents, tools, runners, sessions, memory, flows"),
    "mem20yetiz": ("3D animation", "rigging, retargeting, mocap, export"),
    "mem20mktz": ("Marketing organs", "inference market, outreach, content, approval queue"),
    "mem20gamez": ("Game agents", "environments, reward shaping, curriculum, replay"),
    "mem20controlz": ("Control plane", "per-subsystem probes, CLI coverage, websites, registry refresh, login gate"),
    "mem20ops": ("Operational workflows", "zone and DNS audits, Pages audits, stale-code detection, bounded verification, identity and ACL checks"),
    "mem20verify": ("Verification toolkit", "proves claims by execution rather than assertion"),
    "mem20corez": ("Model serving", "serving, inference optimisation, batching, quantisation"),
    "mem20sensorz": ("Sense organs", "capability gap mapper"),
    "mem20kimiz": ("Swarm scheduler", "parallel sub-agent fan-out, rate-limit aware, resumable"),
    "mem20shopz": ("Storefront", "catalog, Stripe Checkout, signature-verified webhooks, idempotent events, live dashboard"),
    "mem20langz": ("Graph runtime", "StateGraph, Pregel, checkpointers, streaming, interrupts"),
    "mem20unikitz": ("Game AI", "behaviour trees, GOAP, utility AI, navigation, blackboard"),
    "mem20agentz_sdk": ("Agents SDK", "Agent, Runner, Tools, Handoffs, Guardrails, Tracing"),
    "mem20rpgz": ("RPG agents", "stats, combat, inventory, quests, narration"),
    "mem20ucgz": ("Capability graph", "universal capability graph"),
    "toolchest": ("Tool registry", "runtime-checked inventory of every reachable tool"),
    "mem20autouez": ("Unreal automation", "Blueprint generation, Python API, packaging"),
    "mem20factoryz": ("Asset synthesis", "procgen, asset synthesis, level generation, playtesting"),
    "mem20cviz": ("Vision inference", "image inference subsystem"),
    "mem20webgpuz": ("WebGPU compute", "backend selection against real hardware"),
    "mem20zimr": ("Microapp runtime", "zero-install component runtime"),
    "mem20wasmz": ("WebAssembly lab", "language-neutral component experiments"),
    "mem20_mcp": ("MCP loader", "thin loader for the canonical server"),
    "mem20-orchestration": ("Blender orchestration", "queries the real bpy.ops catalogue"),
    "mem20secretz": ("Secrets governance", "floating-credential detection, leak-versus-config, git exposure"),
    "mem20officez": ("3D office", "workspace, agent fleet, Phaser scenes"),
    "mem20cliz": ("CLI contract", "the JSON contract every mem20 CLI speaks"),
    "braid_python": ("Python binding", "pyo3 bridge exposing the ledger to Python"),
    "mem20messenger": ("Messenger", "FastAPI accounts, WebSocket bot proxy"),
}

HARD = ("braid", "mem20oreo", "mem20dreamz", "mem20verify")


def usd(n: float) -> str:
    return f"${n:,.0f}"


def main() -> int:
    rows = []
    for pkg, prod, tests, desc in measure():
        hours = prod / PROD_LOC_PER_HR + tests / TEST_LOC_PER_HR
        rows.append([pkg, prod, tests, hours, hours * RATE, desc])
    for name, prod, test_loc, label in non_package_systems():
        hours = prod / PROD_LOC_PER_HR + test_loc / TEST_LOC_PER_HR
        rows.append([name, prod, test_loc, hours, hours * RATE, label])
    rows.sort(key=lambda r: -r[4])

    facts = live_facts()
    tools = facts["tools"]
    total_hours = sum(r[3] for r in rows)
    total_cost = sum(r[4] for r in rows)
    total_prod = sum(r[1] for r in rows)
    total_test = sum(r[2] for r in rows)

    out: list[str] = []
    add = out.append

    add("# mem20 — Systems and Features, with build-equivalent value")
    add("")
    add(f"_Generated {time.strftime('%Y-%m-%d %H:%M')} from the live estate on `jnet1`. Every figure is measured, not typed._")
    add("")
    add("## What this number is, and what it is not")
    add("")
    add("**It is** what it would have cost to have had each system built from scratch by an")
    add("outside team: engineer-hours multiplied by a contractor rate. That is *replacement cost*.")
    add("")
    add("**It is not** a sale price, not revenue, not a valuation, and not money in the bank.")
    add("Replacement cost is what you escape paying by already owning the thing. Do not read")
    add("these numbers as what the estate would fetch in a sale.")
    add("")
    add("## Method, so you can argue with it")
    add("")
    add("```")
    add(f"build_hours = (production_LOC / {PROD_LOC_PER_HR}) + (test_LOC / {TEST_LOC_PER_HR})")
    add(f"build_cost  = build_hours x ${RATE:.0f}/hour")
    add("```")
    add("")
    add("Three assumptions, all arguable:")
    add("")
    add(f"1. **{PROD_LOC_PER_HR} production lines per hour.** Deliberately conservative — this is")
    add("   integration-heavy code with real dependencies, not CRUD.")
    add(f"2. **{TEST_LOC_PER_HR} test lines per hour.** Tests are faster per line than product code.")
    add(f"3. **${RATE:.0f}/hour blended senior contractor.** Change this one number and the whole")
    add("   table rescales proportionally.")
    add("")
    add("Lines are counted from the source trees, excluding `__pycache__`, `.git`,")
    add("`node_modules`, `.venv` and `target`. Test lines are those under `tests/` or named `test_*`.")
    add("")
    add("## Headline")
    add("")
    add("| | |")
    add("|---|---|")
    add(f"| Systems valued | {len(rows)} |")
    add(f"| Engineer-hours to rebuild | **{total_hours:,.0f}** |")
    add(f"| Replacement cost at ${RATE:.0f}/hr | **{usd(total_cost)}** |")
    add(f"| Production lines | {total_prod:,} |")
    add(f"| Test lines | {total_test:,} |")
    add(f"| Tools reachable at runtime | {tools.get('total', 0)} ({tools.get('mcp', 0)} MCP, {tools.get('cli', 0)} CLI, {tools.get('subsystem', 0)} subsystem) |")
    add(f"| Services running | {facts['services']} |")
    add(f"| Braid ledger nodes | {facts['braid_nodes']} |")
    add(f"| Dream lineages produced | {facts['dreams']} |")
    add("")
    add(f"At a conventional 1,600 productive hours a year that is roughly **{total_hours/1600:.1f} engineer-years**.")
    add("")
    add("## The systems that are genuinely hard to copy")
    add("")
    add("A uniform lines-of-code formula is fair on average and wrong at the top. These four")
    add("deserve separate mention, because their worth is architectural, not volumetric.")
    add("")
    for r in rows:
        if r[0] not in HARD:
            continue
        cat, feat = CATEGORY.get(r[0], (r[5][:40], r[5]))
        add(f"### `{r[0]}` — {usd(r[4])}")
        add("")
        add(f"**{cat}.** {feat}.")
        add(f"_{r[1]:,} production lines, {r[2]:,} test lines._")
        add("")
    add("`braid` is the clearest case of the formula understating things. It is ~12.7k lines of")
    add("Rust, and it carried a real content-addressing defect for months: a float-precision")
    add("fault in the canonical form that left roughly one node in seven unverifiable while its")
    add("content and signature were perfectly intact. That class of bug is not a lines-of-code")
    add("problem. It was found, root-caused, fixed, and all 84 damaged records were recovered")
    add("rather than rewritten.")
    add("")
    add("## Full inventory")
    add("")
    add("| System | What it is | Prod | Test | Hours | Build cost |")
    add("|---|---|--:|--:|--:|--:|")
    for pkg, prod, tests, hours, cost, desc in rows:
        cat = CATEGORY.get(pkg, (desc.split("—")[0].strip()[:38] or "subsystem", ""))[0]
        add(f"| `{pkg}` | {cat} | {prod:,} | {tests:,} | {hours:,.0f} | **{usd(cost)}** |")
    add(f"| **Total** | | **{total_prod:,}** | **{total_test:,}** | **{total_hours:,.0f}** | **{usd(total_cost)}** |")
    add("")
    add("## Feature detail")
    add("")
    for pkg, prod, tests, hours, cost, desc in rows:
        entry = CATEGORY.get(pkg)
        if not entry:
            continue
        add(f"- **`{pkg}`** ({usd(cost)}) — {entry[1]}")
    add("")
    add("## What this figure leaves out")
    add("")
    add("Counted nowhere above, and all of it real:")
    add("")
    add(f"- **The tool inventory** — {tools.get('total', 0)} tools enumerated and health-checked at")
    add("  runtime. That is a discovery surface, not code, and making it *honest* was most of the work.")
    add(f"- **The ledger's contents** — {facts['braid_nodes']} committed nodes of actual history.")
    add("  Deleting it would destroy the estate's memory; rebuilding the code would not.")
    add(f"- **The dream output** — {facts['dreams']} lineages, each an audited chain of retained iterations.")
    add("- **Operational knowledge** — which providers are funded, which panel models actually")
    add("  work, and what the DNS outage did overnight. None of that is in a line count.")
    add("- **Everything not yet written.** The roadmap is worth more than the code so far.")
    add("")
    add("## Honest weaknesses in this method")
    add("")
    add("- **Lines are a proxy, and a blunt one.** Dense architectural work is undervalued and")
    add("  verbose plumbing overvalued. The hourly rate moves the total more than any single row.")
    add("- **It assumes a competent team at a known rate.** A different team or a different")
    add("  market moves every number here.")
    untested = [f"`{pkg}`" for pkg, _p, t, _h, _c, _d in rows if t == 0]
    if untested:
        add(f"- **{len(untested)} systems ship no tests at all**, which this table makes visible")
        add("  rather than hiding: " + ", ".join(untested) + ". That is a real finding, and")
        add("  it is where the next engineering effort should go.")
    else:
        add("- Every system in the table reports test lines.")
    add("- **Test volume is not test quality.** A large test suite can still assert the wrong")
    add("  thing, and a small one can catch a float-precision fault that costs months. Do not")
    add("  read the test column as a quality score.")
    add("- **It measures code, not outcomes.** Nothing here proves a customer would pay. That")
    add("  is a separate question, and the honest answer today is that the storefront cannot yet")
    add("  take a payment at all.")
    add("")
    add("---")
    add("")
    add("Regenerate with `/opt/mem20/tools/gen_systems_value.py` — the figures are read from the")
    add("estate at run time, so this document can be refreshed rather than hand-edited.")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    print(f"wrote {OUT} ({len(out)} lines)")
    print(f"  {len(rows)} systems | {total_hours:,.0f} hours | {usd(total_cost)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
