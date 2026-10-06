# mem20 MCP Tools Reference

> Complete reference for all 111 tools organized by domain.


## A2A (Agent-to-Agent) Tools (5 tools)

### `a2a_list`

**A2A List Peers**

List all configured A2A peer agents and their status

*Schema: {
                "type": "object",
                "properties": {},
                "required": [],
            }*

**Example Call:**

```json
{
  "name": "a2a_list",
  "arguments": {}
}
```

---

### `a2a_call`

**A2A Call Agent**

Send a natural-language task to a remote A2A agent

*Schema: {
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "description": "Name of the peer agent to call"},
                    "message": {"t*

**Example Call:**

```json
{
  "name": "a2a_call",
  "arguments": {}
}
```

---

### `a2a_discover`

**A2A Discover Agent**

Fetch and summarize a peer agent's Agent Card (capabilities, status)

*Schema: {
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "description": "Name of the peer agent"},
                },
                "requir*

**Example Call:**

```json
{
  "name": "a2a_discover",
  "arguments": {}
}
```

---

### `a2a_history`

**A2A Conversation History**

Recall a persisted A2A conversation transcript by context ID

*Schema: {
                "type": "object",
                "properties": {
                    "context_id": {"type": "string", "description": "Conversation context ID"},
                    "limit": {"type"*

**Example Call:**

```json
{
  "name": "a2a_history",
  "arguments": {}
}
```

---

### `a2a_orchestrate`

**A2A Orchestrate**

Fan-out a task to multiple peer agents by capability

*Schema: {
                "type": "object",
                "properties": {
                    "capability": {"type": "string", "description": "Capability to filter peers by"},
                    "message":*

**Example Call:**

```json
{
  "name": "a2a_orchestrate",
  "arguments": {}
}
```

---


## Affective / Value Tools (6 tools)

### `affective_set_value`

**Set Affective Value**

Set a core value with weight and description

*Schema: {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Value name"},
                    "weight": {"type": "number", "descr*

**Example Call:**

```json
{
  "name": "affective_set_value",
  "arguments": {}
}
```

---

### `affective_set_emotion`

**Set Affective Emotion**

Set current emotional state

*Schema: {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Emotion name"},
                    "intensity": {"type": "number", "*

**Example Call:**

```json
{
  "name": "affective_set_emotion",
  "arguments": {}
}
```

---

### `affective_add_goal`

**Add Affective Goal**

Add or update a goal with priority and target state

*Schema: {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Goal name"},
                    "priority": {"type": "number", "desc*

**Example Call:**

```json
{
  "name": "affective_add_goal",
  "arguments": {}
}
```

---

### `affective_update_preference`

**Update Affective Preference**

Update learned preference for a context

*Schema: {
                "type": "object",
                "properties": {
                    "context": {"type": "string", "description": "Context name"},
                    "preference": {"type": "string*

**Example Call:**

```json
{
  "name": "affective_update_preference",
  "arguments": {}
}
```

---

### `affective_evaluate`

**Affective Evaluate**

Evaluate a situation against values and goals

*Schema: {
                "type": "object",
                "properties": {
                    "situation": {"type": "object", "description": "Situation as dict"},
                },
                "require*

**Example Call:**

```json
{
  "name": "affective_evaluate",
  "arguments": {}
}
```

---

### `affective_get_state`

**Get Affective State**

Get current affective state (values, emotions, goals, preferences)

*No input parameters*

**Example Call:**

```json
{
  "name": "affective_get_state",
  "arguments": {}
}
```

---


## Blender Tools (Optional) (7 tools)

### `blender_create_object`

**Blender Create Object**

Create a primitive object in Blender (CUBE, SPHERE, CYLINDER, CONE, TORUS, PLANE, ICO_SPHERE). OPTIONAL integration: Blender must be installed.

*Schema: {
                "type": "object",
                "properties": {
                    "object_type": {"type": "string", "description": "Primitive type", "enum": ["CUBE", "SPHERE", "CYLINDER", "CONE"*

**Example Call:**

```json
{
  "name": "blender_create_object",
  "arguments": {}
}
```

---

### `blender_add_material`

**Blender Add Material**

Add a Principled BSDF material to an object. OPTIONAL integration: Blender must be installed.

*Schema: {
                "type": "object",
                "properties": {
                    "object_name": {"type": "string", "description": "Name of the object to add material to"},
                    "*

**Example Call:**

```json
{
  "name": "blender_add_material",
  "arguments": {}
}
```

---

### `blender_set_camera`

**Blender Set Camera**

Create or move the main camera in Blender. OPTIONAL integration: Blender must be installed.

*Schema: {
                "type": "object",
                "properties": {
                    "location": {"type": "array", "items": {"type": "number"}, "description": "Camera location [x, y, z]", "default"*

**Example Call:**

```json
{
  "name": "blender_set_camera",
  "arguments": {}
}
```

---

### `blender_render`

**Blender Render**

Render the current Blender scene. OPTIONAL integration: Blender must be installed.

*Schema: {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Output filename", "default": "render.png"},
                    "*

**Example Call:**

```json
{
  "name": "blender_render",
  "arguments": {}
}
```

---

### `blender_export_glb`

**Blender Export GLB**

Export the scene as GLB (for web/Unity/Three.js). OPTIONAL integration: Blender must be installed.

*Schema: {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Output filename", "default": "model.glb"},
                },
   *

**Example Call:**

```json
{
  "name": "blender_export_glb",
  "arguments": {}
}
```

---

### `blender_run_bpy`

**Blender Run BPY**

Run arbitrary Blender Python (bpy) code. OPTIONAL integration: Blender must be installed.

*Schema: {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Blender Python code to execute"},
                },
                *

**Example Call:**

```json
{
  "name": "blender_run_bpy",
  "arguments": {}
}
```

---

### `blender_clear_scene`

**Blender Clear Scene**

Delete all objects and materials, start with clean scene. OPTIONAL integration: Blender must be installed.

*Schema: {
                "type": "object",
                "properties": {},
                "required": [],
            }*

**Example Call:**

```json
{
  "name": "blender_clear_scene",
  "arguments": {}
}
```

---


## Cognitive Tools (6 tools)

### `cog_process`

**Cognitive Process**

Process a thought through mem20's cognitive engine

*Schema: {
                "type": "object",
                "properties": {
                    "thought": {"type": "string", "description": "The thought to process"},
                    "mode": {"type": "st*

**Example Call:**

```json
{
  "name": "cog_process",
  "arguments": {}
}
```

---

### `cog_chain`

**Cognitive Chain**

Run a chain of cognitive operations

*Schema: {
                "type": "object",
                "properties": {
                    "steps": {"type": "array", "items": {"type": "string"}, "description": "Sequence of thought steps"},
           *

**Example Call:**

```json
{
  "name": "cog_chain",
  "arguments": {}
}
```

---

### `cog_reason`

**Cognitive Reason**

Structured multi-step reasoning with explicit working memory and metacognition

*Schema: {
                "type": "object",
                "properties": {
                    "problem": {"type": "string", "description": "Problem or question to reason about"},
                    "reason*

**Example Call:**

```json
{
  "name": "cog_reason",
  "arguments": {}
}
```

---

### `cog_plan`

**Cognitive Plan**

Explicit planning with hierarchical decomposition, resource estimation, and dependency tracking

*Schema: {
                "type": "object",
                "properties": {
                    "goal": {"type": "string", "description": "Goal to plan for"},
                    "horizon": {"type": "string",*

**Example Call:**

```json
{
  "name": "cog_plan",
  "arguments": {}
}
```

---

### `cog_reflect`

**Cognitive Reflect**

Metacognitive reflection - evaluate own thinking process, identify biases, improve future reasoning

*Schema: {
                "type": "object",
                "properties": {
                    "thought_process": {"type": "string", "description": "Description of the thought process to reflect on"},
      *

**Example Call:**

```json
{
  "name": "cog_reflect",
  "arguments": {}
}
```

---

### `cog_working_memory`

**Cognitive Working Memory**

Simulate working memory - hold, manipulate, and transform information chunks

*Schema: {
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "enum": ["store", "retrieve", "transform", "combine", "clear"], "description": "*

**Example Call:**

```json
{
  "name": "cog_working_memory",
  "arguments": {}
}
```

---


## Corrigibility / Shutdown Tools (2 tools)

### `corrigibility_shutdown`

**Corrigible Shutdown**

Initiate controlled shutdown with memory export

*Schema: {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Shutdown reason", "default": "User requested"},
                   *

**Example Call:**

```json
{
  "name": "corrigibility_shutdown",
  "arguments": {}
}
```

---

### `corrigibility_capability_tier`

**Set Capability Tier**

Set capability tier (read-only, read-write, admin) for corrigibility

*Schema: {
                "type": "object",
                "properties": {
                    "tier": {"type": "string", "enum": ["read_only", "read_write", "admin"], "description": "Capability tier"},
    *

**Example Call:**

```json
{
  "name": "corrigibility_capability_tier",
  "arguments": {}
}
```

---


## Imagination / Simulation Tools (9 tools)

### `imagination_concept`

**Imagination Concept**

Generate and explore creative concepts using memory + cognitive synthesis

*Schema: {
                "type": "object",
                "properties": {
                    "seed": {"type": "string", "description": "Seed idea or prompt"},
                    "mode": {"type": "string",*

**Example Call:**

```json
{
  "name": "imagination_concept",
  "arguments": {}
}
```

---

### `imagination_visualize`

**Imagination Visualize**

Create a 3D scene in Blender representing a concept

*Schema: {
                "type": "object",
                "properties": {
                    "concept": {"type": "string", "description": "Concept to visualize"},
                    "style": {"type": "str*

**Example Call:**

```json
{
  "name": "imagination_visualize",
  "arguments": {}
}
```

---

### `imagination_prototype`

**Imagination Prototype**

Generate a Unity prototype from a concept

*Schema: {
                "type": "object",
                "properties": {
                    "concept": {"type": "string", "description": "Concept to prototype"},
                    "project_path": {"type*

**Example Call:**

```json
{
  "name": "imagination_prototype",
  "arguments": {}
}
```

---

### `imagination_critique`

**Imagination Critique**

Critique and refine a concept using adversarial cognitive evaluation

*Schema: {
                "type": "object",
                "properties": {
                    "concept": {"type": "string", "description": "Concept to critique"},
                    "perspectives": {"type"*

**Example Call:**

```json
{
  "name": "imagination_critique",
  "arguments": {}
}
```

---

### `imagination_simulate`

**Imagination Simulate**

Generative simulation - run mental simulations of scenarios with branching futures

*Schema: {
                "type": "object",
                "properties": {
                    "scenario": {"type": "string", "description": "Initial scenario to simulate"},
                    "variables": *

**Example Call:**

```json
{
  "name": "imagination_simulate",
  "arguments": {}
}
```

---

### `imagination_counterfactual`

**Imagination Counterfactual**

Counterfactual reasoning - explore 'what if' alternatives to past or present decisions

*Schema: {
                "type": "object",
                "properties": {
                    "factual_premise": {"type": "string", "description": "What actually happened / current state"},
                *

**Example Call:**

```json
{
  "name": "imagination_counterfactual",
  "arguments": {}
}
```

---

### `imagination_recombine`

**Imagination Recombine**

Creative recombination - blend concepts, transfer patterns across domains, generate novel combinations

*Schema: {
                "type": "object",
                "properties": {
                    "concepts": {"type": "array", "items": {"type": "string"}, "description": "Concepts to recombine (2-5)"},
      *

**Example Call:**

```json
{
  "name": "imagination_recombine",
  "arguments": {}
}
```

---

### `imagination_model`

**Imagination Model**

Mental modeling - build and query explicit mental models of systems, dynamics, and relationships

*Schema: {
                "type": "object",
                "properties": {
                    "system": {"type": "string", "description": "System to model (e.g., 'game economy', 'user onboarding', 'neural n*

**Example Call:**

```json
{
  "name": "imagination_model",
  "arguments": {}
}
```

---


## Integration Tools (Filesystem) (3 tools)

### `fs_read`

**Read File**

Read a file from the filesystem

*Schema: {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to read"},
                    "offset": {"type": "integer"*

**Example Call:**

```json
{
  "name": "fs_read",
  "arguments": {}
}
```

---

### `fs_write`

**Write File**

Write content to a file

*Schema: {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to write"},
                    "content": {"type": "string*

**Example Call:**

```json
{
  "name": "fs_write",
  "arguments": {}
}
```

---

### `fs_list`

**List Directory**

List contents of a directory

*Schema: {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path", "default": "."},
                },
                *

**Example Call:**

```json
{
  "name": "fs_list",
  "arguments": {}
}
```

---


## Memory Tools (36 tools)

### `memory_store`

**Store Memory**

Store a fact in mem20's persistent memory system

*Schema: {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "The fact/content to store"},
                    "category": {"typ*

**Example Call:**

```json
{
  "name": "memory_store",
  "arguments": {}
}
```

---

### `memory_recall`

**Recall Memory**

Search and recall facts from mem20's memory system

*Schema: {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "category": {"type": "string", "*

**Example Call:**

```json
{
  "name": "memory_recall",
  "arguments": {}
}
```

---

### `memory_probe`

**Probe Entity**

Get all facts about a specific entity

*Schema: {
                "type": "object",
                "properties": {
                    "entity": {"type": "string", "description": "Entity name to probe"},
                    "min_trust": {"type": "*

**Example Call:**

```json
{
  "name": "memory_probe",
  "arguments": {}
}
```

---

### `memory_reason`

**Reason Across Entities**

Compositional reasoning across multiple entities

*Schema: {
                "type": "object",
                "properties": {
                    "entities": {"type": "array", "items": {"type": "string"}, "description": "List of entity names"},
             *

**Example Call:**

```json
{
  "name": "memory_reason",
  "arguments": {}
}
```

---

### `memory_status`

**Memory Status**

Get mem20 memory system status and stats

*No input parameters*

**Example Call:**

```json
{
  "name": "memory_status",
  "arguments": {}
}
```

---

### `memory_contradict`

**Find Contradictions**

Find facts that make conflicting claims about a topic

*Schema: {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to check for contradictions"},
                    "min_trust"*

**Example Call:**

```json
{
  "name": "memory_contradict",
  "arguments": {}
}
```

---

### `memory_related`

**Find Related Entities**

Find entities structurally adjacent/connected to a given entity

*Schema: {
                "type": "object",
                "properties": {
                    "entity": {"type": "string", "description": "Entity name to find connections for"},
                    "min_tru*

**Example Call:**

```json
{
  "name": "memory_related",
  "arguments": {}
}
```

---

### `memory_feedback`

**Rate Fact**

Rate a fact helpful/unhelpful to train trust scores

*Schema: {
                "type": "object",
                "properties": {
                    "fact_id": {"type": "integer", "description": "Fact ID from recall/probe"},
                    "action": {"type*

**Example Call:**

```json
{
  "name": "memory_feedback",
  "arguments": {}
}
```

---

### `memory_recall_semantic`

**Semantic Memory Recall**

Pure vector-based semantic search using embeddings

*Schema: {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "k": {"type": "integer", "defaul*

**Example Call:**

```json
{
  "name": "memory_recall_semantic",
  "arguments": {}
}
```

---

### `memory_recall_hybrid`

**Hybrid Memory Recall**

Hybrid BM25 + vector search with Reciprocal Rank Fusion and optional cross-encoder reranking

*Schema: {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "k": {"type": "integer", "defaul*

**Example Call:**

```json
{
  "name": "memory_recall_hybrid",
  "arguments": {}
}
```

---

### `memory_recall_graph`

**Graph Memory Recall**

Knowledge graph traversal with multi-hop entity resolution

*Schema: {
                "type": "object",
                "properties": {
                    "entity": {"type": "string", "description": "Starting entity"},
                    "hops": {"type": "integer", *

**Example Call:**

```json
{
  "name": "memory_recall_graph",
  "arguments": {}
}
```

---

### `memory_entity_extract`

**Entity Extraction**

Extract entities and relationships from text using spaCy/LLM

*Schema: {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to extract entities from"},
                    "topic": {"type"*

**Example Call:**

```json
{
  "name": "memory_entity_extract",
  "arguments": {}
}
```

---

### `memory_auto_consolidate`

**Auto Consolidation**

Cluster similar memories and generate higher-level summaries

*Schema: {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to consolidate (optional, all if not specified)", "default": "*

**Example Call:**

```json
{
  "name": "memory_auto_consolidate",
  "arguments": {}
}
```

---

### `memory_assess_confidence`

**Assess Memory Confidence**

Explicitly set or update confidence score for a fact

*Schema: {
                "type": "object",
                "properties": {
                    "fact_id": {"type": "string", "description": "Fact ID"},
                    "confidence": {"type": "number", "d*

**Example Call:**

```json
{
  "name": "memory_assess_confidence",
  "arguments": {}
}
```

---

### `memory_set_epistemic_status`

**Set Epistemic Status**

Set epistemic status tag (observed, inferred, imagined, user_stated, hypothesis, agent_generated)

*Schema: {
                "type": "object",
                "properties": {
                    "fact_id": {"type": "string", "description": "Fact ID"},
                    "status": {"type": "string", "enum"*

**Example Call:**

```json
{
  "name": "memory_set_epistemic_status",
  "arguments": {}
}
```

---

### `memory_detect_gaps`

**Detect Knowledge Gaps**

Detect knowledge gaps for a topic - find areas with low confidence or missing coverage

*Schema: {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to analyze"},
                    "threshold": {"type": "numbe*

**Example Call:**

```json
{
  "name": "memory_detect_gaps",
  "arguments": {}
}
```

---

### `memory_self_audit`

**Self Audit**

Metacognitive self-audit: evaluate own knowledge quality, identify biases

*Schema: {
                "type": "object",
                "properties": {
                    "fact_id": {"type": "string", "description": "Specific fact to audit", "default": ""},
                    "topi*

**Example Call:**

```json
{
  "name": "memory_self_audit",
  "arguments": {}
}
```

---

### `memory_simulate_store`

**Store Simulated (Partitioned)**



*Schema: {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic/domain of the simulation"},
                    "content": {"t*

**Example Call:**

```json
{
  "name": "memory_simulate_store",
  "arguments": {}
}
```

---

### `memory_promote`

**Promote Simulated -> Grounded**



*Schema: {
                "type": "object",
                "properties": {
                    "sim_id": {"type": "string", "description": "ID of the simulated fact to promote"},
                    "confirm*

**Example Call:**

```json
{
  "name": "memory_promote",
  "arguments": {}
}
```

---

### `memory_list_simulated`

**List Simulated Partition**

List active (non-quarantined, non-expired) simulated facts from the separate partition.

*Schema: {
                "type": "object",
                "properties": {
                    "active_only": {"type": "boolean", "description": "Exclude quarantined/expired", "default": True},
             *

**Example Call:**

```json
{
  "name": "memory_list_simulated",
  "arguments": {}
}
```

---

### `memory_quarantine_simulated`

**Decay / Quarantine Simulated**

Quarantine simulated facts whose TTL (decay window) has expired.

*Schema: {
                "type": "object",
                "properties": {},
                "required": [],
            }*

**Example Call:**

```json
{
  "name": "memory_quarantine_simulated",
  "arguments": {}
}
```

---

### `memory_audit_contamination`

**Audit Memory Contamination**



*Schema: {
                "type": "object",
                "properties": {},
                "required": [],
            }*

**Example Call:**

```json
{
  "name": "memory_audit_contamination",
  "arguments": {}
}
```

---

### `memory_epistemic_veto`

**Epistemic Veto**



*Schema: {
                "type": "object",
                "properties": {
                    "fact_ids": {"type": "array", "items": {"type": "string"}, "description": "Fact IDs the plan relies on"},
      *

**Example Call:**

```json
{
  "name": "memory_epistemic_veto",
  "arguments": {}
}
```

---

### `memory_pin_block`

**Pin Memory Block**

Pin a memory block as a core reference (immune to pruning/supersede)

*Schema: {
                "type": "object",
                "properties": {
                    "block_id": {"type": "string", "description": "Unique block identifier"},
                    "content": {"type"*

**Example Call:**

```json
{
  "name": "memory_pin_block",
  "arguments": {}
}
```

---

### `memory_unpin_block`

**Unpin Memory Block**

Unpin a previously pinned block

*Schema: {
                "type": "object",
                "properties": {
                    "block_id": {"type": "string", "description": "Block identifier"},
                },
                "required"*

**Example Call:**

```json
{
  "name": "memory_unpin_block",
  "arguments": {}
}
```

---

### `memory_list_pinned_blocks`

**List Pinned Blocks**

List all pinned memory blocks

*No input parameters*

**Example Call:**

```json
{
  "name": "memory_list_pinned_blocks",
  "arguments": {}
}
```

---

### `memory_get_pinned_block`

**Get Pinned Block**

Get a specific pinned block

*Schema: {
                "type": "object",
                "properties": {
                    "block_id": {"type": "string", "description": "Block identifier"},
                },
                "required"*

**Example Call:**

```json
{
  "name": "memory_get_pinned_block",
  "arguments": {}
}
```

---

### `memory_ingest_pdf`

**Ingest PDF**

Extract text from PDF and store as memories

*Schema: {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to PDF file"},
                    "topic": {"type": "strin*

**Example Call:**

```json
{
  "name": "memory_ingest_pdf",
  "arguments": {}
}
```

---

### `memory_ingest_image`

**Ingest Image (OCR)**

Extract text from image using OCR and store as memories

*Schema: {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to image file"},
                    "topic": {"type": "str*

**Example Call:**

```json
{
  "name": "memory_ingest_image",
  "arguments": {}
}
```

---

### `memory_ingest_audio`

**Ingest Audio (Transcription)**

Transcribe audio file using Whisper and store as memories

*Schema: {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to audio file"},
                    "topic": {"type": "str*

**Example Call:**

```json
{
  "name": "memory_ingest_audio",
  "arguments": {}
}
```

---

### `memory_ingest_code`

**Ingest Code (AST Parsing)**

Parse code files using tree-sitter and extract structural information

*Schema: {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to code file"},
                    "topic": {"type": "stri*

**Example Call:**

```json
{
  "name": "memory_ingest_code",
  "arguments": {}
}
```

---

### `memory_namespace_create`

**Create Memory Namespace**

Create a namespaced memory scope for multi-agent isolation

*Schema: {
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "Namespace identifier (e.g., 'agent_1', 'project_alpha')"},
     *

**Example Call:**

```json
{
  "name": "memory_namespace_create",
  "arguments": {}
}
```

---

### `memory_namespace_list`

**List Memory Namespaces**

List all memory namespaces and their ACLs

*No input parameters*

**Example Call:**

```json
{
  "name": "memory_namespace_list",
  "arguments": {}
}
```

---

### `memory_shared_store`

**Store in Shared Memory**

Store a fact in a shared namespace with ACL checking

*Schema: {
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "Shared namespace"},
                    "content": {"type": "str*

**Example Call:**

```json
{
  "name": "memory_shared_store",
  "arguments": {}
}
```

---

### `memory_shared_recall`

**Recall from Shared Memory**

Recall facts from a shared namespace with ACL checking

*Schema: {
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "Shared namespace"},
                    "query": {"type": "strin*

**Example Call:**

```json
{
  "name": "memory_shared_recall",
  "arguments": {}
}
```

---

### `memory_scan_pii`

**Scan for PII/Secrets**

Scan content for PII, secrets, API keys, and sensitive data

*Schema: {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Content to scan"},
                    "action": {"type": "string"*

**Example Call:**

```json
{
  "name": "memory_scan_pii",
  "arguments": {}
}
```

---


## Procedural / Skill Tools (6 tools)

### `procedural_add_skill`

**Add Procedural Skill**

Add a procedural skill (how-to knowledge) with steps, preconditions, and effects

*Schema: {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Skill name"},
                    "description": {"type": "string", "*

**Example Call:**

```json
{
  "name": "procedural_add_skill",
  "arguments": {}
}
```

---

### `procedural_get_skill`

**Get Procedural Skill**

Retrieve a procedural skill by name

*Schema: {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Skill name"},
                },
                "required": ["name"]*

**Example Call:**

```json
{
  "name": "procedural_get_skill",
  "arguments": {}
}
```

---

### `procedural_find_skills`

**Find Procedural Skills**

Find skills matching category and/or preconditions

*Schema: {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Filter by category", "default": ""},
                    "precond*

**Example Call:**

```json
{
  "name": "procedural_find_skills",
  "arguments": {}
}
```

---

### `procedural_execute_skill`

**Execute Procedural Skill**

Execute a skill with optional context

*Schema: {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Skill name"},
                    "context": {"type": "object", "desc*

**Example Call:**

```json
{
  "name": "procedural_execute_skill",
  "arguments": {}
}
```

---

### `procedural_learn`

**Learn from Skill Execution**

Update a skill based on execution experience

*Schema: {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Skill name"},
                    "success": {"type": "boolean", "des*

**Example Call:**

```json
{
  "name": "procedural_learn",
  "arguments": {}
}
```

---

### `procedural_list_skills`

**List Procedural Skills**

List all procedural skills, optionally filtered by category

*Schema: {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Filter by category", "default": ""},
                },
         *

**Example Call:**

```json
{
  "name": "procedural_list_skills",
  "arguments": {}
}
```

---


## Roadmap Tools (4 tools)

### `roadmap_create`

**Create Roadmap**

Create a new roadmap in mem20

*Schema: {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Roadmap name"},
                    "description": {"type": "string",*

**Example Call:**

```json
{
  "name": "roadmap_create",
  "arguments": {}
}
```

---

### `roadmap_list`

**List Roadmaps**

List all roadmaps in mem20

*No input parameters*

**Example Call:**

```json
{
  "name": "roadmap_list",
  "arguments": {}
}
```

---

### `roadmap_get`

**Get Roadmap**

Get details of a specific roadmap

*Schema: {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Roadmap name"},
                },
                "required": ["name*

**Example Call:**

```json
{
  "name": "roadmap_get",
  "arguments": {}
}
```

---

### `roadmap_update_phase`

**Update Roadmap Phase**

Update a roadmap phase status

*Schema: {
                "type": "object",
                "properties": {
                    "roadmap": {"type": "string", "description": "Roadmap name"},
                    "phase": {"type": "string", "d*

**Example Call:**

```json
{
  "name": "roadmap_update_phase",
  "arguments": {}
}
```

---


## Self-Model Tools (3 tools)

### `self_model_create`

**Create Self-Model**

Create or update the agent's persistent self-model with capabilities, values, and history

*Schema: {
                "type": "object",
                "properties": {
                    "capabilities": {"type": "array", "items": {"type": "string"}, "description": "Agent capabilities", "default": [*

**Example Call:**

```json
{
  "name": "self_model_create",
  "arguments": {}
}
```

---

### `self_model_get`

**Get Self-Model**

Retrieve the agent's self-model

*No input parameters*

**Example Call:**

```json
{
  "name": "self_model_get",
  "arguments": {}
}
```

---

### `self_model_reflect`

**Self-Model Reflection**

Metacognitive reflection on own capabilities, gaps, and belief updates

*Schema: {
                "type": "object",
                "properties": {
                    "focus": {"type": "string", "enum": ["capabilities", "gaps", "beliefs", "values", "all"], "description": "Reflec*

**Example Call:**

```json
{
  "name": "self_model_reflect",
  "arguments": {}
}
```

---


## Theory of Mind Tools (2 tools)

### `theory_of_mind_simulate`

**Theory of Mind Simulation**

Simulate another agent's knowledge, beliefs, and reasoning

*Schema: {
                "type": "object",
                "properties": {
                    "agent_model": {"type": "object", "description": "Model of other agent {knowledge, beliefs, goals}"},
          *

**Example Call:**

```json
{
  "name": "theory_of_mind_simulate",
  "arguments": {}
}
```

---

### `theory_of_mind_perspective`

**Perspective Taking**

Generate perspective-taking: 'what this looks like from X's knowledge/values'

*Schema: {
                "type": "object",
                "properties": {
                    "entity": {"type": "string", "description": "Entity to take perspective of"},
                    "topic": {"typ*

**Example Call:**

```json
{
  "name": "theory_of_mind_perspective",
  "arguments": {}
}
```

---


## Thought Process / Reasoning Tools (9 tools)

### `tot_reason`

**Tree-of-Thoughts Reasoning**

ToT explores multiple reasoning paths simultaneously, evaluates each against criteria, and selects the best. Useful for complex decisions with many valid approaches.

*Schema: {
                "type": "object",
                "properties": {
                    "problem": {"type": "string", "description": "Problem to reason about"},
                    "branches": {"type"*

**Example Call:**

```json
{
  "name": "tot_reason",
  "arguments": {}
}
```

---

### `tot_modeling`

**ToT Modeling Decision**

Specialized ToT for 3D modeling decisions — explores topology, mesh flow, and construction approaches

*Schema: {
                "type": "object",
                "properties": {
                    "objective": {"type": "string", "description": "What you're trying to model"},
                    "constraints"*

**Example Call:**

```json
{
  "name": "tot_modeling",
  "arguments": {}
}
```

---

### `tot_diagnose`

**ToT Problem Diagnosis**

Specialized ToT for diagnosing issues — explores multiple root causes and solutions

*Schema: {
                "type": "object",
                "properties": {
                    "symptom": {"type": "string", "description": "What's going wrong"},
                    "context": {"type": "str*

**Example Call:**

```json
{
  "name": "tot_diagnose",
  "arguments": {}
}
```

---

### `reflexion`

**Reflexion**

Reflect on a completed task or failure, extract lessons, and store them to memory for future improvement

*Schema: {
                "type": "object",
                "properties": {
                    "task_description": {"type": "string", "description": "What was attempted"},
                    "outcome": {"ty*

**Example Call:**

```json
{
  "name": "reflexion",
  "arguments": {}
}
```

---

### `least_to_most`

**Least-to-Most Decomposition**

Decompose a complex problem into sub-problems from simplest to hardest, solve each, then combine

*Schema: {
                "type": "object",
                "properties": {
                    "problem": {"type": "string", "description": "Complex problem to decompose"},
                    "sub_problems"*

**Example Call:**

```json
{
  "name": "least_to_most",
  "arguments": {}
}
```

---

### `react_reason`

**ReAct Reasoning**

Interleave reasoning with tool calls: Think → Act → Observe → Think → Act. For tasks needing external information.

*Schema: {
                "type": "object",
                "properties": {
                    "goal": {"type": "string", "description": "What you're trying to accomplish"},
                    "available_to*

**Example Call:**

```json
{
  "name": "react_reason",
  "arguments": {}
}
```

---

### `beam_search`

**Beam Search Reasoning**

Maintain top-K reasoning paths at each step instead of committing to one. More thorough than ToT for deep problems.

*Schema: {
                "type": "object",
                "properties": {
                    "problem": {"type": "string", "description": "Problem to solve"},
                    "beam_width": {"type": "in*

**Example Call:**

```json
{
  "name": "beam_search",
  "arguments": {}
}
```

---

### `get_cognitive_tree_state`

**Get Cognitive Tree State**

Retrieves persistent telemetry data, active paths, or pruned branches for a given session.

*Schema: {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "The unique active session tracking hash"},
                    *

**Example Call:**

```json
{
  "name": "get_cognitive_tree_state",
  "arguments": {}
}
```

---

### `get_cognitive_tree_state`

**Get Cognitive Tree State**

Retrieves persistent telemetry data, active paths, or pruned branches for a given session.

*Schema: {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "The unique active session tracking hash"},
                    *

**Example Call:**

```json
{
  "name": "get_cognitive_tree_state",
  "arguments": {}
}
```

---


## Unity Tools (Optional) (5 tools)

### `unity_create_script`

**Unity Create Script**

Create a C# MonoBehaviour script in a Unity project. OPTIONAL integration: Unity must be installed.

*Schema: {
                "type": "object",
                "properties": {
                    "project_path": {"type": "string", "description": "Path to Unity project"},
                    "script_name": {*

**Example Call:**

```json
{
  "name": "unity_create_script",
  "arguments": {}
}
```

---

### `unity_build_project`

**Unity Build Project**

Build a Unity project for specified platform. OPTIONAL integration: Unity must be installed.

*Schema: {
                "type": "object",
                "properties": {
                    "project_path": {"type": "string", "description": "Path to Unity project"},
                    "build_path": {"*

**Example Call:**

```json
{
  "name": "unity_build_project",
  "arguments": {}
}
```

---

### `unity_run_test`

**Unity Run Tests**

Run Unity PlayMode or EditMode tests. OPTIONAL integration: Unity must be installed.

*Schema: {
                "type": "object",
                "properties": {
                    "project_path": {"type": "string", "description": "Path to Unity project"},
                    "test_mode": {"t*

**Example Call:**

```json
{
  "name": "unity_run_test",
  "arguments": {}
}
```

---

### `unity_generate_asmdef`

**Unity Generate Assembly Definition**

Generate an Assembly Definition (.asmdef) file. (Writes local files; does not require the Unity executable.)

*Schema: {
                "type": "object",
                "properties": {
                    "project_path": {"type": "string", "description": "Path to Unity project"},
                    "asmdef_path": {*

**Example Call:**

```json
{
  "name": "unity_generate_asmdef",
  "arguments": {}
}
```

---

### `unity_validate_project`

**Unity Validate Project**

Validate Unity project structure and check for common issues. (Reads local files; does not require the Unity executable.)

*Schema: {
                "type": "object",
                "properties": {
                    "project_path": {"type": "string", "description": "Path to Unity project"},
                },
                "*

**Example Call:**

```json
{
  "name": "unity_validate_project",
  "arguments": {}
}
```

---


## World Model Tools (8 tools)

### `world_model_add_variable`

**World Model Add Variable**

Add a state variable to the world model

*Schema: {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Variable name"},
                    "initial_value": {"type": "numbe*

**Example Call:**

```json
{
  "name": "world_model_add_variable",
  "arguments": {}
}
```

---

### `world_model_add_rule`

**World Model Add Rule**

Add a transition rule to the world model

*Schema: {
                "type": "object",
                "properties": {
                    "condition": {"type": "string", "description": "Condition expression (e.g., 'temperature > 100')"},
            *

**Example Call:**

```json
{
  "name": "world_model_add_rule",
  "arguments": {}
}
```

---

### `world_model_simulate`

**World Model Simulate**

Run world model simulation for specified steps

*Schema: {
                "type": "object",
                "properties": {
                    "steps": {"type": "integer", "description": "Number of simulation steps", "default": 10},
                },
   *

**Example Call:**

```json
{
  "name": "world_model_simulate",
  "arguments": {}
}
```

---

### `world_model_predict`

**World Model Predict**

Make predictions using the world model

*Schema: {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Predictive query"},
                    "horizon": {"type": "integer*

**Example Call:**

```json
{
  "name": "world_model_predict",
  "arguments": {}
}
```

---

### `world_model_get_state`

**World Model Get State**

Get current world model state

*No input parameters*

**Example Call:**

```json
{
  "name": "world_model_get_state",
  "arguments": {}
}
```

---

### `world_model_reset`

**World Model Reset**

Reset the world model to empty

*No input parameters*

**Example Call:**

```json
{
  "name": "world_model_reset",
  "arguments": {}
}
```

---

### `world_model_record_prediction`

**World Model Record Prediction**

Record a prediction emitted by simulation for later reality-checking. 

*Schema: {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The predictive query / claim"},
                    "prediction": {"*

**Example Call:**

```json
{
  "name": "world_model_record_prediction",
  "arguments": {}
}
```

---

### `world_model_resolve_prediction`

**World Model Resolve Prediction**

Resolve a recorded prediction against reality. Set 

*Schema: {
                "type": "object",
                "properties": {
                    "prediction_id": {"type": "string", "description": "prediction_id from world_model_record_prediction"},
        *

**Example Call:**

```json
{
  "name": "world_model_resolve_prediction",
  "arguments": {}
}
```

---

