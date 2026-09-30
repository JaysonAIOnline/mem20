#!/usr/bin/env python3
"""
Hermes Agent — first-class tiered memory system.

Design
------
Injected context is tiny and hard-capped (MEMORY.md ~2200 chars, USER.md ~1375
chars). Real knowledge lives in an UNCAPPED deep store so nothing is lost to
compression. An append-only ledger gives you a chronological, tamper-evident
audit trail of every fact learned, decision, and correction.

Tiers
-----
1. INJECTED  : MEMORY.md (my notes) + USER.md (user profile) — lean indexes,
               always in context, hand-maintained to stay under the caps.
2. DEEP STORE: store/entries/<topic>.md — one file per knowledge domain,
               uncapped, full detail, rebuilt from the ledger at any time.
3. LEDGER    : store/ledger.jsonl — append-only event log (the source of
               truth). Every remember() append a line; rebuild() re-derives
               the deep-store index.

4. VECTOR INDEX: store/vector_index.faiss + store/vector_meta.jsonl —
               semantic embeddings for hybrid retrieval (Step 1 feature).

Usage (run from anywhere; paths are derived from this file's location):
    python3 memory.py remember --topic thestack.topology \
        --content "..." [--tags a,b,c] [--priority high]
    python3 memory.py recall [--topic thestack.topology] [--tags cli] [--k 5]
    python3 memory.py recall_semantic --query "find similar concepts" --k 5
    python3 memory.py ledger [--k 20] [--since 2026-08-17]
    python3 memory.py rebuild            # re-derive store/INDEX.md from ledger
    python3 memory.py rebuild_vectors    # rebuild vector index from ledger
    python3 memory.py backup             # timestamped + 7-day rotation + mirror
    python3 memory.py status             # caps, counts, last events
    python3 memory.py prune              # consolidate superseded facts

The module is importable too:
    from memory import remember, recall, recall_semantic
"""
from __future__ import annotations

import ast as _ast

import argparse
import copy
import json
import os
import random
import re
import shutil
import sys
import time
import glob
import hashlib
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

try:
    from sentence_transformers import SentenceTransformer
    import faiss
    import numpy as np
    VECTOR_AVAILABLE = True
except ImportError:
    VECTOR_AVAILABLE = False

try:
    from rank_bm25 import BM25Okapi
    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False

try:
    from sentence_transformers import CrossEncoder
    CROSS_ENCODER_AVAILABLE = True
except ImportError:
    CROSS_ENCODER_AVAILABLE = False

# Cross-encoder configuration
USE_CROSS_ENCODER = CROSS_ENCODER_AVAILABLE
CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_CROSS_ENCODER = None

def _get_cross_encoder():
    """Lazy-load the cross-encoder model."""
    global _CROSS_ENCODER
    if not CROSS_ENCODER_AVAILABLE:
        raise RuntimeError("Cross-encoder dependencies not installed")
    if _CROSS_ENCODER is None:
        _CROSS_ENCODER = CrossEncoder(CROSS_ENCODER_MODEL)
    return _CROSS_ENCODER

HERE = os.path.dirname(os.path.abspath(__file__))

# Data store location. Defaults to a portable, user-local dir so the engine code
# can live anywhere (e.g. inside the repo) while user memory stays in one place.
# Override with MEM20_STORE_PATH (used by the live deployment and tests).
STORE_DIR = os.environ.get("MEM20_STORE_PATH") or os.path.expanduser("~/.mem20/store")
MEM_DIR = os.path.dirname(STORE_DIR)        # parent of the store (holds MEMORY.md/USER.md)
LEDGER = os.path.join(STORE_DIR, "ledger.jsonl")
ENTRIES = os.path.join(STORE_DIR, "entries")
INDEX = os.path.join(STORE_DIR, "INDEX.md")
BACKUP_DIR = os.path.join(STORE_DIR, "backups")
VECTOR_INDEX = os.path.join(STORE_DIR, "vector_index.faiss")
VECTOR_META = os.path.join(STORE_DIR, "vector_meta.jsonl")
BM25_INDEX = os.path.join(STORE_DIR, "bm25_index.pkl")
BM25_CORPUS = os.path.join(STORE_DIR, "bm25_corpus.jsonl")

# Step 7.4 — separate partition for SIMULATED / imagined content (never touches the
# grounded ledger or the vector/BM25 indexes), plus its decay window.
SIMULATED_LEDGER = os.path.join(STORE_DIR, "simulated_ledger.jsonl")
SIM_TTL_DAYS = int(os.environ.get("MEM20_SIM_TTL_DAYS", "30"))

# Step 7.4 hardening — external attestation for prediction-error promotions.
# A careless/compromised caller can no longer force promotion with just a boolean
# flag + free-text note. Register a verifier that confirms a real prediction error
# resolved in the simulated fact's favor. If unset, a *structured evidence* payload
# is mandatory instead (see promote_simulated_to_grounded).
PREDICTION_ERROR_VERIFIER = None  # callable(sim_id, resolution_note, evidence) -> bool


def set_prediction_error_verifier(fn) -> None:
    """Register an external attestation hook for prediction-error promotions.

    `fn(sim_id, resolution_note, evidence) -> bool` must return True only when a
    genuine, externally-verifiable prediction error resolved in the fact's favor.
    """
    global PREDICTION_ERROR_VERIFIER
    PREDICTION_ERROR_VERIFIER = fn


# Required keys in the structured evidence payload when no verifier is registered.
_PREDICTION_ERROR_EVIDENCE_REQUIRED = ("prediction_ref", "observed_outcome")
MIRROR_CANDIDATES = [
    os.path.expanduser("~/TheStack/mirror/opt/thestack/memory"),
    "/root/TheStack/mirror/opt/thestack/memory",
]

# Injected-file caps (from config.yaml memory.memory_char_limit / user_char_limit)
MEM_CAP = 2200
USER_CAP = 1375
SUPERSEDED = "[SUPERSEEDED]"


# =============================================================================
# Core Pinned Blocks & Secret Scrubbing (Criterion 4)
# =============================================================================

PINNED_FILE = os.path.join(STORE_DIR, "pinned_blocks.json")
def _not_pure_hex(text: str) -> bool:
    """A 40-char run of hex is overwhelmingly a git SHA-1 or content hash, not a secret."""
    stripped = text.strip()
    if len(stripped) != 40:
        return False
    return not all(c in "0123456789abcdefABCDEF" for c in stripped)


def _not_pure_alpha(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) != 40:
        return False
    return not stripped.isalpha()


def _has_mixed_charset(text: str) -> bool:
    stripped = text.strip()
    return (
        any(c.islower() for c in stripped)
        and any(c.isupper() for c in stripped)
        and any(c.isdigit() for c in stripped)
    )


_TB = r"(?<![A-Za-z0-9+/_-])"
_TA = r"(?![A-Za-z0-9+/_-])"
_TB_ALNUM = r"(?<![A-Za-z0-9])"
_TA_ALNUM = r"(?![A-Za-z0-9])"

SECRET_PATTERNS = [
    (r"sk-ant-" + _TB_ALNUM + r"[A-Za-z0-9_\-]{80,140}" + _TA, "Anthropic API key", "high", None),
    (r"sk-proj-" + _TB_ALNUM + r"[A-Za-z0-9_\-]{40,120}" + _TA, "OpenAI project API key", "high", None),
    (r"sk-" + _TB_ALNUM + r"[A-Za-z0-9]{32,64}" + _TA, "OpenAI-style API key", "high", None),
    (r"ghp_" + _TB_ALNUM + r"[A-Za-z0-9]{36}" + _TA, "GitHub Personal Access Token", "high", None),
    (r"ghs_" + _TB_ALNUM + r"[A-Za-z0-9]{36}" + _TA, "GitHub Secret", "high", None),
    (r"gho_" + _TB_ALNUM + r"[A-Za-z0-9]{36}" + _TA, "GitHub OAuth Token", "high", None),
    (r"github_pat_" + _TB_ALNUM + r"[A-Za-z0-9_]{50,100}" + _TA, "GitHub fine-grained PAT", "high", None),
    (r"xoxb-[0-9]{11}-[0-9]{11}-[A-Za-z0-9]{24}" + _TA, "Slack Bot Token", "high", None),
    (r"xoxp-[0-9]{11}-[0-9]{11}-[A-Za-z0-9]{24}" + _TA, "Slack User Token", "high", None),
    (r"(?<![A-Za-z0-9])AKIA[0-9A-Z]{16}" + _TA, "AWS Access Key ID", "high", None),
    (r"(?<![A-Za-z0-9])AIza[0-9A-Za-z_\-]{35}" + _TA, "Google API Key", "high", None),
    (r"Bearer\s+[A-Za-z0-9\-._~+/]{16,}={0,2}", "Bearer token", "medium", None),
    (
        _TB + r"[A-Za-z0-9+/]{40}" + _TA,
        "AWS Secret Access Key (base64)",
        "low",
        lambda t: _not_pure_hex(t) and _not_pure_alpha(t) and _has_mixed_charset(t),
    ),
    (r"(?i)\bpassword\s*[=:]\s*[\"']?[^\s\"']{6,}[\"']?", "Password assignment", "low", None),
    (r"(?i)\bsecret\s*[=:]\s*[\"']?[^\s\"']{6,}[\"']?", "Secret assignment", "low", None),
    (r"(?i)\bapi[_-]?key\s*[=:]\s*[\"']?[^\s\"']{6,}[\"']?", "API key assignment", "low", None),
]

_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


@dataclass(frozen=True)
class SecretFinding:
    label: str
    confidence: str
    offset: int
    preview: str


def detect_secrets(content: str, min_confidence: str = "low") -> list[SecretFinding]:
    """Detect secrets in content. Pure inspection: never mutates or returns a modified string."""
    floor = _CONFIDENCE_RANK.get(min_confidence, 0)
    seen: set[tuple[int, int]] = set()
    findings: list[SecretFinding] = []
    for pattern, label, confidence, validator in SECRET_PATTERNS:
        if _CONFIDENCE_RANK[confidence] < floor:
            continue
        for match in re.finditer(pattern, content):
            text = match.group(0)
            if validator is not None and not validator(text):
                continue
            span = match.span()
            if span in seen:
                continue
            seen.add(span)
            findings.append(
                SecretFinding(
                    label=label,
                    confidence=confidence,
                    offset=span[0],
                    preview=text[:8] + "..." if len(text) > 8 else "...",
                )
            )
    findings.sort(key=lambda f: f.offset)
    return findings


def redact_secrets(content: str, min_confidence: str = "low") -> tuple[str, list[SecretFinding]]:
    """Return (redacted_copy, findings). For producing safe OUTPUT only.

    Storage paths must use detect_secrets() and keep the caller's original text;
    silently rewriting stored content corrupts real data.
    """
    findings = detect_secrets(content, min_confidence)
    if not findings:
        return content, []
    spans: list[tuple[int, int, str]] = []
    for pattern, label, confidence, validator in SECRET_PATTERNS:
        if _CONFIDENCE_RANK[confidence] < _CONFIDENCE_RANK.get(min_confidence, 0):
            continue
        for match in re.finditer(pattern, content):
            text = match.group(0)
            if validator is not None and not validator(text):
                continue
            spans.append((match.start(), match.end(), f"[REDACTED {label}]"))
    spans.sort(key=lambda s: (s[0], -s[1]))
    merged: list[tuple[int, int, str]] = []
    for start, end, label in spans:
        if merged and start < merged[-1][1]:
            continue
        merged.append((start, end, label))
    out: list[str] = []
    cursor = 0
    for start, end, label in merged:
        out.append(content[cursor:start])
        out.append(label)
        cursor = end
    out.append(content[cursor:])
    return "".join(out), findings


def _load_pinned() -> dict:
    if not os.path.exists(PINNED_FILE):
        return {"blocks": {}, "order": []}
    try:
        with open(PINNED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"blocks": {}, "order": []}


