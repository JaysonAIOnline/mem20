import ast
import os
import sys
import json
import re
import subprocess
import tempfile
import base64
import asyncio
import hashlib
import shutil
import glob
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from mcp.server import Server
    from mcp.server.lowlevel.server import ServerRequestContext
    import mcp_types as mt
except ImportError:
    print("Error: mcp package not installed. Please install with: pip install mcp")
    sys.exit(1)

sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
try:
    from memory import recall, remember, status as mem_status, rebuild_index, ledger_view
    MEMORY_SYSTEM_AVAILABLE = True
except ImportError:
    MEMORY_SYSTEM_AVAILABLE = False


def _engine():
    """Return the loaded memory engine module.

    The engine is imported once at module scope from MEM20_STORE_PATH. Handlers
    used to re-run `sys.path.insert` and `from memory import ...` inside every
    call, which both repeated the import machinery per query and silently picked
    up whichever `memory` module happened to be first on sys.path.
    """
    if not MEMORY_SYSTEM_AVAILABLE:
        raise RuntimeError(
            "memory engine not importable from "
            f"{os.environ.get('MEM20_STORE_PATH', os.path.expanduser('~/.mem20/store'))}")
    import memory as _m
    return _m


_NAMESPACE_META_TOPIC = "namespace_meta"
_NAMESPACE_META_PREFIX = "NSMETA2 "
_NAMESPACE_CONTENT_TOPIC = "namespace_"
_ACL_RANKS = {
    "none": 0,
    "viewer": 1,
    "read": 1,
    "write": 2,
    "editor": 2,
    "admin": 3,
    "owner": 3,
}
_ACL_REQUIREMENTS = {"read": 1, "write": 2, "admin": 3}
_LEGACY_META_RE = re.compile(
    r"^Namespace:\s*(?P<namespace>[^,]*),\s*Owner:\s*(?P<owner>[^,]*),\s*ACL:\s*(?P<acl>\{.*\})\s*$"
)


def _parse_namespace_meta(content, namespace):
    if not isinstance(content, str):
        return None
    text = content.strip()
    if text.startswith(_NAMESPACE_META_PREFIX):
        try:
            payload = json.loads(text[len(_NAMESPACE_META_PREFIX):])
        except ValueError:
            return None
        if not isinstance(payload, dict) or payload.get("namespace") != namespace:
            return None
        acl = payload.get("acl")
        return {
            "namespace": namespace,
            "owner": str(payload.get("owner") or ""),
            "acl": {str(k): str(v) for k, v in acl.items()} if isinstance(acl, dict) else {},
        }
    match = _LEGACY_META_RE.match(text)
    if not match or match.group("namespace").strip() != namespace:
        return None
    try:
        acl = ast.literal_eval(match.group("acl"))
    except (SyntaxError, ValueError):
        acl = {}
    if not isinstance(acl, dict):
        acl = {}
    return {
        "namespace": namespace,
        "owner": match.group("owner").strip(),
        "acl": {str(k): str(v) for k, v in acl.items()},
    }


def _namespace_meta(namespace, recall_fn):
    rows = recall_fn(topic=_NAMESPACE_META_TOPIC, tags=[namespace], k=200)
    parsed = [m for m in (_parse_namespace_meta(r.get("content", ""), namespace) for r in rows) if m]
    if not parsed:
        rows = recall_fn(topic=_NAMESPACE_META_TOPIC, k=1000)
        parsed = [m for m in (_parse_namespace_meta(r.get("content", ""), namespace) for r in rows) if m]
    return parsed[0] if parsed else None


def _acl_grant(meta, actor):
    if not meta:
        return 0
    if meta.get("owner") and actor == meta["owner"]:
        return _ACL_RANKS["admin"]
    acl = meta.get("acl") or {}
    return max((_ACL_RANKS.get(str(acl[key]).lower(), 0) for key in (actor, "*") if key in acl), default=0)


_LEGACY_SELF_MODEL_TOPIC = "self_model"
_SELF_MODEL_TOPIC_PREFIX = "self_model__"
_SELF_MODEL_RECORD_PREFIX = "SELFMODEL2 "
_SELF_MODEL_IDENTITY_TOPIC_PREFIX = "self_model_identity__"
_SELF_MODEL_LEGACY_SCAN_K = 1000


def _slugify_identity(identity: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(identity).strip().lower()).strip("-")
    return slug or "unnamed"


def _legacy_identity_key(identity_text: str) -> str:
    """Derive an identity key from a legacy free-text identity description.

    Legacy records stored a prose sentence such as "big-pickle, grounded builder
    agent ...". The first token before punctuation identifies the writer.
    """
    head = re.split(r"[,\.\n]", str(identity_text).strip(), maxsplit=1)[0]
    return _slugify_identity(head.split()[0] if head.split() else head)


def _parse_self_model_record(content: str, identity: str | None = None) -> dict | None:
    if not isinstance(content, str):
        return None
    text = content.strip()

    if text.startswith(_SELF_MODEL_RECORD_PREFIX):
        try:
            payload = json.loads(text[len(_SELF_MODEL_RECORD_PREFIX):])
        except ValueError:
            return None
        if not isinstance(payload, dict):
            return None
        if identity is not None and payload.get("identity_key") != _slugify_identity(identity):
            return None
        return payload

    if text.startswith("Self-Model: "):
        try:
            legacy = ast.literal_eval(text[len("Self-Model: "):])
        except (SyntaxError, ValueError):
            return None
        if not isinstance(legacy, dict):
            return None
        key = _legacy_identity_key(legacy.get("identity", ""))
        if identity is not None and key != _slugify_identity(identity):
            return None
        return {
            "identity": legacy.get("identity", ""),
            "identity_key": key,
            "capabilities": list(legacy.get("capabilities") or []),
            "values": list(legacy.get("values") or []),
            "created": legacy.get("created"),
            "actor": None,
            "legacy": True,
        }
    return None


def _legacy_self_model_rows(recall_fn) -> list[dict]:
    """Legacy un-keyed self-model records, parsed and grouped by identity.

    ``recall`` matches topics by substring, so the unscoped ``self_model`` topic
    shares matches with the per-identity topics. A small k therefore returns only
    the newest per-identity rows and crowds the older legacy rows out entirely;
    the scan must be wide enough to reach them.
    """
    rows = [
        r
        for r in recall_fn(topic=_LEGACY_SELF_MODEL_TOPIC, k=_SELF_MODEL_LEGACY_SCAN_K)
        if r.get("topic") == _LEGACY_SELF_MODEL_TOPIC
    ]
    parsed = [p for p in (_parse_self_model_record(r.get("content", "")) for r in rows) if p]
    parsed.sort(key=lambda p: str(p.get("created") or ""), reverse=True)
    return parsed


def _self_model_rows(identity: str, recall_fn, k: int = 200) -> list[dict]:
    """Return records for one identity only, newest first.

    ``recall`` matches topics by substring, so every candidate is re-checked for
    exact topic and exact identity before it can be returned.
    """
    slug = _slugify_identity(identity)
    topic = f"{_SELF_MODEL_TOPIC_PREFIX}{slug}"
    rows = [r for r in recall_fn(topic=topic, k=k) if r.get("topic") == topic]
    parsed = [p for p in (_parse_self_model_record(r.get("content", ""), identity) for r in rows) if p]
    parsed += [
        p for p in _legacy_self_model_rows(recall_fn) if p["identity_key"] == slug
    ]
    parsed.sort(key=lambda p: str(p.get("created") or ""), reverse=True)
    return parsed


def _all_self_model_rows(recall_fn, k: int = 1000) -> dict[str, list[dict]]:
    rows = recall_fn(topic=_SELF_MODEL_TOPIC_PREFIX, k=k)
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        if not str(row.get("topic", "")).startswith(_SELF_MODEL_TOPIC_PREFIX):
            continue
        payload = _parse_self_model_record(row.get("content", ""))
        if payload:
            grouped.setdefault(payload["identity_key"], []).append(payload)
    for payload in _legacy_self_model_rows(recall_fn):
        grouped.setdefault(payload["identity_key"], []).append(payload)
    for entries in grouped.values():
        entries.sort(key=lambda p: str(p.get("created") or ""), reverse=True)
    return grouped


def _self_model_owner(identity: str, recall_fn) -> dict | None:
    slug = _slugify_identity(identity)
    topic = f"{_SELF_MODEL_IDENTITY_TOPIC_PREFIX}{slug}"
    rows = [r for r in recall_fn(topic=topic, k=200) if r.get("topic") == topic]
    for row in rows:
        content = row.get("content", "")
        if content.startswith(_NAMESPACE_META_PREFIX):
            try:
                payload = json.loads(content[len(_NAMESPACE_META_PREFIX):])
            except ValueError:
                continue
            if payload.get("namespace") == topic:
                return payload
    return None


