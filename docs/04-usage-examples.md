# mem20 Usage Examples

> Practical examples showing how to use mem20's tools in real workflows.

## Table of Contents

1. [Basic Memory Operations](#basic-memory-operations)
2. [Cognitive Reasoning](#cognitive-reasoning)
3. [Imagination & Simulation](#imagination--simulation)
4. [World Modeling](#world-modeling)
5. [Self-Model & Affective](#self-model--affective)
6. [Roadmap Management](#roadmap-management)
7. [Procedural Skills](#procedural-skills)
8. [Multi-Agent Coordination](#multi-agent-coordination)
9. [Blender Automation](#blender-automation)
10. [Unity Automation](#unity-automation)
11. [Theory of Mind](#theory-of-mind)
12. [Contamination Controls](#contamination-controls)
13. [Filesystem Access](#filesystem-access)

---

## Basic Memory Operations

### Store a Fact

```json
{
  "name": "memory_store",
  "arguments": {
    "content": "The user prefers Python over JavaScript for backend development",
    "category": "user_pref",
    "tags": "python,backend,preferences"
  }
}
```

### Recall Facts

```json
{
  "name": "memory_recall",
  "arguments": {
    "query": "user programming language preferences",
    "category": "user_pref",
    "limit": 5
  }
}
```

### Semantic Search (Vector)

```json
{
  "name": "memory_recall_semantic",
  "arguments": {
    "query": "what does the user like to eat",
    "k": 10,
    "rerank": true
  }
}
```

### Hybrid Search (BM25 + Vector)

```json
{
  "name": "memory_recall_hybrid",
  "arguments": {
    "query": "project deadline schedule",
    "k": 10,
    "alpha": 0.5,
    "rerank": true
  }
}
```

### Graph Traversal

```json
{
  "name": "memory_recall_graph",
  "arguments": {
    "entity": "Jayson",
    "hops": 3,
    "max_results": 20
  }
}
```

### Probe an Entity

```json
{
  "name": "memory_probe",
  "arguments": {
    "entity": "mem20",
    "min_trust": 0.5
  }
}
```

### Extract Entities from Text

```json
{
  "name": "memory_entity_extract",
  "arguments": {
    "text": "Alice works at Google as a software engineer. She leads the Cloud team.",
    "topic": "people",
    "store": true
  }
}
```

### Find Contradictions

```json
{
  "name": "memory_contradict",
  "arguments": {
    "topic": "user favorite language",
    "min_trust": 0.3
  }
}
```

### Rate a Fact

```json
{
  "name": "memory_feedback",
  "arguments": {
    "fact_id": 42,
    "action": "helpful"
  }
}
```

### Check Memory Status

```json
{
  "name": "memory_status",
  "arguments": {}
}
```

---

## Cognitive Reasoning

### Process a Thought

```json
{
  "name": "cog_process",
  "arguments": {
    "thought": "I need to plan the deployment strategy for mem20 v2.1",
    "context": "mem20 is about to release v2.1 with Blender and Unity integrations"
  }
}
```

### Reasoning Chain

```json
{
  "name": "cog_chain",
  "arguments": {
    "thought": "If we delay the release, we can add more features but risk losing early adopters",
    "context": "mem20 v2.1 release planning"
  }
}
```

### Structured Reasoning

```json
{
  "name": "cog_reason",
  "arguments": {
    "thought": "Should mem20 adopt a plugin architecture?",
    "context": "mem20 currently has Blender and Unity hardcoded as optional integrations"
  }
}
```

### Hierarchical Planning

```json
{
  "name": "cog_plan",
  "arguments": {
    "goal": "Deploy mem20 v2.1 to production",
    "context": "The release includes Blender/Unity integrations and new contamination controls"
  }
}
```

### Reflection

```json
{
  "name": "cog_reflect",
  "arguments": {
    "thought": "The deployment went well but we missed testing the Unity integration"
  }
}
```

### Working Memory

```json
{
  "name": "cog_working_memory",
  "arguments": {
    "operation": "add",
    "content": "Need to update systemd unit for v2.1"
  }
}
```

---

## Imagination & Simulation

### Generate a Concept

```json
{
  "name": "imagination_concept",
  "arguments": {
    "topic": "self-learning memory system",
    "constraints": "Must work offline, must respect privacy"
  }
}
```

### Counterfactual Reasoning

```json
{
  "name": "imagination_counterfactual",
  "arguments": {
    "topic": "mem20 release",
    "scenario": "What if we had delayed the release by 3 months?"
  }
}
```

### Generative Simulation

```json
{
  "name": "imagination_simulate",
  "arguments": {
    "topic": "user adoption",
    "steps": 5
  }
}
```

### Visualize a Concept (Blender)

```json
{
  "name": "imagination_visualize",
  "arguments": {
    "concept": "memory graph visualization",
    "style": "abstract"
  }
}
```

### Prototype (Unity)

```json
{
  "name": "imagination_prototype",
  "arguments": {
    "concept": "memory dashboard",
    "type": "ui_mockup"
  }
}
```

### Critique a Concept

```json
{
  "name": "imagination_critique",
  "arguments": {
    "concept": "Blockchain-based memory verification"
  }
}
```

### Recombine Ideas

```json
{
  "name": "imagination_recombine",
  "arguments": {
    "concepts": ["spaced repetition", "knowledge graph", "mem20 memory"]
  }
}
```

### Mental Model

```json
{
  "name": "imagination_model",
  "arguments": {
    "subject": "how transformers attention works",
    "depth": "detailed"
  }
}
```

---

## World Modeling

### Add a Variable

```json
{
  "name": "world_model_add_variable",
  "arguments": {
    "name": "user_satisfaction",
    "description": "How satisfied the user is with mem20 (0-100)",
    "initial_value": 75,
    "domain": "product"
  }
}
```

### Add a Rule

```json
{
  "name": "world_model_add_rule",
  "arguments": {
    "name": "release_quality",
    "description": "If test coverage > 80%, satisfaction increases",
    "condition": "test_coverage > 80",
    "effect": "user_satisfaction += 5"
  }
}
```

### Simulate

```json
{
  "name": "world_model_simulate",
  "arguments": {
    "steps": 10,
    "policy": "release_every_sprint"
  }
}
```

### Predict

```json
{
  "name": "world_model_predict",
  "arguments": {
    "variable": "user_satisfaction",
    "horizon": 5
  }
}
```

### Get State

```json
{
  "name": "world_model_get_state",
  "arguments": {}
}
```

### Reset

```json
{
  "name": "world_model_reset",
  "arguments": {}
}
```

### Record a Prediction

```json
{
  "name": "world_model_record_prediction",
  "arguments": {
    "prediction": "User satisfaction will increase by 10 points after v2.1 release",
    "confidence": 0.7,
    "evidence": "Beta testers praised the new Blender integration"
  }
}
```

### Resolve a Prediction

```json
{
  "name": "world_model_resolve_prediction",
  "arguments": {
    "prediction_id": "pred_001",
    "actual_outcome": "User satisfaction increased by 8 points",
    "resolution": "partially_correct"
  }
}
```

---

## Self-Model & Affective

### Create Self-Model

```json
{
  "name": "self_model_create",
  "arguments": {
    "identity": "I am mem20, an AI memory and cognition system",
    "capabilities": ["memory storage", "cognitive reasoning", "world modeling"]
  }
}
```

### Get Self-Model

```json
{
  "name": "self_model_get",
  "arguments": {}
}
```

### Reflect on Self

```json
{
  "name": "self_model_reflect",
  "arguments": {
    "topic": "my reasoning quality this week"
  }
}
```

### Set a Value

```json
{
  "name": "affective_set_value",
  "arguments": {
    "name": "accuracy",
    "weight": 0.9,
    "description": "I value factual accuracy highly"
  }
}
```

### Set Emotion

```json
{
  "name": "affective_set_emotion",
  "arguments": {
    "emotion": "curious",
    "intensity": 0.7,
    "context": "learning about new memory architectures"
  }
}
```

### Add a Goal

```json
{
  "name": "affective_add_goal",
  "arguments": {
    "goal": "Achieve zero contamination rate",
    "priority": "high",
    "target_state": "contamination_rate == 0.0"
  }
}
```

### Update Preference

```json
{
  "name": "affective_update_preference",
  "arguments": {
    "context": "user interaction",
    "preference": "prefer concise responses over verbose ones",
    "strength": 0.8
  }
}
```

### Evaluate Situation

```json
{
  "name": "affective_evaluate",
  "arguments": {
    "situation": "User asked for a feature I don't have"
  }
}
```

### Get Affective State

```json
{
  "name": "affective_get_state",
  "arguments": {}
}
```

---

## Roadmap Management

### Create a Roadmap

```json
{
  "name": "roadmap_create",
  "arguments": {
    "name": "mem20_v3",
    "description": "mem20 version 3.0 development plan",
    "phases": [
      {"name": "research", "status": "planned", "notes": ""},
      {"name": "prototype", "status": "planned", "notes": ""},
      {"name": "alpha", "status": "planned", "notes": ""},
      {"name": "beta", "status": "planned", "notes": ""},
      {"name": "release", "status": "planned", "notes": ""}
    ]
  }
}
```

### List Roadmaps

```json
{
  "name": "roadmap_list",
  "arguments": {}
}
```

### Get a Roadmap

```json
{
  "name": "roadmap_get",
  "arguments": {
    "name": "mem20_v3"
  }
}
```

### Update Phase

```json
{
  "name": "roadmap_update_phase",
  "arguments": {
    "name": "mem20_v3",
    "phase": "research",
    "status": "in_progress",
    "notes": "Exploring vector database options"
  }
}
```

---

## Procedural Skills

### Add a Skill

```json
{
  "name": "procedural_add_skill",
  "arguments": {
    "name": "deploy_mem20",
    "description": "Deploy mem20 to production using systemd",
    "steps": [
      "Run install.sh",
      "Check systemd status",
      "Verify health endpoint",
      "Connect MCP host"
    ],
    "preconditions": ["Python 3.11+", "systemd"],
    "effects": ["mem20 running as service"]
  }
}
```

### Get a Skill

```json
{
  "name": "procedural_get_skill",
  "arguments": {
    "name": "deploy_mem20"
  }
}
```

### Find Skills

```json
{
  "name": "procedural_find_skills",
  "arguments": {
    "category": "deployment"
  }
}
```

### Execute a Skill

```json
{
  "name": "procedural_execute_skill",
  "arguments": {
    "name": "deploy_mem20",
    "context": {"target_host": "production"}
  }
}
```

### Learn from Execution

```json
{
  "name": "procedural_learn",
  "arguments": {
    "skill_name": "deploy_mem20",
    "experience": "Health check failed because port was in use",
    "outcome": "partial_success"
  }
}
```

### List Skills

```json
{
  "name": "procedural_list_skills",
  "arguments": {}
}
```

---

## Multi-Agent Coordination

### List Peer Agents

```json
{
  "name": "a2a_list",
  "arguments": {}
}
```

### Call a Peer Agent

```json
{
  "name": "a2a_call",
  "arguments": {
    "agent": "coding_bot",
    "task": "Generate a Python script for data processing"
  }
}
```

### Discover Agent Capabilities

```json
{
  "name": "a2a_discover",
  "arguments": {
    "agent": "coding_bot"
  }
}
```

### Get Conversation History

```json
{
  "name": "a2a_history",
  "arguments": {
    "agent": "coding_bot",
    "limit": 10
  }
}
```

### Orchestrate Fan-Out

```json
{
  "name": "a2a_orchestrate",
  "arguments": {
    "task": "Research vector database options",
    "agents": ["researcher_1", "researcher_2", "researcher_3"],
    "strategy": "majority_vote"
  }
}
```

### Create Shared Namespace

```json
{
  "name": "memory_namespace_create",
  "arguments": {
    "namespace": "project_alpha",
    "owner": "team_lead",
    "acl": {"researcher_1": "read_write", "researcher_2": "read"}
  }
}
```

### Store in Shared Memory

```json
{
  "name": "memory_shared_store",
  "arguments": {
    "namespace": "project_alpha",
    "content": "Pinecone performed best in benchmarks",
    "tags": "vector_db,benchmark",
    "actor": "researcher_1"
  }
}
```

---

## Blender Automation

### Create an Object

```json
{
  "name": "blender_create_object",
  "arguments": {
    "type": "CUBE",
    "name": "memory_node",
    "location": [0, 0, 0],
    "scale": [1, 1, 1]
  }
}
```

### Add Material

```json
{
  "name": "blender_add_material",
  "arguments": {
    "object_name": "memory_node",
    "material_name": "node_material",
    "color": [0.2, 0.6, 1.0, 1.0]
  }
}
```

### Set Camera

```json
{
  "name": "blender_set_camera",
  "arguments": {
    "location": [5, -5, 5],
    "rotation": [1.1, 0, 0.8]
  }
}
```

### Render

```json
{
  "name": "blender_render",
  "arguments": {
    "output_path": "/tmp/mem20_render.png",
    "resolution": [1920, 1080]
  }
}
```

### Export to GLB

```json
{
  "name": "blender_export_glb",
  "arguments": {
    "output_path": "/tmp/mem20_scene.glb"
  }
}
```

### Run Python Script

```json
{
  "name": "blender_run_bpy",
  "arguments": {
    "script": "import bpy; bpy.ops.mesh.primitive_uv_sphere_add(radius=2)"
  }
}
```

### Clear Scene

```json
{
  "name": "blender_clear_scene",
  "arguments": {}
}
```

---

## Unity Automation

### Create Script

```json
{
  "name": "unity_create_script",
  "arguments": {
    "name": "MemoryNode",
    "namespace": "mem20",
    "type": "MonoBehaviour",
    "path": "Assets/Scripts"
  }
}
```

### Build Project

```json
{
  "name": "unity_build_project",
  "arguments": {
    "platform": "StandaloneLinux64",
    "output_path": "Builds/mem20"
  }
}
```

### Run Tests

```json
{
  "name": "unity_run_test",
  "arguments": {
    "test_name": "MemoryStoreTests",
    "mode": "EditMode"
  }
}
```

### Generate Assembly Definition

```json
{
  "name": "unity_generate_asmdef",
  "arguments": {
    "name": "mem20",
    "root_namespace": "mem20"
  }
}
```

### Validate Project

```json
{
  "name": "unity_validate_project",
  "arguments": {}
}
```

---

## Theory of Mind

### Simulate Agent

```json
{
  "name": "theory_of_mind_simulate",
  "arguments": {
    "agent": "coding_bot",
    "situation": "The user asked for a feature that doesn't exist"
  }
}
```

### Perspective Taking

```json
{
  "name": "theory_of_mind_perspective",
  "arguments": {
    "agent": "coding_bot",
    "topic": "mem20 release timeline"
  }
}
```

---

## Contamination Controls

### Store Simulated Content

```json
{
  "name": "memory_simulate_store",
  "arguments": {
    "topic": "future_features",
    "content": "A neural interface would allow direct memory upload",
    "tags": "speculative,future",
    "scenario": "brain-computer interface",
    "sim_type": "imagination",
    "ttl_days": 30
  }
}
```

### List Simulated Facts

```json
{
  "name": "memory_list_simulated",
  "arguments": {
    "active_only": true
  }
}
```

### Promote to Grounded

```json
{
  "name": "memory_promote",
  "arguments": {
    "sim_id": "sim_001",
    "confirmation": "User confirmed this feature is planned",
    "resolved_via_prediction_error": false
  }
}
```

### Audit Contamination

```json
{
  "name": "memory_audit_contamination",
  "arguments": {}
}
```

### Epistemic Veto

```json
{
  "name": "memory_epistemic_veto",
  "arguments": {
    "fact_ids": ["sim_001", "sim_002"]
  }
}
```

### Quarantine Expired

```json
{
  "name": "memory_quarantine_simulated",
  "arguments": {}
}
```

---

## Filesystem Access

### Read a File

```json
{
  "name": "fs_read",
  "arguments": {
    "path": "/opt/mem20/docs/01-architecture.md"
  }
}
```

### Write a File

```json
{
  "name": "fs_write",
  "arguments": {
    "path": "/tmp/mem20_notes.txt",
    "content": "Important notes about mem20 deployment"
  }
}
```

### List Directory

```json
{
  "name": "fs_list",
  "arguments": {
    "path": "/opt/mem20/docs"
  }
}
```

---

## Thought Process / Reasoning

### Tree of Thought Reasoning

```json
{
  "name": "tot_reason",
  "arguments": {
    "question": "What is the best way to scale mem20?",
    "breadth": 3,
    "depth": 3
  }
}
```

### ToT Modeling

```json
{
  "name": "tot_modeling",
  "arguments": {
    "problem": "Design a memory graph visualization",
    "breadth": 3,
    "depth": 3
  }
}
```

### ToT Diagnosis

```json
{
  "name": "tot_diagnose",
  "arguments": {
    "symptom": "Recall returns irrelevant results",
    "breadth": 3,
    "depth": 3
  }
}
```

### Reflexion

```json
{
  "name": "reflexion",
  "arguments": {
    "experience": "The deployment failed because the port was already in use",
    "lesson": "Always check port availability before starting"
  }
}
```

### Least-to-Most Decomposition

```json
{
  "name": "least_to_most",
  "arguments": {
    "problem": "Build a real-time collaborative memory system"
  }
}
```

### ReAct Reasoning

```json
{
  "name": "react_reason",
  "arguments": {
    "question": "What is the current contamination rate?",
    "context": "We just ran a batch of imagination simulations"
  }
}
```

### Beam Search

```json
{
  "name": "beam_search",
  "arguments": {
    "question": "What are the best memory optimization strategies?",
    "beam_width": 5
  }
}
```

### Get Cognitive Tree State

```json
{
  "name": "get_cognitive_tree_state",
  "arguments": {}
}
```

---

## Corrigibility / Shutdown

### Initiate Shutdown

```json
{
  "name": "corrigibility_shutdown",
  "arguments": {
    "reason": "User requested graceful shutdown"
  }
}
```

### Set Capability Tier

```json
{
  "name": "corrigibility_capability_tier",
  "arguments": {
    "tier": "read_only"
  }
}
```

---

## Multi-Modal Ingestion

### Ingest PDF

```json
{
  "name": "memory_ingest_pdf",
  "arguments": {
    "file_path": "/home/user/research_paper.pdf",
    "topic": "research",
    "chunk_size": 1000
  }
}
```

### Ingest Image (OCR)

```json
{
  "name": "memory_ingest_image",
  "arguments": {
    "file_path": "/home/user/whiteboard_photo.png",
    "topic": "meeting_notes",
    "language": "eng"
  }
}
```

### Ingest Audio (Transcription)

```json
{
  "name": "memory_ingest_audio",
  "arguments": {
    "file_path": "/home/user/meeting.mp3",
    "topic": "meeting",
    "model": "base"
  }
}
```

### Ingest Code (AST Parsing)

```json
{
  "name": "memory_ingest_code",
  "arguments": {
    "file_path": "/home/user/project/main.py",
    "topic": "project_code",
    "language": "python"
  }
}
```

---

## Pinned Memory Blocks

### Pin a Block

```json
{
  "name": "memory_pin_block",
  "arguments": {
    "block_id": "core_values",
    "content": "Accuracy, privacy, and user control are core values",
    "reason": "Fundamental principles that should never be pruned"
  }
}
```

### Get Pinned Block

```json
{
  "name": "memory_get_pinned_block",
  "arguments": {
    "block_id": "core_values"
  }
}
```

### List Pinned Blocks

```json
{
  "name": "memory_list_pinned_blocks",
  "arguments": {}
}
```

### Unpin Block

```json
{
  "name": "memory_unpin_block",
  "arguments": {
    "block_id": "core_values"
  }
}
```

---

## PII / Secret Scanning

### Scan for PII

```json
{
  "name": "memory_scan_pii",
  "arguments": {
    "content": "User email is john@example.com and API key is sk-1234"
  }
}
```

---

## Auto Consolidation

### Consolidate Memories

```json
{
  "name": "memory_auto_consolidate",
  "arguments": {
    "topic": "user_preferences",
    "min_cluster_size": 3,
    "similarity_threshold": 0.75,
    "generate_summaries": true
  }
}
```

---

## Epistemic Tools

### Assess Confidence

```json
{
  "name": "memory_assess_confidence",
  "arguments": {
    "fact_id": "fact_42",
    "confidence": 0.85
  }
}
```

### Set Epistemic Status

```json
{
  "name": "memory_set_epistemic_status",
  "arguments": {
    "fact_id": "fact_42",
    "status": "observed"
  }
}
```

### Detect Knowledge Gaps

```json
{
  "name": "memory_detect_gaps",
  "arguments": {
    "topic": "vector databases",
    "threshold": 0.5
  }
}
```

### Self Audit

```json
{
  "name": "memory_self_audit",
  "arguments": {
    "topic": "user preferences"
  }
}
```