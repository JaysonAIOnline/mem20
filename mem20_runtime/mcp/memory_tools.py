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
    from memory import remember, recall, status as mem_status, rebuild_index, ledger_view
    MEMORY_SYSTEM_AVAILABLE = True
except ImportError:
    MEMORY_SYSTEM_AVAILABLE = False


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
            description="Knowledge graph traversal with multi-hop entity resolution",
            inputSchema={
                "type": "object",
                "properties": {
                    "entity": {"type": "string", "description": "Starting entity"},
                    "hops": {"type": "integer", "description": "Number of graph hops", "default": 2},
                    "min_trust": {"type": "number", "description": "Minimum trust score", "default": 0.3},
                    "max_results": {"type": "integer", "default": 20},
                },
                "required": ["entity"],
            },
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
                },
                "required": [],
            },
        )
        self.tools["self_model_get"] = mt.Tool(
            name="self_model_get",
            title="Get Self-Model",
            description="Retrieve the agent's self-model",
            inputSchema={"type": "object", "properties": {}},
        )
        self.tools["self_model_reflect"] = mt.Tool(
            name="self_model_reflect",
            title="Self-Model Reflection",
            description="Metacognitive reflection on own capabilities, gaps, and belief updates",
            inputSchema={
                "type": "object",
                "properties": {
                    "focus": {"type": "string", "enum": ["capabilities", "gaps", "beliefs", "values", "all"], "description": "Reflection focus", "default": "all"},
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
        """Knowledge graph traversal with multi-hop entity resolution."""
        entity = args.get("entity", "")
        hops = args.get("hops", 2)
        min_trust = args.get("min_trust", 0.3)
        max_results = args.get("max_results", 20)

        if not entity:
            return "Error: entity is required"

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import _load_ledger, SUPERSEDED
            from collections import defaultdict, deque
            
            recs = _load_ledger()
            facts = [r for r in recs 
                    if r.get("action") == "remember" 
                    and SUPERSEDED not in r.get("content", "")]
            
            # Build entity graph from co-occurrence
            entity_graph = defaultdict(set)
            entity_facts = defaultdict(list)
            
            for f in facts:
                content = f.get("content", "").lower()
                topic = f.get("topic", "").lower()
                # Extract potential entities (simple heuristic: capitalized words, topics)
                words = content.split()
                entities_in_fact = set()
                for w in words:
                    clean = w.strip('.,!?;:"()[]{}')
                    if clean and (clean[0].isupper() or clean in topic):
                        entities_in_fact.add(clean)
                entities_in_fact.add(topic)
                
                for e1 in entities_in_fact:
                    entity_facts[e1].append(f)
                    for e2 in entities_in_fact:
                        if e1 != e2:
                            entity_graph[e1].add(e2)
            
            if entity.lower() not in [e.lower() for e in entity_graph]:
                return f"Entity '{entity}' not found in knowledge graph"
            
            # Find actual case-matched entity name
            actual_entity = next(e for e in entity_graph if e.lower() == entity.lower())
            
            # Multi-hop traversal
            visited = set([actual_entity])
            current_level = {actual_entity}
            all_related = {}
            
            for hop in range(1, hops + 1):
                next_level = set()
                for e in current_level:
                    for neighbor in entity_graph.get(e, []):
                        if neighbor not in visited:
                            visited.add(neighbor)
                            next_level.add(neighbor)
                            if neighbor not in all_related:
                                all_related[neighbor] = hop
                current_level = next_level
                if not current_level:
                    break
            
            if not all_related:
                return f"No related entities found for: {entity} (hops={hops})"
            
            # Sort by hop distance and fact count
            sorted_related = sorted(all_related.items(), key=lambda x: (x[1], -len(entity_facts.get(x[0], []))))
            
            output = f"**Graph Recall: '{entity}'** (hops={hops}, max={max_results})\n\n"
            output += f"Starting entity: {actual_entity} ({len(entity_facts.get(actual_entity, []))} facts)\n\n"
            output += f"Related entities:\n"
            for rel_entity, hop_dist in sorted_related[:max_results]:
                fact_count = len(entity_facts.get(rel_entity, []))
                output += f"  Hop {hop_dist}: {rel_entity} ({fact_count} facts)\n"
                # Show sample fact
                sample_facts = entity_facts.get(rel_entity, [])
                if sample_facts:
                    sample = sample_facts[0].get('content', '')[:200]
                    output += f"    Sample: {sample}...\n"
            return output
        except Exception as e:
            return f"Error in graph recall: {str(e)}"
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
            from memory import remember
            
            # Store namespace metadata
            remember(
                topic="namespace_meta",
                content=f"Namespace: {namespace}, Owner: {owner}, ACL: {acl}",
                tags=["namespace", "metadata", namespace],
                priority="high"
            )
            
            return f"✅ Namespace created: {namespace}\nOwner: {owner}\nACL: {acl}"
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
            from memory import remember, recall
            
            # Check ACL by looking at namespace metadata
            meta_results = recall(topic="namespace_meta", k=10)
            namespace_meta = next((r for r in meta_results if namespace in r.get('content', '')), None)
            
            # Simple ACL check - in production would be more sophisticated
            if namespace_meta:
                import json
                try:
                    acl_str = namespace_meta.get('content', '').split('ACL: ')[-1]
                    acl = json.loads(acl_str.replace("'", '"'))
                    if actor not in acl and '*' not in acl:
                        return f"Access denied: {actor} not in ACL for namespace {namespace}"
                except:
                    pass  # No ACL or parse error - allow
            
            remember(
                topic=f"namespace_{namespace}",
                content=content,
                tags=tags + ["shared", namespace, f"actor_{actor}"]
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
            
            results = recall(topic=f"namespace_{namespace}", k=k)
            
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

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import remember
            
            model_data = {
                "capabilities": capabilities,
                "values": values,
                "identity": identity,
                "created": __import__('datetime').datetime.now().isoformat()
            }
            
            remember(
                topic="self_model",
                content=f"Self-Model: {model_data}",
                tags=["self_model", "identity", "core"],
                priority="high"
            )
            
            return f"✅ Self-model created/updated\nCapabilities: {len(capabilities)}\nValues: {len(values)}\nIdentity: {identity[:100] if identity else 'Not set'}"
        except Exception as e:
            return f"Error creating self-model: {str(e)}"
    async def _self_model_get(self, args: Dict) -> str:
        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import recall
            
            results = recall(topic="self_model", k=5)
            
            if not results:
                return "No self-model found. Create one first."
            
            output = "**Self-Model**\n\n"
            for r in results:
                ts = r.get('ts', '')[:19]
                content = r.get('content', '')
                output += f"[{ts}] {content}\n\n"
            return output
        except Exception as e:
            return f"Error getting self-model: {str(e)}"
    async def _self_model_reflect(self, args: Dict) -> str:
        focus = args.get("focus", "all")

        try:
            sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", os.path.expanduser("~/.mem20/store")))
            from memory import recall, self_audit
            
            # Get self-model
            model_results = recall(topic="self_model", k=1)
            model_content = model_results[0].get('content', '') if model_results else "No self-model"
            
            # Run self-audit
            audit = self_audit(topic="self_model")
            
            # Get capabilities from memory
            cap_results = recall(topic=None, k=20)
            cap_facts = [r for r in cap_results if 'capab' in r.get('content', '').lower()]
            
            output = f"**Self-Model Reflection** (focus: {focus})\n\n"
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