def _authorize_self_model_write(identity: str, actor: str, recall_fn) -> tuple[bool, str]:
    slug = _slugify_identity(identity)
    owner = _self_model_owner(identity, recall_fn)
    if owner is not None:
        delegates = owner.get("acl") or {}
        if actor == owner.get("owner"):
            return True, "owner"
        if delegates.get(actor) in {"admin", "write"}:
            return True, "delegate"
        return False, (
            f"identity '{identity}' is owned by '{owner.get('owner')}'; actor '{actor}' is neither "
            "the owner nor an authorised delegate. Self-models are write-protected so coexisting "
            "identities cannot overwrite each other."
        )

    existing = _self_model_rows(identity, recall_fn, k=5)
    if existing and actor != slug:
        return False, (
            f"identity '{identity}' already has {len(existing)} self-model record(s) but no owner "
            f"registration, so it belongs to an incumbent identity. Actor '{actor}' may not claim it. "
            f"Only the identity itself (actor '{slug}') may adopt it, or the owner must be registered "
            "explicitly by the user. Claiming another identity's records is never permitted."
        )
    return True, "bootstrap"


def _check_namespace_access(meta, actor, need):
    required = _ACL_REQUIREMENTS[need]
    if not meta:
        return False, "namespace does not exist; create it with memory_namespace_create first"
    granted = _acl_grant(meta, actor)
    if granted < required:
        return False, (
            f"actor '{actor}' lacks '{need}' permission on namespace "
            f"'{meta['namespace']}' (owner: {meta['owner'] or 'unset'})"
        )
    return True, "ok"


def _namespace_access(namespace, actor, need, recall_fn):
    meta = _namespace_meta(namespace, recall_fn)
    allowed, reason = _check_namespace_access(meta, actor, need)
    return allowed, reason, meta


def _namespace_content_rows(namespace, recall_fn, k):
    topic = f"{_NAMESPACE_CONTENT_TOPIC}{namespace}"
    rows = [r for r in recall_fn(topic=topic, k=max(k * 20, 200)) if r.get("topic") == topic]
    return rows[:k]


