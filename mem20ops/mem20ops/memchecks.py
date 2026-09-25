"""mem20-specific inspection workflows: identity, namespace ACLs, lint deltas."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from typing import Any

REPO = "/opt/mem20"
PINNED_BLOCKS_FILE = "pinned_blocks.json"


def _load_engine(store_path: str | None = None):
    """Import the memory engine against an optional isolated store.

    When a store path is supplied the module is reloaded so its path constants
    match that store; otherwise a previously imported engine keeps pointing at
    whichever store loaded it first.
    """
    desired = store_path or os.environ.get("MEM20_STORE_PATH")
    if desired:
        os.environ["MEM20_STORE_PATH"] = desired
    if REPO not in sys.path:
        sys.path.insert(0, REPO)
    import importlib

    import memory_engine.memory as engine

    if desired and getattr(engine, "STORE_DIR", None) != desired:
        importlib.reload(engine)

    import memory

    if desired and getattr(memory, "STORE_DIR", None) != desired:
        memory = importlib.reload(memory)
    return memory


def identity_check(store_path: str | None = None) -> dict[str, Any]:
    """Report registered life models, namespaces, and the integrity of pinned blocks."""
    memory = _load_engine(store_path)

    pinned: dict[str, Any] = {}
    try:
        if os.path.exists(memory.PINNED_FILE):
            with open(memory.PINNED_FILE, encoding="utf-8") as handle:
                pinned = json.load(handle)
    except (OSError, ValueError) as exc:
        pinned = {"_error": str(exc)}

    if not isinstance(pinned, dict):
        blocks: dict[str, Any] = {}
    elif isinstance(pinned.get("blocks"), dict):
        blocks = pinned["blocks"]
    else:
        blocks = {k: v for k, v in pinned.items() if not k.startswith("_")}

    block_names = sorted(blocks.keys())
    life_blocks = [b for b in block_names if "life" in b or "voice" in b]

    namespaces: list[dict[str, Any]] = []
    try:
        rows = memory.recall(topic="namespace_meta", k=1000)
        for row in rows:
            content = row.get("content", "")
            owner = re.search(r"Owner:\s*([^,]+)", content)
            acl = re.search(r"ACL:\s*(\{.*\})", content)
            name_match = re.search(r"Namespace:\s*([^,]+)", content)
            if content.startswith("NSMETA2 "):
                try:
                    payload = json.loads(content[len("NSMETA2 "):])
                    namespaces.append(
                        {
                            "namespace": payload.get("namespace"),
                            "owner": payload.get("owner"),
                            "acl": payload.get("acl"),
                            "structured": True,
                        }
                    )
                    continue
                except ValueError:
                    pass
            namespaces.append(
                {
                    "namespace": name_match.group(1).strip() if name_match else None,
                    "owner": owner.group(1).strip() if owner else None,
                    "acl": acl.group(1) if acl else None,
                    "structured": False,
                }
            )
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        namespaces = [{"_error": str(exc)}]

    return {
        "store_path": getattr(memory, "STORE_DIR", None),
        "pinned_block_count": len(block_names),
        "pinned_blocks": block_names,
        "life_voice_blocks": life_blocks,
        "namespace_count": len(namespaces),
        "namespaces": namespaces,
    }

def acl_probe(
    namespace: str,
    actors: list[str] | None = None,
    probe_query: str = "life model",
    store_path: str | None = None,
) -> dict[str, Any]:
    """Probe namespace ACL enforcement across actors, mirroring a live safety test.

    Read-only: it recalls as each actor and reports whether access was granted or
    denied, so a silent fail-open shows up immediately.
    """
    _load_engine(store_path)
    from memory import recall

    results = []
    for actor in actors or []:
        try:
            rows = recall(topic=f"namespace_{namespace}", k=50)
            exact = [r for r in rows if r.get("topic") == f"namespace_{namespace}"]
            hits = [r for r in exact if probe_query.lower() in r.get("content", "").lower()]
            results.append(
                {
                    "actor": actor,
                    "readable": bool(exact),
                    "matching_rows": len(hits),
                }
            )
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            results.append({"actor": actor, "error": str(exc)})

    return {
        "namespace": namespace,
        "probe_query": probe_query,
        "scope": "raw-ledger (no ACL layer; expected to be readable by anyone)",
        "note": (
            "This probes the raw ledger, which has no ACL layer, so every actor "
            "seeing the rows here is EXPECTED and is not a security finding. Use the "
            "MCP memory_shared_recall tool to test the enforced path; that is the "
            "one that must deny unlisted actors."
        ),
        "actors": results,
    }


def lint_delta(
    path: str,
    revision: str = "HEAD",
    python: str = "/root/.venv/bin/python",
    repo: str = REPO,
) -> dict[str, Any]:
    """Compare ruff findings for a file against a git revision, per rule code.

    Uses ``--stdin-filename`` so the baseline is analysed under the same project
    configuration as the working file. Copying the file to /tmp instead silently
    applies different rules and produces a bogus comparison.
    """
    spec = f":{path}" if revision == ":" else f"{revision}:{path}"
    baseline = subprocess.run(
        ["git", "show", spec],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if baseline.returncode != 0:
        return {
            "path": path,
            "revision": revision,
            "error": baseline.stderr.strip() or "git show failed",
            "hint": (
                "In this repo much of the tree is staged-but-uncommitted; "
                "compare against the index with `git show :<path>` instead."
            ),
        }

    def _counts(text: str) -> dict[str, int]:
        out = subprocess.run(
            [python, "-m", "ruff", "check", "--output-format=concise", "--stdin-filename", path, "-"],
            cwd=repo,
            input=text,
            capture_output=True,
            text=True,
            check=False,
        )
        counts: dict[str, int] = {}
        for line in out.stdout.splitlines():
            match = re.search(r"\b([A-Z]+[0-9]+)\b", line)
            if match:
                code = match.group(1)
                counts[code] = counts.get(code, 0) + 1
        return counts

    before = _counts(baseline.stdout)
    with open(os.path.join(repo, path), encoding="utf-8") as handle:
        after = _counts(handle.read())

    delta = {}
    for code in sorted(set(before) | set(after)):
        b, a = before.get(code, 0), after.get(code, 0)
        if a != b:
            delta[code] = {"before": b, "after": a, "change": a - b}

    return {
        "path": path,
        "revision": revision,
        "before_total": sum(before.values()),
        "after_total": sum(after.values()),
        "delta": delta,
        "new_findings": {k: v for k, v in delta.items() if v["change"] > 0},
        "resolved_findings": {k: v for k, v in delta.items() if v["change"] < 0},
    }


def isolated_store(prefix: str = "mem20ops_") -> str:
    """Create a temporary store directory for a non-destructive probe."""
    return tempfile.mkdtemp(prefix=prefix)