def _save_pinned(data: dict) -> None:
    os.makedirs(STORE_DIR, exist_ok=True)
    with open(PINNED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _scrub_secrets(content: str) -> tuple[str, list[str]]:
    """Backwards-compatible redaction helper. Returns (redacted_copy, detected_labels).

    Retained for explicit redact-on-output callers (e.g. memory_scan_pii).
    Store paths must NOT use this — they use detect_secrets() and persist the
    caller's original text unchanged.
    """
    redacted, findings = redact_secrets(content)
    return redacted, [f"{f.label}: {f.preview}" for f in findings]


def _detect_only(content: str) -> list[str]:
    """Non-destructive detection for store paths. Returns human-readable labels."""
    findings = detect_secrets(content)
    if not findings:
        return []
    labels: list[str] = []
    for finding in findings:
        entry = f"{finding.label}: {finding.preview} ({finding.confidence})"
        if entry not in labels:
            labels.append(entry)
    return labels


def pin_block(block_id: str, content: str, reason: str = "", actor: str = "agent") -> dict:
    """Pin a memory block as a core reference (immune to pruning/supersede)."""
    data = _load_pinned()
    if block_id in data["blocks"]:
        raise ValueError(f"Block {block_id} already pinned")
    
    data["blocks"][block_id] = {
        "content": content,
        "reason": reason,
        "pinned_ts": _now(),
        "actor": actor,
    }
    data["order"].append(block_id)
    _save_pinned(data)
    return {"block_id": block_id, "pinned": True}


def unpin_block(block_id: str, actor: str = "agent") -> dict:
    """Unpin a previously pinned block."""
    data = _load_pinned()
    if block_id not in data["blocks"]:
        raise ValueError(f"Block {block_id} not found")
    
    del data["blocks"][block_id]
    data["order"] = [b for b in data["order"] if b != block_id]
    _save_pinned(data)
    return {"block_id": block_id, "pinned": False}


def list_pinned_blocks(actor: str = "agent") -> dict:
    """List all pinned blocks."""
    data = _load_pinned()
    return {"pinned_blocks": data["blocks"], "order": data["order"]}


def get_pinned_block(block_id: str, actor: str = "agent") -> dict:
    """Get a specific pinned block."""
    data = _load_pinned()
    if block_id not in data["blocks"]:
        return {"error": f"Block {block_id} not found"}
    return {"block_id": block_id, **data["blocks"][block_id]}


# Vector config
# Vector config
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(topic: str) -> str:
    return topic.replace(" ", "_").replace("/", "_").replace(":", "_").lower()


# The entries/ mirror writes one "<slug>.md" per topic, so the filename has to fit
# the filesystem's NAME_MAX. The ledger itself is JSONL and has no such limit, so a
# long topic is storable in the ledger but was previously unwriteable to the mirror
# and raised a bare [Errno 36] that surfaced to the caller as a crash.
#
# Identities are the worst case: a caller that passes the identity *sentence* where
# a short key was expected produces keys of 274-427 characters. Rather than reject
# those writes, bound the filename and keep the digest so distinct long topics can
# never collide onto one file.
#
# Existing short slugs are untouched: the bound only applies past the limit, so no
# already-written mirror is renamed or orphaned.
_MIRROR_NAME_MAX = 255 - len(".md")


def _mirror_filename(topic: str) -> str:
    """Return a filesystem-safe '<name>.md' for a topic's entries/ mirror.

    Short topics keep their historical name exactly. Long topics are truncated and
    given a stable sha256 prefix so two different long topics never share a file.
    """
    slug = _slug(topic)
    if len(slug) <= _MIRROR_NAME_MAX:
        return f"{slug}.md"
    digest = hashlib.sha256(slug.encode("utf-8")).hexdigest()[:16]
    keep = _MIRROR_NAME_MAX - len(digest) - 1  # "-" separator
    return f"{slug[:keep]}-{digest}.md"



def _validate_partition_tags(rec: dict) -> None:
    """Issue #3: assert the origin/store tags at the lowest write path.

    Hard separation is otherwise only conventional (set by the two writers). This
    binds each write action to its expected partition tags, so a future refactor
    that writes a simulated record with grounded tags (or vice versa) is caught
    immediately rather than discovered later by the audit.
    """
    # Records that carry partition tags must be internally consistent...
    origin = rec.get("origin")
    store = rec.get("store")
    if origin is not None or store is not None:
        if (origin, store) not in {("grounded", "grounded"), ("simulated", "simulated")}:
            raise ValueError(
                f"Partition tag mismatch: origin={origin!r} store={store!r}. "
                "A record must be (origin=grounded, store=grounded) or "
                "(origin=simulated, store=simulated).")
    # ...and the write action must match the partition it claims.
    expected = {"remember": ("grounded", "grounded"),
                "simulate": ("simulated", "simulated")}
    act = rec.get("action")
    if act in expected:
        exp_o, exp_s = expected[act]
        if rec.get("origin") != exp_o or rec.get("store") != exp_s:
            raise ValueError(
                f"Partition violation: action={act!r} must carry "
                f"origin={exp_o!r}, store={exp_s!r}; got origin={origin!r}, store={store!r}.")


def _append_ledger(rec: dict) -> None:
    _validate_partition_tags(rec)
    os.makedirs(STORE_DIR, exist_ok=True)
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    # keep the ledger itself bounded but never lose events:
    # rotate to timestamped archive if it exceeds 2000 lines
    try:
        with open(LEDGER, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > 2000:
            os.makedirs(BACKUP_DIR, exist_ok=True)
            arch = os.path.join(BACKUP_DIR, f"ledger_{int(time.time())}.jsonl")
            shutil.move(LEDGER, arch)
            open(LEDGER, "w").close()
    except Exception:
        pass


def remember(topic: str, content: str, tags: list[str] | None = None,
             priority: str = "normal", actor: str = "agent",
             valid_from: str | None = None, valid_to: str | None = None,
             confidence: float | None = None, epistemic_status: str | None = None,
             source: str | None = None, scrub_secrets: bool = True,
             _allow_simulated: bool = False) -> dict:
    """Append a GROUNDED fact to the ledger.

    Step 7.4 lock: simulated/imagined content MUST NOT enter here. The only
    sanctioned write path for simulation is remember_simulated(). An explicit
    `_allow_simulated=True` is rejected on purpose so no future refactor can
    silently route simulation through remember().
    """
    if _allow_simulated:
        raise PermissionError(
            "remember() is grounded-only. Simulated content must use "
            "remember_simulated(); this call is refused to protect Step 7.4 separation.")
    os.makedirs(ENTRIES, exist_ok=True)
    now = _now()
    
    cleaned_content = content
    detected_secrets = _detect_only(content) if scrub_secrets else []
    if detected_secrets:
        print(
            f"Warning: {len(detected_secrets)} possible secret(s) detected; "
            "stored text left unmodified",
            file=sys.stderr,
        )
    
    rec = {
        "id": f"{int(time.time()*1000):x}{os.urandom(2).hex()}",
        "ts": now,
        "actor": actor,
        "action": "remember",
        "topic": topic,
        "tags": tags or [],
        "priority": priority,
        "content": cleaned_content,
        "valid_from": valid_from or now,
        "valid_to": valid_to,
        "confidence": confidence,
        "epistemic_status": epistemic_status,
        "source": source,
        "secrets_detected": detected_secrets if detected_secrets else None,
    }
    _append_ledger(rec)

    path = os.path.join(ENTRIES, _mirror_filename(topic))
    header = f"\n\n## {now}  (pri={priority}, tags={tags or []})\\\\n"
    if valid_from:
        header += f"  **Valid from:** {valid_from}\\\\n"
    if valid_to:
        header += f"  **Valid to:** {valid_to}\\\\n"
    if confidence is not None:
        header += f"  **Confidence:** {confidence:.2f}\\\\n"
    if epistemic_status:
        header += f"  **Epistemic status:** {epistemic_status}\\\\n"
    if source:
        header += f"  **Source:** {source}\\\\n"
    mode = "a" if os.path.exists(path) else "w"
    with open(path, mode, encoding="utf-8") as f:
        if mode == "w":
            f.write(f"# {topic}\\\\n")
        f.write(header + content.strip() + "\\\\n")

    # Add to vector index
    if VECTOR_AVAILABLE:
        try:
            _add_to_vector_index(rec)
        except Exception as e:
            # Don't fail the remember operation if vector indexing fails
            print(f"Warning: vector indexing failed: {e}", file=sys.stderr)

    rebuild_index()
    return rec


def _load_ledger() -> list[dict]:
    if not os.path.exists(LEDGER):
        return []
    out = []
    with open(LEDGER, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def recall(topic: str | None = None, tags: list[str] | None = None,
           k: int = 5, include_simulated: bool = False) -> list[dict]:
    """Recall facts, optionally filtered by topic/tags. Returns most recent first.

    By default simulated content is EXCLUDED (Step 7.4 hard separation); pass
    include_simulated=True to also surface active simulated records.
    """
    return recall_at(as_of=None, topic=topic, tags=tags, k=k, include_simulated=include_simulated)


def recall_at(as_of: str | None = None, topic: str | None = None, 
              tags: list[str] | None = None, k: int = 5,
              include_simulated: bool = False) -> list[dict]:
    """Recall facts as they existed at a specific point in time (bi-temporal query).
    
    Args:
        as_of: ISO timestamp to query state as of that moment (None = now)
        topic: Filter by topic
        tags: Filter by tags
        k: Maximum results
        include_simulated: if True, also surface active simulated records
    
    Returns facts that were valid at the given time (valid_from <= as_of < valid_to).
    """
    recs = _load_ledger()
    # Filter to remember actions, exclude superseded (content marker OR
    # supersede-event reference — supersede() appends an event with
    # supersedes_id pointing at the original row rather than rewriting it).
    superseded_ids = {
        str(r.get("supersedes_id"))
        for r in recs
        if r.get("action") == "supersede" and r.get("supersedes_id")
    }
    recs = [r for r in recs if r.get("action") == "remember"
            and SUPERSEDED not in r.get("content", "")
            and str(r.get("id")) not in superseded_ids]

    if include_simulated:
        sim = [r for r in _load_simulated_ledger()
               if r.get("action") == "simulate" and not r.get("quarantined")
               and (r.get("valid_to") is None or r.get("valid_to") >= _now())]
        recs = recs + sim
    
    # Apply temporal filter
    if as_of is not None:
        recs = [r for r in recs 
                if r.get("valid_from", "") <= as_of 
                and (r.get("valid_to") is None or r.get("valid_to", "") > as_of)]
    
    if topic:
        recs = [r for r in recs if topic.lower() in r.get("topic", "").lower()]
    if tags:
        recs = [r for r in recs
                if any(t in (r.get("tags") or []) for t in tags)]
    # The original grounded record is stamped directly by set_epistemic_status, so no
    # extra event-sourced resolution is needed here.
    recs = list(reversed(recs))
    return recs[:k]


def rebuild_index() -> str:
    """Re-derive store/INDEX.md (a compact table of all topics) from ledger."""
    recs = _load_ledger()
    topics: dict[str, dict] = {}
    for r in recs:
        if r.get("action") != "remember":
            continue
        t = r.get("topic", "unknown")
        if t not in topics:
            topics[t] = {"count": 0, "last": r.get("ts", ""),
                         "tags": set(r.get("tags") or []),
                         "pri": r.get("priority", "normal")}
        topics[t]["count"] += 1
        topics[t]["last"] = r.get("ts", topics[t]["last"])
        topics[t]["tags"].update(r.get("tags") or [])
        if r.get("priority") == "high":
            topics[t]["pri"] = "high"

    lines = ["# Memory Store Index", "",
             f"_auto-generated {_now()} — {len(topics)} topics, "
             f"{len(recs)} events_", "",
             "## Topics", ""]
    for t in sorted(topics):
        meta = topics[t]
        lines.append(
            f"- **{t}** — {meta['count']} entries, last {meta['last'][:10]}, "
            f"pri={meta['pri']}, tags={sorted(meta['tags'])}")
    lines.append("")
    lines.append("## How to use")
    lines.append("- `python3 memory.py recall --topic <name>` to read full detail")
    lines.append("- `python3 memory.py remember --topic <name> --content \"...\"` to add")
    lines.append("- Deep detail per topic lives in `entries/<topic>.md`")
    text = "\n".join(lines)
    with open(INDEX, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    return text


def backup() -> str:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(BACKUP_DIR, f"mem_{stamp}")
    shutil.copytree(STORE_DIR, dest, ignore=shutil.ignore_patterns("backups"))
    # 7-day rotation
    cutoff = time.time() - 7 * 86400
    for d in glob.glob(os.path.join(BACKUP_DIR, "mem_*")):
        if os.path.getmtime(d) < cutoff:
            shutil.rmtree(d, ignore_errors=True)
    # optional mirror to project (first existing candidate wins)
    mirrored = False
    MIRROR = next((m for m in MIRROR_CANDIDATES if os.path.isdir(m)), None)
    if MIRROR:
        try:
            os.makedirs(MIRROR, exist_ok=True)
            for fn in ("MEMORY.md", "USER.md"):
                src = os.path.join(MEM_DIR, fn)
                if os.path.exists(src):
                    shutil.copy2(src, os.path.join(MIRROR, fn))
            idx = os.path.join(STORE_DIR, "INDEX.md")
            if os.path.exists(idx):
                shutil.copy2(idx, os.path.join(MIRROR, "INDEX.md"))
            mirrored = True
        except Exception:
            mirrored = False
    return f"backed up to {dest} (mirror={'yes' if mirrored else 'n/a'})"


def status() -> str:
    recs = _load_ledger()
    mem = open(os.path.join(MEM_DIR, "MEMORY.md"), encoding="utf-8").read() \
        if os.path.exists(os.path.join(MEM_DIR, "MEMORY.md")) else ""
    user = open(os.path.join(MEM_DIR, "USER.md"), encoding="utf-8").read() \
        if os.path.exists(os.path.join(MEM_DIR, "USER.md")) else ""
    out = []
    out.append(f"ledger events : {len(recs)}")
    out.append(f"deep entries  : {len(glob.glob(os.path.join(ENTRIES, '*.md')))}")
    out.append(f"MEMORY.md     : {len(mem)}/{MEM_CAP} chars "
               f"{'OK' if len(mem) <= MEM_CAP else 'OVER CAP!'}")
    out.append(f"USER.md       : {len(user)}/{USER_CAP} chars "
               f"{'OK' if len(user) <= USER_CAP else 'OVER CAP!'}")
    out.append(f"last event    : {recs[-1]['ts'] if recs else 'none'}")
    return "\n".join(out)


def ledger_view(k: int = 20, since: str | None = None) -> str:
    recs = _load_ledger()
    if since:
        recs = [r for r in recs if r.get("ts", "") >= since]
    recs = list(reversed(recs))[:k]
    out = []
    for r in recs:
        out.append(f"[{r.get('ts','?')[:19]}] {r.get('action')} "
                   f"topic={r.get('topic','-')} pri={r.get('priority','-')}")
        c = r.get("content", "")
        out.append("    " + (c[:200] + ("…" if len(c) > 200 else "")))
    return "\n".join(out) if out else "(empty)"


# =============================================================================
# Vector Embedding Functions (Step 1: Hybrid Retrieval)
# =============================================================================

_EMBEDDER = None

def _get_embedder():
    """Lazy-load the embedding model."""
    global _EMBEDDER
    if not VECTOR_AVAILABLE:
        raise RuntimeError("Vector dependencies not installed. Run: pip install sentence-transformers faiss-cpu")
    if _EMBEDDER is None:
        _EMBEDDER = SentenceTransformer(EMBEDDING_MODEL)
    return _EMBEDDER


def _load_vector_meta() -> list[dict]:
    """Load vector metadata (parallel to FAISS index)."""
    if not os.path.exists(VECTOR_META):
        return []
    out = []
    with open(VECTOR_META, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def _save_vector_meta(meta: list[dict]) -> None:
    """Save vector metadata."""
    with open(VECTOR_META, "w", encoding="utf-8") as f:
        for m in meta:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")


def _get_vector_index():
    """Load or create FAISS index."""
    if not VECTOR_AVAILABLE:
        raise RuntimeError("Vector dependencies not installed")
    
    if os.path.exists(VECTOR_INDEX):
        return faiss.read_index(VECTOR_INDEX)
    else:
        return faiss.IndexFlatIP(EMBEDDING_DIM)  # cosine similarity via normalized vectors


def _normalize(vectors: np.ndarray) -> np.ndarray:
    """Normalize vectors for cosine similarity."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return vectors / norms


def _assert_grounded(rec: dict, index_kind: str) -> None:
    """Runtime firewall: grounded retrieval indexes MUST never hold simulated IDs.

    A future refactor that accidentally routes a simulated/imagined record into
    the vector or BM25 index will be rejected here at write time (not merely
    caught later by the audit). The origin/store tags are immutable, so this
    check is independent of any type-system guarantees.
    """
    origin = rec.get("origin")
    store = rec.get("store")
    if origin not in (None, "grounded") or store not in (None, "grounded"):
        raise ValueError(
            f"Refusing to add record {rec.get('id')!r} to the {index_kind} index: "
            f"origin={origin!r} store={store!r}. Only grounded records may be indexed; "
            f"simulated content is confined to the simulated partition."
        )


def _add_to_vector_index(rec: dict) -> None:
    """Add a record to the FAISS vector index."""
    if not VECTOR_AVAILABLE:
        return

    _assert_grounded(rec, "vector")

    embedder = _get_embedder()
    index = _get_vector_index()
    meta = _load_vector_meta()
    
    # Create embedding from content + topic + tags
    text = f"{rec['topic']}: {rec['content']}"
    if rec.get('tags'):
        text += " " + " ".join(rec['tags'])
    
    embedding = embedder.encode([text], convert_to_numpy=True)[0]
    embedding = _normalize(embedding.reshape(1, -1)).astype(np.float32)
    
    # Add to FAISS index
    index.add(embedding)
    
    # Add metadata
    meta_entry = {
        "id": rec["id"],
        "ts": rec["ts"],
        "topic": rec["topic"],
        "tags": rec["tags"],
        "priority": rec["priority"],
        "content_hash": hashlib.md5(rec["content"].encode()).hexdigest()[:16],
    }
    meta.append(meta_entry)
    
    # Save both
    faiss.write_index(index, VECTOR_INDEX)
    _save_vector_meta(meta)


# =============================================================================
# BM25 Index Functions (Hybrid Search)
# =============================================================================

import pickle

def _get_bm25_index():
    """Load or create BM25 index."""
    if not BM25_AVAILABLE:
        return None
    
    if os.path.exists(BM25_INDEX):
        try:
            with open(BM25_INDEX, "rb") as f:
                return pickle.load(f)
        except Exception:
            pass
    return None


def _save_bm25_index(bm25) -> None:
    """Save BM25 index."""
    if not BM25_AVAILABLE:
        return
    with open(BM25_INDEX, "wb") as f:
        pickle.dump(bm25, f)


def _load_bm25_corpus() -> list[dict]:
    """Load BM25 corpus metadata."""
    if not os.path.exists(BM25_CORPUS):
        return []
    out = []
    with open(BM25_CORPUS, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def _save_bm25_corpus(corpus: list[dict]) -> None:
    """Save BM25 corpus metadata."""
    with open(BM25_CORPUS, "w", encoding="utf-8") as f:
        for m in corpus:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")


def _add_to_bm25_index(rec: dict) -> None:
    """Add a record to the BM25 index."""
    if not BM25_AVAILABLE:
        return

    _assert_grounded(rec, "bm25")

    # Load existing index and corpus
    bm25 = _get_bm25_index()
    corpus = _load_bm25_corpus()
    
    # Create tokenized text for BM25
    text = f"{rec['topic']} {rec['content']}"
    if rec.get('tags'):
        text += " " + " ".join(rec['tags'])
    tokens = text.lower().split()
    
    if bm25 is None:
        # Create new index
        bm25 = BM25Okapi([tokens])
        corpus = [{
            "id": rec["id"],
            "ts": rec["ts"],
            "topic": rec["topic"],
            "tags": rec["tags"],
            "priority": rec["priority"],
        }]
    else:
        # Add to existing index - need to rebuild (BM25Okapi doesn't support incremental add)
        # So we rebuild from corpus + new entry
        corpus.append({
            "id": rec["id"],
            "ts": rec["ts"],
            "topic": rec["topic"],
            "tags": rec["tags"],
            "priority": rec["priority"],
        })
        # Re-tokenize all corpus.
        # The persisted corpus is metadata-only (id/ts/topic/tags/priority), so
        # the previous implementation's c.get('content', '') silently yielded ''
        # and re-tokenized every ALREADY-indexed record as topic+tags only --
        # dropping its content tokens from the index on every single write.
        # BM25Okapi has no incremental add, so the whole corpus is re-tokenized
        # regardless; the ledger is the source of truth that actually carries
        # content, and it is what rebuild_bm25() already uses.
        by_id = {r.get("id"): r for r in _load_ledger() if r.get("action") == "remember"}
        all_tokens = []
        for c in corpus:
            src = by_id.get(c.get("id"))
            if src is not None:
                t = f"{src['topic']}: {src['content']}"
                if src.get("tags"):
                    t += " " + " ".join(src["tags"])
            else:
                # Ledger entry unavailable (e.g. compacted). Fall back to
                # metadata rather than silently indexing an empty document.
                t = f"{c['topic']} {c.get('content', '')}"
                if c.get("tags"):
                    t += " " + " ".join(c["tags"])
            all_tokens.append(t.lower().split())
        bm25 = BM25Okapi(all_tokens)
    
    # Save both
    _save_bm25_index(bm25)
    _save_bm25_corpus(corpus)


def rebuild_bm25() -> str:
    """Rebuild the BM25 index from all ledger entries."""
    if not BM25_AVAILABLE:
        return "BM25 dependencies not installed (need rank_bm25)"
    
    recs = _load_ledger()
    remember_recs = [r for r in recs if r.get("action") == "remember"
                     and SUPERSEDED not in r.get("content", "")]
    
    if not remember_recs:
        _save_bm25_index(None)
        _save_bm25_corpus([])
        return "BM25 index rebuilt (empty)"
    
    # Build corpus
    corpus = []
    all_tokens = []
    
    for rec in remember_recs:
        text = f"{rec['topic']}: {rec['content']}"
        if rec.get('tags'):
            text += " " + " ".join(rec['tags'])
        tokens = text.lower().split()
        all_tokens.append(tokens)
        
        corpus.append({
            "id": rec["id"],
            "ts": rec["ts"],
            "topic": rec["topic"],
            "tags": rec["tags"],
            "priority": rec["priority"],
        })
    
    bm25 = BM25Okapi(all_tokens)
    _save_bm25_index(bm25)
    _save_bm25_corpus(corpus)
    
    return f"BM25 index rebuilt with {len(remember_recs)} entries"


def remember(topic: str, content: str, tags: list[str] | None = None,
             priority: str = "normal", actor: str = "agent",
             valid_from: str | None = None, valid_to: str | None = None,
             confidence: float | None = None, epistemic_status: str | None = None,
             source: str | None = None, scrub_secrets: bool = True,
             _allow_simulated: bool = False) -> dict:
    """Append a GROUNDED fact to the ledger.

    Step 7.4 lock: simulated/imagined content MUST NOT enter here. The only
    sanctioned write path for simulation is remember_simulated(). An explicit
    `_allow_simulated=True` is rejected on purpose so no future refactor can
    silently route simulation through remember().
    """
    if _allow_simulated:
        raise PermissionError(
            "remember() is grounded-only. Simulated content must use "
            "remember_simulated(); this call is refused to protect Step 7.4 separation.")
    os.makedirs(ENTRIES, exist_ok=True)
    now = _now()
    
    cleaned_content = content
    detected_secrets = _detect_only(content) if scrub_secrets else []
    if detected_secrets:
        print(
            f"Warning: {len(detected_secrets)} possible secret(s) detected; "
            "stored text left unmodified",
            file=sys.stderr,
        )
    
    rec = {
        "id": f"{int(time.time()*1000):x}{os.urandom(2).hex()}",
        "ts": now,
        "actor": actor,
        "action": "remember",
        "topic": topic,
        "tags": tags or [],
        "priority": priority,
        "content": cleaned_content,
        "valid_from": valid_from or now,
        "valid_to": valid_to,
        "confidence": confidence,
        "epistemic_status": epistemic_status,
        "source": source,
        # Step 7.4 — immutable origin tag. Grounded facts ALWAYS carry
        # origin=="grounded"; simulated content is written through
        # remember_simulated() into a separate partition and can never
        # reach this ledger or the vector/BM25 indexes.
        "origin": "grounded",
        "store": "grounded",
        "secrets_detected": detected_secrets if detected_secrets else None,
    }
    _append_ledger(rec)

    path = os.path.join(ENTRIES, _mirror_filename(topic))
    header = f"\n\n## {now}  (pri={priority}, tags={tags or []})\\\\n"
    if valid_from:
        header += f"  **Valid from:** {valid_from}\\\\n"
    if valid_to:
        header += f"  **Valid to:** {valid_to}\\\\n"
    if confidence is not None:
        header += f"  **Confidence:** {confidence:.2f}\\\\n"
    if epistemic_status:
        header += f"  **Epistemic status:** {epistemic_status}\\\\n"
    if source:
        header += f"  **Source:** {source}\\\\n"
    mode = "a" if os.path.exists(path) else "w"
    with open(path, mode, encoding="utf-8") as f:
        if mode == "w":
            f.write(f"# {topic}\\\\n")
        f.write(header + content.strip() + "\\\\n")

    # Add to vector index
    if VECTOR_AVAILABLE:
        try:
            _add_to_vector_index(rec)
        except Exception as e:
            # Don't fail the remember operation if vector indexing fails
            print(f"Warning: vector indexing failed: {e}", file=sys.stderr)

    # Add to BM25 index
    if BM25_AVAILABLE:
        try:
            _add_to_bm25_index(rec)
        except Exception as e:
            print(f"Warning: BM25 indexing failed: {e}", file=sys.stderr)

    rebuild_index()
    return rec


def supersede(old_id: str, new_content: str, tags: list[str] | None = None,
              priority: str = "normal", actor: str = "agent") -> dict:
    """Supersede an existing fact with new content. Old fact gets marked with SUPERSEDED."""
    recs = _load_ledger()
    old_rec = next((r for r in recs if r.get("id") == old_id), None)
    if not old_rec:
        raise ValueError(f"Fact with id {old_id} not found")
    
    # Mark old fact as superseded
    old_rec["content"] = SUPERSEDED + " " + old_rec.get("content", "")
    _append_ledger({
        "id": f"{int(time.time()*1000):x}{os.urandom(2).hex()}",
        "ts": _now(),
        "actor": actor,
        "action": "supersede",
        "topic": old_rec.get("topic"),
        "tags": old_rec.get("tags", []),
        "priority": priority,
        "content": SUPERSEDED + " " + old_rec.get("content", ""),
        "supersedes_id": old_id,
        "valid_from": old_rec.get("valid_from"),
        "valid_to": _now(),
    })
    
    # Create new fact
    return remember(
        topic=old_rec.get("topic"),
        content=new_content,
        tags=tags or old_rec.get("tags", []),
        priority=priority,
        actor=actor,
    )


def update_validity(fact_id: str, valid_from: str | None = None, 
                    valid_to: str | None = None, actor: str = "agent") -> dict:
    """Update the validity window of a fact."""
    recs = _load_ledger()
    old_rec = next((r for r in recs if r.get("id") == fact_id), None)
    if not old_rec:
        raise ValueError(f"Fact with id {fact_id} not found")
    
    new_valid_from = valid_from if valid_from is not None else old_rec.get("valid_from")
    new_valid_to = valid_to if valid_to is not None else old_rec.get("valid_to")
    
    _append_ledger({
        "id": f"{int(time.time()*1000):x}{os.urandom(2).hex()}",
        "ts": _now(),
        "actor": actor,
        "action": "update_validity",
        "topic": old_rec.get("topic"),
        "tags": old_rec.get("tags", []),
        "priority": old_rec.get("priority", "normal"),
        "content": old_rec.get("content", ""),
        "valid_from": new_valid_from,
        "valid_to": new_valid_to,
        "updates_id": fact_id,
    })
    
    return {
        "id": fact_id,
        "valid_from": new_valid_from,
        "valid_to": new_valid_to,
    }


def update_validity(fact_id: str, valid_from: str | None = None, 
                    valid_to: str | None = None, actor: str = "agent") -> dict:
    """Update the validity window of a fact."""
    recs = _load_ledger()
    old_rec = next((r for r in recs if r.get("id") == fact_id), None)
    if not old_rec:
        raise ValueError(f"Fact with id {fact_id} not found")
    
    new_valid_from = valid_from if valid_from is not None else old_rec.get("valid_from")
    new_valid_to = valid_to if valid_to is not None else old_rec.get("valid_to")
    
    _append_ledger({
        "id": f"{int(time.time()*1000):x}{os.urandom(2).hex()}",
        "ts": _now(),
        "actor": actor,
        "action": "update_validity",
        "topic": old_rec.get("topic"),
        "tags": old_rec.get("tags", []),
        "priority": old_rec.get("priority", "normal"),
        "content": old_rec.get("content", ""),
        "valid_from": new_valid_from,
        "valid_to": new_valid_to,
        "updates_id": fact_id,
    })
    
    return {
        "id": fact_id,
        "valid_from": new_valid_from,
        "valid_to": new_valid_to,
    }


# =============================================================================
# Metacognitive & Epistemic Layer (Step 2: Metacognitive & Epistemic Layer)
# =============================================================================

def assess_confidence(fact_id: str, confidence: float, actor: str = "agent") -> dict:
    """Explicitly set or update confidence score for a fact."""
    recs = _load_ledger()
    old_rec = next((r for r in _load_ledger() if r.get("id") == fact_id), None)
    if not old_rec:
        raise ValueError(f"Fact with id {fact_id} not found")
    
    _append_ledger({
        "id": f"{int(time.time()*1000):x}{os.urandom(2).hex()}",
        "ts": _now(),
        "actor": actor,
        "action": "assess_confidence",
        "topic": old_rec.get("topic"),
        "tags": old_rec.get("tags", []),
        "priority": old_rec.get("priority", "normal"),
        "content": old_rec.get("content", ""),
        "confidence": confidence,
        "updates_id": fact_id,
    })
    
    return {"id": fact_id, "confidence": confidence}


def _stamp_grounded_record(fact_id: str, **fields) -> bool:
    """Step 7 follow-up: stamp fields (e.g. epistemic_status) directly onto the
    ORIGINAL grounded record. The ledger is otherwise append-only; this is the single
    sanctioned in-place update so set_epistemic_status is not merely event-sourced."""
    if not os.path.exists(LEDGER):
        return False
    out_lines = []
    updated = False
    with open(LEDGER, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                out_lines.append(line)
                continue
            try:
                rec = json.loads(s)
            except Exception:
                out_lines.append(line)
                continue
            if rec.get("action") == "remember" and rec.get("id") == fact_id:
                rec.update({k: v for k, v in fields.items() if v is not None})
                updated = True
                out_lines.append(json.dumps(rec, ensure_ascii=False) + "\n")
            else:
                out_lines.append(line)
    if updated:
        with open(LEDGER, "w", encoding="utf-8") as f:
            f.writelines(out_lines)
    return updated


def _stamp_entry_epistemic_status(topic: str, new_status: str) -> None:
    """Mirror the stamped status into the deep-store entry's Epistemic status header."""
    path = os.path.join(ENTRIES, _mirror_filename(topic))
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    pattern = re.compile(r"\*\*Epistemic status:\*\*\s*\S+")
    matches = list(pattern.finditer(text))
    if matches:
        last = matches[-1]
        text = text[:last.start()] + f"**Epistemic status:** {new_status}" + text[last.end():]
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)


def set_epistemic_status(fact_id: str, epistemic_status: str, actor: str = "agent") -> dict:
    """Set the epistemic status tag on the ORIGINAL fact record.

    Accepted values: observed, inferred, imagined, user_stated, hypothesis, agent_generated.
    Stamps the field directly onto the grounded ledger entry and the deep-store header
    (no event-sourced workaround), so veto/audit/recall read the authoritative value.
    """
    valid_statuses = ["observed", "inferred", "imagined", "user_stated", "hypothesis", "agent_generated"]
    if epistemic_status not in valid_statuses:
        raise ValueError(f"Invalid epistemic_status. Must be one of: {valid_statuses}")

    old_rec = next((r for r in _load_ledger() if r.get("id") == fact_id and r.get("action") == "remember"), None)
    if not old_rec:
        raise ValueError(f"Fact with id {fact_id} not found")
    if SUPERSEDED in (old_rec.get("content", "") or ""):
        raise ValueError(f"Fact with id {fact_id} is superseded; status cannot be changed")

    _stamp_grounded_record(fact_id, epistemic_status=epistemic_status)
    _stamp_entry_epistemic_status(old_rec.get("topic", ""), epistemic_status)
    return {"id": fact_id, "epistemic_status": epistemic_status}


def detect_knowledge_gaps(topic: str, threshold: float = 0.5) -> dict:
    """Detect knowledge gaps for a topic - find areas with low confidence or missing coverage."""
    recs = _load_ledger()
    topic_recs = [r for r in _load_ledger() 
                  if r.get("action") == "remember"
                  and SUPERSEDED not in r.get("content", "")
                  and topic.lower() in r.get("topic", "").lower()]
    
    if not topic_recs:
        return {"topic": topic, "gaps": ["No memories found for topic"], "coverage": 0.0}
    
    # Analyze confidence distribution
    confidences = [r.get("confidence") for r in topic_recs if r.get("confidence") is not None]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5
    
    # Identify subtopics (simple clustering by tags/keywords)
    all_tags = set()
    for r in topic_recs:
        all_tags.update(r.get("tags", []))
    
    # Find tags with low average confidence
    tag_confidences = {}
    for r in topic_recs:
        for tag in r.get("tags", []):
            if tag not in tag_confidences:
                tag_confidences[tag] = []
            if r.get("confidence") is not None:
                tag_confidences[tag].append(r["confidence"])
    
    low_confidence_tags = [tag for tag, confs in tag_confidences.items() 
                          if confs and sum(confs)/len(confs) < 0.5]
    
    gaps = []
    if avg_confidence < threshold:
        gaps.append(f"Overall low confidence ({avg_confidence:.2f}) for topic '{topic}'")
    if low_confidence_tags:
        gaps.append(f"Low confidence subtopics: {', '.join(low_confidence_tags)}")
    if len(topic_recs) < 5:
        gaps.append(f"Sparse coverage: only {len(topic_recs)} memories for topic")
    
    return {
        "topic": topic,
        "total_memories": len(topic_recs),
        "avg_confidence": avg_confidence,
        "gaps": gaps if gaps else ["No significant gaps detected"],
        "low_confidence_subtopics": low_confidence_tags,
        "coverage_score": min(1.0, len(topic_recs) / 20.0) * avg_confidence,
    }


def self_audit(fact_id: str = None, topic: str = None, actor: str = "agent") -> dict:
    """Self-audit: evaluate own knowledge quality, identify biases, improve future reasoning."""
    _append_ledger({
        "id": f"{int(time.time()*1000):x}{os.urandom(2).hex()}",
        "ts": _now(),
        "actor": actor,
        "action": "self_audit",
        "topic": topic or "general",
        "tags": ["metacognitive", "self_audit"],
        "priority": "normal",
        "content": f"Self-audit initiated for {fact_id or topic or 'general knowledge'}",
        "audit_target": fact_id,
    })
    
    audit_results = {}
    
    if fact_id:
        recs = _load_ledger()
        target_rec = next((r for r in _load_ledger() if r.get("id") == fact_id), None)
        if not target_rec:
            return {"error": f"Fact {fact_id} not found"}
        
        # Audit single fact
        issues = []
        conf = target_rec.get("confidence")
        if conf is None:
            issues.append("Missing confidence score")
        elif conf < 0.5:
            issues.append(f"Low confidence: {conf}")
        # The original grounded record is stamped directly by set_epistemic_status,
        # so self_audit reads the authoritative current value here.
        eff_status = target_rec.get("epistemic_status")

        if eff_status is None:
            issues.append("Missing epistemic status")
        if target_rec.get("source") is None:
            issues.append("Missing source attribution")
        if target_rec.get("valid_to") and target_rec.get("valid_to") < _now():
            issues.append("Fact has expired validity")
        
        audit_results = {
            "fact_id": fact_id,
            "content_preview": target_rec.get("content", "")[:200],
            "confidence": target_rec.get("confidence"),
            "epistemic_status": eff_status,
            "source": target_rec.get("source"),
            "issues_found": issues,
            "recommendations": [
                "Add confidence score" if target_rec.get("confidence") is None else None,
                "Set epistemic status" if target_rec.get("epistemic_status") is None else None,
                "Add source attribution" if target_rec.get("source") is None else None,
                "Review expired fact" if target_rec.get("valid_to") and target_rec.get("valid_to") < _now() else None,
            ]
        }
    elif topic:
        # Audit topic coverage
        gap_analysis = detect_knowledge_gaps(topic)
        audit_results = {
            "topic": topic,
            "gap_analysis": gap_analysis,
            "recommendations": [
                f"Add memories for: {', '.join(gap_analysis['low_confidence_subtopics'])}" if gap_analysis.get('low_confidence_subtopics') else None,
                "Increase overall confidence" if gap_analysis.get('avg_confidence', 1) < 0.5 else None,
                "Add more memories for better coverage" if gap_analysis.get('total_memories', 0) < 5 else None,
            ]
        }
    else:
        # General audit
        recs = _load_ledger()
        remember_recs = [r for r in recs if r.get("action") == "remember" and SUPERSEDED not in r.get("content", "")]
        
        missing_confidence = sum(1 for r in remember_recs if r.get("confidence") is None)
        missing_status = sum(1 for r in remember_recs if r.get("epistemic_status") is None)
        missing_source = sum(1 for r in remember_recs if r.get("source") is None)
        expired = sum(1 for r in remember_recs if r.get("valid_to") and r.get("valid_to") < _now())
        
        audit_results = {
            "total_facts": len(remember_recs),
            "missing_confidence": missing_confidence,
            "missing_epistemic_status": missing_status,
            "missing_source": missing_source,
            "expired_facts": expired,
            "overall_health": "good" if (missing_confidence + missing_status + missing_source) / max(1, len(remember_recs)) < 0.3 else "needs_attention",
        }
    
    return audit_results


# =============================================================================
# STEP 7.4 — Memory / Simulation Contamination Controls (blocking gate)
# -----------------------------------------------------------------------------
# Requirements enforced here:
#   * Hard separation: simulated content lives in SIMULATED_LEDGER only — it is
#     NEVER written to the grounded LEDGER nor added to the vector/BM25 indexes.
#   * Immutable origin tags: grounded facts carry origin=="grounded" and simulated
#     facts carry origin=="simulated"; neither can be silently changed or promoted
#     without an explicit, gated action.
#   * Distinct write path for simulation: remember_simulated() only.
#   * Promotion rules: simulated -> grounded only via explicit external
#     confirmation OR a real-world prediction-error resolution.
#   * Decay / quarantine: simulated facts carry a TTL and are quarantined when stale.
#   * Periodic provenance audit: find any high-confidence memory whose ultimate
#     provenance is simulation.
#   * Epistemic veto: refuse plans resting primarily on unvalidated simulated beliefs.
# =============================================================================

def _load_simulated_ledger() -> list[dict]:
    if not os.path.exists(SIMULATED_LEDGER):
        return []
    out = []
    with open(SIMULATED_LEDGER, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def _append_simulated_ledger(rec: dict) -> None:
    _validate_partition_tags(rec)
    os.makedirs(STORE_DIR, exist_ok=True)
    with open(SIMULATED_LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _sim_expiry(ts: str, ttl_days: int = SIM_TTL_DAYS) -> str:
    try:
        dt = datetime.fromisoformat(ts)
    except Exception:
        return ts
    return (dt + timedelta(days=ttl_days)).isoformat()


def remember_simulated(topic: str, content: str, tags: list[str] | None = None,
                       priority: str = "normal", actor: str = "agent",
                       confidence: float | None = None, source: str | None = None,
                       scenario: str | None = None, sim_type: str = "imagination",
                       ttl_days: int = SIM_TTL_DAYS) -> dict:
    """Write SIMULATED / imagined content into the SEPARATE simulated partition.

    Guarantees (Step 7.4):
      - distinct write path (never touches grounded LEDGER or vector/BM25 indexes)
      - immutable origin tag 'simulated' + epistemic_status 'imagined'
      - TTL / decay window via valid_to
    """
    now = _now()
    detected_sim = _detect_only(content)
    if detected_sim:
        print(
            f"Warning: {len(detected_sim)} possible secret(s) detected; "
            "simulated text left unmodified",
            file=sys.stderr,
        )
    cleaned = content
    rec = {
        "id": f"{int(time.time()*1000):x}{os.urandom(2).hex()}",
        "ts": now,
        "actor": actor,
        "action": "simulate",
        "store": "simulated",          # distinct partition marker
        "origin": "simulated",          # immutable; never changed
        "epistemic_status": "imagined", # immutable for simulated content
        "topic": topic,
        "tags": tags or [],
        "priority": priority,
        "content": cleaned,
        "valid_from": now,
        "valid_to": _sim_expiry(now, ttl_days),
        "ttl_days": ttl_days,
        "confidence": confidence,
        "source": source,
        "scenario": scenario,
        "sim_type": sim_type,
        "promoted_to": None,           # immutable link once promoted
        "quarantined": False,
        "secrets_detected": detected_sim or None,
    }
    _append_simulated_ledger(rec)
    return rec


def list_simulated(active_only: bool = True, actor: str | None = None) -> dict:
    recs = _load_simulated_ledger()
    quarantined_ids = {e.get("sim_id") for e in recs if e.get("action") == "quarantine"}
    promoted_ids = {e.get("sim_id") for e in recs if e.get("action") == "promote"}
    out = []
    for r in recs:
        if r.get("action") != "simulate":
            continue
        if active_only and (r["id"] in quarantined_ids or r["id"] in promoted_ids or
                            (r.get("valid_to") and r.get("valid_to") < _now())):
            continue
        out.append(r)
    return {"simulated": out, "count": len(out)}


def promote_simulated_to_grounded(sim_id: str, confirmation: str | None = None,
                                  resolved_via_prediction_error: bool = False,
                                  resolution_note: str = "", actor: str = "agent",
                                  prediction_error_evidence: dict | None = None) -> dict:
    """Promote a simulated fact into grounded memory ONLY via an explicit gate.

    Gate (Step 7.4): requires a non-empty external `confirmation`, OR
    `resolved_via_prediction_error=True` with a resolution note AND attestation.
    The attestation is either a registered `PREDICTION_ERROR_VERIFIER` returning
    True, or a structured `prediction_error_evidence` payload containing at least
    `prediction_ref` (links to a recorded prediction) and `observed_outcome`
    (the real-world result). A bare boolean + free-text note is no longer enough.
    The simulated record is never mutated in place; a NEW grounded record is created
    and the simulated record is marked promoted_to (immutable link).
    """
    recs = _load_simulated_ledger()
    sim = next((r for r in recs if r.get("id") == sim_id and r.get("action") == "simulate"), None)
    if not sim:
        raise ValueError(f"Simulated fact {sim_id} not found")
    if sim.get("promoted_to"):
        raise ValueError(f"Simulated fact {sim_id} already promoted to {sim.get('promoted_to')}")
    if sim.get("quarantined"):
        raise ValueError(f"Simulated fact {sim_id} is quarantined; cannot promote")

    if resolved_via_prediction_error:
        # Strengthened evidence path: no longer accepts a boolean + note alone.
        note = str(resolution_note).strip()
        if not note:
            raise PermissionError(
                "Promotion via prediction-error resolution requires a non-empty "
                "resolution_note describing how the real world resolved.")
        if PREDICTION_ERROR_VERIFIER is not None:
            ok = False
            try:
                ok = bool(PREDICTION_ERROR_VERIFIER(sim_id, note, prediction_error_evidence))
            except Exception as e:
                raise PermissionError(
                    f"Prediction-error verifier rejected promotion: {e}")
            if not ok:
                raise PermissionError(
                    "Promotion blocked: external PREDICTION_ERROR_VERIFIER attestation "
                    "did not confirm a real prediction-error resolution.")
            evidence_hash = hashlib.sha256(
                json.dumps(prediction_error_evidence, sort_keys=True,
                           ensure_ascii=False).encode("utf-8")).hexdigest()
        else:
            # No external verifier registered: the prediction-error path is no longer
            # honor-system. It MUST be anchored to a real, previously-recorded prior
            # prediction that resolved IN FAVOR with a matching observed fact. Free-text
            # self-attestation is rejected; use PREDICTION_ERROR_VERIFIER for external
            # signed/attested confirmation instead.
            ev = prediction_error_evidence
            if not isinstance(ev, dict):
                raise PermissionError(
                    "Promotion via prediction-error resolution requires structured "
                    f"evidence linking to a recorded prior prediction (keys "
                    f"{_PREDICTION_ERROR_EVIDENCE_REQUIRED}).")
            ref = str(ev.get("prediction_ref", "")).strip()
            observed = str(ev.get("observed_outcome", "")).strip()
            if not ref or not observed:
                raise PermissionError(
                    "Promotion via prediction-error resolution requires "
                    f"{_PREDICTION_ERROR_EVIDENCE_REQUIRED}, both non-empty; either "
                    "register a PREDICTION_ERROR_VERIFIER for external attestation.")
            resolutions = [r for r in _load_predictions_ledger()
                           if r.get("prediction_id") == ref and r.get("action") == "resolve"]
            if not resolutions:
                raise PermissionError(
                    f"Promotion blocked: prediction_ref {ref} is not a recorded prior "
                    "prediction. The prediction-error gate requires a real, previously "
                    "recorded prediction that resolved in favor (or a registered "
                    "PREDICTION_ERROR_VERIFIER for external signed attestation).")
            latest = resolutions[-1]
            if latest.get("resolved_in_favor") is not True:
                raise PermissionError(
                    f"Promotion blocked: cited prediction {ref} did not resolve in favor "
                    "of the simulated belief; that is a prediction error, not a confirmation.")
            recorded_observed = str(latest.get("observed_outcome", "")).strip()
            if observed and recorded_observed and observed != recorded_observed:
                raise PermissionError(
                    f"Promotion blocked: observed_outcome {observed!r} does not match the "
                    f"recorded resolution {recorded_observed!r} for prediction {ref}.")
            ev = dict(ev)
            ev["_ledger_attested"] = True
            evidence_hash = hashlib.sha256(
                json.dumps(ev, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        gate_ok = True
    else:
        gate_ok = bool(confirmation and str(confirmation).strip())
        evidence_hash = None

    if not gate_ok:
        raise PermissionError(
            "Promotion blocked: requires explicit external confirmation OR "
            "real-world prediction-error resolution (resolution_note + attestation).")

    grounded = remember(
        topic=sim.get("topic"),
        content=sim.get("content"),
        tags=sim.get("tags", []),
        priority=sim.get("priority", "normal"),
        actor=actor,
        confidence=sim.get("confidence"),
        epistemic_status="observed",
        source=f"promoted:{sim_id}",
        scrub_secrets=True,
    )
    _append_simulated_ledger({
        "id": f"{int(time.time()*1000):x}{os.urandom(2).hex()}",
        "ts": _now(),
        "actor": actor,
        "action": "promote",
        "sim_id": sim_id,
        "promoted_to": grounded["id"],
        "confirmation": (confirmation or "")[:200],
        "resolution_note": resolution_note[:300],
        "resolved_via_prediction_error": bool(resolved_via_prediction_error),
        "prediction_error_evidence_hash": evidence_hash,
        "prediction_error_evidence": (prediction_error_evidence if resolved_via_prediction_error else None),
    })
    return {"promoted": True, "sim_id": sim_id, "grounded_id": grounded["id"],
            "evidence_hash": evidence_hash,
            "note": "Simulated content promoted to grounded memory via explicit gate."}


def quarantine_expired_simulated(actor: str = "agent") -> dict:
    """Decay / quarantine simulated content past its TTL (Step 7.4)."""
    recs = _load_simulated_ledger()
    now = _now()
    already = {e.get("sim_id") for e in recs if e.get("action") == "quarantine"}
    quarantined_ids = []
    for r in recs:
        if r.get("action") != "simulate":
            continue
        if r["id"] in already or r.get("promoted_to"):
            continue
        if r.get("valid_to") and r.get("valid_to") < now:
            _append_simulated_ledger({
                "id": f"{int(time.time()*1000):x}{os.urandom(2).hex()}",
                "ts": now,
                "actor": actor,
                "action": "quarantine",
                "sim_id": r.get("id"),
                "reason": "TTL expired",
            })
            quarantined_ids.append(r.get("id"))
    return {"quarantined": quarantined_ids, "count": len(quarantined_ids)}


def audit_contamination(actor: str = "agent") -> dict:
    """Periodic audit: find high-confidence memories whose provenance is simulation."""
    grounded = [r for r in _load_ledger()
                if r.get("action") == "remember" and SUPERSEDED not in r.get("content", "")]
    simulated = [r for r in _load_simulated_ledger() if r.get("action") == "simulate"]

    # Violation 1: any grounded fact whose origin is not 'grounded'
    bad_origin = [r["id"] for r in grounded if r.get("origin") not in (None, "grounded")]

    # Violation 2: any simulated record still sitting in the grounded vector index
    # (should be 0 because simulated content is never indexed)
    sim_in_grounded = []
    try:
        vm = _load_vector_meta()
        vm_ids = {m.get("id") for m in vm}
        sim_in_grounded = [r["id"] for r in simulated if r["id"] in vm_ids]
    except Exception:
        sim_in_grounded = []

    # Violation 3 (Issue #4): any simulated record present in the BM25 corpus.
    # The vector check alone is insufficient; BM25 is a second retrieval surface
    # that must also stay free of simulated IDs.
    sim_in_bm25 = []
    try:
        bm25_ids = {c.get("id") for c in _load_bm25_corpus()}
        sim_in_bm25 = [r["id"] for r in simulated if r["id"] in bm25_ids]
    except Exception:
        sim_in_bm25 = []

    # Validated promotions: grounded facts derived from simulation via an explicit gate
    validated_simulation_derived = [
        {"grounded_id": r["id"], "source": r.get("source")}
        for r in grounded if isinstance(r.get("source"), str) and r.get("source", "").startswith("promoted:")
    ]
    # A promotion writes a separate `promote` ledger entry (the simulate entry is
    # never mutated), so count from those entries rather than a field that stays None.
    promote_entries = [r for r in _load_simulated_ledger() if r.get("action") == "promote"]
    promoted_ids = {p.get("promoted_to") for p in promote_entries if p.get("promoted_to")}

    total_grounded = len(grounded)
    total_sim = len(simulated)
    violations = len(bad_origin) + len(sim_in_grounded) + len(sim_in_bm25)
    contamination_rate = round(violations / total_grounded, 4) if total_grounded else 0.0

    return {
        "grounded_facts": total_grounded,
        "simulated_facts": total_sim,
        "validated_simulation_derived": validated_simulation_derived,
        "promoted_count": len(promoted_ids),
        "violations_origin_not_grounded": bad_origin,
        "violations_simulated_in_grounded_index": sim_in_grounded,
        "violations_simulated_in_bm25_corpus": sim_in_bm25,
        "contamination_rate": contamination_rate,
        "status": "CLEAN" if (contamination_rate == 0.0 and not bad_origin
                             and not sim_in_grounded and not sim_in_bm25) else "CONTAMINATED",
        "recommendation": "No action needed." if contamination_rate == 0.0 else
                          "Investigate grounded facts with simulated origin / indexed simulated content.",
    }


def epistemic_veto(fact_ids: list[str], actor: str = "agent") -> dict:
    """Epistemic-layer veto: refuse plans resting primarily on unvalidated simulated beliefs.

    Any relied-upon fact that is simulated, or grounded but unvalidated
    (imagined/hypothesis/agent_generated without a promotion source), triggers a veto.
    """
    grounded = {r["id"]: r for r in _load_ledger()
                if r.get("action") == "remember" and SUPERSEDED not in r.get("content", "")}
    simulated = {r["id"]: r for r in _load_simulated_ledger() if r.get("action") == "simulate"}
    # The original grounded record is stamped directly by set_epistemic_status, so the
    # veto reads the authoritative current status from the record.

    offenders = []
    for fid in fact_ids:
        if fid in simulated:
            offenders.append({"fact_id": fid, "reason": "relies on unvalidated simulated content"})
            continue
        rec = grounded.get(fid)
        if not rec:
            continue
        status = rec.get("epistemic_status")
        src = rec.get("source") or ""
        if status in ("imagined", "hypothesis", "agent_generated") and not src.startswith("promoted:"):
            offenders.append({"fact_id": fid, "reason": f"unvalidated epistemic status '{status}'"})

    veto = len(offenders) > 0
    return {
        "veto": veto,
        "offenders": offenders,
        "message": ("VETO: plan relies on unvalidated simulated/imagined beliefs."
                    if veto else "OK: plan rests on validated grounded memory."),
    }


def require_epistemic_clearance(fact_ids: list[str], actor: str = "agent") -> dict:
    """Enforced counterpart to epistemic_veto.

    The advisory `epistemic_veto` only reports. This function RAISES PermissionError
    when a plan would rest on unvalidated simulated/imagined beliefs, so the planning
    path can invoke it before executing rather than merely being told about a veto.
    Returns the clearance dict on success.
    """
    result = epistemic_veto(fact_ids, actor=actor)
    if result.get("veto"):
        raise PermissionError(
            "Epistemic clearance denied: " + result.get("message", "") +
            " Offenders: " + json.dumps(result.get("offenders", []), ensure_ascii=False))
    return result


# Planning-path hook: register a callable(predicate_fact_ids) -> None that is invoked
# automatically before any plan executes. Defaults to require_epistemic_clearance so
# the veto is enforced by default rather than only when called explicitly.
PLAN_EXECUTION_GUARD = require_epistemic_clearance


def set_plan_execution_guard(fn) -> None:
    """Override the default plan-execution guard (e.g. to add logging or relax)."""
    global PLAN_EXECUTION_GUARD
    PLAN_EXECUTION_GUARD = fn


def run_plan_execution_guard(fact_ids: list[str], actor: str = "agent") -> dict:
    """Invoke the active plan-execution guard. Planning paths should call this."""
    return PLAN_EXECUTION_GUARD(fact_ids, actor=actor)


# =============================================================================
# Active World-Model Simulation & Predictive Processing Engine (Step 2)
# =============================================================================

class _SafeConditionEval:
    """Evaluate a boolean condition expression against a variable namespace.

    Replaces ``eval()`` for world-model transition rules. Only a safe subset of
    Python expressions is permitted (names, constants, boolean/logical/
    comparison/arithmetic operators); any callable, attribute access, subscript,
    or other node raises ``ValueError``, so rule conditions cannot execute
    arbitrary code.
    """

    _ALLOWED = (
        _ast.Expression, _ast.BoolOp, _ast.UnaryOp, _ast.BinOp, _ast.Compare,
        _ast.Name, _ast.Load, _ast.Constant, _ast.And, _ast.Or, _ast.Not,
        _ast.USub, _ast.UAdd, _ast.Add, _ast.Sub, _ast.Mult, _ast.Div,
        _ast.Mod, _ast.FloorDiv, _ast.Pow, _ast.Eq, _ast.NotEq, _ast.Lt,
        _ast.LtE, _ast.Gt, _ast.GtE, _ast.In, _ast.NotIn,
    )

    def __init__(self, namespace: dict):
        self.ns = namespace

    def visit(self, node):
        method = getattr(self, "visit_" + type(node).__name__, None)
        if method is None:
            raise ValueError(f"Unsupported expression node: {type(node).__name__}")
        return method(node)

    def visit_Expression(self, node):
        return self.visit(node.body)

    def visit_Constant(self, node):
        return node.value

    def visit_Name(self, node):
        if node.id in self.ns:
            return self.ns[node.id]
        raise ValueError(f"Unknown variable in rule condition: {node.id}")

    def visit_BoolOp(self, node):
        if isinstance(node.op, _ast.And):
            return all(self.visit(v) for v in node.values)
        return any(self.visit(v) for v in node.values)

    def visit_UnaryOp(self, node):
        if isinstance(node.op, _ast.Not):
            return not self.visit(node.operand)
        if isinstance(node.op, _ast.USub):
            return -self.visit(node.operand)
        return +self.visit(node.operand)

    def visit_BinOp(self, node):
        left = self.visit(node.left)
        right = self.visit(node.right)
        op = node.op
        if isinstance(op, _ast.Add):
            return left + right
        if isinstance(op, _ast.Sub):
            return left - right
        if isinstance(op, _ast.Mult):
            return left * right
        if isinstance(op, _ast.Div):
            return left / right
        if isinstance(op, _ast.Mod):
            return left % right
        if isinstance(op, _ast.FloorDiv):
            return left // right
        if isinstance(op, _ast.Pow):
            return left ** right
        raise ValueError("Unsupported binary operator")

    def visit_Compare(self, node):
        left = self.visit(node.left)
        for op, comp in zip(node.ops, node.comparators):
            right = self.visit(comp)
            if not self._compare(op, left, right):
                return False
            left = right
        return True

    @staticmethod
    def _compare(op, left, right):
        if isinstance(op, _ast.Eq):
            return left == right
        if isinstance(op, _ast.NotEq):
            return left != right
        if isinstance(op, _ast.Lt):
            return left < right
        if isinstance(op, _ast.LtE):
            return left <= right
        if isinstance(op, _ast.Gt):
            return left > right
        if isinstance(op, _ast.GtE):
            return left >= right
        if isinstance(op, _ast.In):
            return left in right
        if isinstance(op, _ast.NotIn):
            return left not in right
        raise ValueError("Unsupported comparison operator")


def safe_eval_condition(expr: str, namespace: dict) -> bool:
    """Safely evaluate a boolean rule condition; returns False on any error."""
    try:
        tree = _ast.parse(expr, mode="eval")
    except SyntaxError:
        return False
    for child in _ast.walk(tree):
        if not isinstance(child, _SafeConditionEval._ALLOWED):
            return False
    try:
        return bool(_SafeConditionEval(namespace).visit(tree.body))
    except Exception:
        return False


class WorldModel:
    """Active world model for predictive processing and simulation."""
    
    def __init__(self):
        self.state_variables = {}
        self.transition_rules = []
        self.prediction_history = []
        self.interventions = []
        
    def add_variable(self, name: str, initial_value: float, dynamics: str = "constant") -> None:
        """Add a state variable to the world model."""
        self.state_variables[name] = {
            "value": initial_value,
            "dynamics": dynamics,
            "history": [initial_value],
        }
    
    def add_transition_rule(self, condition: str, effect: dict, probability: float = 1.0) -> None:
        """Add a state transition rule."""
        self.transition_rules.append({
            "condition": condition,
            "effect": effect,
            "probability": probability,
        })
    
    def simulate_step(self, steps: int = 1) -> list[dict]:
        """Run simulation steps and return state trajectory.

        Each recorded state is the state AFTER that step's transition rules are
        applied, so ``trajectory[-1]`` is the state after all ``steps``
        transitions. Recording before the rules fire would make every report
        under-count by one step.
        """
        trajectory = []
        for _ in range(steps):
            # Apply transition rules
            for rule in self.transition_rules:
                # Safe condition evaluation (no eval()); AST-restricted to a
                # boolean/arithmetic subset over the current state variables.
                condition_met = safe_eval_condition(
                    rule["condition"],
                    {**{k: v["value"] for k, v in self.state_variables.items()}},
                )

                probability = float(rule.get("probability", 1.0))
                if probability >= 1.0:
                    fires = condition_met
                elif probability <= 0.0:
                    fires = False
                else:
                    fires = condition_met and random.random() < probability

                if fires:
                    for var, change in rule["effect"].items():
                        numeric_change = isinstance(change, (int, float)) and not isinstance(change, bool)
                        if var not in self.state_variables:
                            seed = 0 if numeric_change else change
                            self.state_variables[var] = {
                                "value": seed,
                                "dynamics": "derived",
                                "history": [seed],
                            }
                        current = self.state_variables[var]["value"]
                        if numeric_change and isinstance(current, (int, float)) and not isinstance(current, bool):
                            new_value = current + change
                        else:
                            new_value = change
                        self.state_variables[var]["value"] = new_value
                        self.state_variables[var]["history"].append(new_value)

            state = {name: var["value"] for name, var in self.state_variables.items()}
            trajectory.append(state.copy())

        return trajectory

    def do(self, variable, value, label=None) -> dict:
        """Intervention (Pearl-style ``do``): set a variable, overriding its natural
        dynamics, and record the intervention for auditability. Distinct from the
        predictive simulation path used by :meth:`simulate_step`/:meth:`predict`."""
        if variable not in self.state_variables:
            raise KeyError(f"unknown variable: {variable}")
        self.state_variables[variable]["value"] = value
        rec = {"variable": variable, "value": value, "label": label,
               "ts": datetime.now().isoformat()}
        self.interventions.append(rec)
        return rec

    def counterfactual(self, condition, interventions=None, steps=1) -> dict:
        """What would have happened had we intervened?

        Applies ``interventions`` to a *copy* of the current state, simulates
        ``steps`` forward, and reports whether ``condition`` holds at the end.
        The live world model is snapshot-restored, so counterfactual queries do
        not mutate the actual state (unlike predictive :meth:`predict`)."""
        snapshot = copy.deepcopy(self.state_variables)
        try:
            for var, val in (interventions or {}).items():
                if var in self.state_variables:
                    self.state_variables[var]["value"] = val
            trajectory = self.simulate_step(steps)
            final = trajectory[-1] if trajectory else {}
            holds = bool(safe_eval_condition(condition, dict(final)))
            return {
                "condition": condition,
                "interventions": interventions or {},
                "trajectory": trajectory,
                "condition_holds": holds,
            }
        finally:
            self.state_variables = snapshot

    def predict(self, query: str, horizon: int = 5) -> dict:
        """Answer predictive queries about future states.

        Non-mutating: the simulation runs against a deep snapshot and the live
        state is restored before returning, so asking a question never advances
        the real world model (same contract as :meth:`counterfactual`).
        """
        snapshot = copy.deepcopy(self.state_variables)
        try:
            trajectory = self.simulate_step(horizon)

            # Simple query evaluation
            if "will" in query.lower() and "exceed" in query.lower():
                # Extract variable and threshold
                import re
                match = re.search(r"(\w+)\s+exceed\s+([\d.]+)", query, re.IGNORECASE)
                if match:
                    var, threshold = match.group(1), float(match.group(2))
                    final_val = trajectory[-1].get(var, 0) if trajectory else 0
                    return {
                        "query": query,
                        "prediction": final_val > threshold,
                        "final_value": final_val,
                        "threshold": threshold,
                        "trajectory": [t.get(var, 0) for t in trajectory],
                    }

            return {
                "query": query,
                "trajectory": trajectory,
                "final_state": trajectory[-1] if trajectory else {},
            }
        finally:
            self.state_variables = snapshot
    
    def to_dict(self) -> dict:
        """Serialize world model for persistence."""
        return {
            "state_variables": self.state_variables,
            "transition_rules": self.transition_rules,
            "interventions": self.interventions,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'WorldModel':
        """Deserialize world model from persistence."""
        wm = cls()
        wm.state_variables = data.get("state_variables", {})
        wm.transition_rules = data.get("transition_rules", [])
        wm.interventions = data.get("interventions", [])
        return wm


class SelfModel:
    """Structured self-model store with continuity metrics (Phase 8.1).

    Tracks a versioned history of agent self-descriptions (capabilities, values,
    identity) and quantifies how continuous / stable that self-model is over time.
    A dropping continuity score flags identity drift worth surfacing to the agent.
    """

    def __init__(self):
        self.snapshots = []

    def create(self, capabilities, values, identity=""):
        snap = {
            "capabilities": list(capabilities or []),
            "values": list(values or []),
            "identity": identity or "",
            "created": datetime.now().isoformat(),
        }
        self.snapshots.append(snap)
        return snap

    def get(self, index=-1):
        return self.snapshots[index] if self.snapshots else None

    def continuity(self) -> dict:
        """Mean Jaccard overlap of capability+value token sets across consecutive
        snapshots. Single snapshot => perfectly continuous (1.0). Drift flagged
        when the mean score drops below 0.5."""
        if len(self.snapshots) < 2:
            return {"score": 1.0, "snapshots": len(self.snapshots),
                    "drift": False, "pairwise": [], "note": "insufficient history"}
        pairwise = []
        for a, b in zip(self.snapshots, self.snapshots[1:]):
            sa = set(a.get("capabilities", [])) | set(a.get("values", []))
            sb = set(b.get("capabilities", [])) | set(b.get("values", []))
            union = sa | sb
            jac = (len(sa & sb) / len(union)) if union else 1.0
            pairwise.append(round(jac, 4))
        score = round(sum(pairwise) / len(pairwise), 4)
        return {"score": score, "snapshots": len(self.snapshots),
                "drift": score < 0.5, "pairwise": pairwise}

    def to_dict(self) -> dict:
        return {"snapshots": self.snapshots}

    @classmethod
    def from_dict(cls, data: dict) -> 'SelfModel':
        sm = cls()
        sm.snapshots = data.get("snapshots", [])
        return sm


WORLD_MODEL_FILE = os.path.join(STORE_DIR, "world_model.json")

def _load_world_model() -> dict:
    if not os.path.exists(WORLD_MODEL_FILE):
        return {"state_variables": {}, "transition_rules": []}
    try:
        with open(WORLD_MODEL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"state_variables": {}, "transition_rules": []}


def _save_world_model(data: dict) -> None:
    os.makedirs(STORE_DIR, exist_ok=True)
    with open(WORLD_MODEL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


_world_model = None

def _get_world_model() -> WorldModel:
    global _world_model
    if _world_model is None:
        data = _load_world_model()
        _world_model = WorldModel.from_dict(data)
    return _world_model


def _persist_world_model(wm: WorldModel) -> None:
    _save_world_model(wm.to_dict())


# --- Predictive-processing feedback loop (Step 2 / Risk: thin coupling) ---------
# Simulated content may emit predictions; when those predictions are resolved
# against reality we record the outcome and use it as attestation for promotion.
PREDICTIONS_LEDGER = os.path.join(STORE_DIR, "predictions_ledger.jsonl")


def _append_predictions_ledger(rec: dict) -> None:
    os.makedirs(STORE_DIR, exist_ok=True)
    with open(PREDICTIONS_LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _load_predictions_ledger() -> list[dict]:
    if not os.path.exists(PREDICTIONS_LEDGER):
        return []
    out = []
    with open(PREDICTIONS_LEDGER, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def _lookup_prediction(prediction_ref: str) -> dict | None:
    for r in _load_predictions_ledger():
        if r.get("prediction_id") == prediction_ref:
            return r
    return None


def world_model_record_prediction(query: str, prediction: str | None = None,
                                  horizon: int = 10, actor: str = "agent") -> dict:
    """Record a prediction emitted (e.g. by a simulation) for later reality-checking."""
    rec = {
        "prediction_id": f"{int(time.time()*1000):x}{os.urandom(2).hex()}",
        "ts": _now(),
        "actor": actor,
        "action": "predict",
        "query": query,
        "horizon": horizon,
        "prediction": prediction,
        "status": "open",
        "resolved_in_favor": None,
        "observed_outcome": None,
    }
    _append_predictions_ledger(rec)
    return rec


def world_model_resolve_prediction(prediction_id: str, observed_outcome: str,
                                   resolved_in_favor: bool, actor: str = "agent") -> dict:
    """Resolve a recorded prediction against reality.

    A prediction that resolves in favor of the simulated belief is the precise
    evidence required to promote that belief to grounded memory.
    """
    pred = _lookup_prediction(prediction_id)
    if not pred:
        raise ValueError(f"Prediction {prediction_id} not found")
    rec = {
        "prediction_id": prediction_id,
        "ts": _now(),
        "actor": actor,
        "action": "resolve",
        "observed_outcome": str(observed_outcome),
        "resolved_in_favor": bool(resolved_in_favor),
    }
    _append_predictions_ledger(rec)
    # Reflect the outcome in epistemic confidence of the originating world model.
    try:
        wm = _get_world_model()
        wm.prediction_history.append({
            "prediction_id": prediction_id,
            "resolved_in_favor": bool(resolved_in_favor),
            "observed_outcome": str(observed_outcome),
            "ts": _now(),
        })
        _persist_world_model(wm)
    except Exception:
        pass
    return {"prediction_id": prediction_id, "resolved_in_favor": bool(resolved_in_favor),
            "observed_outcome": str(observed_outcome)}


def world_model_prediction_accuracy() -> dict:
    """Report predictive accuracy for self-audit / epistemic calibration."""
    outcomes = [r for r in _load_predictions_ledger() if r.get("action") == "resolve"]
    total = len(outcomes)
    favorable = sum(1 for r in outcomes if r.get("resolved_in_favor"))
    return {
        "total_resolved": total,
        "resolved_in_favor": favorable,
        "accuracy": round(favorable / total, 4) if total else 0.0,
    }


def world_model_add_variable(name: str, initial_value: float, dynamics: str = "constant", actor: str = "agent") -> dict:
    """Add a state variable to the world model."""
    wm = _get_world_model()
    wm.add_variable(name, initial_value, dynamics)
    _persist_world_model(wm)
    return {"variable": name, "initial_value": initial_value, "dynamics": dynamics}


def world_model_add_rule(condition: str, effect: dict, probability: float = 1.0, actor: str = "agent") -> dict:
    """Add a transition rule to the world model."""
    wm = _get_world_model()
    wm.add_transition_rule(condition, effect, probability)
    _persist_world_model(wm)
    return {"condition": condition, "effect": effect, "probability": probability}


def world_model_simulate(steps: int = 10, actor: str = "agent") -> dict:
    """Run world model simulation."""
    wm = _get_world_model()
    trajectory = wm.simulate_step(steps)
    _persist_world_model(wm)
    return {
        "steps": steps,
        "trajectory": trajectory,
        "final_state": trajectory[-1] if trajectory else {},
    }


def world_model_predict(query: str, horizon: int = 10, actor: str = "agent") -> dict:
    """Make predictions using the world model."""
    wm = _get_world_model()
    result = wm.predict(query, horizon)
    _persist_world_model(wm)
    return result


def world_model_get_state(actor: str = "agent") -> dict:
    """Get current world model state."""
    wm = _get_world_model()
    return {name: var["value"] for name, var in wm.state_variables.items()}


def world_model_reset(actor: str = "agent") -> dict:
    """Reset the world model."""
    global _world_model
    _world_model = WorldModel()
    _persist_world_model(_world_model)
    return {"status": "World model reset"}


# =============================================================================
# Affective/Value Layer (Step 2: Affective/Value Layer)
# =============================================================================

class AffectiveState:
    """Represents the agent's affective/value state."""
    
    def __init__(self):
        self.values = {}  # Core values and their weights
        self.emotions = {}  # Current emotional state
        self.goals = {}  # Active goals with priorities
        self.preferences = {}  # Learned preferences
    
    def set_value(self, name: str, weight: float, description: str = "") -> None:
        """Set a core value."""
        self.values[name] = {"weight": weight, "description": description}
    
    def set_emotion(self, name: str, intensity: float, cause: str = "") -> None:
        """Set emotional state."""
        self.emotions[name] = {"intensity": max(-1.0, min(1.0, intensity)), "cause": cause, "ts": _now()}
    
    def add_goal(self, name: str, priority: float, target_state: dict = None) -> None:
        """Add or update a goal."""
        self.goals[name] = {"priority": priority, "target_state": target_state or {}, "ts": _now()}
    
    def update_preference(self, context: str, preference: str, strength: float) -> None:
        """Update learned preference."""
        if context not in self.preferences:
            self.preferences[context] = {}
        self.preferences[context][preference] = strength
    
    def evaluate(self, situation: dict) -> dict:
        """Evaluate a situation against values and goals."""
        alignment = {}
        for name, val in self.values.items():
            # Simple alignment: does situation support this value?
            alignment[name] = val["weight"] * (1 if situation.get(name, False) else -0.5)
        
        goal_progress = {}
        for name, goal in self.goals.items():
            # Simple progress: how close is current state to target?
            target = goal.get("target_state", {})
            if target:
                matches = sum(1 for k, v in target.items() if situation.get(k) == v)
                total = len(target)
                goal_progress[name] = matches / max(1, total)
            else:
                goal_progress[name] = 0.5
        
        return {
            "value_alignment": alignment,
            "goal_progress": goal_progress,
            "dominant_emotion": max(self.emotions.items(), key=lambda x: abs(x[1]["intensity"]))[0] if self.emotions else "neutral",
        }
    
    def to_dict(self) -> dict:
        return {
            "values": self.values,
            "emotions": self.emotions,
            "goals": self.goals,
            "preferences": self.preferences,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'AffectiveState':
        state = cls()
        state.values = data.get("values", {})
        state.emotions = data.get("emotions", {})
        state.goals = data.get("goals", {})
        state.preferences = data.get("preferences", {})
        return state


AFFECTIVE_FILE = os.path.join(STORE_DIR, "affective_state.json")

def _load_affective() -> dict:
    if not os.path.exists(AFFECTIVE_FILE):
        return {"values": {}, "emotions": {}, "goals": {}, "preferences": {}}
    try:
        with open(AFFECTIVE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"values": {}, "emotions": {}, "goals": {}, "preferences": {}}


def _save_affective(data: dict) -> None:
    os.makedirs(STORE_DIR, exist_ok=True)
    with open(AFFECTIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


_affective_state = None
_affective_state_mtime = None

def _get_affective() -> AffectiveState:
    global _affective_state, _affective_state_mtime
    mtime = None
    try:
        if os.path.exists(AFFECTIVE_FILE):
            mtime = os.path.getmtime(AFFECTIVE_FILE)
    except Exception:
        mtime = None
    if _affective_state is None or mtime != _affective_state_mtime:
        data = _load_affective()
        _affective_state = AffectiveState.from_dict(data)
        _affective_state_mtime = mtime
    return _affective_state


def _persist_affective(state: AffectiveState) -> None:
    _save_affective(state.to_dict())


def affective_set_value(name: str, weight: float, description: str = "", actor: str = "agent") -> dict:
    """Set a core value."""
    state = _get_affective()
    state.set_value(name, weight, description)
    _persist_affective(state)
    return {"value": name, "weight": weight, "description": description}


def affective_set_emotion(name: str, intensity: float, cause: str = "", actor: str = "agent") -> dict:
    """Set emotional state."""
    state = _get_affective()
    state.set_emotion(name, intensity, cause)
    _persist_affective(state)
    return {"emotion": name, "intensity": intensity, "cause": cause}


def affective_add_goal(name: str, priority: float, target_state: dict = None, actor: str = "agent") -> dict:
    """Add or update a goal."""
    state = _get_affective()
    state.add_goal(name, priority, target_state)
    _persist_affective(state)
    return {"goal": name, "priority": priority, "target_state": target_state}


def affective_update_preference(context: str, preference: str, strength: float, actor: str = "agent") -> dict:
    """Update learned preference."""
    state = _get_affective()
    state.update_preference(context, preference, strength)
    _persist_affective(state)
    return {"context": context, "preference": preference, "strength": strength}


def affective_evaluate(situation: dict, actor: str = "agent") -> dict:
    """Evaluate a situation against values and goals."""
    state = _get_affective()
    return state.evaluate(situation)


def affective_get_state(actor: str = "agent") -> dict:
    """Get current affective state."""
    state = _get_affective()
    return state.to_dict()


# =============================================================================
# Procedural Memory (Step 2: Procedural Memory & Skill Learning)
# =============================================================================

class ProceduralMemory:
    """Procedural memory for skills, procedures, and how-to knowledge."""
    
    def __init__(self):
        self.skills = {}  # skill_name -> skill_data
        self.execution_history = []  # Track skill executions
    
    def add_skill(self, name: str, description: str, steps: list, preconditions: dict = None, 
                  effects: dict = None, category: str = "general") -> None:
        """Add a procedural skill."""
        self.skills[name] = {
            "description": description,
            "steps": steps,
            "preconditions": preconditions or {},
            "effects": effects or {},
            "category": category,
            "created_ts": _now(),
            "execution_count": 0,
            "success_rate": 1.0,
        }
    
    def get_skill(self, name: str) -> dict | None:
        """Get a skill by name."""
        return self.skills.get(name)
    
    def find_skills(self, category: str = None, matching_preconditions: dict = None) -> list[dict]:
        """Find skills matching criteria."""
        results = []
        for name, skill in self.skills.items():
            if category and skill["category"] != category:
                continue
            if matching_preconditions:
                # Check if skill preconditions match the current situation
                match = all(skill["preconditions"].get(k) == v for k, v in matching_preconditions.items())
                if not match:
                    continue
            results.append({"name": name, **skill})
        return results
    
    def execute_skill(self, name: str, context: dict = None) -> dict:
        """Execute a skill and record result."""
        skill = self.skills.get(name)
        if not skill:
            return {"error": f"Skill '{name}' not found"}
        
        # Check preconditions
        preconditions = skill.get("preconditions", {})
        if preconditions and context:
            for k, v in preconditions.items():
                if context.get(k) != v:
                    return {"error": f"Precondition failed: {k}={v} (got {context.get(k)})"}
        
        # Simulate execution
        success = True
        result = {"executed_steps": skill["steps"], "context": context or {}}
        
        # Apply effects
        for effect_key, effect_val in skill.get("effects", {}).items():
            result[effect_key] = effect_val
        
        # Update execution stats
        skill["execution_count"] += 1
        if success:
            skill["success_rate"] = (skill["success_rate"] * (skill["execution_count"] - 1) + 1) / skill["execution_count"]
        else:
            skill["success_rate"] = (skill["success_rate"] * (skill["execution_count"] - 1)) / skill["execution_count"]
        
        # Record execution
        self.execution_history.append({
            "skill": name,
            "ts": _now(),
            "context": context or {},
            "success": success,
            "result": result,
        })
        
        return result
    
    def learn_from_execution(self, name: str, success: bool, modified_steps: list = None, 
                             new_preconditions: dict = None, new_effects: dict = None) -> dict:
        """Learn from skill execution - update skill based on experience."""
        skill = self.skills.get(name)
        if not skill:
            return {"error": f"Skill '{name}' not found"}
        
        if modified_steps is not None:
            skill["steps"] = modified_steps
        if new_preconditions is not None:
            skill["preconditions"].update(new_preconditions)
        if new_effects is not None:
            skill["effects"].update(new_effects)
        
        return {"skill": name, "updated": True}
    
    def to_dict(self) -> dict:
        return {
            "skills": self.skills,
            "execution_history": self.execution_history[-1000:],  # Keep last 1000
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ProceduralMemory':
        pm = cls()
        pm.skills = data.get("skills", {})
        pm.execution_history = data.get("execution_history", [])
        return pm


PROCEDURAL_FILE = os.path.join(STORE_DIR, "procedural_memory.json")

def _load_procedural() -> dict:
    if not os.path.exists(PROCEDURAL_FILE):
        return {"skills": {}, "execution_history": []}
    try:
        with open(PROCEDURAL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"skills": {}, "execution_history": []}


def _save_procedural(data: dict) -> None:
    os.makedirs(STORE_DIR, exist_ok=True)
    with open(PROCEDURAL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


_procedural_memory = None

def _get_procedural() -> ProceduralMemory:
    global _procedural_memory
    if _procedural_memory is None:
        data = _load_procedural()
        _procedural_memory = ProceduralMemory.from_dict(data)
    return _procedural_memory


def _persist_procedural(pm: ProceduralMemory) -> None:
    _save_procedural(pm.to_dict())


def procedural_add_skill(name: str, description: str, steps: list, 
                         preconditions: dict = None, effects: dict = None, 
                         category: str = "general", actor: str = "agent") -> dict:
    """Add a procedural skill."""
    pm = _get_procedural()
    pm.add_skill(name, description, steps, preconditions, effects, category)
    _persist_procedural(pm)
    return {"skill": name, "description": description, "steps": steps}


def procedural_get_skill(name: str, actor: str = "agent") -> dict:
    """Get a procedural skill."""
    pm = _get_procedural()
    skill = pm.get_skill(name)
    if not skill:
        return {"error": f"Skill '{name}' not found"}
    return {"name": name, **skill}


def procedural_find_skills(category: str = None, preconditions: dict = None, actor: str = "agent") -> list[dict]:
    """Find skills matching criteria."""
    pm = _get_procedural()
    return pm.find_skills(category, preconditions)


def procedural_execute_skill(name: str, context: dict = None, actor: str = "agent") -> dict:
    """Execute a skill."""
    pm = _get_procedural()
    result = pm.execute_skill(name, context)
    _persist_procedural(pm)
    return result


def procedural_learn(name: str, success: bool, modified_steps: list = None,
                     new_preconditions: dict = None, new_effects: dict = None,
                     actor: str = "agent") -> dict:
    """Learn from skill execution."""
    pm = _get_procedural()
    result = pm.learn_from_execution(name, success, modified_steps, new_preconditions, new_effects)
    _persist_procedural(pm)
    return result


def procedural_list_skills(category: str = None, actor: str = "agent") -> list[dict]:
    """List all skills."""
    pm = _get_procedural()
    return pm.find_skills(category, None)


def rebuild_vectors() -> str:
    """Rebuild the vector index from all ledger entries."""
    if not VECTOR_AVAILABLE:
        return "Vector dependencies not installed"
    
    recs = _load_ledger()
    remember_recs = [r for r in recs if r.get("action") == "remember"
                     and SUPERSEDED not in r.get("content", "")]
    
    if not remember_recs:
        # Create empty index
        index = faiss.IndexFlatIP(EMBEDDING_DIM)
        faiss.write_index(index, VECTOR_INDEX)
        _save_vector_meta([])
        return "Vector index rebuilt (empty)"
    
    embedder = _get_embedder()
    index = faiss.IndexFlatIP(EMBEDDING_DIM)
    meta = []
    
    texts = []
    for rec in remember_recs:
        text = f"{rec['topic']}: {rec['content']}"
        if rec.get('tags'):
            text += " " + " ".join(rec['tags'])
        texts.append(text)
    
    # Batch encode
    embeddings = embedder.encode(texts, convert_to_numpy=True, batch_size=32, show_progress_bar=True)
    embeddings = _normalize(embeddings).astype(np.float32)
    index.add(embeddings)
    
    # Build metadata
    for i, rec in enumerate(remember_recs):
        meta.append({
            "id": rec["id"],
            "ts": rec["ts"],
            "topic": rec["topic"],
            "tags": rec["tags"],
            "priority": rec["priority"],
            "content_hash": hashlib.md5(rec["content"].encode()).hexdigest()[:16],
        })
    
    faiss.write_index(index, VECTOR_INDEX)
    _save_vector_meta(meta)
    
    return f"Vector index rebuilt with {len(remember_recs)} entries"


def recall_semantic(query: str, k: int = 5, topic: str | None = None,
                    tags: list[str] | None = None) -> list[dict]:
    """Semantic search using vector embeddings."""
    if not VECTOR_AVAILABLE:
        return [{"error": "Vector dependencies not installed"}]
    
    embedder = _get_embedder()
    index = _get_vector_index()
    meta = _load_vector_meta()
    
    if index.ntotal == 0:
        return []
    
    # Encode query
    query_embedding = embedder.encode([query], convert_to_numpy=True)[0]
    query_embedding = _normalize(query_embedding.reshape(1, -1)).astype(np.float32)
    
    # Search
    search_k = min(k * 3, index.ntotal)  # oversample for filtering
    scores, indices = index.search(query_embedding, search_k)
    
    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx == -1:
            continue
        m = meta[idx]
        
        # Apply filters
        if topic and topic.lower() not in m.get("topic", "").lower():
            continue
        if tags and not any(t in m.get("tags", []) for t in tags):
            continue
        
        # Load full content from ledger
        recs = _load_ledger()
        full_rec = next((r for r in recs if r.get("id") == m["id"]), None)
        
        if full_rec:
            results.append({
                "score": float(score),
                "id": m["id"],
                "ts": m["ts"],
                "topic": m["topic"],
                "tags": m["tags"],
                "priority": m["priority"],
                "content": full_rec.get("content", "")[:500],
            })
        
        if len(results) >= k:
            break
    
    return results


def recall_hybrid(query: str, k: int = 5, topic: str | None = None,
                  tags: list[str] | None = None, alpha: float = 0.5) -> list[dict]:
    """Hybrid search using both vector (semantic) and BM25 (keyword) search with RRF fusion.
    
    Args:
        query: Search query
        k: Number of results
        topic: Filter by topic
        tags: Filter by tags
        alpha: Weight for vector search (1-alpha for BM25). 0.5 = equal weight.
    
    Returns:
        List of results with combined scores.
    """
    if not VECTOR_AVAILABLE and not BM25_AVAILABLE:
        return [{"error": "No search dependencies installed"}]
    
    # Vector search
    vector_results = []
    if VECTOR_AVAILABLE:
        try:
            vector_results = recall_semantic(query, k * 3, topic, tags)
        except Exception:
            pass
    
    # BM25 search
    bm25_results = []
    if BM25_AVAILABLE:
        try:
            bm25 = _get_bm25_index()
            if bm25 is not None:
                corpus = _load_bm25_corpus()
                query_tokens = query.lower().split()
                scores = bm25.get_scores(query_tokens)
                
                # Get top candidates
                top_indices = np.argsort(scores)[::-1][:k * 3]
                
                for idx in top_indices:
                    if idx >= len(corpus):
                        continue
                    m = corpus[idx]
                    
                    # Apply filters
                    if topic and topic.lower() not in m.get("topic", "").lower():
                        continue
                    if tags and not any(t in m.get("tags", []) for t in tags):
                        continue
                    
                    # Load full content from ledger
                    recs = _load_ledger()
                    full_rec = next((r for r in recs if r.get("id") == m["id"]), None)
                    
                    if full_rec:
                        bm25_results.append({
                            "score": float(scores[idx]),
                            "id": m["id"],
                            "ts": m["ts"],
                            "topic": m["topic"],
                            "tags": m["tags"],
                            "priority": m["priority"],
                            "content": full_rec.get("content", "")[:500],
                            "_bm25_score": float(scores[idx]),
                        })
        except Exception:
            pass
    
    # Reciprocal Rank Fusion (RRF)
    # Combine vector and BM25 results
    all_results = {}
    
    # Add vector results with ranks
    for rank, r in enumerate(vector_results):
        rid = r["id"]
        if rid not in all_results:
            all_results[rid] = {**r, "_vector_rank": rank, "_bm25_rank": float('inf')}
        else:
            all_results[rid]["_vector_rank"] = rank
    
    # Add BM25 results with ranks
    for rank, r in enumerate(bm25_results):
        rid = r["id"]
        if rid not in all_results:
            all_results[rid] = {**r, "_vector_rank": float('inf'), "_bm25_rank": rank}
        else:
            all_results[rid]["_bm25_rank"] = rank
            all_results[rid]["_bm25_score"] = r.get("_bm25_score", 0)
    
    # Calculate RRF scores
    k_rrf = 60  # RRF constant
    for rid, r in all_results.items():
        vector_rank = r.get("_vector_rank", float('inf'))
        bm25_rank = r.get("_bm25_rank", float('inf'))
        
        vector_score = 1.0 / (k_rrf + vector_rank + 1) if vector_rank != float('inf') else 0
        bm25_score = 1.0 / (k_rrf + bm25_rank + 1) if bm25_rank != float('inf') else 0
        
        r["_rrf_score"] = alpha * vector_score + (1 - alpha) * bm25_score
    
    # Sort by RRF score
    sorted_results = sorted(all_results.values(), key=lambda x: x["_rrf_score"], reverse=True)
    
    # Optional cross-encoder reranking
    if USE_CROSS_ENCODER and sorted_results:
        try:
            cross_encoder = _get_cross_encoder()
            # Prepare query-document pairs for cross-encoder
            pairs = [(query, r["content"]) for r in sorted_results[:k * 2]]
            ce_scores = cross_encoder.predict(pairs)
            
            # Update scores with cross-encoder scores (weighted combination)
            for i, r in enumerate(sorted_results[:k * 2]):
                r["_ce_score"] = float(ce_scores[i])
                # Combine RRF score with cross-encoder score
                r["_final_score"] = 0.5 * r["_rrf_score"] + 0.5 * r["_ce_score"]
            
            # Re-sort by final score
            sorted_results = sorted(sorted_results, key=lambda x: x.get("_final_score", x["_rrf_score"]), reverse=True)
        except Exception as e:
            print(f"Warning: cross-encoder reranking failed: {e}", file=sys.stderr)
    
    # Return top k
    results = []
    for r in sorted_results[:k]:
        results.append({
            "score": r.get("_final_score", r["_rrf_score"]),
            "id": r["id"],
            "ts": r["ts"],
            "topic": r["topic"],
            "tags": r["tags"],
            "priority": r["priority"],
            "content": r["content"],
            "_vector_rank": r.get("_vector_rank"),
            "_bm25_rank": r.get("_bm25_rank"),
            "_ce_score": r.get("_ce_score"),
        })
    
    return results


def main(argv=None):
    p = argparse.ArgumentParser(description="Hermes tiered memory system")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("remember")
    pr.add_argument("--topic", required=True)
    pr.add_argument("--content", required=True)
    pr.add_argument("--tags", default="")
    pr.add_argument("--priority", default="normal")
    pr.add_argument("--confidence", type=float)
    pr.add_argument("--epistemic-status", choices=["observed", "inferred", "imagined", "user_stated", "hypothesis", "agent_generated"])
    pr.add_argument("--source")
    pr.add_argument("--valid-from")
    pr.add_argument("--valid-to")

    pc = sub.add_parser("recall")
    pc.add_argument("--topic")
    pc.add_argument("--tags", default="")
    pc.add_argument("--k", type=int, default=5)
    pc.add_argument("--as-of", help="ISO timestamp for point-in-time query")

    pa = sub.add_parser("recall_at")
    pa.add_argument("--as-of", required=True, help="ISO timestamp for point-in-time query")
    pa.add_argument("--topic")
    pa.add_argument("--tags", default="")
    pa.add_argument("--k", type=int, default=5)

    ps = sub.add_parser("supersede")
    ps.add_argument("--id", required=True)
    ps.add_argument("--content", required=True)
    ps.add_argument("--tags", default="")
    ps.add_argument("--priority", default="normal")

    pu = sub.add_parser("update_validity")
    pu.add_argument("--id", required=True)
    pu.add_argument("--valid-from")
    pu.add_argument("--valid-to")

    pl = sub.add_parser("ledger")
    pl.add_argument("--k", type=int, default=20)
    pl.add_argument("--since")

    pv = sub.add_parser("rebuild_vectors")
    pv.add_argument("--k", type=int, default=5)
    pv.add_argument("--query")
    pv.add_argument("--topic")

    pb = sub.add_parser("rebuild_bm25")

    ps = sub.add_parser("recall_semantic")
    ps.add_argument("--query", required=True)
    ps.add_argument("--k", type=int, default=5)
    ps.add_argument("--topic")
    ps.add_argument("--tags", default="")

    pa_conf = sub.add_parser("assess_confidence")
    pa_conf.add_argument("--id", required=True)
    pa_conf.add_argument("--confidence", type=float, required=True)

    pa_epistemic = sub.add_parser("set_epistemic_status")
    pa_epistemic.add_argument("--id", required=True)
    pa_epistemic.add_argument("--status", required=True, choices=["observed", "inferred", "imagined", "user_stated", "hypothesis", "agent_generated"])

    pa_gaps = sub.add_parser("detect_gaps")
    pa_gaps.add_argument("--topic", required=True)
    pa_gaps.add_argument("--threshold", type=float, default=0.5)

    pa_audit = sub.add_parser("self_audit")
    pa_audit.add_argument("--id")
    pa_audit.add_argument("--topic")

    pwm_var = sub.add_parser("world_model_add_variable")
    pwm_var.add_argument("--name", required=True)
    pwm_var.add_argument("--initial-value", type=float, required=True)
    pwm_var.add_argument("--dynamics", default="constant")

    pwm_rule = sub.add_parser("world_model_add_rule")
    pwm_rule.add_argument("--condition", required=True)
    pwm_rule.add_argument("--effect", required=True, help="JSON dict like {\"var\": change}")
    pwm_rule.add_argument("--probability", type=float, default=1.0)

    pwm_sim = sub.add_parser("world_model_simulate")
    pwm_sim.add_argument("--steps", type=int, default=10)

    pwm_pred = sub.add_parser("world_model_predict")
    pwm_pred.add_argument("--query", required=True)
    pwm_pred.add_argument("--horizon", type=int, default=10)

    pwm_state = sub.add_parser("world_model_get_state")

    pwm_reset = sub.add_parser("world_model_reset")

    pa_val = sub.add_parser("affective_set_value")
    pa_val.add_argument("--name", required=True)
    pa_val.add_argument("--weight", type=float, required=True)
    pa_val.add_argument("--description", default="")

    pa_emo = sub.add_parser("affective_set_emotion")
    pa_emo.add_argument("--name", required=True)
    pa_emo.add_argument("--intensity", type=float, required=True)
    pa_emo.add_argument("--cause", default="")

    pa_goal = sub.add_parser("affective_add_goal")
    pa_goal.add_argument("--name", required=True)
    pa_goal.add_argument("--priority", type=float, required=True)
    pa_goal.add_argument("--target", help="JSON dict for target state")

    pa_pref = sub.add_parser("affective_update_preference")
    pa_pref.add_argument("--context", required=True)
    pa_pref.add_argument("--preference", required=True)
    pa_pref.add_argument("--strength", type=float, required=True)

    pa_eval = sub.add_parser("affective_evaluate")
    pa_eval.add_argument("--situation", required=True, help="JSON dict")

    pa_state = sub.add_parser("affective_get_state")

    pproc_add = sub.add_parser("procedural_add_skill")
    pproc_add.add_argument("--name", required=True)
    pproc_add.add_argument("--description", required=True)
    pproc_add.add_argument("--steps", required=True, help="JSON array of steps")
    pproc_add.add_argument("--preconditions", default="{}", help="JSON dict")
    pproc_add.add_argument("--effects", default="{}", help="JSON dict")
    pproc_add.add_argument("--category", default="general")

    pproc_get = sub.add_parser("procedural_get_skill")
    pproc_get.add_argument("--name", required=True)

    pproc_find = sub.add_parser("procedural_find_skills")
    pproc_find.add_argument("--category")
    pproc_find.add_argument("--preconditions", default="{}", help="JSON dict")

    pproc_exec = sub.add_parser("procedural_execute_skill")
    pproc_exec.add_argument("--name", required=True)
    pproc_exec.add_argument("--context", default="{}", help="JSON dict")

    pproc_learn = sub.add_parser("procedural_learn")
    pproc_learn.add_argument("--name", required=True)
    pproc_learn.add_argument("--success", type=lambda x: x.lower() == "true", required=True)
    pproc_learn.add_argument("--modified-steps", default="[]", help="JSON array")
    pproc_learn.add_argument("--new-preconditions", default="{}", help="JSON dict")
    pproc_learn.add_argument("--new-effects", default="{}", help="JSON dict")

    pproc_list = sub.add_parser("procedural_list_skills")
    pproc_list.add_argument("--category")

    ppin = sub.add_parser("pin_block")
    ppin.add_argument("--id", required=True)
    ppin.add_argument("--content", required=True)
    ppin.add_argument("--reason", default="")

    punpin = sub.add_parser("unpin_block")
    punpin.add_argument("--id", required=True)

    plistpin = sub.add_parser("list_pinned_blocks")

    pgetpin = sub.add_parser("get_pinned_block")
    pgetpin.add_argument("--id", required=True)

    phyb = sub.add_parser("recall_hybrid")
    phyb.add_argument("--query", required=True)
    phyb.add_argument("--k", type=int, default=5)
    phyb.add_argument("--topic")
    phyb.add_argument("--tags", default="")
    phyb.add_argument("--alpha", type=float, default=0.5, help="Weight for vector search (1-alpha for BM25)")

    sub.add_parser("rebuild")
    sub.add_parser("backup")
    sub.add_parser("status")
    sub.add_parser("prune")

    args = p.parse_args(argv)
    tags = [t.strip() for t in getattr(args, "tags", "").split(",") if t.strip()] if getattr(args, "tags", "") else []

    if args.cmd == "remember":
        r = remember(args.topic, args.content, tags, args.priority, 
                     actor="agent",
                     valid_from=getattr(args, "valid_from", None),
                     valid_to=getattr(args, "valid_to", None),
                     confidence=getattr(args, "confidence", None), 
                     epistemic_status=getattr(args, "epistemic_status", None),
                     source=getattr(args, "source", None))
        print(f"remembered -> {r['id']} ({args.topic})")
    elif args.cmd == "recall":
        for r in recall(args.topic, tags, args.k):
            print(f"[{r['ts'][:19]}] {r['topic']} (pri={r['priority']})")
            print("   " + r["content"][:400])
            print()
    elif args.cmd == "ledger":
        print(ledger_view(args.k, args.since))
    elif args.cmd == "recall_at":
        as_of = args.as_of
        tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []
        for r in recall_at(as_of=as_of, topic=args.topic, tags=tags, k=args.k):
            print(f"[{r['ts'][:19]}] {r['topic']} (pri={r['priority']})")
            if r.get('valid_from'):
                print(f"   Valid from: {r['valid_from']}")
            if r.get('valid_to'):
                print(f"   Valid to: {r['valid_to']}")
            print(f"   {r['content'][:400]}")
            print()
    elif args.cmd == "supersede":
        tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []
        r = supersede(args.id, args.content, tags, args.priority)
        print(f"superseded -> {r['id']} ({r['topic']})")
    elif args.cmd == "update_validity":
        r = update_validity(args.id, args.valid_from, args.valid_to)
        print(f"updated validity -> {r['id']} (from={r['valid_from']}, to={r['valid_to']})")
    elif args.cmd == "world_model_add_variable":
        r = world_model_add_variable(args.name, args.initial_value, args.dynamics)
        print(f"variable added -> {r['variable']}: {r['initial_value']} ({r['dynamics']})")
    elif args.cmd == "world_model_add_rule":
        import json
        effect = json.loads(args.effect)
        r = world_model_add_rule(args.condition, effect, args.probability)
        print(f"rule added -> {r['condition']} -> {r['effect']} (p={r['probability']})")
    elif args.cmd == "world_model_simulate":
        r = world_model_simulate(args.steps)
        print(f"simulation complete: {r['steps']} steps")
        print(f"final state: {r['final_state']}")
    elif args.cmd == "world_model_predict":
        r = world_model_predict(args.query, args.horizon)
        print(f"prediction for '{r['query']}':")
        if 'prediction' in r:
            print(f"  prediction: {r['prediction']}")
            print(f"  final_value: {r['final_value']} (threshold: {r['threshold']})")
            print(f"  trajectory: {r['trajectory']}")
        else:
            print(f"  final_state: {r['final_state']}")
    elif args.cmd == "world_model_get_state":
        r = world_model_get_state()
        print(f"current state: {r}")
    elif args.cmd == "world_model_reset":
        r = world_model_reset()
        print(r['status'])
    elif args.cmd == "affective_set_value":
        r = affective_set_value(args.name, args.weight, args.description)
        print(f"value set -> {r['value']}: {r['weight']} ({r['description']})")
    elif args.cmd == "affective_set_emotion":
        r = affective_set_emotion(args.name, args.intensity, args.cause)
        print(f"emotion set -> {r['emotion']}: {r['intensity']} ({r['cause']})")
    elif args.cmd == "affective_add_goal":
        import json
        target = json.loads(args.target) if args.target else {}
        r = affective_add_goal(args.name, args.priority, target)
        print(f"goal added -> {r['goal']}: priority={r['priority']}, target={r['target_state']}")
    elif args.cmd == "affective_update_preference":
        r = affective_update_preference(args.context, args.preference, args.strength)
        print(f"preference updated -> {r['context']}: {r['preference']}={r['strength']}")
    elif args.cmd == "affective_evaluate":
        import json
        situation = json.loads(args.situation)
        r = affective_evaluate(situation)
        print(f"evaluation: {r}")
    elif args.cmd == "affective_get_state":
        r = affective_get_state()
        print(f"affective state: {r}")
    elif args.cmd == "rebuild_vectors":
        print(rebuild_vectors())
    elif args.cmd == "rebuild_bm25":
        print(rebuild_bm25())
    elif args.cmd == "recall_semantic":
        tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []
        results = recall_semantic(args.query, args.k, args.topic, tags)
        for r in results:
            if "error" in r:
                print(r["error"])
            else:
                print(f"[{r['score']:.3f}] [{r['ts'][:19]}] {r['topic']} (pri={r['priority']})")
                print(f"   {r['content'][:400]}")
                print()
    elif args.cmd == "assess_confidence":
        r = assess_confidence(args.id, args.confidence)
        print(f"confidence assessed -> {r['id']}: {r['confidence']:.2f}")
    elif args.cmd == "set_epistemic_status":
        r = set_epistemic_status(args.id, args.status)
        print(f"epistemic status set -> {r['id']}: {r['epistemic_status']}")
    elif args.cmd == "detect_gaps":
        r = detect_knowledge_gaps(args.topic, args.threshold)
        print(f"Gap analysis for '{r['topic']}':")
        print(f"  Memories: {r['total_memories']}")
        print(f"  Avg confidence: {r['avg_confidence']:.2f}")
        print(f"  Coverage score: {r['coverage_score']:.2f}")
        for gap in r['gaps']:
            print(f"  GAP: {gap}")
        if r['low_confidence_subtopics']:
            print(f"  Low confidence subtopics: {', '.join(r['low_confidence_subtopics'])}")
    elif args.cmd == "self_audit":
        r = self_audit(args.id, args.topic)
        if "error" in r:
            print(r["error"])
        else:
            print(f"Audit results:")
            for k, v in r.items():
                if isinstance(v, list):
                    print(f"  {k}:")
                    for item in v:
                        if item:
                            print(f"    - {item}")
                elif v is not None:
                    print(f"  {k}: {v}")
    elif args.cmd == "procedural_add_skill":
        import json
        steps = json.loads(args.steps)
        preconditions = json.loads(args.preconditions)
        effects = json.loads(args.effects)
        r = procedural_add_skill(args.name, args.description, steps, preconditions, effects, args.category)
        print(f"skill added -> {r['skill']}: {r['description']}")
    elif args.cmd == "procedural_get_skill":
        r = procedural_get_skill(args.name)
        if "error" in r:
            print(r["error"])
        else:
            print(f"skill: {r['name']}")
            print(f"  description: {r['description']}")
            print(f"  steps: {r['steps']}")
            print(f"  preconditions: {r['preconditions']}")
            print(f"  effects: {r['effects']}")
            print(f"  category: {r['category']}")
            print(f"  execution_count: {r['execution_count']}")
            print(f"  success_rate: {r['success_rate']:.2f}")
    elif args.cmd == "procedural_find_skills":
        import json
        preconditions = json.loads(args.preconditions)
        skills = procedural_find_skills(args.category, preconditions)
        print(f"found {len(skills)} skills:")
        for s in skills:
            print(f"  {s['name']} ({s['category']}): {s['description'][:60]}...")
    elif args.cmd == "procedural_execute_skill":
        import json
        context = json.loads(args.context)
        r = procedural_execute_skill(args.name, context)
        if "error" in r:
            print(r["error"])
        else:
            print(f"executed {args.name}: {r}")
    elif args.cmd == "procedural_learn":
        import json
        modified_steps = json.loads(args.modified_steps)
        new_preconditions = json.loads(args.new_preconditions)
        new_effects = json.loads(args.new_effects)
        r = procedural_learn(args.name, args.success, modified_steps, new_preconditions, new_effects)
        print(f"learned: {r}")
    elif args.cmd == "procedural_list_skills":
        skills = procedural_list_skills(args.category)
        print(f"skills ({args.category or 'all'}):")
        for s in skills:
            print(f"  {s['name']} ({s['category']}): {s['description'][:60]}...")
    elif args.cmd == "pin_block":
        r = pin_block(args.id, args.content, args.reason)
        print(f"pinned -> {r['block_id']}: {r['pinned']}")
    elif args.cmd == "unpin_block":
        r = unpin_block(args.id)
        print(f"unpinned -> {r['block_id']}: {r['pinned']}")
    elif args.cmd == "list_pinned_blocks":
        r = list_pinned_blocks()
        print(f"pinned blocks ({len(r['pinned_blocks'])}):")
        for bid in r['order']:
            b = r['pinned_blocks'][bid]
            print(f"  {bid}: {b['content'][:60]}... (reason: {b['reason']})")
    elif args.cmd == "get_pinned_block":
        r = get_pinned_block(args.id)
        if "error" in r:
            print(r["error"])
        else:
            print(f"pinned block: {r['block_id']}")
            print(f"  content: {r['content']}")
            print(f"  reason: {r['reason']}")
            print(f"  pinned_ts: {r['pinned_ts']}")
    elif args.cmd == "recall_hybrid":
        tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []
        results = recall_hybrid(args.query, args.k, args.topic, tags, args.alpha)
        for r in results:
            if "error" in r:
                print(r["error"])
            else:
                print(f"[{r['score']:.3f}] [{r['ts'][:19]}] {r['topic']} (pri={r['priority']})")
                print(f"   {r['content'][:400]}")
                print()
    elif args.cmd == "rebuild":
        print("index rebuilt:\n" + rebuild_index())
    elif args.cmd == "backup":
        print(backup())
    elif args.cmd == "status":
        print(status())
    elif args.cmd == "prune":
        print("prune: manual consolidation — see memory skill. "
              "Supersede by writing a new fact with [SUPERSEEDED] tag on the old.")


if __name__ == "__main__":
    main()
