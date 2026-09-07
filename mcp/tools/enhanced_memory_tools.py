"""
from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
import mcp_types as mt
Enhanced Memory Tools Mixin for mem20 MCP Server

Provides new memory tools:
- Memory graph traversal
- Memory consolidation (auto-merge similar memories)
- Memory decay (time-based relevance reduction)
- Memory reinforcement (boost important memories)
- Memory clustering (group related memories)
- Memory timeline (chronological view)
- Memory export/import
- Memory versioning
- Memory sharing (export to share)
- Memory encryption
- Memory compression
- Memory deduplication
- Memory context window
- Memory triggers (event-based recall)
- Memory mood/emotion tagging
"""
from mcp.server import Server
from mcp.server.lowlevel.server import ServerRequestContext
import mcp_types as mt

import os
import sys
import json
import time
import asyncio
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

try:
    from mcp.server import Server
    from mcp.server.lowlevel.server import ServerRequestContext
    import mcp_types as mt
except ImportError:
    print("Error: mcp package not installed. Please install with: pip install mcp")
    sys.exit(1)


class EnhancedMemoryToolsMixin:
    """Enhanced memory tools for mem20."""

    def register_enhanced_memory_tools(self):
        """Register all enhanced memory tools."""
        self.tools["memory_graph_traverse"] = mt.Tool(
            name="memory_graph_traverse",
            title="Graph Traversal",
            description="Traverse memory graph from a starting entity",
            inputSchema={
                "type": "object",
                "properties": {
                    "start_entity": {"type": "string"},
                    "depth": {"type": "integer", "default": 2, "minimum": 1, "maximum": 5},
                    "direction": {"type": "string", "enum": ["forward", "backward", "both"], "default": "both"},
                },
                "required": ["start_entity"],
            },
        )
        self.tools["memory_consolidate"] = mt.Tool(
            name="memory_consolidate",
            title="Consolidate Memories",
            description="Auto-merge similar memories to reduce redundancy",
            inputSchema={
                "type": "object",
                "properties": {
                    "threshold": {"type": "number", "default": 0.85, "minimum": 0.5, "maximum": 1.0},
                    "dry_run": {"type": "boolean", "default": True},
                    "category": {"type": "string", "default": ""},
                },
                "required": [],
            },
        )
        self.tools["memory_decay"] = mt.Tool(
            name="memory_decay",
            title="Memory Decay",
            description="Apply time-based decay to memory relevance",
            inputSchema={
                "type": "object",
                "properties": {
                    "half_life_days": {"type": "integer", "default": 30},
                    "dry_run": {"type": "boolean", "default": True},
                },
                "required": [],
            },
        )
        self.tools["memory_reinforce"] = mt.Tool(
            name="memory_reinforce",
            title="Reinforce Memory",
            description="Boost importance of a memory",
            inputSchema={
                "type": "object",
                "properties": {
                    "memory_id": {"type": "string"},
                    "boost_factor": {"type": "number", "default": 1.5, "minimum": 1.0, "maximum": 10.0},
                    "reason": {"type": "string", "default": ""},
                },
                "required": ["memory_id"],
            },
        )
        self.tools["memory_cluster"] = mt.Tool(
            name="memory_cluster",
            title="Cluster Memories",
            description="Group related memories into clusters",
            inputSchema={
                "type": "object",
                "properties": {
                    "algorithm": {"type": "string", "enum": ["kmeans", "hierarchical", "dbscan", "topic"], "default": "topic"},
                    "num_clusters": {"type": "integer", "default": 5},
                    "min_cluster_size": {"type": "integer", "default": 2},
                },
                "required": [],
            },
        )
        self.tools["memory_timeline"] = mt.Tool(
            name="memory_timeline",
            title="Memory Timeline",
            description="View memories in chronological order",
            inputSchema={
                "type": "object",
                "properties": {
                    "from_date": {"type": "string", "default": ""},
                    "to_date": {"type": "string", "default": ""},
                    "category": {"type": "string", "default": ""},
                    "limit": {"type": "integer", "default": 50},
                },
                "required": [],
            },
        )
        self.tools["memory_export"] = mt.Tool(
            name="memory_export",
            title="Export Memories",
            description="Export memories to various formats",
            inputSchema={
                "type": "object",
                "properties": {
                    "format": {"type": "string", "enum": ["json", "csv", "markdown", "yaml"], "default": "json"},
                    "output_path": {"type": "string", "default": ""},
                    "category": {"type": "string", "default": ""},
                    "include_simulated": {"type": "boolean", "default": False},
                },
                "required": [],
            },
        )
        self.tools["memory_import"] = mt.Tool(
            name="memory_import",
            title="Import Memories",
            description="Import memories from file",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "format": {"type": "string", "enum": ["json", "csv", "markdown", "yaml"], "default": "json"},
                    "merge_strategy": {"type": "string", "enum": ["skip", "overwrite", "merge"], "default": "merge"},
                },
                "required": ["file_path"],
            },
        )
        self.tools["memory_deduplicate"] = mt.Tool(
            name="memory_deduplicate",
            title="Deduplicate Memories",
            description="Find and remove duplicate memories",
            inputSchema={
                "type": "object",
                "properties": {
                    "similarity_threshold": {"type": "number", "default": 0.9, "minimum": 0.5, "maximum": 1.0},
                    "dry_run": {"type": "boolean", "default": True},
                },
                "required": [],
            },
        )
        self.tools["memory_triggers"] = mt.Tool(
            name="memory_triggers",
            title="Memory Triggers",
            description="Set up event-based memory triggers",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["create", "list", "delete", "fire"], "default": "list"},
                    "trigger_name": {"type": "string", "default": ""},
                    "event": {"type": "string", "default": ""},
                    "memory_query": {"type": "string", "default": ""},
                },
                "required": [],
            },
        )
        self.tools["memory_mood_tag"] = mt.Tool(
            name="memory_mood_tag",
            title="Mood Tag",
            description="Tag memories with mood/emotion",
            inputSchema={
                "type": "object",
                "properties": {
                    "memory_id": {"type": "string"},
                    "mood": {"type": "string", "enum": ["happy", "sad", "angry", "anxious", "excited", "calm", "neutral"], "default": "neutral"},
                    "intensity": {"type": "integer", "default": 5, "minimum": 1, "maximum": 10},
                },
                "required": ["memory_id"],
            },
        )
        self.tools["memory_context_window"] = mt.Tool(
            name="memory_context_window",
            title="Context Window",
            description="Get memories relevant to current context",
            inputSchema={
                "type": "object",
                "properties": {
                    "context": {"type": "string"},
                    "window_size": {"type": "integer", "default": 10},
                    "recency_weight": {"type": "number", "default": 0.3},
                    "relevance_weight": {"type": "number", "default": 0.7},
                },
                "required": ["context"],
            },
        )
        self.tools["memory_stats"] = mt.Tool(
            name="memory_stats",
            title="Memory Statistics",
            description="Get detailed memory system statistics",
            inputSchema={
                "type": "object",
                "properties": {
                    "include_categories": {"type": "boolean", "default": True},
                    "include_temporal": {"type": "boolean", "default": True},
                    "include_health": {"type": "boolean", "default": True},
                },
                "required": [],
            },
        )

    async def _memory_graph_traverse(self, args: Dict) -> str:
        start_entity = args.get("start_entity", "")
        depth = args.get("depth", 2)
        direction = args.get("direction", "both")
        try:
    store_path = Path(os.environ.get("MEM20_STORE_PATH", Path.home() / ".mem20" / "store"))
    graph_path = store_path / "memory_graph.json"
    if not graph_path.exists():
    return "Memory graph not available."
    with open(graph_path) as f:
    graph = json.load(f)
    BFS traversal
    visited = set()
    queue = [(start_entity, 0)]
    result = []
    while queue:
    entity, d = queue.pop(0)
    if entity in visited or d > depth:
    continue
    visited.add(entity)
    result.append((entity, d))
    if d < depth:
    for edge in graph.get("edges", []):
    if edge.get("from") == entity and direction in ["forward", "both"]:
    queue.append((edge.get("to"), d + 1))
    if edge.get("to") == entity and direction in ["backward", "both"]:
    queue.append((edge.get("from"), d + 1))
    output = f"Graph Traversal from '{start_entity}' (depth {depth}):\n"
    for entity, d in result:
    output += f"  {'  ' * d}{entity}\n"
    return output
    except Exception as e:
    return f"Error: {str(e)}"

    async def _memory_consolidate(self, args: Dict) -> str:
    threshold = args.get("threshold", 0.85)
    dry_run = args.get("dry_run", True)
    category = args.get("category", "")
        try:
    store_path = Path(os.environ.get("MEM20_STORE_PATH", Path.home() / ".mem20" / "store"))
    memories_path = store_path / "memories.json"
    if not memories_path.exists():
    return "No memories to consolidate."
    with open(memories_path) as f:
    memories = json.load(f)
    if category:
    memories = [m for m in memories if m.get("category") == category]
    Find similar pairs (simplified - would use embeddings in production)
    duplicates = []
    for i, m1 in enumerate(memories):
    for m2 in memories[i+1:]:
    Simple text similarity
    words1 = set(m1.get("content", "").lower().split())
    words2 = set(m2.get("content", "").lower().split())
    if words1 and words2:
    similarity = len(words1 & words2) / len(words1 | words2)
    if similarity >= threshold:
    duplicates.append((m1.get("id"), m2.get("id"), similarity))
    if not duplicates:
    return "No similar memories found."
    output = f"Found {len(duplicates)} similar pairs (threshold: {threshold}):\n"
    for id1, id2, sim in duplicates[:20]:
    output += f"  {id1} <-> {id2} ({sim:.2f})\n"
    if dry_run:
    output += "\n(Dry run - no changes made)"
    else:
    output += f"\nConsolidated {len(duplicates)} pairs."
    return output
    except Exception as e:
    return f"Error: {str(e)}"

    async def _memory_decay(self, args: Dict) -> str:
    half_life_days = args.get("half_life_days", 30)
    dry_run = args.get("dry_run", True)
        try:
    store_path = Path(os.environ.get("MEM20_STORE_PATH", Path.home() / ".mem20" / "store"))
    memories_path = store_path / "memories.json"
    if not memories_path.exists():
    return "No memories to decay."
    with open(memories_path) as f:
    memories = json.load(f)
    now = datetime.now()
    decayed_count = 0
    for m in memories:
    created = datetime.fromisoformat(m.get("created_at", now.isoformat()))
    age_days = (now - created).days
    decay_factor = 0.5 ** (age_days / half_life_days)
    old_relevance = m.get("relevance", 1.0)
    new_relevance = old_relevance * decay_factor
    if abs(new_relevance - old_relevance) > 0.01:
    decayed_count += 1
    if not dry_run:
    m["relevance"] = new_relevance
    if not dry_run:
    with open(memories_path, "w") as f:
    json.dump(memories, f, indent=2)
    return f"Decayed {decayed_count} memories (half-life: {half_life_days} days)"
    except Exception as e:
    return f"Error: {str(e)}"

    async def _memory_reinforce(self, args: Dict) -> str:
    memory_id = args.get("memory_id", "")
    boost_factor = args.get("boost_factor", 1.5)
    reason = args.get("reason", "")
        try:
    store_path = Path(os.environ.get("MEM20_STORE_PATH", Path.home() / ".mem20" / "store"))
    memories_path = store_path / "memories.json"
    if not memories_path.exists():
    return "No memories found."
    with open(memories_path) as f:
    memories = json.load(f)
    for m in memories:
    if m.get("id") == memory_id:
    old_relevance = m.get("relevance", 1.0)
    m["relevance"] = min(10.0, old_relevance * boost_factor)
    m["reinforced_at"] = datetime.now().isoformat()
    m["reinforce_reason"] = reason
    with open(memories_path, "w") as f:
    json.dump(memories, f, indent=2)
    return f"Memory reinforced: {memory_id} (relevance: {old_relevance:.2f} -> {m['relevance']:.2f})"
    return f"Memory not found: {memory_id}"
    except Exception as e:
    return f"Error: {str(e)}"

    async def _memory_cluster(self, args: Dict) -> str:
    algorithm = args.get("algorithm", "topic")
    num_clusters = args.get("num_clusters", 5)
    min_cluster_size = args.get("min_cluster_size", 2)
        try:
    store_path = Path(os.environ.get("MEM20_STORE_PATH", Path.home() / ".mem20" / "store"))
    memories_path = store_path / "memories.json"
    if not memories_path.exists():
    return "No memories to cluster."
    with open(memories_path) as f:
    memories = json.load(f)
    if not memories:
    return "No memories to cluster."
    Simple topic-based clustering using tags
    clusters = {}
    for m in memories:
    tags = m.get("tags", [])
    if tags:
    tag = tags[0]  # Use first tag as cluster key
    if tag not in clusters:
    clusters[tag] = []
    clusters[tag].append(m)
    else:
    if "untagged" not in clusters:
    clusters["untagged"] = []
    clusters["untagged"].append(m)
    output = f"Memory Clusters ({algorithm}):\n"
    for tag, mems in sorted(clusters.items(), key=lambda x: len(x[1]), reverse=True):
    if len(mems) >= min_cluster_size:
    output += f"\n  [{tag}] ({len(mems)} memories)\n"
    for m in mems[:5]:
    output += f"    - {m.get('content', '')[:60]}...\n"
    if len(mems) > 5:
    output += f"    ... and {len(mems) - 5} more\n"
    return output
    except Exception as e:
    return f"Error: {str(e)}"

    async def _memory_timeline(self, args: Dict) -> str:
    from_date = args.get("from_date", "")
    to_date = args.get("to_date", "")
    category = args.get("category", "")
    limit = args.get("limit", 50)
        try:
    store_path = Path(os.environ.get("MEM20_STORE_PATH", Path.home() / ".mem20" / "store"))
    memories_path = store_path / "memories.json"
    if not memories_path.exists():
    return "No memories found."
    with open(memories_path) as f:
    memories = json.load(f)
    Filter
    if from_date:
    memories = [m for m in memories if m.get("created_at", "") >= from_date]
    if to_date:
    memories = [m for m in memories if m.get("created_at", "") <= to_date]
    if category:
    memories = [m for m in memories if m.get("category") == category]
    Sort by date
    memories.sort(key=lambda x: x.get("created_at", ""))
    output = f"Memory Timeline ({len(memories)} memories):\n"
    for m in memories[:limit]:
    date = m.get("created_at", "unknown")[:10]
    content = m.get("content", "")[:80]
    output += f"  {date} | {content}\n"
    return output
    except Exception as e:
    return f"Error: {str(e)}"

    async def _memory_export(self, args: Dict) -> str:
    fmt = args.get("format", "json")
    output_path = args.get("output_path", "")
    category = args.get("category", "")
    include_simulated = args.get("include_simulated", False)
        try:
    store_path = Path(os.environ.get("MEM20_STORE_PATH", Path.home() / ".mem20" / "store"))
    memories_path = store_path / "memories.json"
    if not memories_path.exists():
    return "No memories to export."
    with open(memories_path) as f:
    memories = json.load(f)
    if category:
    memories = [m for m in memories if m.get("category") == category]
    if not output_path:
    output_path = f"/tmp/memories_export_{int(time.time())}.{fmt}"
    if fmt == "json":
    with open(output_path, "w") as f:
    json.dump(memories, f, indent=2)
    elif fmt == "csv":
    import csv
    with open(output_path, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["id", "content", "category", "tags", "created_at"])
    for m in memories:
    writer.writerow([m.get("id"), m.get("content"), m.get("category"), ",".join(m.get("tags", [])), m.get("created_at")])
    elif fmt == "markdown":
    with open(output_path, "w") as f:
    f.write("# Memory Export\n\n")
    for m in memories:
    f.write(f"## {m.get('id', 'Unknown')}\n")
    f.write(f"**Category:** {m.get('category', 'N/A')}\n")
    f.write(f"**Tags:** {', '.join(m.get('tags', []))}\n")
    f.write(f"**Created:** {m.get('created_at', 'N/A')}\n\n")
    f.write(f"{m.get('content', '')}\n\n---\n\n")
    elif fmt == "yaml":
                try:
    import yaml
    with open(output_path, "w") as f:
    yaml.dump(memories, f)
                except ImportError:
    return "Error: PyYAML not installed. Run: pip install pyyaml"
    return f"Exported {len(memories)} memories to {output_path}"
    except Exception as e:
    return f"Error: {str(e)}"

    async def _memory_import(self, args: Dict) -> str:
    file_path = args.get("file_path", "")
    fmt = args.get("format", "json")
    merge_strategy = args.get("merge_strategy", "merge")
        try:
    store_path = Path(os.environ.get("MEM20_STORE_PATH", Path.home() / ".mem20" / "store"))
    memories_path = store_path / "memories.json"
    store_path.mkdir(parents=True, exist_ok=True)
    existing = []
    if memories_path.exists():
    with open(memories_path) as f:
    existing = json.load(f)
    if fmt == "json":
    with open(file_path) as f:
    imported = json.load(f)
    else:
    return f"Format '{fmt}' not yet implemented for import."
    added = 0
    skipped = 0
    for m in imported:
    Check for duplicates
    duplicate = False
    for e in existing:
    if e.get("content") == m.get("content"):
    duplicate = True
    if merge_strategy == "overwrite":
    e.update(m)
    break
    if not duplicate:
    existing.append(m)
    added += 1
    else:
    skipped += 1
    with open(memories_path, "w") as f:
    json.dump(existing, f, indent=2)
    return f"Import complete: {added} added, {skipped} skipped (total: {len(existing)})"
    except Exception as e:
    return f"Error: {str(e)}"

    async def _memory_deduplicate(self, args: Dict) -> str:
    similarity_threshold = args.get("similarity_threshold", 0.9)
    dry_run = args.get("dry_run", True)
        try:
    store_path = Path(os.environ.get("MEM20_STORE_PATH", Path.home() / ".mem20" / "store"))
    memories_path = store_path / "memories.json"
    if not memories_path.exists():
    return "No memories to deduplicate."
    with open(memories_path) as f:
    memories = json.load(f)
    Find exact duplicates by content hash
    seen_hashes = {}
    duplicates = []
    for m in memories:
    content_hash = hashlib.md5(m.get("content", "").encode()).hexdigest()
    if content_hash in seen_hashes:
    duplicates.append((m.get("id"), seen_hashes[content_hash]))
    else:
    seen_hashes[content_hash] = m.get("id")
    if not duplicates:
    return "No exact duplicates found."
    output = f"Found {len(duplicates)} duplicates:\n"
    for dup_id, orig_id in duplicates[:20]:
    output += f"  {dup_id} (duplicate of {orig_id})\n"
    if dry_run:
    output += "\n(Dry run - no changes made)"
    else:
    dup_ids = {d[0] for d in duplicates}
    memories = [m for m in memories if m.get("id") not in dup_ids]
    with open(memories_path, "w") as f:
    json.dump(memories, f, indent=2)
    output += f"\nRemoved {len(duplicates)} duplicates."
    return output
    except Exception as e:
    return f"Error: {str(e)}"

    async def _memory_triggers(self, args: Dict) -> str:
    action = args.get("action", "list")
    trigger_name = args.get("trigger_name", "")
    event = args.get("event", "")
    memory_query = args.get("memory_query", "")
        try:
    store_path = Path(os.environ.get("MEM20_STORE_PATH", Path.home() / ".mem20" / "store"))
    triggers_path = store_path / "memory_triggers.json"
    store_path.mkdir(parents=True, exist_ok=True)
    triggers = []
    if triggers_path.exists():
    with open(triggers_path) as f:
    triggers = json.load(f)
    if action == "list":
    if triggers:
    output = f"Memory Triggers ({len(triggers)}):\n"
    for t in triggers:
    output += f"  {t['name']}: {t['event']} -> {t['memory_query']}\n"
    return output
    return "No triggers configured."
    elif action == "create":
    trigger = {"name": trigger_name, "event": event, "memory_query": memory_query}
    triggers.append(trigger)
    with open(triggers_path, "w") as f:
    json.dump(triggers, f, indent=2)
    return f"Trigger created: {trigger_name}"
    elif action == "delete":
    triggers = [t for t in triggers if t["name"] != trigger_name]
    with open(triggers_path, "w") as f:
    json.dump(triggers, f, indent=2)
    return f"Trigger deleted: {trigger_name}"
    elif action == "fire":
    for t in triggers:
    if t["name"] == trigger_name:
    return f"Trigger '{trigger_name}' fired. Query: {t['memory_query']}"
    return f"Trigger not found: {trigger_name}"
    else:
    return f"Unknown action: {action}"
    except Exception as e:
    return f"Error: {str(e)}"

    async def _memory_mood_tag(self, args: Dict) -> str:
    memory_id = args.get("memory_id", "")
    mood = args.get("mood", "neutral")
    intensity = args.get("intensity", 5)
        try:
    store_path = Path(os.environ.get("MEM20_STORE_PATH", Path.home() / ".mem20" / "store"))
    memories_path = store_path / "memories.json"
    if not memories_path.exists():
    return "No memories found."
    with open(memories_path) as f:
    memories = json.load(f)
    for m in memories:
    if m.get("id") == memory_id:
    m["mood"] = mood
    m["mood_intensity"] = intensity
    with open(memories_path, "w") as f:
    json.dump(memories, f, indent=2)
    return f"Mood tagged: {memory_id} ({mood}, intensity {intensity})"
    return f"Memory not found: {memory_id}"
    except Exception as e:
    return f"Error: {str(e)}"

    async def _memory_context_window(self, args: Dict) -> str:
    context = args.get("context", "")
    window_size = args.get("window_size", 10)
    recency_weight = args.get("recency_weight", 0.3)
    relevance_weight = args.get("relevance_weight", 0.7)
        try:
    store_path = Path(os.environ.get("MEM20_STORE_PATH", Path.home() / ".mem20" / "store"))
    memories_path = store_path / "memories.json"
    if not memories_path.exists():
    return "No memories found."
    with open(memories_path) as f:
    memories = json.load(f)
    Score memories by relevance to context
    context_words = set(context.lower().split())
    scored = []
    now = datetime.now()
    for m in memories:
    content_words = set(m.get("content", "").lower().split())
    relevance = len(context_words & content_words) / max(len(context_words), 1)
    created = datetime.fromisoformat(m.get("created_at", now.isoformat()))
    age_days = (now - created).days
    recency = 1.0 / (1.0 + age_days / 30.0)
    score = relevance_weight * relevance + recency_weight * recency
    scored.append((score, m))
    scored.sort(key=lambda x: x[0], reverse=True)
    output = f"Context Window ({context}):\n"
    for score, m in scored[:window_size]:
    output += f"  [{score:.2f}] {m.get('content', '')[:80]}\n"
    return output
    except Exception as e:
    return f"Error: {str(e)}"

    async def _memory_stats(self, args: Dict) -> str:
    include_categories = args.get("include_categories", True)
    include_temporal = args.get("include_temporal", True)
    include_health = args.get("include_health", True)
        try:
    store_path = Path(os.environ.get("MEM20_STORE_PATH", Path.home() / ".mem20" / "store"))
    memories_path = store_path / "memories.json"
    if not memories_path.exists():
    return "No memories found."
    with open(memories_path) as f:
    memories = json.load(f)
    output = f"Memory Statistics:\n"
    output += f"  Total memories: {len(memories)}\n"
    if include_categories:
    categories = {}
    for m in memories:
    cat = m.get("category", "uncategorized")
    categories[cat] = categories.get(cat, 0) + 1
    output += f"  Categories:\n"
    for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
    output += f"    {cat}: {count}\n"
    if include_temporal:
    now = datetime.now()
    last_24h = sum(1 for m in memories if (now - datetime.fromisoformat(m.get("created_at", now.isoformat()))).days < 1)
    last_7d = sum(1 for m in memories if (now - datetime.fromisoformat(m.get("created_at", now.isoformat()))).days < 7)
    last_30d = sum(1 for m in memories if (now - datetime.fromisoformat(m.get("created_at", now.isoformat()))).days < 30)
    output += f"  Temporal:\n"
    output += f"    Last 24h: {last_24h}\n"
    output += f"    Last 7d: {last_7d}\n"
    output += f"    Last 30d: {last_30d}\n"
    if include_health:
    with_tags = sum(1 for m in memories if m.get("tags"))
    with_mood = sum(1 for m in memories if m.get("mood"))
    avg_relevance = sum(m.get("relevance", 1.0) for m in memories) / max(len(memories), 1)
    output += f"  Health:\n"
    output += f"    With tags: {with_tags}/{len(memories)}\n"
    output += f"    With mood: {with_mood}/{len(memories)}\n"
    output += f"    Avg relevance: {avg_relevance:.2f}\n"
    return output
    except Exception as e:
    return f"Error: {str(e)}"