class MemoryToolsMixin:
    def register_memory_tools(self):
        self.tools["memory_store"] = mt.Tool(
            name="memory_store",
            title="Store Memory",
            description="Store a fact in mem20's persistent memory system",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "The fact/content to store"},
                    "category": {"type": "string", "enum": ["user_pref", "project", "tool", "general"], "default": "general"},
                    "tags": {"type": "string", "description": "Comma-separated tags", "default": ""},
                },
                "required": ["content"],
            },
        )
        self.tools["memory_recall"] = mt.Tool(
            name="memory_recall",
            title="Recall Memory",
            description="Search and recall facts from mem20's memory system",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "category": {"type": "string", "enum": ["user_pref", "project", "tool", "general"], "default": ""},
                    "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50},
                },
                "required": ["query"],
            },
        )
        self.tools["memory_probe"] = mt.Tool(
            name="memory_probe",
            title="Probe Entity",
            description="Get all facts about a specific entity",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity": {"type": "string", "description": "Entity name to probe"},
                    "min_trust": {"type": "number", "default": 0.3},
                },
                "required": ["entity"],
            },
        )
        self.tools["memory_reason"] = mt.Tool(
            name="memory_reason",
            title="Reason Across Entities",
            description="Compositional reasoning across multiple entities",
            inputSchema={
                "type": "object",
                "properties": {
                    "entities": {"type": "array", "items": {"type": "string"}, "description": "List of entity names"},
                    "min_trust": {"type": "number", "default": 0.3},
                },
                "required": ["entities"],
            },
        )
        self.tools["memory_status"] = mt.Tool(
            name="memory_status",
            title="Memory Status",
            description="Get mem20 memory system status and stats",
            inputSchema={"type": "object", "properties": {}},
        )
        self.tools["memory_contradict"] = mt.Tool(
            name="memory_contradict",
            title="Find Contradictions",
            description="Find facts that make conflicting claims about a topic",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to check for contradictions"},
                    "min_trust": {"type": "number", "description": "Minimum trust score", "default": 0.3},
                },
                "required": ["topic"],
            },
        )
        self.tools["memory_related"] = mt.Tool(
            name="memory_related",
            title="Find Related Entities",
            description="Find entities structurally adjacent/connected to a given entity",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity": {"type": "string", "description": "Entity name to find connections for"},
                    "min_trust": {"type": "number", "description": "Minimum trust score", "default": 0.3},
                },
                "required": ["entity"],
            },
        )
        self.tools["memory_feedback"] = mt.Tool(
            name="memory_feedback",
            title="Rate Fact",
            description="Rate a fact helpful/unhelpful to train trust scores",
            inputSchema={
                "type": "object",
                "properties": {
                    "fact_id": {"type": "integer", "description": "Fact ID from recall/probe"},
                    "action": {"type": "string", "enum": ["helpful", "unhelpful"], "description": "Rating action"},
                },
                "required": ["fact_id", "action"],
            },
        )
        self.tools["memory_recall_semantic"] = mt.Tool(
            name="memory_recall_semantic",
            title="Semantic Memory Recall",
            description="Pure vector-based semantic search using embeddings",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 50},
                    "topic": {"type": "string", "description": "Filter by topic", "default": ""},
                    "tags": {"type": "string", "description": "Comma-separated tags", "default": ""},
                    "rerank": {"type": "boolean", "description": "Apply cross-encoder reranking", "default": True},
                },
                "required": ["query"],
            },
        )
        self.tools["memory_recall_hybrid"] = mt.Tool(
            name="memory_recall_hybrid",
            title="Hybrid Memory Recall",
            description="Hybrid BM25 + vector search with Reciprocal Rank Fusion and optional cross-encoder reranking",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 50},
                    "topic": {"type": "string", "description": "Filter by topic", "default": ""},
                    "tags": {"type": "string", "description": "Comma-separated tags", "default": ""},
                    "alpha": {"type": "number", "description": "Weight for vector search (1-alpha for BM25), 0.5 = equal", "default": 0.5},
                    "rerank": {"type": "boolean", "description": "Apply cross-encoder reranking", "default": True},
                },
                "required": ["query"],
            },
        )
        self.tools["memory_recall_graph"] = mt.Tool(
            name="memory_recall_graph",
            title="Graph Memory Recall",
            description=(
                "Multi-hop entity traversal over the persisted knowledge graph. "
                "Entities are extracted at write time from topics, tags, and "
                "proper nouns; returns related entities with hop distance plus "
                "the facts that support them. Falls back to partial and "
                "substring entity matching. Reports honestly when the graph "
                "index has not been built."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "entity": {"type": "string", "description": "Starting entity (exact, case-insensitive, or substring)"},
                    "hops": {"type": "integer", "description": "Number of graph hops", "default": 2},
                    "max_results": {"type": "integer", "default": 20},
                    "min_facts": {"type": "integer", "description": "Require the starting entity to have at least this many supporting facts", "default": 1},
                    "topic": {"type": "string", "description": "Only return entities seen under this topic", "default": ""},
                },
                "required": ["entity"],
            },
        )
        self.tools["memory_index_health"] = mt.Tool(
            name="memory_index_health",
            title="Retrieval Index Health",
            description=(
                "Report whether the vector, BM25, and graph indexes still agree "
                "with the ledger, with exact counts. An index entry whose record "
                "no longer exists is a stale pointer: search finds it and then "
                "cannot resolve its content. This reports the drift instead of "
                "silently returning fewer results."
            ),
            inputSchema={"type": "object", "properties": {}},
        )
        self.tools["memory_entity_extract"] = mt.Tool(
            name="memory_entity_extract",
            title="Entity Extraction",
            description="Extract entities and relationships from text using spaCy/LLM",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to extract entities from"},
                    "topic": {"type": "string", "description": "Topic/category for the extracted entities", "default": "general"},
                    "store": {"type": "boolean", "description": "Store extracted entities as memories", "default": True},
                },
                "required": ["text"],
            },
        )
        self.tools["memory_auto_consolidate"] = mt.Tool(
            name="memory_auto_consolidate",
            title="Auto Consolidation",
            description="Cluster similar memories and generate higher-level summaries",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to consolidate (optional, all if not specified)", "default": ""},
                    "min_cluster_size": {"type": "integer", "description": "Minimum memories per cluster", "default": 3},
                    "similarity_threshold": {"type": "number", "description": "Clustering similarity threshold", "default": 0.75},
                    "generate_summaries": {"type": "boolean", "description": "Generate LLM summaries for clusters", "default": True},
                },
                "required": [],
            },
        )
        self.tools["memory_assess_confidence"] = mt.Tool(
            name="memory_assess_confidence",
            title="Assess Memory Confidence",
            description="Explicitly set or update confidence score for a fact",
            inputSchema={
                "type": "object",
                "properties": {
                    "fact_id": {"type": "string", "description": "Fact ID"},
                    "confidence": {"type": "number", "description": "Confidence 0.0-1.0"},
                },
                "required": ["fact_id", "confidence"],
            },
        )
        self.tools["memory_set_epistemic_status"] = mt.Tool(
            name="memory_set_epistemic_status",
            title="Set Epistemic Status",
            description="Set epistemic status tag (observed, inferred, imagined, user_stated, hypothesis, agent_generated)",
            inputSchema={
                "type": "object",
                "properties": {
                    "fact_id": {"type": "string", "description": "Fact ID"},
                    "status": {"type": "string", "enum": ["observed", "inferred", "imagined", "user_stated", "hypothesis", "agent_generated"], "description": "Epistemic status"},
                },
                "required": ["fact_id", "status"],
            },
        )
        self.tools["memory_detect_gaps"] = mt.Tool(
            name="memory_detect_gaps",
            title="Detect Knowledge Gaps",
            description="Detect knowledge gaps for a topic - find areas with low confidence or missing coverage",
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to analyze"},
                    "threshold": {"type": "number", "description": "Confidence threshold", "default": 0.5},
                },
                "required": ["topic"],
            },
        )
        self.tools["memory_self_audit"] = mt.Tool(
            name="memory_self_audit",
            title="Self Audit",
            description="Metacognitive self-audit: evaluate own knowledge quality, identify biases",
            inputSchema={
                "type": "object",
                "properties": {
                    "fact_id": {"type": "string", "description": "Specific fact to audit", "default": ""},
                    "topic": {"type": "string", "description": "Topic to audit", "default": ""},
                },
                "required": [],
            },
        )
        self.tools["memory_simulate_store"] = mt.Tool(
            name="memory_simulate_store",
            title="Store Simulated (Partitioned)",
            description=("Store SIMULATED / imagined content into the SEPARATE simulated "
                         "partition. This content is NEVER written to grounded memory or the "
                         "semantic indexes, and cannot be promoted to grounded memory without an "
                         "explicit confirmation or real-world prediction-error resolution."),
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic/domain of the simulation"},
                    "content": {"type": "string", "description": "The simulated/imagined content"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags", "default": []},
                    "scenario": {"type": "string", "description": "Scenario description", "default": ""},
                    "sim_type": {"type": "string", "description": "imagination|simulate|counterfactual|recombine|model|dream|critique", "default": "imagination"},
                    "ttl_days": {"type": "integer", "description": "Decay window in days", "default": 30},
                },
                "required": ["topic", "content"],
            },
        )
        self.tools["memory_promote"] = mt.Tool(
            name="memory_promote",
            title="Promote Simulated -> Grounded",
            description=("Promote a simulated fact into grounded memory ONLY via an explicit gate: "
                         "supply a non-empty `confirmation`, or set resolved_via_prediction_error=true "
                         "with a resolution_note. Otherwise promotion is refused."),
            inputSchema={
                "type": "object",
                "properties": {
                    "sim_id": {"type": "string", "description": "ID of the simulated fact to promote"},
                    "confirmation": {"type": "string", "description": "External confirmation that the simulation was validated", "default": ""},
                    "resolved_via_prediction_error": {"type": "boolean", "description": "Promote because a real-world prediction-error resolved in its favor", "default": False},
                    "resolution_note": {"type": "string", "description": "Note describing the prediction-error resolution", "default": ""},
                },
                "required": ["sim_id"],
            },
        )
        self.tools["memory_list_simulated"] = mt.Tool(
            name="memory_list_simulated",
            title="List Simulated Partition",
            description="List active (non-quarantined, non-expired) simulated facts from the separate partition.",
            inputSchema={
                "type": "object",
                "properties": {
                    "active_only": {"type": "boolean", "description": "Exclude quarantined/expired", "default": True},
                },
                "required": [],
            },
        )
        self.tools["memory_quarantine_simulated"] = mt.Tool(
            name="memory_quarantine_simulated",
            title="Decay / Quarantine Simulated",
            description="Quarantine simulated facts whose TTL (decay window) has expired.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        )
        self.tools["memory_audit_contamination"] = mt.Tool(
            name="memory_audit_contamination",
            title="Audit Memory Contamination",
            description=("Periodic provenance audit: detect any high-confidence memory whose ultimate "
                         "provenance is simulation, and any simulated content leaking into grounded indexes."),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        )
        self.tools["memory_epistemic_veto"] = mt.Tool(
            name="memory_epistemic_veto",
            title="Epistemic Veto",
            description=("Epistemic-layer veto: refuse a plan that rests primarily on unvalidated "
                         "simulated/imagined beliefs. Pass the fact_ids the plan depends on."),
            inputSchema={
                "type": "object",
                "properties": {
                    "fact_ids": {"type": "array", "items": {"type": "string"}, "description": "Fact IDs the plan relies on"},
                },
                "required": ["fact_ids"],
            },
        )
        self.tools["memory_pin_block"] = mt.Tool(
            name="memory_pin_block",
            title="Pin Memory Block",
            description="Pin a memory block as a core reference (immune to pruning/supersede)",
            inputSchema={
                "type": "object",
                "properties": {
                    "block_id": {"type": "string", "description": "Unique block identifier"},
                    "content": {"type": "string", "description": "Block content"},
                    "reason": {"type": "string", "description": "Reason for pinning", "default": ""},
                },
                "required": ["block_id", "content"],
            },
        )
        self.tools["memory_unpin_block"] = mt.Tool(
            name="memory_unpin_block",
            title="Unpin Memory Block",
            description="Unpin a previously pinned block",
            inputSchema={
                "type": "object",
                "properties": {
                    "block_id": {"type": "string", "description": "Block identifier"},
                },
                "required": ["block_id"],
            },
        )
        self.tools["memory_list_pinned_blocks"] = mt.Tool(
            name="memory_list_pinned_blocks",
            title="List Pinned Blocks",
            description="List all pinned memory blocks",
            inputSchema={"type": "object", "properties": {}},
        )
        self.tools["memory_get_pinned_block"] = mt.Tool(
            name="memory_get_pinned_block",
            title="Get Pinned Block",
            description="Get a specific pinned block",
            inputSchema={
                "type": "object",
                "properties": {
                    "block_id": {"type": "string", "description": "Block identifier"},
                },
                "required": ["block_id"],
            },
        )
        self.tools["memory_ingest_pdf"] = mt.Tool(
            name="memory_ingest_pdf",
            title="Ingest PDF",
            description="Extract text from PDF and store as memories",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to PDF file"},
                    "topic": {"type": "string", "description": "Topic for extracted content", "default": "document"},
                    "chunk_size": {"type": "integer", "description": "Chunk size for large PDFs", "default": 1000},
                },
                "required": ["file_path"],
            },
        )
        self.tools["memory_ingest_image"] = mt.Tool(
            name="memory_ingest_image",
            title="Ingest Image (OCR)",
            description="Extract text from image using OCR and store as memories",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to image file"},
                    "topic": {"type": "string", "description": "Topic for extracted content", "default": "image"},
                    "language": {"type": "string", "description": "OCR language", "default": "eng"},
                },
                "required": ["file_path"],
            },
        )
        self.tools["memory_ingest_audio"] = mt.Tool(
            name="memory_ingest_audio",
            title="Ingest Audio (Transcription)",
            description="Transcribe audio file using Whisper and store as memories",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to audio file"},
                    "topic": {"type": "string", "description": "Topic for transcribed content", "default": "audio"},
                    "model": {"type": "string", "description": "Whisper model size", "default": "base", "enum": ["tiny", "base", "small", "medium", "large"]},
                },
                "required": ["file_path"],
            },
        )
        self.tools["memory_ingest_code"] = mt.Tool(
            name="memory_ingest_code",
            title="Ingest Code (AST Parsing)",
            description="Parse code files using tree-sitter and extract structural information",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to code file"},
                    "topic": {"type": "string", "description": "Topic for extracted content", "default": "code"},
                    "language": {"type": "string", "description": "Programming language", "default": "python"},
                },
                "required": ["file_path"],
            },
        )
        self.tools["memory_namespace_create"] = mt.Tool(
            name="memory_namespace_create",
            title="Create Memory Namespace",
            description="Create a namespaced memory scope for multi-agent isolation",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "Namespace identifier (e.g., 'agent_1', 'project_alpha')"},
                    "owner": {"type": "string", "description": "Owner agent/user", "default": "agent"},
                    "acl": {"type": "object", "description": "Access control list {agent: permission}", "default": {}},
                    "actor": {"type": "string", "description": "Authenticated actor requesting the change; required to modify an existing namespace and defaults to owner for a new one"},
                },
                "required": ["namespace"],
            },
        )
        self.tools["memory_namespace_list"] = mt.Tool(
            name="memory_namespace_list",
            title="List Memory Namespaces",
            description="List all memory namespaces and their ACLs",
            inputSchema={"type": "object", "properties": {}},
        )
        self.tools["memory_shared_store"] = mt.Tool(
            name="memory_shared_store",
            title="Store in Shared Memory",
            description="Store a fact in a shared namespace with ACL checking",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "Shared namespace"},
                    "content": {"type": "string", "description": "Content to store"},
                    "tags": {"type": "string", "description": "Comma-separated tags", "default": ""},
                    "actor": {"type": "string", "description": "Acting agent", "default": "agent"},
                },
                "required": ["namespace", "content"],
            },
        )
        self.tools["memory_shared_recall"] = mt.Tool(
            name="memory_shared_recall",
            title="Recall from Shared Memory",
            description="Recall facts from a shared namespace with ACL checking",
            inputSchema={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "Shared namespace"},
                    "query": {"type": "string", "description": "Search query"},
                    "actor": {"type": "string", "description": "Acting agent", "default": "agent"},
                    "k": {"type": "integer", "default": 10},
                },
                "required": ["namespace", "query"],
            },
        )
        self.tools["memory_scan_pii"] = mt.Tool(
            name="memory_scan_pii",
            title="Scan for PII/Secrets",
            description="Scan content for PII, secrets, API keys, and sensitive data",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Content to scan"},
                    "action": {"type": "string", "enum": ["detect", "redact", "quarantine"], "description": "Action to take", "default": "detect"},
                },
                "required": ["content"],
            },
        )
        self.tools["self_model_create"] = mt.Tool(
            name="self_model_create",
            title="Create Self-Model",
            description="Create or update the agent's persistent self-model with capabilities, values, and history",
            inputSchema={
                "type": "object",
                "properties": {
                    "capabilities": {"type": "array", "items": {"type": "string"}, "description": "Agent capabilities", "default": []},
                    "values": {"type": "array", "items": {"type": "string"}, "description": "Core values", "default": []},
                    "identity": {"type": "string", "description": "Identity description", "default": ""},
                    "actor": {"type": "string", "description": "Authenticated identity performing the write; must be the owner of that identity or an authorised delegate", "default": ""},
                },
                "required": ["identity"],
            },
        )
        self.tools["self_model_get"] = mt.Tool(
            name="self_model_get",
            title="Get Self-Model",
            description="Retrieve a self-model by identity, or list the self-model registry when no identity is given",
            inputSchema={
                "type": "object",
                "properties": {
                    "identity": {"type": "string", "description": "Identity whose self-model to retrieve; omit to list all registered identities", "default": ""},
                    "k": {"type": "integer", "description": "Maximum records to summarise", "default": 10},
                },
            },
        )
        self.tools["self_model_reflect"] = mt.Tool(
            name="self_model_reflect",
            title="Self-Model Reflection",
            description="Metacognitive reflection on own capabilities, gaps, and belief updates",
            inputSchema={
                "type": "object",
                "properties": {
                    "focus": {"type": "string", "enum": ["capabilities", "gaps", "beliefs", "values", "all"], "description": "Reflection focus", "default": "all"},
                    "identity": {"type": "string", "description": "Identity to reflect on; omit to use the most recently updated identity", "default": ""},
                },
                "required": [],
            },
        )

    async def _memory_store(self, args: Dict) -> str:
        content = args.get("content", "")
        category = args.get("category", "general")
        tags_str = args.get("tags", "")
        tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []
        
        try:
            rec = remember(topic=category, content=content, tags=tags, priority="normal")
            return f"Stored in mem20 memory: [{category}] {content} (tags: {tags_str})\nRecord ID: {rec['id']}"
        except Exception as e:
            return f"Error storing memory: {str(e)}"
    async def _memory_recall(self, args: Dict) -> str:
        query = args.get("query", "")
        category = args.get("category", "")
        limit = args.get("limit", 10)
        
        try:
            # Search by topic if category provided, otherwise search all
            results = recall(topic=category if category else None, k=limit)
            
            if not results:
                return f"No memories found for query: '{query}' (category: {category})"
            
            output = f"Memory recall results for '{query}' (category: {category}, limit: {limit}):\n\n"
            for r in results:
                ts = r.get('ts', '')[:19]
                topic = r.get('topic', '-')
                pri = r.get('priority', '-')
                content = r.get('content', '')[:500]
                output += f"[{ts}] {topic} (pri={pri})\n   {content}\n\n"
            return output
        except Exception as e:
            return f"Error recalling memory: {str(e)}"
    async def _memory_probe(self, args: Dict) -> str:
        entity = args.get("entity", "")
        min_trust = args.get("min_trust", 0.3)
        
        try:
            # Search for facts about this entity
            results = recall(topic=None, k=20)
            filtered = [r for r in results if entity.lower() in r.get('content', '').lower()]
            
            if not filtered:
                return f"No facts found about entity: '{entity}'"
            
            output = f"Facts about entity '{entity}':\n\n"
            for r in filtered[:10]:
                ts = r.get('ts', '')[:19]
                topic = r.get('topic', '-')
                pri = r.get('priority', '-')
                content = r.get('content', '')[:500]
                output += f"[{ts}] {topic} (pri={pri})\n   {content}\n\n"
            return output
        except Exception as e:
            return f"Error probing entity: {str(e)}"
    async def _memory_reason(self, args: Dict) -> str:
        entities = args.get("entities", [])
        min_trust = args.get("min_trust", 0.3)
        
        try:
            # Get facts for all entities
            all_facts = []
            for entity in entities:
                results = recall(topic=None, k=20)
                filtered = [r for r in results if entity.lower() in r.get('content', '').lower()]
                all_facts.extend(filtered)
            
            if not all_facts:
                return f"No facts found for entities: {entities}"
            
            output = f"Reasoning across entities: {entities}\n\n"
            # Deduplicate
            seen = set()
            for r in all_facts:
                content = r.get('content', '')
                if content not in seen:
                    seen.add(content)
                    ts = r.get('ts', '')[:19]
                    topic = r.get('topic', '-')
                    pri = r.get('priority', '-')
                    output += f"[{ts}] {topic} (pri={pri})\n   {content[:500]}\n\n"
            return output
        except Exception as e:
            return f"Error reasoning across entities: {str(e)}"
    async def _memory_status(self) -> str:
        try:
            return mem_status()
        except Exception as e:
            return f"Error getting memory status: {str(e)}"
    async def _memory_recall_semantic(self, args: Dict) -> str:
        """Pure vector-based semantic search using embeddings."""
        query = args.get("query", "")
        k = args.get("k", 5)
        topic = args.get("topic", "")
        tags_str = args.get("tags", "")
        rerank = args.get("rerank", True)
        tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []

        if not query:
            return "Error: query is required"

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import recall_semantic
            
            results = recall_semantic(query, k, topic if topic else None, tags)
            
            if not results:
                return f"No semantic matches for: '{query}'"
            
            output = f"**Semantic Recall: '{query}'** (k={k}, rerank={rerank})\n\n"
            for r in results:
                if "error" in r:
                    output += f"Error: {r['error']}\n"
                else:
                    ts = r.get('ts', '')[:19]
                    topic_name = r.get('topic', '-')
                    pri = r.get('priority', '-')
                    score = r.get('score', 0)
                    content = r.get('content', '')[:500]
                    output += f"[{score:.3f}] [{ts}] {topic_name} (pri={pri})\n   {content}\n\n"
            return output
        except Exception as e:
            return f"Error in semantic recall: {str(e)}"
    async def _memory_recall_hybrid(self, args: Dict) -> str:
        """Hybrid BM25 + vector search with RRF and optional cross-encoder reranking."""
        query = args.get("query", "")
        k = args.get("k", 5)
        topic = args.get("topic", "")
        tags_str = args.get("tags", "")
        alpha = args.get("alpha", 0.5)
        rerank = args.get("rerank", True)
        tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []

        if not query:
            return "Error: query is required"

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import recall_hybrid
            
            results = recall_hybrid(query, k, topic if topic else None, tags, alpha)
            
            if not results:
                return f"No hybrid matches for: '{query}'"
            
            output = f"**Hybrid Recall: '{query}'** (k={k}, alpha={alpha}, rerank={rerank})\n\n"
            for r in results:
                if "error" in r:
                    output += f"Error: {r['error']}\n"
                else:
                    ts = r.get('ts', '')[:19]
                    topic_name = r.get('topic', '-')
                    pri = r.get('priority', '-')
                    score = r.get('score', 0)
                    content = r.get('content', '')[:500]
                    vr = r.get('_vector_rank', 'N/A')
                    br = r.get('_bm25_rank', 'N/A')
                    ce = r.get('_ce_score', 'N/A')
                    output += f"[{score:.3f}] [{ts}] {topic_name} (pri={pri})\n   V-rank: {vr}, BM25-rank: {br}, CE: {ce}\n   {content}\n\n"
            return output
        except Exception as e:
            return f"Error in hybrid recall: {str(e)}"

    async def _memory_recall_graph(self, args: Dict) -> str:
        """Multi-hop entity traversal over the persisted graph index."""
        entity = args.get("entity", "")
        hops = int(args.get("hops", 2))
        max_results = int(args.get("max_results", 20))
        min_facts = int(args.get("min_facts", 1))
        topic = args.get("topic", "") or None

        if not entity:
            return "Error: entity is required"

        try:
            m = _engine()
            r = m.recall_graph(entity, hops=hops, max_results=max_results,
                               min_facts=min_facts, topic=topic)

            if not r.get("found"):
                err = r.get("error", "not found")
                if r.get("known_entities"):
                    err += f" ({r['known_entities']} entities in graph)"
                return f"Graph recall miss for '{entity}': {err}"

            out = (f"**Graph Recall: {r['start']}** (hops={hops}, "
                   f"{r['entity_count']} entities, {r['fact_count']} facts)\n")
            out += (f"_Graph holds {r['graph_entities']} entities / "
                    f"{r['graph_edges']} edges_\n\n")

            out += "Entities:\n"
            for e in r["entities"]:
                mark = " <- start" if e["is_start"] else ""
                out += (f"  hop {e['hop']}: {e['entity']}{mark} "
                        f"({e['fact_count']} facts, topics={e['topics']})\n")

            if r["facts"]:
                out += "\nFacts:\n"
                for f in r["facts"]:
                    out += (f"  [{f['topic']}] {f['content'][:200]}\n")
            return out
        except Exception as e:
            return f"Error in graph recall: {type(e).__name__}: {str(e)}"

    async def _memory_index_health(self, args: Dict) -> str:
        """Report index/ledger agreement with exact counts."""
        try:
            h = _engine().index_health()
            lines = [f"**Retrieval index health** — store `{h['store']}`",
                     f"Ledger records: **{h['ledger_records']}**", ""]
            for key, idx in h["indexes"].items():
                if not idx.get("present"):
                    lines.append(f"- `{key}`: **ABSENT** — run rebuild to create it")
                    continue
                status = "ok" if idx.get("healthy") else "**DRIFTED**"
                detail = []
                if "indexed" in idx:
                    detail.append(f"{idx['resolvable']}/{idx['indexed']} resolvable")
                if idx.get("missing_from_ledger"):
                    detail.append(f"{idx['missing_from_ledger']} stale pointers")
                if "entities" in idx:
                    detail.append(f"{idx['entities']} entities, "
                                  f"{idx.get('edges', 0)} edges")
                if idx.get("meta_matches_index") is False:
                    detail.append("metadata/FAISS count mismatch")
                lines.append(f"- `{key}`: {status} — {', '.join(detail) or 'ok'}")

            lines.append("")
            lines.append("**Overall: " + ("healthy" if h["healthy"] else "NEEDS REBUILD") + "**")
            if not h["healthy"]:
                lines.append("\nStale pointers mean search matches records that no "
                             "longer exist. Run `rebuild_vectors`, `rebuild_bm25`, "
                             "and `rebuild_graph` to reindex from the ledger.")
            return "\n".join(lines)
        except Exception as e:
            return f"Error reading index health: {type(e).__name__}: {str(e)}"
    async def _memory_entity_extract(self, args: Dict) -> str:
        """Extract entities and relationships from text using spaCy/LLM."""
        text = args.get("text", "")
        topic = args.get("topic", "general")
        store = args.get("store", True)

        if not text:
            return "Error: text is required"

        try:
            # Try spaCy first
            entities = []
            relationships = []
            
            try:
                import spacy
                nlp = spacy.load("en_core_web_sm")
                doc = nlp(text)
                
                for ent in doc.ents:
                    entities.append({
                        "text": ent.text,
                        "label": ent.label_,
                        "start": ent.start_char,
                        "end": ent.end_char
                    })
            except Exception:
                # Fallback: simple regex-based extraction
                import re
                # Find capitalized words and phrases
                candidates = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
                for c in set(candidates):
                    entities.append({
                        "text": c,
                        "label": "ENTITY",
                        "start": text.find(c),
                        "end": text.find(c) + len(c)
                    })
            
            # Extract simple relationships (subject-verb-object patterns)
            # This is a simplified version - could be enhanced with LLM
            import re
            svos = re.findall(r'(\b\w+\b)\s+(is|has|contains|uses|creates|manages|controls|depends on)\s+(\b\w+\b)', text, re.IGNORECASE)
            for subj, verb, obj in svos:
                relationships.append({
                    "subject": subj,
                    "predicate": verb,
                    "object": obj
                })
            
            output = f"**Entity Extraction** (topic: {topic})\n\n"
            output += f"**Entities ({len(entities)}):**\n"
            for e in entities[:20]:
                output += f"  • {e['text']} ({e['label']})\n"
            
            output += f"\n**Relationships ({len(relationships)}):**\n"
            for r in relationships[:20]:
                output += f"  • {r['subject']} --[{r['predicate']}]--> {r['object']}\n"
            
            if store and (entities or relationships):
                # Store as memories
                sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
                from memory import remember
                
                for e in entities:
                    remember(topic=topic, content=f"Entity: {e['text']} (type: {e['label']})", tags=["entity", e['label'].lower()])
                
                for r in relationships:
                    remember(topic=topic, content=f"Relation: {r['subject']} --[{r['predicate']}]--> {r['object']}", tags=["relationship", r['predicate'].lower()])
                
                output += "\n✅ Stored extracted entities and relationships in memory"
            
            return output
        except Exception as e:
            return f"Error in entity extraction: {str(e)}"
    async def _memory_auto_consolidate(self, args: Dict) -> str:
        """Cluster similar memories and generate higher-level summaries."""
        topic = args.get("topic", "")
        min_cluster_size = args.get("min_cluster_size", 3)
        similarity_threshold = args.get("similarity_threshold", 0.75)
        generate_summaries = args.get("generate_summaries", True)

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import _load_ledger, SUPERSEDED, remember
            import numpy as np
            
            recs = _load_ledger()
            facts = [r for r in recs 
                    if r.get("action") == "remember" 
                    and SUPERSEDED not in r.get("content", "")
                    and (not topic or topic.lower() in r.get("topic", "").lower())]
            
            if len(facts) < min_cluster_size:
                return f"Not enough facts ({len(facts)}) for consolidation (min: {min_cluster_size})"
            
            # Use vector embeddings for clustering if available
            try:
                from sentence_transformers import SentenceTransformer
                embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
                
                texts = [f"{f.get('topic', '')}: {f.get('content', '')}" for f in facts]
                embeddings = embedder.encode(texts, convert_to_numpy=True)
                
                # Normalize
                norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
                norms[norms == 0] = 1
                embeddings = embeddings / norms
                
                # Simple agglomerative clustering
                clusters = []
                assigned = set()
                
                for i, emb in enumerate(embeddings):
                    if i in assigned:
                        continue
                    cluster = [i]
                    assigned.add(i)
                    
                    for j, emb2 in enumerate(embeddings):
                        if j in assigned:
                            continue
                        sim = np.dot(emb, emb2)
                        if sim >= similarity_threshold:
                            cluster.append(j)
                            assigned.add(j)
                    
                    if len(cluster) >= min_cluster_size:
                        clusters.append(cluster)
                
                output = f"**Auto Consolidation** (topic: {topic or 'all'})\n\n"
                output += f"Total facts: {len(facts)}\n"
                output += f"Clusters formed: {len(clusters)}\n\n"
                
                for idx, cluster in enumerate(clusters):
                    cluster_facts = [facts[i] for i in cluster]
                    topics = set(f.get('topic', '') for f in cluster_facts)
                    output += f"**Cluster {idx+1}** ({len(cluster)} facts, topics: {', '.join(topics)})\n"
                    
                    if generate_summaries and len(cluster) >= 3:
                        # Generate summary using cognitive engine
                        try:
                            sys.path.insert(0, os.environ.get("MEM20_COG_PATH", os.environ.get("MEM20_COG_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cog"))))
                            from cognitive_engine import process_thought
                            
                            combined = "\n".join([f"- {f.get('content', '')[:300]}" for f in cluster_facts[:10]])
                            summary_prompt = f"Summarize these related memories into a higher-level observation:\n\n{combined}\n\nProvide a concise summary that captures the common theme."
                            summary = process_thought(summary_prompt, mode="synthesize")
                            
                            output += f"  Summary: {summary[:500]}\n"
                            
                            # Store summary as higher-level memory
                            remember(topic=f"{topic}_summary" if topic else "summary", 
                                   content=f"Consolidated summary (cluster {idx+1}): {summary}", 
                                   tags=["summary", "consolidated", f"cluster_{idx+1}"],
                                   priority="high")
                        except Exception:
                            output += f"  Summary: [generation failed]\n"
                    
                    output += "\n"
                
                return output
            except ImportError:
                return "Vector dependencies not installed for clustering (need sentence-transformers)"
                
        except Exception as e:
            return f"Error in auto consolidation: {str(e)}"
    async def _memory_assess_confidence(self, args: Dict) -> str:
        fact_id = args.get("fact_id", "")
        confidence = args.get("confidence", 0)

        if not fact_id:
            return "Error: fact_id is required"

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import assess_confidence
            
            result = assess_confidence(fact_id, confidence)
            return f"✅ Confidence assessed: {result['id']} = {result['confidence']}"
        except Exception as e:
            return f"Error assessing confidence: {str(e)}"
    async def _memory_set_epistemic_status(self, args: Dict) -> str:
        fact_id = args.get("fact_id", "")
        status = args.get("status", "")

        if not fact_id or not status:
            return "Error: fact_id and status are required"

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import set_epistemic_status
            
            result = set_epistemic_status(fact_id, status)
            return f"✅ Epistemic status set: {result['id']} = {result['epistemic_status']}"
        except Exception as e:
            return f"Error setting epistemic status: {str(e)}"
    async def _memory_detect_gaps(self, args: Dict) -> str:
        topic = args.get("topic", "")
        threshold = args.get("threshold", 0.5)

        if not topic:
            return "Error: topic is required"

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import detect_knowledge_gaps
            
            result = detect_knowledge_gaps(topic, threshold)
            output = f"**Knowledge Gap Analysis: {result['topic']}**\n\n"
            output += f"Total Memories: {result['total_memories']}\n"
            output += f"Average Confidence: {result['avg_confidence']:.2f}\n"
            output += f"Coverage Score: {result['coverage_score']:.2f}\n\n"
            output += "Gaps:\n"
            for gap in result['gaps']:
                output += f"  • {gap}\n"
            if result['low_confidence_subtopics']:
                output += f"\nLow Confidence Subtopics: {', '.join(result['low_confidence_subtopics'])}"
            return output
        except Exception as e:
            return f"Error detecting gaps: {str(e)}"
    async def _memory_self_audit(self, args: Dict) -> str:
        fact_id = args.get("fact_id", "")
        topic = args.get("topic", "")

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import self_audit
            
            result = self_audit(fact_id if fact_id else None, topic if topic else None)
            
            if "error" in result:
                return result["error"]
            
            output = "**Self Audit Results**\n\n"
            for k, v in result.items():
                if isinstance(v, list):
                    output += f"{k}:\n"
                    for item in v:
                        if item:
                            output += f"  • {item}\n"
                elif v is not None:
                    output += f"{k}: {v}\n"
            return output
        except Exception as e:
            return f"Error in self audit: {str(e)}"
    async def _memory_simulate_store(self, args: Dict) -> str:
        topic = args.get("topic", "")
        content = args.get("content", "")
        if not topic or not content:
            return "Error: topic and content are required"
        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import remember_simulated
            rec = remember_simulated(
                topic=topic,
                content=content,
                tags=args.get("tags", []) or [],
                scenario=args.get("scenario", "") or None,
                sim_type=args.get("sim_type", "imagination"),
                ttl_days=int(args.get("ttl_days", 30)),
            )
            return (f"Stored SIMULATED fact (partition=simulated, origin=simulated, "
                    f"id={rec['id']}). It is NOT in grounded memory and cannot promote "
                    f"without explicit confirmation / prediction-error resolution.")
        except Exception as e:
            return f"Error storing simulated fact: {e}"
    async def _memory_promote(self, args: Dict) -> str:
        sim_id = args.get("sim_id", "")
        if not sim_id:
            return "Error: sim_id is required"
        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import promote_simulated_to_grounded
            res = promote_simulated_to_grounded(
                sim_id,
                confirmation=args.get("confirmation", "") or None,
                resolved_via_prediction_error=bool(args.get("resolved_via_prediction_error", False)),
                resolution_note=args.get("resolution_note", "") or "",
                prediction_error_evidence=args.get("prediction_error_evidence"),
            )
            return f"PROMOTED -> grounded_id={res['grounded_id']}. {res['note']}"
        except PermissionError as e:
            return f"VETO / BLOCKED: {e}"
        except Exception as e:
            return f"Error promoting simulated fact: {e}"
    async def _memory_list_simulated(self, args: Dict) -> str:
        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import list_simulated
            res = list_simulated(active_only=bool(args.get("active_only", True)))
            if not res["count"]:
                return "Simulated partition is empty."
            out = [f"Simulated partition ({res['count']} active):"]
            for r in res["simulated"]:
                out.append(f"- [{r['id']}] {r.get('topic')} ({r.get('sim_type')}) valid_to={r.get('valid_to')}")
                out.append(f"    {str(r.get('content'))[:160]}")
            return "\n".join(out)
        except Exception as e:
            return f"Error listing simulated facts: {e}"
    async def _memory_quarantine_simulated(self, args: Dict) -> str:
        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import quarantine_expired_simulated
            res = quarantine_expired_simulated()
            return f"Quarantined {res['count']} expired simulated fact(s): {res['quarantined']}"
        except Exception as e:
            return f"Error quarantining simulated facts: {e}"
    async def _memory_audit_contamination(self, args: Dict) -> str:
        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import audit_contamination
            res = audit_contamination()
            out = ["**Memory Contamination Audit (Step 7.4)**", ""]
            out.append(f"status: {res['status']}")
            out.append(f"grounded_facts: {res['grounded_facts']}")
            out.append(f"simulated_facts: {res['simulated_facts']}")
            out.append(f"promoted_count: {res['promoted_count']}")
            out.append(f"contamination_rate: {res['contamination_rate']}")
            if res["validated_simulation_derived"]:
                out.append(f"validated_simulation_derived: {len(res['validated_simulation_derived'])} (promoted via explicit gate)")
            if res["violations_origin_not_grounded"]:
                out.append(f"VIOLATIONS origin!=grounded: {res['violations_origin_not_grounded']}")
            if res["violations_simulated_in_grounded_index"]:
                out.append(f"VIOLATIONS simulated in grounded index: {res['violations_simulated_in_grounded_index']}")
            out.append(f"recommendation: {res['recommendation']}")
            return "\n".join(out)
        except Exception as e:
            return f"Error auditing contamination: {e}"
    async def _memory_epistemic_veto(self, args: Dict) -> str:
        fact_ids = args.get("fact_ids", []) or []
        if not fact_ids:
            return "Error: fact_ids required"
        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import epistemic_veto
            res = epistemic_veto(fact_ids)
            out = [f"VETO: {res['veto']}", res["message"]]
            for o in res["offenders"]:
                out.append(f"  - {o['fact_id']}: {o['reason']}")
            return "\n".join(out)
        except Exception as e:
            return f"Error running epistemic veto: {e}"
    async def _memory_pin_block(self, args: Dict) -> str:
        block_id = args.get("block_id", "")
        content = args.get("content", "")
        reason = args.get("reason", "")

        if not block_id or not content:
            return "Error: block_id and content are required"

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import pin_block
            
            result = pin_block(block_id, content, reason)
            return f"✅ Pinned: {result['block_id']} ({result['pinned']})"
        except Exception as e:
            return f"Error pinning block: {str(e)}"
    async def _memory_unpin_block(self, args: Dict) -> str:
        block_id = args.get("block_id", "")

        if not block_id:
            return "Error: block_id is required"

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import unpin_block
            
            result = unpin_block(block_id)
            return f"✅ Unpinned: {result['block_id']} ({result['pinned']})"
        except Exception as e:
            return f"Error unpinning block: {str(e)}"
    async def _memory_list_pinned_blocks(self, args: Dict) -> str:
        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import list_pinned_blocks
            
            result = list_pinned_blocks()
            blocks = result.get('pinned_blocks', {})
            order = result.get('order', [])
            
            if not blocks:
                return "No pinned blocks"
            
            output = f"**Pinned Blocks ({len(blocks)})**\n\n"
            for bid in order:
                b = blocks[bid]
                output += f"• **{bid}**: {b['content'][:100]}... (reason: {b['reason']}, ts: {b['pinned_ts']})\n"
            return output
        except Exception as e:
            return f"Error listing pinned blocks: {str(e)}"
    async def _memory_get_pinned_block(self, args: Dict) -> str:
        block_id = args.get("block_id", "")

        if not block_id:
            return "Error: block_id is required"

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import get_pinned_block
            
            result = get_pinned_block(block_id)
            if "error" in result:
                return result["error"]
            
            output = f"**Pinned Block: {result['block_id']}**\n\n"
            output += f"Content: {result['content']}\n"
            output += f"Reason: {result['reason']}\n"
            output += f"Pinned: {result['pinned_ts']}"
            return output
        except Exception as e:
            return f"Error getting pinned block: {str(e)}"
    async def _memory_ingest_pdf(self, args: Dict) -> str:
        file_path = args.get("file_path", "")
        topic = args.get("topic", "document")
        chunk_size = args.get("chunk_size", 1000)

        if not file_path:
            return "Error: file_path is required"

        try:
            import fitz  # PyMuPDF
            doc = fitz.open(file_path)
            
            full_text = ""
            for page_num in range(len(doc)):
                page = doc[page_num]
                full_text += page.get_text()
            
            doc.close()
            
            if not full_text.strip():
                return f"No text extracted from PDF: {file_path}"
            
            # Chunk the text
            chunks = [full_text[i:i+chunk_size] for i in range(0, len(full_text), chunk_size)]
            
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import remember
            
            stored_count = 0
            for i, chunk in enumerate(chunks):
                if chunk.strip():
                    remember(
                        topic=topic,
                        content=f"[PDF Chunk {i+1}/{len(chunks)}] {chunk}",
                        tags=["pdf", "ingested", f"chunk_{i+1}"],
                        source=file_path
                    )
                    stored_count += 1
            
            return f"✅ PDF ingested: {file_path}\nPages: {len(doc) if 'doc' in locals() else 'N/A'}\nChunks stored: {stored_count}\nTopic: {topic}"
        except ImportError:
            return "PyMuPDF not installed. Install with: pip install pymupdf"
        except Exception as e:
            return f"Error ingesting PDF: {str(e)}"
    async def _memory_ingest_image(self, args: Dict) -> str:
        file_path = args.get("file_path", "")
        topic = args.get("topic", "image")
        language = args.get("language", "eng")

        if not file_path:
            return "Error: file_path is required"

        try:
            import pytesseract
            from PIL import Image
            
            image = Image.open(file_path)
            text = pytesseract.image_to_string(image, lang=language)
            image.close()
            
            if not text.strip():
                return f"No text extracted from image: {file_path}"
            
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import remember
            
            remember(
                topic=topic,
                content=f"[OCR from {file_path}] {text}",
                tags=["ocr", "image", "ingested"],
                source=file_path
            )
            
            return f"✅ Image OCR complete: {file_path}\nText length: {len(text)} chars\nTopic: {topic}\n\nExtracted text:\n{text[:500]}..."
        except ImportError:
            return "Dependencies not installed. Install with: pip install pytesseract pillow"
        except Exception as e:
            return f"Error in OCR: {str(e)}"
    async def _memory_ingest_audio(self, args: Dict) -> str:
        file_path = args.get("file_path", "")
        topic = args.get("topic", "audio")
        model = args.get("model", "base")

        if not file_path:
            return "Error: file_path is required"

        try:
            import whisper
            
            whisper_model = whisper.load_model(model)
            result = whisper_model.transcribe(file_path)
            text = result.get("text", "")
            
            if not text.strip():
                return f"No speech detected in audio: {file_path}"
            
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import remember
            
            remember(
                topic=topic,
                content=f"[Transcription from {file_path}] {text}",
                tags=["transcription", "audio", "ingested", f"model_{model}"],
                source=file_path
            )
            
            return f"✅ Audio transcribed: {file_path}\nModel: {model}\nLanguage: {result.get('language', 'unknown')}\nText length: {len(text)} chars\n\nTranscription:\n{text[:500]}..."
        except ImportError:
            return "Whisper not installed. Install with: pip install openai-whisper"
        except Exception as e:
            return f"Error transcribing audio: {str(e)}"
    async def _memory_ingest_code(self, args: Dict) -> str:
        file_path = args.get("file_path", "")
        topic = args.get("topic", "code")
        language = args.get("language", "python")

        if not file_path:
            return "Error: file_path is required"

        try:
            # Try tree-sitter first
            try:
                from tree_sitter import Language, Parser
                # This would need language-specific parsers - simplified fallback
                raise ImportError("tree-sitter languages not configured")
            except ImportError:
                # Fallback: simple AST parsing for Python
                import ast
                
                with open(file_path, 'r') as f:
                    code = f.read()
                
                tree = ast.parse(code)
                
                # Extract structural info
                classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
                functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
                imports = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imports.extend([alias.name for alias in node.names])
                    elif isinstance(node, ast.ImportFrom):
                        imports.append(f"{node.module}.{', '.join(alias.name for alias in node.names)}")
                
                summary = f"File: {file_path}\nLanguage: {language}\nClasses: {', '.join(classes) if classes else 'None'}\nFunctions: {', '.join(functions) if functions else 'None'}\nImports: {', '.join(imports) if imports else 'None'}\n\nFull code:\n{code[:2000]}"
                
                sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
                from memory import remember
                
                remember(
                    topic=topic,
                    content=f"[Code Analysis: {file_path}]\n{summary}",
                    tags=["code", "ast", "ingested", language],
                    source=file_path
                )
                
                return f"✅ Code ingested: {file_path}\nClasses: {len(classes)}\nFunctions: {len(functions)}\nImports: {len(imports)}\n\n{summary[:1000]}..."
        except Exception as e:
            return f"Error ingesting code: {str(e)}"
    async def _memory_namespace_create(self, args: Dict) -> str:
        namespace = args.get("namespace", "")
        owner = args.get("owner", "agent")
        acl = args.get("acl", {})

        if not namespace:
            return "Error: namespace is required"

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import recall, remember

            existing = _namespace_meta(namespace, recall)
            if existing is not None:
                effective_actor = args.get("actor") or owner
                allowed, reason = _check_namespace_access(existing, effective_actor, "admin")
                if not allowed:
                    return f"Access denied: {reason}"

            if not isinstance(acl, dict):
                return "Error: acl must be an object mapping actor to permission"
            payload = {"namespace": namespace, "owner": owner, "acl": {str(k): str(v) for k, v in acl.items()}}
            remember(
                topic=_NAMESPACE_META_TOPIC,
                content=_NAMESPACE_META_PREFIX + json.dumps(payload, sort_keys=True),
                tags=["namespace", "metadata", namespace],
                priority="high",
                actor=args.get("actor") or owner
            )

            return f"✅ Namespace created: {namespace}\nOwner: {owner}\nACL: {payload['acl']}"
        except Exception as e:
            return f"Error creating namespace: {str(e)}"
    async def _memory_namespace_list(self, args: Dict) -> str:
        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import recall
            
            results = recall(topic="namespace_meta", k=50)
            
            if not results:
                return "No namespaces found"
            
            output = "**Memory Namespaces**\n\n"
            for r in results:
                content = r.get('content', '')
                output += f"• {content}\n"
            return output
        except Exception as e:
            return f"Error listing namespaces: {str(e)}"
    async def _memory_shared_store(self, args: Dict) -> str:
        namespace = args.get("namespace", "")
        content = args.get("content", "")
        tags_str = args.get("tags", "")
        actor = args.get("actor", "agent")
        tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []

        if not namespace or not content:
            return "Error: namespace and content are required"

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import recall, remember

            allowed, reason, _ = _namespace_access(namespace, actor, "write", recall)
            if not allowed:
                return f"Access denied: {reason}"

            remember(
                topic=f"{_NAMESPACE_CONTENT_TOPIC}{namespace}",
                content=content,
                tags=tags + ["shared", namespace, f"actor_{actor}"],
                actor=actor
            )

            return f"✅ Stored in shared namespace: {namespace}\nActor: {actor}\nTags: {tags}"
        except Exception as e:
            return f"Error storing in shared memory: {str(e)}"
    async def _memory_shared_recall(self, args: Dict) -> str:
        namespace = args.get("namespace", "")
        query = args.get("query", "")
        actor = args.get("actor", "agent")
        k = args.get("k", 10)

        if not namespace or not query:
            return "Error: namespace and query are required"

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import recall

            allowed, reason, _ = _namespace_access(namespace, actor, "read", recall)
            if not allowed:
                return f"Access denied: {reason}"

            results = _namespace_content_rows(namespace, recall, k)

            if not results:
                return f"No memories found in namespace: {namespace}"

            # Filter by query
            filtered = [r for r in results if query.lower() in r.get('content', '').lower()]
            
            output = f"**Shared Recall: '{query}' from {namespace}** (actor: {actor})\n\n"
            for r in filtered[:k]:
                ts = r.get('ts', '')[:19]
                topic = r.get('topic', '-')
                pri = r.get('priority', '-')
                content = r.get('content', '')[:500]
                output += f"[{ts}] {topic} (pri={pri})\n   {content}\n\n"
            return output
        except Exception as e:
            return f"Error recalling from shared memory: {str(e)}"
    async def _memory_scan_pii(self, args: Dict) -> str:
        content = args.get("content", "")
        action = args.get("action", "detect")

        if not content:
            return "Error: content is required"

        try:
            # Use the existing secret scrubbing from memory.py
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import _scrub_secrets
            
            cleaned, detected = _scrub_secrets(content)
            
            output = f"**PII/Secret Scan** (action: {action})\n\n"
            output += f"Original length: {len(content)} chars\n"
            output += f"Cleaned length: {len(cleaned)} chars\n"
            output += f"Secrets detected: {len(detected)}\n\n"
            
            if detected:
                output += "Detected:\n"
                for d in detected:
                    output += f"  • {d}\n"
            else:
                output += "No secrets detected.\n"
            
            if action == "redact":
                output += f"\n**Redacted Content:**\n{cleaned}"
            elif action == "quarantine":
                # Store in quarantine
                sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
                from memory import remember
                remember(
                    topic="quarantine",
                    content=f"Quarantined content (PII detected): {content}",
                    tags=["quarantine", "pii", "auto"],
                    priority="high"
                )
                output += "\n⚠️ Content quarantined in memory."
            
            return output
        except Exception as e:
            return f"Error scanning PII: {str(e)}"
    async def _self_model_create(self, args: Dict) -> str:
        capabilities = args.get("capabilities", [])
        values = args.get("values", [])
        identity = args.get("identity", "")
        actor = args.get("actor", "") or _slugify_identity(identity or "agent")

        if not identity:
            return ("Error: identity is required. Self-models are keyed per identity so that "
                    "coexisting agents never shadow each other; state who the model belongs to.")

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import recall, remember

            slug = _slugify_identity(identity)
            allowed, reason = _authorize_self_model_write(identity, actor, recall)
            if not allowed:
                return f"Access denied: {reason}"

            payload = {
                "identity": identity,
                "identity_key": slug,
                "capabilities": list(capabilities),
                "values": list(values),
                "actor": actor,
                "created": __import__('datetime').datetime.now().isoformat(),
                "legacy": False,
            }
            topic = f"{_SELF_MODEL_TOPIC_PREFIX}{slug}"
            remember(
                topic=topic,
                content=_SELF_MODEL_RECORD_PREFIX + json.dumps(payload, sort_keys=True),
                tags=["self_model", "identity", "core", slug],
                priority="high",
                actor=actor,
            )

            if _self_model_owner(identity, recall) is None:
                remember(
                    topic=f"{_SELF_MODEL_IDENTITY_TOPIC_PREFIX}{slug}",
                    content=_NAMESPACE_META_PREFIX
                    + json.dumps({"namespace": f"{_SELF_MODEL_IDENTITY_TOPIC_PREFIX}{slug}",
                                  "owner": actor, "acl": {}}, sort_keys=True),
                    tags=["self_model_identity", slug],
                    priority="high",
                    actor=actor,
                )

            return (f"Self-model recorded\nIdentity: {identity} (key: {slug})\n"
                    f"Written by: {actor} ({reason})\n"
                    f"Capabilities: {len(capabilities)}\nValues: {len(values)}")

        except Exception as e:
            return f"Error creating self-model: {str(e)}"

    async def _self_model_get(self, args: Dict) -> str:
        identity = args.get("identity", "")

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import recall

            if identity:
                rows = _self_model_rows(identity, recall, k=args.get("k", 10))
                if not rows:
                    return f"No self-model found for identity '{identity}'."
                latest = rows[0]
                owner = _self_model_owner(identity, recall)
                output = f"**Self-Model — {identity}**\n\n"
                output += f"identity key: {latest.get('identity_key')}\n"
                output += f"owner: {(owner or {}).get('owner', 'unregistered')}\n"
                output += f"records: {len(rows)}\n"
                output += f"created: {latest.get('created')}\n"
                output += f"written by: {latest.get('actor') or 'unknown (legacy record)'}\n"
                output += f"legacy: {latest.get('legacy', False)}\n\n"
                output += f"Identity text: {latest.get('identity')}\n\n"
                output += f"Capabilities ({len(latest.get('capabilities') or [])}):\n"
                for cap in latest.get("capabilities") or []:
                    output += f"  - {cap}\n"
                output += f"Values ({len(latest.get('values') or [])}):\n"
                for val in latest.get("values") or []:
                    output += f"  - {val}\n"
                return output

            grouped = _all_self_model_rows(recall)
            if not grouped:
                return "No self-model found. Create one first."
            output = "**Self-Model Registry**\n\n"
            output += (f"{len(grouped)} identit{'y' if len(grouped) == 1 else 'ies'} registered. "
                       "Each is stored under its own key; no identity shadows another.\n\n")
            for key in sorted(grouped):
                entries = grouped[key]
                latest = entries[0]
                owner = _self_model_owner(key, recall)
                output += (f"### {key}\n"
                           f"  records: {len(entries)}\n"
                           f"  owner: {(owner or {}).get('owner', 'unregistered')}\n"
                           f"  last written: {latest.get('created')}\n"
                           f"  written by: {latest.get('actor') or 'unknown (legacy record)'}\n"
                           f"  legacy records: {sum(1 for e in entries if e.get('legacy'))}\n\n")
            return output
        except Exception as e:
            return f"Error getting self-model: {str(e)}"
    async def _self_model_reflect(self, args: Dict) -> str:
        focus = args.get("focus", "all")

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import recall, self_audit

            target = args.get("identity", "")
            if not target:
                grouped = _all_self_model_rows(recall)
                if grouped:
                    target = max(
                        grouped,
                        key=lambda key: str(grouped[key][0].get("created") or ""),
                    )
                else:
                    target = ""

            if target:
                rows = _self_model_rows(target, recall, k=1)
                model_content = (
                    f"identity: {rows[0].get('identity')}\n"
                    f"written by: {rows[0].get('actor') or 'unknown (legacy record)'}\n"
                    f"created: {rows[0].get('created')}"
                    if rows
                    else f"No self-model found for identity '{target}'."
                )
            else:
                model_content = "No self-model found."

            audit = self_audit(topic=_SELF_MODEL_TOPIC_PREFIX if target else _LEGACY_SELF_MODEL_TOPIC)

            cap_results = recall(topic=None, k=20)
            cap_facts = [r for r in cap_results if 'capab' in r.get('content', '').lower()]

            output = f"**Self-Model Reflection** (focus: {focus})\n\n"
            output += f"Identity under reflection: {target or 'none registered'}\n\n"
            output += f"Current Model:\n{model_content}\n\n"
            output += f"Self-Audit:\n"
            for k, v in audit.items():
                if isinstance(v, list):
                    output += f"  {k}:\n"
                    for item in v:
                        if item:
                            output += f"    • {item}\n"
                elif v is not None:
                    output += f"  {k}: {v}\n"
            
            output += f"\nCapability Facts: {len(cap_facts)}"
            return output
        except Exception as e:
            return f"Error in self-model reflection: {str(e)}"
    async def _memory_contradict(self, args: Dict) -> str:
        topic = args.get("topic", "")
        min_trust = args.get("min_trust", 0.3)

        if not topic:
            return "Error: topic is required"

        try:
            # Load ledger and find facts for topic
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import _load_ledger, SUPERSEDED
            
            recs = _load_ledger()
            facts = [r for r in recs 
                    if r.get("action") == "remember" 
                    and SUPERSEDED not in r.get("content", "")
                    and topic.lower() in r.get("topic", "").lower()]
            
            if not facts:
                return f"No facts found for topic: {topic}"
            
            # Extract key claims from content using simple heuristics
            # Group by topic and look for contradictory claims within same topic
            from collections import defaultdict
            by_topic = defaultdict(list)
            for f in facts:
                t = f.get("topic", "unknown")
                by_topic[t].append(f)
            
            contradictions = []
            for t, group in by_topic.items():
                if len(group) > 1:
                    # Check for different claims/values in content
                    contents = [g.get("content", "") for g in group]
                    # Simple heuristic: if content differs significantly, might be contradiction
                    # Look for contradictory keywords
                    contradiction_indicators = ["not", "no ", "never", "cannot", "impossible", "false", "wrong", "incorrect"]
                    for i, c1 in enumerate(contents):
                        for j, c2 in enumerate(contents[i+1:], i+1):
                            # Check if one says X and other says not X
                            c1_lower = c1.lower()
                            c2_lower = c2.lower()
                            for indicator in contradiction_indicators:
                                if indicator in c1_lower and indicator not in c2_lower:
                                    # Possible contradiction
                                    contradictions.append({
                                        "topic": t,
                                        "fact1": group[i],
                                        "fact2": group[j],
                                        "indicator": indicator
                                    })
                                    break
            
            if not contradictions:
                return f"No contradictions found for topic: {topic} (min_trust={min_trust})"
            
            output = f"Contradictions found for '{topic}' (min_trust={min_trust}):\n\n"
            for c in contradictions[:10]:
                output += f"Topic: {c['topic']}\n"
                output += f"  Indicator: {c['indicator']}\n"
                for f in [c['fact1'], c['fact2']]:
                    ts = f.get('ts', '')[:19]
                    content = f.get('content', '')[:300]
                    output += f"  [{ts}] {content}\n"
                output += "\n"
            return output
        except Exception as e:
            return f"Error finding contradictions: {str(e)}"
    async def _memory_related(self, args: Dict) -> str:
        entity = args.get("entity", "")
        min_trust = args.get("min_trust", 0.3)

        if not entity:
            return "Error: entity is required"

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import _load_ledger, SUPERSEDED
            
            recs = _load_ledger()
            # Find facts mentioning the entity in content or topic
            facts = [r for r in recs 
                    if r.get("action") == "remember" 
                    and SUPERSEDED not in r.get("content", "")
                    and (entity.lower() in r.get("content", "").lower() 
                         or entity.lower() in r.get("topic", "").lower())]
            
            if not facts:
                return f"No facts found mentioning entity: {entity}"
            
            # Find co-occurring topics and tags
            from collections import Counter
            cooccurring_topics = Counter()
            cooccurring_tags = Counter()
            
            for f in facts:
                # Co-occurring topics
                t = f.get("topic", "")
                if t and t.lower() != entity.lower():
                    cooccurring_topics[t] += 1
                
                # Co-occurring tags
                for tag in f.get("tags", []):
                    tag_lower = tag.lower()
                    if tag_lower != entity.lower():
                        cooccurring_tags[tag_lower] += 1
            
            # Filter by min_trust (using count as proxy)
            related_topics = [(k, v) for k, v in cooccurring_topics.items() if v >= min_trust]
            related_tags = [(k, v) for k, v in cooccurring_tags.items() if v >= min_trust]
            
            related_topics.sort(key=lambda x: x[1], reverse=True)
            related_tags.sort(key=lambda x: x[1], reverse=True)
            
            if not related_topics and not related_tags:
                return f"No related entities found for: {entity} (min_trust={min_trust})"
            
            output = f"Entities related to '{entity}' (min_trust={min_trust}):\n\n"
            
            if related_topics:
                output += "Related topics:\n"
                for rel_topic, score in related_topics[:15]:
                    # Get sample fact
                    sample = next((f for f in facts if f.get("topic") == rel_topic), None)
                    output += f"  {rel_topic} (co-occurrence count: {score}):\n"
                    if sample:
                        output += f"    Sample: {sample.get('content', '')[:300]}\n\n"
            
            if related_tags:
                output += "Related tags:\n"
                for rel_tag, score in related_tags[:15]:
                    output += f"  {rel_tag} (count: {score})\n"
                output += "\n"
            
            return output
        except Exception as e:
            return f"Error finding related entities: {str(e)}"
    async def _memory_feedback(self, args: Dict) -> str:
        fact_id = args.get("fact_id")
        action = args.get("action")

        if fact_id is None or not action:
            return "Error: fact_id and action are required"

        if action not in ["helpful", "unhelpful"]:
            return "Error: action must be 'helpful' or 'unhelpful'"

        try:
            # Store feedback in ledger
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import remember, _append_ledger
            
            # Store feedback as a remember event
            feedback_content = f"Feedback for fact {fact_id}: {action}"
            remember(topic="feedback", content=feedback_content, tags=[str(fact_id), action], priority="high")
            
            return f"Feedback recorded: {action} for fact {fact_id}"
        except Exception as e:
            return f"Error recording feedback: {str(e)}"
