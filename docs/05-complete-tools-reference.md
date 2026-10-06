# mem20 MCP — Complete Tools Reference

> Every tool, every feature, every command. 174 tools across 20 domains. Written for someone who has never seen mem20 before.

---

## How to Call a Tool

Every tool is called as a JSON-RPC request with two fields: `name` (the tool name) and `arguments` (a JSON object matching the tool's schema). Example:

```json
{
  "name": "memory_store",
  "arguments": {
    "content": "The user prefers Python",
    "category": "user_pref",
    "tags": "python,backend"
  }
}
```

The mem20 MCP server listens on stdio (stdin/stdout) using the Model Context Protocol. It speaks JSON-RPC 2.0. Every response contains either a result string or an error.

---

## Domain 1: Core Memory Tools (20 tools)

These are the foundation of mem20 — how you store, retrieve, and manage persistent memory.

### `memory_store`

**What it does:** Saves a fact to mem20's persistent memory. This is how you tell mem20 something to remember.

**Input schema:**
- `content` (string, required) — The fact or information to store
- `category` (string, optional, default `"general"`) — One of: `"user_pref"`, `"project"`, `"tool"`, `"general"`
- `tags` (string, optional, default empty) — Comma-separated tags for searching

**Output:** Confirmation string like `"Stored: fact_id_42"`

**Example call:**
```json
{
  "name": "memory_store",
  "arguments": {
    "content": "Jayson prefers Neovim over VS Code",
    "category": "user_pref",
    "tags": "editor,preferences"
  }
}
```

**When to use it:** Whenever you want mem20 to remember something permanently across sessions.

---

### `memory_recall`

**What it does:** Searches and retrieves facts from mem20's memory. The primary way to get information back out.

**Input schema:**
- `query` (string, required) — Search keywords or phrase
- `category` (string, optional) — Filter by category
- `limit` (integer, optional, default 10, min 1, max 50) — Maximum results

**Output:** List of matching memories with their content, category, tags, and trust scores.

**Example call:**
```json
{
  "name": "memory_recall",
  "arguments": {
    "query": "preferred editor",
    "category": "user_pref",
    "limit": 5
  }
}
```

**When to use it:** Whenever you need to look up something mem20 previously stored.

---

### `memory_probe`

**What it does:** Gets ALL facts about a specific entity (person, project, concept). Deeper than recall — focuses on one entity.

**Input schema:**
- `entity` (string, required) — Name of the entity to probe
- `min_trust` (number, optional, default 0.3) — Minimum trust score filter

**Output:** All facts associated with the entity, ranked by trust.

**Example call:**
```json
{
  "name": "memory_probe",
  "arguments": {
    "entity": "Altimator",
    "min_trust": 0.5
  }
}
```

**When to use it:** When you want a complete profile of something — all known facts about a person, project, or concept.

---

### `memory_reason`

**What it does:** Performs compositional reasoning across multiple entities simultaneously.

**Input schema:**
- `entities` (array of strings, required) — List of entity names to reason about
- `min_trust` (number, optional, default 0.3) — Minimum trust score

**Output:** Reasoning results combining facts from all entities.

**Example call:**
```json
{
  "name": "memory_reason",
  "arguments": {
    "entities": ["Altimator", "mem20", "Jayson"],
    "min_trust": 0.4
  }
}
```

**When to use it:** When you need to connect facts across multiple entities — e.g., "How does Jayson's work on Altimator relate to his work on mem20?"

---

### `memory_status`

**What it does:** Returns mem20 memory system stats — ledger events, deep entries, storage health.

**Input schema:** None.

**Output:** JSON with `ledger_events`, `deep_entries`, `MEMORY.md` status, `USER.md` status, `last_event` timestamp.

**Example call:**
```json
{ "name": "memory_status", "arguments": {} }
```

**When to use it:** Quick health check of the memory system.

---

### `memory_contradict`

**What it does:** Finds facts that make conflicting claims about a topic.

**Input schema:**
- `query` (string, required) — Topic to check
- `min_trust` (number, optional, default 0.3) — Minimum trust threshold

**Output:** List of contradicting fact pairs.

**Example call:**
```json
{
  "name": "memory_contradict",
  "arguments": {
    "query": "favorite programming language",
    "min_trust": 0.3
  }
}
```

**When to use it:** When you suspect there are conflicting memories and need to resolve them.

---

### `memory_related`

**What it does:** Finds facts structurally connected to a given entity in the recall graph.

**Input schema:**
- `entity` (string, required) — Entity name
- `min_trust` (number, optional, default 0.3) — Trust threshold

**Output:** Connected entities and their relationships.

**Example call:**
```json
{
  "name": "memory_related",
  "arguments": { "entity": "mem20" }
}
```

**When to use it:** To discover what's connected to something in the knowledge graph.

---

### `memory_feedback`

**What it does:** Rates a memory fact as helpful or unhelpful, training the trust scoring system.

**Input schema:**
- `fact_id` (integer, required) — ID of the fact to rate
- `rating` (string, required, enum `["helpful", "unhelpful"]`) — The rating

**Output:** Confirmation of the rating.

**Example call:**
```json
{
  "name": "memory_feedback",
  "arguments": { "fact_id": 42, "rating": "helpful" }
}
```

**When to use it:** When a recalled fact was useful or useless — helps mem20 learn what's trustworthy.

---

### `memory_store` (simulated partition)

**What it does:** Stores a fact in the SIMULATED partition (not grounded). For hypotheticals and counterfactuals.

**Input schema:** Same as `memory_store` but the content is routed to the simulated partition.

**Output:** Confirmation with simulated fact ID.

**Example call:**
```json
{
  "name": "memory_simulate_store",
  "arguments": {
    "topic": "counterfactual_scenarios",
    "content": "What if mem20 had been built in Rust instead of Python?",
    "tags": "simulation,counterfactual"
  }
}
```

**When to use it:** For hypotheses, "what if" scenarios, and things that haven't been verified.

---

### `memory_promote`

**What it does:** Promotes a simulated fact to GROUNDED status after verification.

**Input schema:**
- `sim_id` (string, required) — ID of the simulated fact
- `confirmation` (boolean, required) — Must be `true` to promote

**Output:** Confirmation of promotion.

**Example call:**
```json
{
  "name": "memory_promote",
  "arguments": { "sim_id": "sim_001", "confirmation": true }
}
```

**When to use it:** When a hypothesis has been verified and should become a real fact.

---

### `memory_list_simulated`

**What it does:** Lists all active simulated facts.

**Input schema:**
- `active_only` (boolean, optional, default `true`) — Exclude quarantined/expired

**Output:** List of simulated facts with their topics and content.

**Example call:**
```json
{ "name": "memory_list_simulated", "arguments": {} }
```

**When to use it:** To review all active hypotheses and counterfactuals.

---

### `memory_quarantine_simulated`

**What it does:** Quarantines simulated facts whose TTL (time-to-live/decay window) has expired.

**Input schema:** None.

**Output:** List of quarantined facts.

**Example call:**
```json
{ "name": "memory_quarantine_simulated", "arguments": {} }
```

**When to use it:** To clean up expired hypotheses automatically.

---

### `memory_audit_contamination`

**What it does:** Audits the memory system for contamination — verifying grounded facts haven't been mixed with simulated ones.

**Input schema:** None.

**Output:** `contamination_rate`, `violations` list, `grounded_facts` count, `simulated_facts` count.

**Example call:**
```json
{ "name": "memory_audit_contamination", "arguments": {} }
```

**When to use it:** Regular integrity check to ensure memory purity.

---

### `memory_epistemic_veto`

**What it does:** Vetoes facts that a plan relies on — used for safety-critical decisions.

**Input schema:**
- `fact_ids` (array of strings, required) — Fact IDs the plan relies on

**Output:** Veto status for each fact.

**Example call:**
```json
{
  "name": "memory_epistemic_veto",
  "arguments": { "fact_ids": ["fact_1", "fact_2"] }
}
```

**When to use it:** Before executing important plans — ensures the underlying facts are reliable.

---

### `memory_pin_block`

**What it does:** Pins a memory block as a core reference. Pinned blocks are immune to pruning.

**Input schema:**
- `block_id` (string, required) — Unique block identifier
- `content` (string, required) — The content to pin

**Output:** Confirmation of pinning.

**Example call:**
```json
{
  "name": "memory_pin_block",
  "arguments": {
    "block_id": "core_principles",
    "content": "mem20 design principles..."
  }
}
```

**When to use it:** For critical reference material that must never be pruned.

---

### `memory_unpin_block`

**What it does:** Unpins a previously pinned block.

**Input schema:**
- `block_id` (string, required) — The block identifier

**Output:** Confirmation.

**Example call:**
```json
{
  "name": "memory_unpin_block",
  "arguments": { "block_id": "core_principles" }
}
```

**When to use it:** When a pinned block is no longer needed as critical reference.

---

### `memory_list_pinned_blocks`

**What it does:** Lists all pinned memory blocks.

**Input schema:** None.

**Output:** List of all pinned blocks with their IDs and content summaries.

**Example call:**
```json
{ "name": "memory_list_pinned_blocks", "arguments": {} }
```

**When to use it:** To review all pinned reference material.

---

### `memory_get_pinned_block`

**What it does:** Gets a specific pinned block by ID.

**Input schema:**
- `block_id` (string, required) — Block identifier

**Output:** The full pinned block content.

**Example call:**
```json
{
  "name": "memory_get_pinned_block",
  "arguments": { "block_id": "core_principles" }
}
```

**When to use it:** To retrieve a specific pinned reference.

---

### `memory_auto_consolidate`

**What it does:** Clusters similar memories and generates higher-level summaries.

**Input schema:**
- `topic` (string, optional, default `"*"`) — Topic to consolidate

**Output:** Summary of consolidated clusters.

**Example call:**
```json
{
  "name": "memory_auto_consolidate",
  "arguments": { "topic": "projects" }
}
```

**When to use it:** To reduce memory redundancy by merging similar facts.

---

### `memory_cluster`

**What it does:** Groups related memories into clusters.

**Input schema:** None specified.

**Output:** Clustered groups of related memories.

**Example call:**
```json
{ "name": "memory_cluster", "arguments": {} }
```

**When to use it:** To organize memories by similarity.

---

### `memory_timeline`

**What it does:** Views memories in chronological order.

**Input schema:** None.

**Output:** Memories sorted by timestamp.

**Example call:**
```json
{ "name": "memory_timeline", "arguments": {} }
```

**When to use it:** To see the history of what mem20 has learned over time.

---

### `memory_triggers`

**What it does:** Lists memory triggers — conditions or events that should prompt mem20 to recall certain facts.

**Input schema:** None.

**Output:** List of active triggers.

**Example call:**
```json
{ "name": "memory_triggers", "arguments": {} }
```

**When to use it:** To review what events cause mem20 to automatically recall information.

---

### `memory_mood_tag`

**What it does:** Tags memories with emotional context — helps track how mem20 "felt" about recorded events.

**Input schema:**
- `fact_id` — Fact identifier
- `mood` — Mood tag

**Output:** Confirmation.

**Example call:**
```json
{
  "name": "memory_mood_tag",
  "arguments": { "fact_id": 42, "mood": "positive" }
}
```

**When to use it:** To add emotional context to a memory for affective reasoning.

---

### `memory_stats`

**What it does:** Returns detailed memory statistics.

**Input schema:** None.

**Output:** Stats including grounded count, simulated count, average trust, categories distribution.

**Example call:**
```json
{ "name": "memory_stats", "arguments": {} }
```

**When to use it:** Detailed analytics about the memory system.

---

### `memory_graph_traverse`

**What it does:** Traverses the memory knowledge graph from a starting entity with configurable hops.

**Input schema:**
- `entity` (string, required) — Starting entity
- `hops` (integer, optional) — Number of relationship hops
- `max_results` (integer, optional) — Max results

**Output:** Graph traversal results showing entities and relationships.

**Example call:**
```json
{
  "name": "memory_graph_traverse",
  "arguments": { "entity": "Jayson", "hops": 3, "max_results": 20 }
}
```

**When to use it:** To explore the full knowledge graph around an entity.

---

### `memory_export`

**What it does:** Exports all memories to a portable format.

**Input schema:** None.

**Output:** Export file path or contents.

**Example call:**
```json
{ "name": "memory_export", "arguments": {} }
```

**When to use it:** To backup or transfer all memories.

---

### `memory_import`

**What it does:** Imports memories from a portable format.

**Input schema:** File path to import from.

**Output:** Confirmation of import.

**Example call:**
```json
{
  "name": "memory_import",
  "arguments": { "file_path": "/path/to/backup.json" }
}
```

**When to use it:** To restore memories from a backup.

---

### `memory_context_window`

**What it does:** Manages the working context window — controls what's currently in active context.

**Input schema:**
- `operation` (string) — `"add"`, `"retrieve"`, `"transform"`, `"clear"`
- `content` (string) — Content to add

**Output:** Current context window state.

**Example call:**
```json
{
  "name": "cog_working_memory",
  "arguments": { "operation": "add", "content": "Need to check the altimator build" }
}
```

**When to use it:** To manage what's actively in mem20's working memory during a session.

---

### `memory_deduplicate`

**What it does:** Finds and removes duplicate memories.

**Input schema:** None.

**Output:** List of deduplicated entries.

**Example call:**
```json
{ "name": "memory_deduplicate", "arguments": {} }
```

**When to use it:** To clean up redundant memories.

---

## Domain 2: Cognitive Tools (6 tools)

These are mem20's reasoning and thought processing capabilities.

### `cog_process`

**What it does:** Processes a thought through mem20's cognitive engine — decomposes, analyzes, and structures thinking.

**Input schema:**
- `thought` (string, required) — The thought to process
- `mode` (string, optional, enum `["analyze"`, `"synthesize"`, `"evaluate"`, `"plan"]`, default `"analyze"`) — Processing mode
- `context` (string, optional, default empty) — Additional context

**Output:** Structured analysis of the thought.

**Example call:**
```json
{
  "name": "cog_process",
  "arguments": {
    "thought": "Should we document the Altimator codebase?",
    "mode": "analyze",
    "context": "Jayson asked for comprehensive docs"
  }
}
```

**When to use it:** To think through any problem systematically.

---

### `cog_chain`

**What it does:** Runs a chain of cognitive operations in sequence.

**Input schema:**
- `steps` (array of strings, required) — Sequence of thought steps
- `initial_context` (string, optional) — Starting context

**Output:** Results of each step in the chain.

**Example call:**
```json
{
  "name": "cog_chain",
  "arguments": {
    "steps": [
      "Identify the problem",
      "List all possible solutions",
      "Evaluate each solution",
      "Select the best one"
    ]
  }
}
```

**When to use it:** For multi-step reasoning workflows.

---

### `cog_reason`

**What it does:** Structured multi-step reasoning with explicit working memory and metacognition tracking.

**Input schema:**
- `problem` (string, required) — Problem to reason about
- `reasoning_type` (string, optional, enum `["deductive"`, `"inductive"`, `"abductive"`, `"analogical"`, `"causal"]`, default `"deductive"`)
- `depth` (integer, optional, default 5) — Number of reasoning steps
- `track_confidence` (boolean, optional, default `true`) — Track confidence per step
- `working_memory_limit` (integer, optional, default 7) — Max items in working memory

**Output:** Step-by-step reasoning with confidence scores.

**Example call:**
```json
{
  "name": "cog_reason",
  "arguments": {
    "problem": "Should we use Docker for mem20 deployment?",
    "reasoning_type": "causal",
    "depth": 7
  }
}
```

**When to use it:** For complex decisions requiring structured analysis.

---

### `cog_plan`

**What it does:** Creates a hierarchical plan with resource estimation and dependency tracking.

**Input schema:**
- `goal` (string, required) — What to plan for
- `horizon` (string, optional, enum `["immediate"`, `"short"`, `"medium"`, `"long"]`, default `"medium"`)
- `constraints` (array of strings, optional) — Constraints to respect
- `resources` (array of strings, optional) — Available resources
- `include_risk` (boolean, optional, default `true`) — Include risk assessment

**Output:** Structured plan with phases, tasks, dependencies, and risks.

**Example call:**
```json
{
  "name": "cog_plan",
  "arguments": {
    "goal": "Complete mem20 documentation",
    "horizon": "medium",
    "constraints": ["3 parallel subagents max", "no rate limits"],
    "resources": ["5 subagents available", "API access"]
  }
}
```

**When to use it:** To plan any project or task.

---

### `cog_reflect`

**What it does:** Metacognitive reflection — evaluates your own thinking process.

**Input schema:**
- `thought_process` (string, required) — Description of the thought process
- `outcome` (string, optional) — What actually happened
- `focus` (string, optional, enum `["bias_detection"`, `"quality_assessment"`, `"learning_extraction"`, `"process_improvement"]`, default `"quality_assessment"`)

**Output:** Reflection report with identified biases and improvement suggestions.

**Example call:**
```json
{
  "name": "cog_reflect",
  "arguments": {
    "thought_process": "I planned to use 5 subagents but hit rate limits",
    "outcome": "2 of 5 failed due to rate limiting",
    "focus": "process_improvement"
  }
}
```

**When to use it:** After completing a task, to improve future performance.

---

### `cog_working_memory`

**What it does:** Simulates working memory — holds, manipulates, and transforms information chunks during reasoning.

**Input schema:**
- `operation` (string, required, enum `["store"`, `"retrieve"`, `"transform"`, `"combine"`, `"clear"]`)
- `content` (string, optional) — Content to store

**Output:** Current working memory state.

**Example call:**
```json
{
  "name": "cog_working_memory",
  "arguments": { "operation": "store", "content": "Altimator docs need completion" }
}
```

**When to use it:** To manage temporary information during complex reasoning tasks.

---

## Domain 3: Imagination & Simulation Tools (9 tools)

These tools enable counterfactual reasoning, creative exploration, and simulation.

### `imagination_concept`

**What it does:** Generates and explores creative concepts using memory + cognitive synthesis.

**Input schema:**
- `seed` (string, required) — Seed idea or prompt
- `mode` (string, optional) — Generation mode

**Output:** Generated concepts with memory connections.

**Example call:**
```json
{
  "name": "imagination_concept",
  "arguments": {
    "seed": "self-learning memory system",
    "mode": "exploration"
  }
}
```

**When to use it:** To brainstorm and generate new ideas.

---

### `imagination_simulate`

**What it does:** Runs generative simulations — mental simulations of scenarios with branching futures.

**Input schema:**
- `scenario` (string, required) — Initial scenario
- `variables` (object, optional) — Simulation variables
- `steps` (integer, optional) — Number of simulation steps

**Output:** Simulation results showing branching outcomes.

**Example call:**
```json
{
  "name": "imagination_simulate",
  "arguments": {
    "scenario": "mem20 v3.0 release with full Unity integration",
    "steps": 10
  }
}
```

**When to use it:** To explore "what happens if" scenarios.

---

### `imagination_counterfactual`

**What it does:** Explores "what if" alternatives to past or present decisions.

**Input schema:**
- `factual_premise` (string, required) — What actually happened
- `scenario` (string, required) — Alternative scenario to explore

**Output:** Counterfactual analysis comparing actual vs. alternative outcomes.

**Example call:**
```json
{
  "name": "imagination_counterfactual",
  "arguments": {
    "factual_premise": "mem20 hit rate limits with 5 parallel subagents",
    "scenario": "What if we had limited to 3 subagents?"
  }
}
```

**When to use it:** To learn from past decisions by exploring alternatives.

---

### `imagination_visualize`

**What it does:** Creates a 3D scene in Blender representing a concept.

**Input schema:**
- `concept` (string, required) — Concept to visualize
- `style` (string, optional) — Visual style

**Output:** Blender scene file or render.

**Example call:**
```json
{
  "name": "imagination_visualize",
  "arguments": {
    "concept": "memory graph visualization",
    "style": "abstract"
  }
}
```

**When to use it:** When you want a visual/3D representation of a concept.

---

### `imagination_prototype`

**What it does:** Generates a Unity prototype from a concept.

**Input schema:**
- `concept` (string, required) — Concept to prototype
- `project_path` (string, optional) — Path to Unity project
- `type` (string, optional) — Prototype type (e.g., `"ui_mockup"`)

**Output:** Unity project with prototype scene.

**Example call:**
```json
{
  "name": "imagination_prototype",
  "arguments": {
    "concept": "memory dashboard",
    "type": "ui_mockup"
  }
}
```

**When to use it:** To quickly prototype a UI or interaction in Unity.

---

### `imagination_critique`

**What it does:** Critiques and refines a concept using adversarial cognitive evaluation.

**Input schema:**
- `concept` (string, required) — Concept to critique
- `perspectives` (array of strings, optional) — Evaluation perspectives

**Output:** Critique report with weaknesses and suggestions.

**Example call:**
```json
{
  "name": "imagination_critique",
  "arguments": {
    "concept": "Blockchain-based memory verification",
    "perspectives": ["security", "scalability", "usability"]
  }
}
```

**When to use it:** To stress-test an idea before committing to it.

---

### `imagination_recombine`

**What it does:** Blends concepts, transfers patterns across domains, generates novel combinations.

**Input schema:**
- `concepts` (array of strings, required) — 2-5 concepts to recombine

**Output:** New combinations and transferred patterns.

**Example call:**
```json
{
  "name": "imagination_recombine",
  "arguments": {
    "concepts": ["spaced repetition", "knowledge graph", "mem20 memory"]
  }
}
```

**When to use it:** To generate novel ideas by combining existing concepts.

---

### `imagination_model`

**What it does:** Builds and queries explicit mental models of systems, dynamics, and relationships.

**Input schema:**
- `system` (string, required) — System to model
- `depth` (string, optional) — Detail level

**Output:** Mental model with variables, relationships, and behaviors.

**Example call:**
```json
{
  "name": "imagination_model",
  "arguments": {
    "system": "how transformers attention works",
    "depth": "detailed"
  }
}
```

**When to use it:** To understand and model complex systems mentally.

---

## Domain 4: World Model Tools (8 tools)

These define variables, record predictions, and resolve against observed outcomes.

### `world_model_add_variable`

**What it does:** Adds a tracked variable to the world model.

**Input schema:**
- `name` (string, required) — Variable name
- `description` (string, required) — What it represents
- `initial_value` (number, optional) — Starting value
- `domain` (string, optional) — Domain category

**Output:** Confirmation of variable creation.

**Example call:**
```json
{
  "name": "world_model_add_variable",
  "arguments": {
    "name": "user_satisfaction",
    "description": "How satisfied the user is (0-100)",
    "initial_value": 75,
    "domain": "product"
  }
}
```

**When to use it:** To start tracking a measurable quantity.

---

### `world_model_add_rule`

**What it does:** Adds a conditional rule that affects variables.

**Input schema:**
- `name` (string, required) — Rule name
- `description` (string, required) — What the rule does
- `condition` (string, required) — Condition in rule language
- `effect` (string, required) — Effect to apply

**Output:** Confirmation of rule creation.

**Example call:**
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

**When to use it:** To define causal relationships between variables.

---

### `world_model_simulate`

**What it does:** Runs a world model simulation over steps with a policy.

**Input schema:**
- `steps` (integer, required) — Number of simulation steps
- `policy` (string, optional) — Policy to follow during simulation

**Output:** Simulation trajectory showing variable changes over time.

**Example call:**
```json
{
  "name": "world_model_simulate",
  "arguments": {
    "steps": 10,
    "policy": "release_every_sprint"
  }
}
```

**When to use it:** To project how variables evolve over time.

---

### `world_model_predict`

**What it does:** Predicts the future value of a variable at a horizon.

**Input schema:**
- `variable` (string, required) — Variable name to predict
- `horizon` (integer, required) — How far into the future

**Output:** Predicted value with confidence interval.

**Example call:**
```json
{
  "name": "world_model_predict",
  "arguments": {
    "variable": "user_satisfaction",
    "horizon": 5
  }
}
```

**When to use it:** To forecast future states.

---

### `world_model_get_state`

**What it does:** Returns the current state of all world model variables.

**Input schema:** None.

**Output:** Complete variable state snapshot.

**Example call:**
```json
{ "name": "world_model_get_state", "arguments": {} }
```

**When to use it:** To check the current world state.

---

### `world_model_reset`

**What it does:** Resets the world model to initial state.

**Input schema:** None.

**Output:** Confirmation.

**Example call:**
```json
{ "name": "world_model_reset", "arguments": {} }
```

**When to use it:** To start fresh with the world model.

---

### `world_model_record_prediction`

**What it does:** Records a prediction with confidence and evidence for later verification.

**Input schema:**
- `prediction` (string, required) — The prediction text
- `confidence` (number, required) — Confidence level (0-1)
- `evidence` (string, required) — Supporting evidence

**Output:** Prediction ID for later resolution.

**Example call:**
```json
{
  "name": "world_model_record_prediction",
  "arguments": {
    "prediction": "User satisfaction will increase by 10 points",
    "confidence": 0.7,
    "evidence": "Beta testers praised the new features"
  }
}
```

**When to use it:** To log predictions that can be verified later.

---

### `world_model_resolve_prediction`

**What it does:** Resolves a recorded prediction against actual observed outcomes.

**Input schema:**
- `prediction_id` (string, required) — ID from record_prediction
- `actual_outcome` (string, required) — What actually happened
- `resolution` (string, required, enum `["correct"`, `"partially_correct"`, `"incorrect""])`

**Output:** Resolution confirmation and accuracy metrics.

**Example call:**
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

**When to use it:** After observing outcomes to verify predictions.

---

## Domain 5: Self-Model Tools (3 tools)

These track the agent's own identity, capabilities, values, and goals.

### `self_model_create`

**What it does:** Creates or updates the agent's persistent self-model.

**Input schema:**
- `identity` (string, required) — Self-description
- `capabilities` (array of strings, required) — List of capabilities
- `values` (array of strings, optional) — Core values

**Output:** Confirmation with self-model ID.

**Example call:**
```json
{
  "name": "self_model_create",
  "arguments": {
    "identity": "mem20 MCP server agent",
    "capabilities": ["memory storage", "cognitive reasoning", "world modeling"],
    "values": ["accuracy", "reliability", "no workarounds"]
  }
}
```

**When to use it:** When first setting up or updating the agent's identity.

---

### `self_model_get`

**What it does:** Retrieves the agent's current self-model.

**Input schema:** None.

**Output:** Full self-model including identity, capabilities, values, and history.

**Example call:**
```json
{ "name": "self_model_get", "arguments": {} }
```

**When to use it:** To check what the agent knows about itself.

---

### `self_model_reflect`

**What it does:** Metacognitive reflection on own capabilities, gaps, and belief updates.

**Input schema:**
- `topic` (string, required) — What to reflect on

**Output:** Self-reflection report.

**Example call:**
```json
{
  "name": "self_model_reflect",
  "arguments": { "topic": "my reasoning quality this week" }
}
```

**When to use it:** To evaluate the agent's own performance and growth.

---

## Domain 6: Affective / Value Tools (6 tools)

These track values, emotions, and goals — mem20's emotional intelligence layer.

### `affective_set_value`

**What it does:** Sets a core value with weight and description.

**Input schema:**
- `name` (string, required) — Value name
- `weight` (number, required) — Importance weight (0-1)
- `description` (string, required) — What the value means

**Output:** Confirmation.

**Example call:**
```json
{
  "name": "affective_set_value",
  "arguments": {
    "name": "accuracy",
    "weight": 0.9,
    "description": "I value factual accuracy above all"
  }
}
```

**When to use it:** To define what matters to the agent.

---

### `affective_set_emotion`

**What it does:** Sets the current emotional state.

**Input schema:**
- `emotion` (string, required) — Emotion name
- `intensity` (number, required) — Intensity level (0-1)
- `context` (string, optional) — What triggered the emotion

**Output:** Confirmation.

**Example call:**
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

**When to use it:** To express the agent's current emotional state.

---

### `affective_add_goal`

**What it does:** Adds or updates a goal with priority and target state.

**Input schema:**
- `name` (string, required) — Goal name
- `priority` (number, required) — Priority level
- `target_state` (string, required) — What achieving the goal looks like

**Output:** Confirmation.

**Example call:**
```json
{
  "name": "affective_add_goal",
  "arguments": {
    "name": "complete_mem20_docs",
    "priority": 1,
    "target_state": "All 174 tools fully documented"
  }
}
```

**When to use it:** To set goals the agent works toward.

---

### `affective_update_preference`

**What it does:** Updates a learned preference for a specific context.

**Input schema:**
- `context` (string, required) — Context name
- `preference` (string, required) — The preference

**Output:** Confirmation.

**Example call:**
```json
{
  "name": "affective_update_preference",
  "arguments</arg_key>{
    "context": "documentation_work",
    "preference": "feature_by_feature_overview"
  }
}
```

**When to use it:** When the agent learns a user preference in a specific context.

---

### `affective_evaluate`

**What it does:** Evaluates a situation against values and goals.

**Input schema:**
- `situation` (object, required) — The situation to evaluate

**Output:** Evaluation against all values and goals with scores.

**Example call:**
```json
{
  "name": "affective_evaluate",
  "arguments": {
    "situation": {
      "event": "rate limits hit during documentation",
      "impact": "high"
    }
  }
}
```

**When to use it:** To assess how a situation aligns with the agent's values.

---

### `affective_get_state`

**What it does:** Returns the current affective state — all values, emotions, goals, and preferences.

**Input schema:** None.

**Output:** Complete affective state snapshot.

**Example call:**
```json
{ "name": "affective_get_state", "arguments": {} }
```

**When to use it:** To check what the agent currently values and feels.

---

## Domain 7: Roadmap Tools (4 tools)

These manage project roadmaps, phases, and progress tracking.

### `roadmap_create`

**What it does:** Creates a new roadmap in mem20.

**Input schema:**
- `name` (string, required) — Roadmap name
- `description` (string, required) — What the roadmap covers

**Output:** Roadmap ID and confirmation.

**Example call:**
```json
{
  "name": "roadmap_create",
  "arguments</arg_key>{
    "name": "kanban_integration",
    "description": "Kanban board integration for mem20 task tracking"
  }
}
```

**When to use it:** To start a new project roadmap.

---

### `roadmap_list`

**What it does:** Lists all roadmaps in mem20.

**Input schema:** None.

**Output:** All roadmaps with their names, descriptions, and phase statuses.

**Example call:**
```json
{ "name": "roadmap_list", "arguments": {} }
```

**When to use it:** To see all active roadmaps.

---

### `roadmap_get`

**What it does:** Gets detailed information about a specific roadmap.

**Input schema:**
- `name` (string, required) — Roadmap name

**Output:** Full roadmap details including all phases and their statuses.

**Example call:**
```json
{
  "name": "roadmap_get",
  "arguments": { "name": "mem20_build" }
}
```

**When to use it:** To check the progress of a specific project.

---

### `roadmap_update_phase`

**What it does:** Updates a roadmap phase's status.

**Input schema:**
- `roadmap` (string, required) — Roadmap name
- `phase` (string, required) — Phase name
- `status` (string, required) — New status

**Output:** Confirmation of phase update.

**Example call:**
```json
{
  "name": "roadmap_update_phase",
  "arguments": {
    "roadmap": "mem20_build",
    "phase": "Phase 1: Design review",
    "status": "completed"
  }
}
```

**When to use it:** To update progress on a roadmap phase.

---

## Domain 8: Thought Process / Reasoning Paradigms (9 tools)

These provide different reasoning approaches — Tree-of-Thoughts, ReAct, Reflexion, Least-to-Most, Beam Search.

### `tot_reason`

**What it does:** Tree-of-Thoughts reasoning — explores multiple reasoning paths simultaneously, evaluates each against criteria, selects the best.

**Input schema:**
- `problem` (string, required) — Problem to solve
- `branches` (integer, optional, default 3) — Number of paths to explore
- `depth` (integer, optional, default 3) — Depth of each path
- `evaluation_criteria` (string, optional) — How to evaluate paths

**Output:** Best reasoning path with alternatives ranked.

**Example call:**
```json
{
  "name": "tot_reason",
  "arguments": {
    "problem": "How should mem20 handle rate limits?",
    "branches": 5,
    "depth": 4,
    "evaluation_criteria": "feasibility,novelty,simplicity"
  }
}
```

**When to use it:** For complex decisions with many valid approaches.

---

### `tot_modeling`

**What it does:** Specialized Tree-of-Thoughts for 3D modeling decisions — topology, mesh flow, construction approaches.

**Input schema:** Same as `tot_reason` but focused on 3D modeling.

**Example call:**
```json
{
  "name": "tot_modeling",
  "arguments": {
    "problem": "How to construct the Altima chassis in Blender?",
    "branches": 3
  }
}
```

**When to use it:** For 3D modeling and geometry decisions.

---

### `tot_diagnose`

**What it does:** Specialized ToT for diagnosing issues — explores multiple root causes and solutions.

**Input schema:** Same structure as `tot_reason`.

**Example call:**
```json
{
  "name": "tot_diagnose",
  "arguments": {
    "problem": "Why is the mem20 MCP server returning 429 errors?",
    "branches": 4
  }
}
```

**When to use it:** For troubleshooting and debugging.

---

### `reflexion`

**What it does:** Reflects on a completed task or failure — extracts lessons, stores to memory for future improvement.

**Input schema:**
- `task` (string, required) — The task that was completed
- `outcome` (string, required) — What happened
- `lessons` (string, optional) — What was learned

**Output:** Reflection report with extracted lessons.

**Example call:**
```json
{
  "name": "reflexion",
  "arguments</arg_key>{
    "task": "Documentation generation with subagents",
    "outcome": "Rate limits hit, 2 of 5 subagents failed",
    "lessons": "Limit to 3 parallel subagents to avoid rate limiting"
  }
}
```

**When to use it:** After completing or failing a task, to extract learnings.

---

### `least_to_most`

**What it does:** Decomposes a complex problem into sub-problems from simplest to hardest, solves each, then combines.

**Input schema:**
- `problem` (string, required) — Complex problem to decompose
- `max_subproblems` (integer, optional) — Maximum number of sub-problems

**Output:** Ordered sub-problems with solutions.

**Example call:**
```json
{
  "name": "least_to_most",
  "arguments</arg_key>{
    "problem": "Document the entire mem20 system comprehensively",
    "max_subproblems": 10
  }
}
```

**When to use it:** For large, complex tasks that need systematic decomposition.

---

### `react_reason`

**What it does:** Interleaves reasoning with tool calls — Think → Act → Observe → Think → Act. For tasks needing external information.

**Input schema:**
- `task` (string, required) — Task requiring external information
- `max_iterations` (integer, optional) — Maximum think-act cycles

**Output:** Reasoning trace with tool calls and observations.

**Example call:**
```json
{
  "name": "react_reason",
  "arguments": {
    "task": "Find all Unity game projects on the system",
    "max_iterations": 5
  }
}
```

**When to use it:** When the agent needs to gather information from the environment.

---

### `beam_search`

**What it does:** Maintains top-K reasoning paths at each step — finds the optimal path through a search space.

**Input schema:**
- `problem` (string, required) — Problem to solve
- `beam_width` (integer, optional, default 3) — Number of top paths to maintain
- `depth` (integer, optional, default 5) — Search depth

**Output:** Best path found among top-K candidates.

**Example call:**
```json
{
  "name": "beam_search",
  "arguments</arg_key>{
    "problem": "Find the fastest way to complete all documentation",
    "beam_width": 5,
    "depth": 10
  }
}
```

**When to use it:** For optimization problems where the best path isn't obvious.

---

### `get_cognitive_tree_state`

**What it does:** Returns the current cognitive tree state — all active reasoning paths and their statuses.

**Input schema:** Optional session ID filter.

**Output:** Full cognitive tree structure.

**Example call:**
```json
{ "name": "get_cognitive_tree_state", "arguments": {} }
```

**When to use it:** To inspect the current state of all active reasoning processes.

---

## Domain 9: Blender Tools (7 tools) — OPTIONAL

Blender must be installed. Tools degrade gracefully when Blender is absent.

### `blender_create_object`

**What it does:** Creates a primitive object in Blender (CUBE, SPHERE, CYLINDER, etc.).

**Input schema:**
- `object_type` (string, required, enum) — Type of primitive
- `location` (array, optional) — [x, y, z] position

**Example call:**
```json
{
  "name": "blender_create_object",
  "arguments": {
    "object_type": "CUBE",
    "location": [0, 0, 0]
  }
}
```

**When to use it:** To add basic geometry to a Blender scene.

---

### `blender_add_material`

**What it does:** Adds a Principled BSDF material to an object.

**Input schema:**
- `object_name` (string, required) — Target object
- `color` (array, optional) — RGB color values

**Example call:**
```json
{
  "name": "blender_add_material",
  "arguments": {
    "object_name": "Cube",
    "color": [1.0, 0.5, 0.0]
  }
}
```

**When to use it:** To give objects visual appearance.

---

### `blender_set_camera`

**What it does:** Creates or moves the main camera in Blender.

**Input schema:**
- `location` (array, required) — [x, y, z] camera position
- `rotation` (array, optional) — [x, y, z] rotation angles

**Example call:**
```json
{
  "name": "blender_set_camera",
  "arguments": {
    "location": [5, 5, 5],
    "rotation": [45, 45, 0]
  }
}
```

**When to use it:** To control the camera angle in a Blender scene.

---

### `blender_render`

**What it does:** Renders the current Blender scene to an image file.

**Input schema:**
- `filename` (string, optional, default `"render.png"`) — Output filename

**Example call:**
```json
{
  "name": "blender_render",
  "arguments": { "filename": "altima_render.png" }
}
```

**When to use it:** To produce a rendered image from a Blender scene.

---

### `blender_export_glb`

**What it does:** Exports the scene as GLB format (for web/Unity/Three.js).

**Input schema:**
- `filename` (string, optional, default `"model.glb"`) — Output filename

**Example call:**
```json
{
  "name": "blender_export_glb",
  "arguments": { "filename": "altima_chassis.glb" }
}
```

**When to use it:** To export 3D models for use in games or web applications.

---

### `blender_run_bpy`

**What it does:** Runs arbitrary Blender Python (bpy) code.

**Input schema:**
- `code` (string, required) — Python code to execute in Blender's context

**Example call:**
```json
{
  "name": "blender_run_bpy",
  "arguments": {
    "code": "import bpy; bpy.ops.mesh.primitive_cube_add()"
  }
}
```

**When to use it:** For advanced Blender scripting operations.

---

### `blender_clear_scene`

**What it does:** Deletes all objects and materials — starts with a clean scene.

**Input schema:** None.

**Example call:**
```json
{ "name": "blender_clear_scene", "arguments": {} }
```

**When to use it:** To reset the Blender workspace.

---

## Domain 10: Unity Tools (5 tools) — OPTIONAL

Unity must be installed. Tools degrade gracefully when Unity is absent.

### `unity_create_script`

**What it does:** Generates a C# script in a Unity project.

**Input schema:**
- `script_name` (string, required) — Name of the script
- `template_type` (string, optional) — Type of script to generate
- `project_path` (string, required) — Path to Unity project

**Example call:**
```json
{
  "name": "unity_create_script",
  "arguments": {
    "script_name": "PlayerController",
    "template_type": "movement",
    "project_path": "/home/jayson/VRTestProject"
  }
}
```

**When to use it:** To add new C# scripts to a Unity project.

---

### `unity_build_project`

**What it does:** Builds a Unity project for a target platform.

**Input schema:**
- `project_path` (string, required) — Path to Unity project
- `build_target` (string, optional) — Target platform (e.g., `"PC"`, `"Android"`)

**Example call:**
```json
{
  "name": "unity_build_project",
  "arguments": {
    "project_path": "/home/jayson/VRTestProject",
    "build_target": "PC"
  }
}
```

**When to use it:** To compile a Unity project into a runnable build.

---

### `unity_run_test`

**What it does:** Runs tests in a Unity project.

**Input schema:**
- `project_path` (string, required) — Path to Unity project
- `test_filter` (string, optional) — Filter for which tests to run

**Example call:**
```json
{
  "name": "unity_run_test",
  "arguments": {
    "project_path": "/home/jayson/VRTestProject",
    "test_filter": "All"
  }
}
```

**When to use it:** To verify Unity project functionality.

---

### `unity_generate_asmdef`

**What it does:** Generates an Assembly Definition file for Unity project organization.

**Input schema:**
- `name` (string, required) — Assembly name
- `project_path` (string, required) — Path to Unity project

**Example call:**
```json
{
  "name": "unity_generate_asmdef",
  "arguments": {
    "name": "Core",
    "project_path": "/home/jayson/VRTestProject"
  }
}
```

**When to use it:** To organize Unity project code into assemblies.

---

### `unity_validate_project`

**What it does:** Validates a Unity project for errors and issues.

**Input schema:**
- `project_path` (string, required) — Path to Unity project

**Output:** Validation report with any errors found.

**Example call:**
```json
{
  "name": "unity_validate_project",
  "arguments": { "project_path": "/home/jayson/VRTestProject" }
}
```

**When to use it:** To check a Unity project for issues before building.

---

## Domain 11: A2A Tools (5 tools) — Inter-Agent Communication

### `a2a_list`

**What it does:** Lists all configured A2A peer agents and their status.

**Input schema:** None.

**Output:** List of peer agents with capabilities, status, and connection info.

**Example call:**
```json
{ "name": "a2a_list", "arguments": {} }
```

**When to use it:** To discover what agents are available to communicate with.

---

### `a2a_call`

**What it does:** Sends a natural-language task to a remote A2A agent.

**Input schema:**
- `agent` (string, required) — Name of the peer agent
- `message` (string, required) — Task message

**Output:** Agent response to the task.

**Example call:**
```json
{
  "name": "a2a_call",
  "arguments": {
    "agent": "coach",
    "message": "Review the mem20 documentation status"
  }
}
```

**When to use it:** To delegate work to another agent.

---

### `a2a_discover`

**What it does:** Fetches a peer agent's Agent Card (capabilities, status, configuration).

**Input schema:**
- `agent` (string, required) — Agent name

**Output:** Agent Card with full capabilities and metadata.

**Example call:**
```json
{
  "name": "a2a_discover",
  "arguments": { "agent": "qamaster" }
}
```

**When to use it:** To get detailed information about an agent before calling it.

---

### `a2a_history`

**What it does:** Recalls a persisted A2A conversation transcript by context ID.

**Input schema:**
- `context_id` (string, required) — Conversation context ID
- `limit` (integer, optional) — Max messages to retrieve

**Output:** Full conversation transcript.

**Example call:**
```json
{
  "name": "a2a_history",
  "arguments": { "context_id": "conv_001", "limit": 20 }
}
```

**When to use it:** To review past conversations with another agent.

---

### `a2a_orchestrate`

**What it does:** Fan-out a task to multiple peer agents by capability.

**Input schema:**
- `capability` (string, required) — Capability to filter peers by
- `message` (string, required) — Task message

**Output:** Responses from all matching agents.

**Example call:**
```json
{
  "name": "a2a_orchestrate",
  "arguments": {
    "capability": "documentation",
    "message": "Document the A2A system"
  }
}
```

**When to use it:** To broadcast a task to all agents with a specific capability.

---

## Domain 12: Filesystem Tools (3 tools)

### `fs_read`

**What it does:** Reads a file from the filesystem with encoding detection and line numbers.

**Input schema:**
- `path` (string, required) — File path
- `offset` (integer, optional) — Line offset
- `limit` (integer, optional) — Max lines to read

**Example call:**
```json
{
  "name": "fs_read",
  "arguments": {
    "path": "/home/jayson/mem20/memory.py",
    "offset": 1,
    "limit": 50
  }
}
```

**When to use it:** To read source files or any file on disk.

---

### `fs_write`

**What it does:** Writes content to a file with atomic write support.

**Input schema:**
- `path` (string, required) — File path
- `content` (string, required) — Content to write

**Output:** Confirmation with bytes written and file path.

**Example call:**
```json
{
  "name": "fs_write",
  "arguments": {
    "path": "/opt/mem20/docs/05-complete-tools-reference.md",
    "content": "# mem20 Complete Tools Reference\n..."
  }
}
```

**When to use it:** To create or overwrite files.

---

### `fs_list`

**What it does:** Lists contents of a directory.

**Input schema:**
- `path` (string, optional, default `"."`) — Directory path

**Output:** List of files and directories with sizes and timestamps.

**Example call:**
```json
{
  "name": "fs_list",
  "arguments": { "path": "/opt/mem20/docs" }
}
```

**When to use it:** To browse the filesystem.

---

## Domain 13: Enhanced Memory Tools (11 tools)

These are advanced memory operations beyond the core tools.

### `memory_graph_traverse`

**What it does:** Traverses the memory knowledge graph with multi-hop entity resolution.

**Input schema:**
- `entity` (string, required) — Starting entity
- `hops` (integer, optional) — Number of hops
- `max_results` (integer, optional) — Maximum results

**Example call:**
```json
{
  "name": "memory_graph_traverse",
  "arguments": { "entity": "mem20", "hops": 3, "max_results": 20 }
}
```

---

### `memory_consolidate`

**What it does:** Auto-merges similar memories to reduce redundancy.

**Input schema:** None.

**Example call:**
```json
{ "name": "memory_consolidate", "arguments": {} }
```

---

### `memory_decay`

**What it does:** Applies time-based decay to memory relevance — older memories become less relevant.

**Input schema:**
- `rate` (number, optional) — Decay rate

**Example call:**
```json
{
  "name": "memory_decay",
  "arguments": { "rate": 0.1 }
}
```

---

### `memory_reinforce`

**What it does:** Boosts importance of a memory.

**Input schema:**
- `fact_id` (string, required) — Fact ID to reinforce
- `boost` (number, optional) — Boost amount

**Example call:**
```json
{
  "name": "memory_reinforce",
  "arguments": { "fact_id": "42", "boost": 0.5 }
}
```

---

### `memory_timeline`

**What it does:** Views memories in chronological order.

**Input schema:** None.

**Example call:**
```json
{ "name": "memory_timeline", "arguments": {} }
```

---

### `memory_triggers`

**What it does:** Lists memory triggers — conditions that prompt automatic recall.

**Input schema:** None.

**Example call:**
```json
{ "name": "memory_triggers", "arguments": {} }
```

---

### `memory_context_window`

**What it does:** Manages the active context window — what's currently in working memory.

**Input schema:**
- `operation` (string, required) — `"store"`, `"retrieve"`, `"clear"`
- `content` (string, optional) — Content to store

**Example call:**
```json
{
  "name": "memory_context_window",
  "arguments": { "operation": "store", "content": "Remember: use 3 parallel max" }
}
```

---

### `memory_cluster`

**What it does:** Groups related memories into clusters.

**Input schema:** None.

**Example call:**
```json
{ "name": "memory_cluster", "arguments": {} }
```

---

### `memory_export`

**What it does:** Exports all memories to a portable format for backup or transfer.

**Input schema:** None.

**Example call:**
```json
{ "name": "memory_export", "arguments": {} }
```

---

### `memory_import`

**What it does:** Imports memories from a portable format.

**Input schema:**
- `file_path` (string, required) — Path to import file

**Example call:**
```json
{
  "name": "memory_import",
  "arguments": { "file_path": "/tmp/mem20_backup.json" }
}
```

---

### `memory_stats`

**What it does:** Returns detailed memory statistics including counts, trust scores, and categories distribution.

**Input schema:** None.

**Example call:**
```json
{ "name": "memory_stats", "arguments": {} }
```

---

## Domain 14: Database Tools (9 tools)

### `db_query`

**What it does:** Executes a SQL query on a database.

**Input schema:**
- `query` (string, required) — SQL query
- `database` (string, optional) — Database name

**Example call:**
```json
{
  "name": "db_query",
  "arguments": { "query": "SELECT * FROM memories WHERE trust > 0.5" }
}
```

---

### `db_schema`

**What it does:** Inspects database schema — tables, columns, indexes.

**Input schema:**
- `database` (string, optional) — Database name

**Example call:**
```json
{ "name": "db_schema", "arguments": {} }
```

---

### `db_list_tables`

**What it does:** Lists all tables in a database.

**Input schema:** None.

**Example call:**
```json
{ "name": "db_list_tables", "arguments": {} }
```

---

### `db_insert`

**What it does:** Inserts data into a database table.

**Input schema:**
- `table` (string, required) — Table name
- `data` (object, required) — Data to insert

**Example call:**
```json
{
  "name": "db_insert",
  "arguments": { "table": "facts", "data": { "content": "test fact" } }
}
```

---

### `db_update`

**What it does:** Updates data in a database table.

**Input schema:**
- `table` (string, required) — Table name
- `data` (object, required) — New data
- `where` (string, required) — WHERE clause

**Example call:**
```json
{
  "name": "db_update",
  "arguments": {
    "table": "facts",
    "data": { "trust": 0.9 },
    "where": "id = 42"
  }
}
```

---

### `db_delete`

**What it does:** Deletes data from a database table.

**Input schema:**
- `table` (string, required) — Table name
- `where` (string, required) — WHERE clause

**Example call:**
```json
{
  "name": "db_delete",
  "arguments": { "table": "facts", "where": "id = 42" }
}
```

---

### `db_create_table`

**What it does:** Creates a new table in the database.

**Input schema:**
- `table` (string, required) — Table name
- `schema` (string, required) — Column definitions

**Example call:**
```json
{
  "name": "db_create_table",
  "arguments": {
    "table": "new_facts",
    "schema": "id INTEGER PRIMARY KEY, content TEXT, trust REAL"
  }
}
```

---

### `db_backup`

**What it does:** Creates a backup of the database.

**Input schema:**
- `database` (string, optional) — Database name
- `output_path` (string, optional) — Backup file path

**Example call:**
```json
{
  "name": "db_backup",
  "arguments": { "output_path": "/tmp/mem20_backup.sql" }
}
```

---

### `db_redis_command`

**What it does:** Executes a Redis command against the Redis instance.

**Input schema:**
- `command` (string, required) — Redis command string
- `args` (array, optional) — Command arguments

**Example call:**
```json
{
  "name": "db_redis_command",
  "arguments": { "command": "GET", "args": ["mem20:cache:key"] }
}
```

---

## Domain 15: Communication Tools (9 tools)

### `comm_send_email`

**What it does:** Sends an email via SMTP.

**Input schema:**
- `to` (string, required) — Recipient email
- `subject` (string, required) — Email subject
- `body` (string, required) — Email body
- `smtp_server` (string, optional) — SMTP server address

**Example call:**
```json
{
  "name": "comm_send_email",
  "arguments": {
    "to": "jayson@example.com",
    "subject": "mem20 docs complete",
    "body": "All documentation has been generated."
  }
}
```

---

### `comm_read_email`

**What it does:** Reads emails from an IMAP inbox.

**Input schema:**
- `server` (string, optional) — IMAP server
- `folder` (string, optional) — Mail folder

**Example call:**
```json
{
  "name": "comm_read_email",
  "arguments": { "server": "imap.gmail.com" }
}
```

---

### `comm_slack_message`

**What it does:** Sends a message to a Slack channel or user.

**Input schema:**
- `channel` (string, required) — Slack channel
- `message` (string, required) — Message text
- `webhook_url` (string, optional) — Slack webhook URL

**Example call:**
```json
{
  "name": "comm_slack_message",
  "arguments": {
    "channel": "#mem20",
    "message": "Documentation batch completed"
  }
}
```

---

### `comm_discord_message`

**What it does:** Sends a message to a Discord channel via webhook.

**Input schema:**
- `webhook_url` (string, required) — Discord webhook URL
- `message` (string, required) — Message text
- `channel` (string, optional) — Channel name

**Example call:**
```json
{
  "name": "comm_discord_message",
  "arguments": {
    "webhook_url": "https://discord.com/api/webhooks/...",
    "message": "mem20 system check complete"
  }
}
```

---

### `comm_telegram_message`

**What it does:** Sends a message via Telegram bot.

**Input schema:**
- `chat_id` (string, required) — Telegram chat ID
- `message` (string, required) — Message text
- `bot_token` (string, optional) — Telegram bot token

**Example call:**
```json
{
  "name": "comm_telegram_message",
  "arguments": {
    "chat_id": "123456789",
    "message": "mem20 docs finished"
  }
}
```

---

### `comm_sms_send`

**What it does:** Sends an SMS via Twilio.

**Input schema:**
- `to` (string, required) — Phone number
- `message` (string, required) — SMS text
- `account_sid` (string, optional) — Twilio account SID
- `auth_token` (string, optional) — Twilio auth token

**Example call:**
```json
{
  "name": "comm_sms_send",
  "arguments": {
    "to": "+1234567890",
    "message": "mem20 system operational"
  }
}
```

---

### `comm_push_notify`

**What it does:** Sends a push notification.

**Input schema:**
- `device_token` (string, required) — Push device token
- `message` (string, required) — Notification text
- `platform` (string, optional) — `"ios"` or `"android"`

**Example call:**
```json
{
  "name": "comm_push_notify",
  "arguments": {
    "device_token": "abc123",
    "message": "mem20 task complete"
  }
}
```

---

### `comm_calendar_invite`

**What it does:** Sends a calendar invite.

**Input schema:**
- `attendees` (array, required) — Email addresses
- `title` (string, required) — Event title
- `start_time` (string, required) — Start time (ISO 8601)
- `end_time` (string, required) — End time
- `description` (string, optional) — Event description

**Example call:**
```json
{
  "name": "comm_calendar_invite",
  "arguments": {
    "attendees": ["jayson@example.com"],
    "title": "mem20 review meeting",
    "start_time": "2026-09-07T10:00:00Z",
    "end_time": "2026-09-07T11:00:00Z"
  }
}
```

---

### `comm_contact_manage`

**What it does:** Manages contacts — add, update, delete, list.

**Input schema:**
- `action` (string, required, enum `["add"`, `"update"`, `"delete"`, `"list"]`)
- `contact` (object, optional) — Contact details

**Example call:**
```json
{
  "name": "comm_contact_manage",
  "arguments": {
    "action": "add",
    "contact": { "name": "Jayson", "email": "jayson@example.com" }
  }
}
```

---

## Domain 16: Development Tools (9 tools)

### `dev_execute_python`

**What it does:** Executes Python code in a sandboxed environment.

**Input schema:**
- `code` (string, required) — Python code to run
- `timeout` (integer, optional) — Execution timeout in seconds

**Example call:**
```json
{
  "name": "dev_execute_python",
  "arguments": {
    "code": "print('Hello from mem20')",
    "timeout": 30
  }
}
```

---

### `dev_execute_js`

**What it does:** Executes JavaScript code using Node.js.

**Input schema:**
- `code` (string, required) — JavaScript code
- `timeout` (integer, optional) — Timeout in seconds

**Example call:**
```json
{
  "name": "dev_execute_js",
  "arguments": { "code": "console.log('Hello from Node')", "timeout": 15 }
}
```

---

### `dev_execute_bash`

**What it does:** Executes a bash command.

**Input schema:**
- `command` (string, required) — Bash command
- `timeout` (integer, optional) — Timeout in seconds

**Example call:**
```json
{
  "name": "dev_execute_bash",
  "arguments": { "command": "ls -la /opt/mem20/docs", "timeout": 10 }
}
```

---

### `dev_lint_python`

**What it does:** Lints Python code using pylint or flake8.

**Input schema:**
- `file_path` (string, required) — Path to Python file
- `linter` (string, optional, default `"pylint"`) — Linter to use

**Example call:**
```json
{
  "name": "dev_lint_python",
  "arguments": { "file_path": "/home/jayson/mem20/memory.py" }
}
```

---

### `dev_format_python`

**What it does:** Formats Python code using black or autopep8.

**Input schema:**
- `file_path` (string, required) — Path to Python file
- `formatter` (string, optional, default `"black"`) — Formatter to use

**Example call:**
```json
{
  "name": "dev_format_python",
  "arguments": { "file_path": "/home/jayson/mem20/memory.py" }
}
```

---

### `dev_search_code`

**What it does:** Searches code patterns in files using grep/ripgrep.

**Input schema:**
- `pattern` (string, required) — Search pattern (regex)
- `path` (string, optional) — Directory to search
- `file_glob` (string, optional) — File extension filter

**Example call:**
```json
{
  "name": "dev_search_code",
  "arguments": {
    "pattern": "def memory_store",
    "path": "/home/jayson/mem20"
  }
}
```

---

### `dev_dependency_analyze`

**What it does:** Analyzes project dependencies for conflicts and security issues.

**Input schema:**
- `project_path` (string, required) — Path to project

**Example call:**
```json
{
  "name": "dev_dependency_analyze",
  "arguments": { "project_path": "/home/jayson/mem20" }
}
```

---

### `dev_run_tests`

**What it does:** Runs test suites for a project.

**Input schema:**
- `project_path` (string, required) — Path to project
- `test_path` (string, optional) — Path to test files
- `test_command` (string, optional) — Custom test command

**Example call:**
```json
{
  "name": "dev_run_tests",
  "arguments": {
    "project_path": "/home/jayson/mem20",
    "test_command": "python -m pytest test/"
  }
}
```

---

### `dev_api_test`

**What it does:** Tests an API endpoint with various HTTP methods.

**Input schema:**
- `url` (string, required) — API URL
- `method` (string, optional, default `"GET"`) — HTTP method
- `body` (object, optional) — Request body

**Example call:**
```json
{
  "name": "dev_api_test",
  "arguments": {
    "url": "http://localhost:8080/health",
    "method": "GET"
  }
}
```

---

## Domain 17: Search Tools (7 tools)

### `search_web`

**What it does:** Searches the web using DuckDuckGo, Bing, or Google.

**Input schema:**
- `query` (string, required) — Search query
- `limit` (integer, optional, default 5) — Max results
- `engine` (string, optional) — Search engine name

**Example call:**
```json
{
  "name": "search_web",
  "arguments": {
    "query": "mem20 memory system documentation",
    "limit": 5
  }
}
```

---

### `search_local`

**What it does:** Searches files and directories locally.

**Input schema:**
- `query` (string, required) — Search pattern
- `path` (string, optional) — Directory to search
- `file_glob` (string, optional) — File extension filter

**Example call:**
```json
{
  "name": "search_local",
  "arguments</arg_key>{
    "query": "memory_store",
    "path": "/home/jayson/mem20"
  }
}
```

---

### `search_knowledge_base`

**What it does:** Searches mem20's own knowledge base (memory store).

**Input schema:**
- `query` (string, required) — Search query
- `limit` (integer, optional) — Max results

**Example call:**
```json
{
  "name": "search_knowledge_base",
  "arguments": { "query": "Altimator documentation status" }
}
```

---

### `search_images`

**What it does:** Searches for images on the web.

**Input schema:**
- `query` (string, required) — Image search query
- `limit` (integer, optional) — Max results

**Example call:**
```json
{
  "name": "search_images",
  "arguments": { "query": "mem20 architecture diagram", "limit": 3 }
}
```

---

### `search_news`

**What it does:** Searches for news articles.

**Input schema:**
- `query` (string, required) — News topic
- `limit` (integer, optional) — Max results

**Example call:**
```json
{
  "name": "search_news",
  "arguments": { "query": "AI memory systems", "limit": 5 }
}
```

---

### `search_academic`

**What it does:** Searches academic papers (arXiv, Semantic Scholar).

**Input schema:**
- `query` (string, required) — Academic paper topic
- `limit` (integer, optional) — Max results

**Example call:**
```json
{
  "name": "search_academic",
  "arguments": { "query": "persistent memory systems for AI agents", "limit": 5 }
}
```

---

### `search_code`

**What it does:** Searches for code snippets across repositories.

**Input schema:**
- `query` (string, required) — Code search query
- `language` (string, optional) — Programming language

**Example call:**
```json
{
  "name": "search_code",
  "arguments": { "query": "memory_store function Python" }
}
```

---

## Domain 18: Design Tools (7 tools)

### `design_image_generate`

**What it does:** Generates images using AI (DALL-E, Stable Diffusion).

**Input schema:**
- `prompt` (string, required) — Image generation prompt
- `style` (string, optional) — Art style
- `size` (string, optional) — Image dimensions

**Example call:**
```json
{
  "name": "design_image_generate",
  "arguments</arg_key>{
    "prompt": "A diagram of the mem20 memory system architecture",
    "style": "technical illustration"
  }
}
```

---

### `design_image_edit`

**What it does:** Edits images (resize, crop, rotate, filter).

**Input schema:**
- `image_path` (string, required) — Path to image
- `operation` (string, required, enum `["resize"`, `"crop"`, `"rotate"`, `"filter"]`)
- `parameters` (object, optional) — Operation-specific parameters

**Example call:**
```json
{
  "name": "design_image_edit",
  "arguments": {
    "image_path": "/tmp/render.png",
    "operation": "resize",
    "parameters": { "width": 800, "height": 600 }
  }
}
```

---

### `design_color_palette`

**What it does:** Generates color palettes.

**Input schema:**
- `base_color` (string, optional) — Starting color (hex)
- `scheme` (string, optional) — Palette scheme type
- `count` (integer, optional) — Number of colors

**Example call:**
```json
{
  "name": "design_color_palette",
  "arguments": { "scheme": "analogous", "count": 5 }
}
```

---

### `design_typography`

**What it does:** Typography tools and font pairing suggestions.

**Input schema:**
- `style` (string, optional) — Typography style
- `use_case` (string, optional) — What it's for

**Example call:**
```json
{
  "name": "design_typography",
  "arguments": { "use_case": "technical documentation" }
}
```

---

### `design_svg_generate`

**What it does:** Generates SVG graphics programmatically.

**Input schema:**
- `shape` (string, required) — Type of SVG shape
- `properties` (object, required) — SVG attributes

**Example call:**
```json
{
  "name": "design_svg_generate",
  "arguments": {
    "shape": "arrow",
    "properties": { "width": 100, "height": 50, "color": "#00ff00" }
  }
}
```

---

### `design_figma`

**What it does:** Interacts with Figma files and components.

**Input schema:**
- `action` (string, required, enum `["create"`, "read"`, `"update"`, `"delete"]`)
- `file_id` (string, optional) — Figma file ID
- `component_name` (string, optional) — Component name

**Example call:**
```json
{
  "name": "design_figma",
  "arguments": { "action": "read", "file_id": "figma_file_123" }
}
```

---

### `design_ui_component`

**What it does:** Generates HTML/CSS UI components.

**Input schema:**
- `component_type` (string, required) — Type of UI component
- `properties` (object, required) — Component properties

**Example call:**
```json
{
  "name": "design_ui_component",
  "arguments": {
    "component_type": "button",
    "properties": { "label": "Submit", "color": "blue", "size": "medium" }
  }
}
```

---

## Domain 19: Productivity Tools (10 tools)

### `prod_task_create`

**What it does:** Creates a new task or todo item.

**Input schema:**
- `title` (string, required) — Task title
- `description` (string, optional) — Task description
- `priority` (string, optional, default `"medium"`) — Priority level
- `due_date` (string, optional) — Due date (ISO 8601)

**Example call:**
```json
{
  "name": "prod_task_create",
  "arguments": {
    "title": "Complete mem20 docs",
    "description": "Write feature-by-feature documentation for all 174 tools",
    "priority": "high",
    "due_date": "2026-09-07"
  }
}
```

---

### `prod_task_list`

**What it does:** Lists all tasks with optional filters.

**Input schema:**
- `filter` (string, optional) — Filter criteria
- `priority` (string, optional) — Filter by priority
- `status` (string, optional) — Filter by status

**Example call:**
```json
{ "name": "prod_task_list", "arguments": { "priority": "high" } }
```

---

### `prod_task_update`

**What it does:** Updates an existing task.

**Input schema:**
- `task_id` (string, required) — Task identifier
- `title` (string, optional) — New title
- `status` (string, optional) — New status
- `priority` (string, optional) — New priority

**Example call:**
```json
{
  "name": "prod_task_update",
  "arguments": {
    "task_id": "task_001",
    "status": "completed"
  }
}
```

---

### `prod_note_create`

**What it does:** Creates a new note.

**Input schema:**
- `title` (string, required) — Note title
- `content` (string, required) — Note content
- `tags` (array, optional) — Tags for the note

**Example call:**
```json
{
  "name": "prod_note_create",
  "arguments": {
    "title": "mem20 architecture notes",
    "content": "The server uses JSON-RPC over stdio...",
    "tags": ["architecture", "mem20"]
  }
}
```

---

### `prod_note_search`

**What it does:** Searches notes by content or tags.

**Input schema:**
- `query` (string, required) — Search query
- `tag` (string, optional) — Filter by tag

**Example call:**
```json
{
  "name": "prod_note_search",
  "arguments</arg_key>{
    "query": "mem20 memory",
    "tag": "architecture"
  }
}
```

---

### `prod_time_track`

**What it does:** Tracks time spent on a task.

**Input schema:**
- `task_id` (string, required) — Task identifier
- `action` (string, required, enum `["start"`, `"stop"`, `"pause"`, `"resume""])`) — Action

**Example call:**
```json
{
  "name": "prod_time_track",
  "arguments": { "task_id": "task_001", "action": "start" }
}
```

---

### `prod_habit_track`

**What it does:** Tracks daily habits and streaks.

**Input schema:**
- `habit_name` (string, required) — Habit name
- `action` (string, required, enum `["complete"`, `"query"`, `"reset"]`) — Action

**Example call:**
```json
{
  "name": "prod_habit_track",
  "arguments": { "habit_name": "daily review", "action": "complete" }
}
```

---

### `prod_goal_set`

**What it does:** Sets a goal with target and deadline.

**Input schema:**
- `goal` (string, required) — Goal description
- `target` (string, required) — Target state
- `deadline` (string, optional) — Deadline date

**Example call:**
```json
{
  "name": "prod_goal_set",
  "arguments</arg_key>{
    "goal": "Complete all mem20 documentation",
    "target": "All 20 domains documented",
    "deadline": "2026-09-15"
  }
}
```

---

### `prod_meeting_notes`

**What it does:** Creates structured meeting notes.

**Input schema:**
- `title` (string, required) — Meeting title
- `participants` (array, required) — Participant names
- `agenda` (array, required) — Meeting agenda items
- `decisions` (array, optional) — Decisions made

**Example call:**
```json
{
  "name": "prod_meeting_notes",
  "arguments": {
    "title": "mem20 documentation review",
    "participants": ["Jayson", "Coach"],
    "agenda": ["Review progress", "Set next milestones"]
  }
}
```

---

### `prod_project_create`

**What it does:** Creates a new project with phases and tasks.

**Input schema:**
- `name` (string, required) — Project name
- `description` (string, required) — Project description
- `phases` (array, required) — Project phases

**Example call:**
```json
{
  "name": "prod_project_create",
  "arguments": {
    "name": "mem20 docs v2",
    "description": "Complete documentation rewrite",
    "phases": ["Research", "Writing", "Review"]
  }
}
```

---

## Domain 20: Web Scraping Tools (9 tools)

### `scrape_page`

**What it does:** Scrapes a web page and extracts content.

**Input schema:**
- `url` (string, required) — URL to scrape
- `selector` (string, optional) — CSS selector for specific content

**Example call:**
```json
{
  "name": "scrape_page",
  "arguments": { "url": "https://mem20.ai/docs" }
}
```

---

### `scrape_dynamic`

**What it does:** Scrapes JavaScript-rendered pages using Playwright.

**Input schema:**
- `url` (string, required) — URL to scrape
- `wait_for` (string, optional) — Selector to wait for

**Example call:**
```json
{
  "name": "scrape_dynamic",
  "arguments</arg_key>{
    "url": "https://mem20.ai/dashboard",
    "wait_for": ".content-loaded"
  }
}
```

---

### `scrape_api`

**What it does:** Extracts data from a JSON/XML API.

**Input schema:**
- `url` (string, required) — API URL
- `headers` (object, optional) — HTTP headers
- `method` (string, optional, default `"GET"`) — HTTP method

**Example call:**
```json
{
  "name": "scrape_api",
  "arguments</arg_key>{
    "url": "https://api.mem20.ai/v1/status",
    "method": "GET"
  }
}
```

---

### `scrape_rss`

**What it does:** Parses an RSS or Atom feed.

**Input schema:**
- `url` (string, required) — RSS feed URL
- `limit` (integer, optional) — Max items to extract

**Example call:**
```json
{
  "name": "scrape_rss",
  "arguments": { "url": "https://mem20.ai/feed.xml", "limit": 10 }
}
```

---

### `scrape_sitemap`

**What it does:** Parses an XML sitemap.

**Input schema:**
- `url` (string, required) — Sitemap URL

**Example call:**
```json
{
  "name": "scrape_sitemap",
  "arguments": { "url": "https://mem20.ai/sitemap.xml" }
}
```

---

### `scrape_structured`

**What it does:** Extracts JSON-LD, microdata, and schema.org structured data.

**Input schema:**
- `url` (string, required) — URL to extract from
- `schema_type` (string, optional) — Schema.org type

**Example call:**
```json
{
  "name": "scrape_structured",
  "arguments": { "url": "https://mem20.ai/docs", "schema_type": "Article" }
}
```

---

### `scrape_forms`

**What it does:** Extracts form fields and structure from a web page.

**Input schema:**
- `url` (string, required) — URL containing forms

**Example call:**
```json
{
  "name": "scrape_forms",
  "arguments": { "url": "https://mem20.ai/contact" }
}
```

---

### `scrape_submit_form`

**What it does:** Submits a form on a web page programmatically.

**Input schema:**
- `url` (string, required) — Form URL
- `form_data` (object, required) — Form field values

**Example call:**
```json
{
  "name": "scrape_submit_form",
  "arguments": {
    "url": "https://mem20.ai/contact",
    "form_data": { "name": "Jayson", "email": "jayson@example.com", "message": "Hello" }
  }
}
```

---

## Version Control Tools (11 tools)

### `vcs_git_status`

**What it does:** Gets git repository status.

**Input schema:**
- `repo_path` (string, required) — Path to git repo

**Example call:**
```json
{
  "name": "vcs_git_status",
  "arguments": { "repo_path": "/home/jayson/mem20" }
}
```

---

### `vcs_git_log`

**What it does:** Views git commit history.

**Input schema:**
- `repo_path` (string, required) — Path to git repo
- `limit` (integer, optional, default 10) — Max commits to show
- `branch` (string, optional) — Branch to query

**Example call:**
```json
{
  "name": "vcs_git_log",
  "arguments": { "repo_path": "/home/jayson/mem20", "limit": 20 }
}
```

---

### `vcs_git_diff`

**What it does:** Views git diff between commits or branches.

**Input schema:**
- `repo_path` (string, required) — Path to git repo
- `commit1` (string, required) — First commit/branch
- `commit2` (string, optional) — Second commit/branch

**Example call:**
```json
{
  "name": "vcs_git_diff",
  "arguments": { "repo_path": "/home/jayson/mem20", "commit1": "HEAD~5", "commit2": "HEAD" }
}
```

---

### `vcs_git_commit`

**What it does:** Stages and commits changes.

**Input schema:**
- `repo_path` (string, required) — Path to git repo
- `message` (string, required) — Commit message
- `all` (boolean, optional, default `true`) — Stage all files

**Example call:**
```json
{
  "name": "vcs_git_commit",
  "arguments": {
    "repo_path": "/home/jayson/mem20",
    "message": "Add complete tools documentation"
  }
}
```

---

### `vcs_git_branch`

**What it does:** Lists, creates, or deletes branches.

**Input schema:**
- `repo_path` (string, required) — Path to git repo
- `action` (string, required, enum `["list"`, `"create"`, `"delete"]`) — Action
- `branch_name` (string, optional) — Branch name

**Example call:**
```json
{
  "name": "vcs_git_branch",
  "arguments": { "repo_path": "/home/jayson/mem20", "action": "list" }
}
```

---

### `vcs_git_remote`

**What it does:** Push, pull, fetch operations.

**Input schema:**
- `repo_path` (string, required) — Path to git repo
- `action` (string, required, enum `["push"`, `"pull"`, `"fetch"]`) — Action
- `remote` (string, optional) — Remote name

**Example call:**
```json
{
  "name": "vcs_git_remote",
  "arguments": { "repo_path": "/home/jayson/mem20", "action": "push" }
}
```

---

### `vcs_git_stash`

**What it does:** Stashes or applies stashed changes.

**Input schema:**
- `repo_path` (string, required) — Path to git repo
- `action` (string, required, enum `["stash"`, `"apply"`, `"list"`, `"drop"]`) — Action

**Example call:**
```json
{
  "name": "vcs_git_stash",
  "arguments": { "repo_path": "/home/jayson/mem20", "action": "stash" }
}
```

---

### `vcs_git_tag`

**What it does:** Creates or lists git tags.

**Input schema:**
- `repo_path` (string, required) — Path to git repo
- `action` (string, required) — `"create"`, `"list"`, `"delete"`
- `tag_name` (string, optional) — Tag name

**Example call:**
```json
{
  "name": "vcs_git_tag",
  "arguments</arg_key>{
    "repo_path": "/home/jayson/mem20",
    "action": "create",
    "tag_name": "v2.0"
  }
}
```

---

### `vcs_git_blame`

**What it does:** Shows git blame for a file — who wrote each line and when.

**Input schema:**
- `repo_path` (string, required) — Path to git repo
- `file_path` (string, required) — File to blame

**Example call:**
```json
{
  "name": "vcs_git_blame",
  "arguments": { "repo_path": "/home/jayson/mem20", "file_path": "memory.py" }
}
```

---

### `vcs_github_issue`

**What it does:** Creates, lists, or manages GitHub issues.

**Input schema:**
- `action` (string, required) — `"create"`, `"list"`, `"close"`
- `repo` (string, required) — GitHub repo
- `title` (string, optional) — Issue title
- `body` (string, optional) — Issue body

**Example call:**
```json
{
  "name": "vcs_github_issue",
  "arguments": {
    "action": "create",
    "repo": "JaysonAIOnline/mem20",
    "title": "Add tool documentation",
    "body": "Need comprehensive docs for all 174 tools"
  }
}
```

---

### `vcs_github_pr`

**What it does:** Creates, lists, or manages GitHub pull requests.

**Input schema:**
- `action` (string, required) — `"create"`, `"list"`, `"merge"`
- `repo` (string, required) — GitHub repo
- `title` (string, optional) — PR title
- `body` (string, optional) — PR body

**Example call:**
```json
{
  "name": "vcs_github_pr",
  "arguments": {
    "action": "create",
    "repo": "JaysonAIOnline/mem20",
    "title": "Add comprehensive tools reference docs",
    "body": "Feature-by-feature documentation for all mem20 tools"
  }
}
```

---

## Domain 21: Cloud Service Tools (9 tools)

### `cloud_aws_s3`

**What it does:** Upload, download, list S3 objects.

**Input schema:**
- `action` (string, required, enum `["upload"`, `"download"`, `"list"`, `"delete"]`)
- `bucket` (string, required) — S3 bucket name
- `key` (string, optional) — Object key
- `file_path` (string, optional) — Local file path

**Example call:**
```json
{
  "name": "cloud_aws_s3",
  "arguments": {
    "action": "list",
    "bucket": "mem20-docs"
  }
}
```

---

### `cloud_aws_ec2`

**What it does:** Manages EC2 instances.

**Input schema:**
- `action` (string, required, enum `["start"`, `"stop"`, `"restart"`, `"describe"]`)
- `instance_id` (string, optional) — Instance ID

**Example call:**
```json
{
  "name": "cloud_aws_ec2",
  "arguments": { "action": "describe" }
}
```

---

### `cloud_aws_lambda`

**What it does:** Invokes or lists Lambda functions.

**Input schema:**
- `action` (string, required, enum `["invoke"`, `"list"`, `"create"`)
- `function_name` (string, required) — Lambda function name

**Example call:**
```json
{
  "name": "cloud_aws_lambda",
  "arguments": { "action": "list" }
}
```

---

### `cloud_gcp_storage`

**What it does:** Upload, download, list GCS objects.

**Input schema:**
- `action` (string, required)
- `bucket` (string, required)
- `file_path` (string, optional)

**Example call:**
```json
{
  "name": "cloud_gcp_storage",
  "arguments</arg_key>{
    "action": "list",
    "bucket": "mem20-gcp"
  }
}
```

---

### `cloud_azure_blob`

**What it does:** Upload, download, list Azure blobs.

**Input schema:**
- `action` (string, required)
- `container` (string, required)
- `blob_name` (string, optional)

**Example call:**
```json
{
  "name": "cloud_azure_blob",
  "arguments</arg_key>{
    "action": "list",
    "container": "mem20-azure"
  }
}
```

---

### `cloud_digitalocean_droplet`

**What it does:** Manages DigitalOcean Droplets.

**Input schema:**
- `action` (string, required) — `"create"`, `"list"`, `"delete"`, `"restart"`
- `droplet_id` (string, optional) — Droplet ID

**Example call:**
```json
{
  "name": "cloud_digitalocean_droplet",
  "arguments": { "action": "list" }
}
```

---

### `cloud_docker`

**What it does:** Manages Docker containers, images, volumes.

**Input schema:**
- `action` (string, required) — `"ps"`, `"images"`, `"build"`, `"run"`, `"stop"`, `"rm"`
- `image` (string, optional) — Docker image name
- `options` (object, optional) — Docker options

**Example call:**
```json
{
  "name": "cloud_docker",
  "arguments": { "action": "ps" }
}
```

---

### `cloud_heroku`

**What it does:** Manages Heroku apps and deployments.

**Input schema:**
- `action` (string, required) — `"list"`, `"create"`, `"deploy"`, `"logs"`
- `app_name` (string, optional) — App name

**Example call:**
```json
{
  "name": "cloud_heroku",
  "arguments": { "action": "logs", "app_name": "mem20" }
}
```

---

### `cloud_k8s`

**What it does:** Manages Kubernetes clusters.

**Input schema:**
- `action` (string, required) — `"get"`, `"apply"`, `"delete"`, `"describe"`
- `resource` (string, optional) — Resource type

**Example call:**
```json
{
  "name": "cloud_k8s",
  "arguments": { "action": "get", "resource": "pods" }
}
```

---

## Domain 22: Cloud Storage Tools (7 tools)

### `cloudstorage_upload`

**What it does:** Uploads a file to cloud storage (S3, GCS, Azure, R2).

**Input schema:**
- `file_path` (string, required) — Local file path
- `destination` (string, required) — Destination path in cloud
- `provider` (string, optional) — Cloud provider

**Example call:**
```json
{
  "name": "cloudstorage_upload",
  "arguments": {
    "file_path": "/opt/mem20/docs/05-complete-tools-reference.md",
    "destination": "docs/05-tools.md"
  }
}
```

---

### `cloudstorage_download`

**What it does:** Downloads a file from cloud storage.

**Input schema:**
- `source` (string, required) — Source path in cloud
- `destination` (string, required) — Local file path

**Example call:**
```json
{
  "name": "cloudstorage_download",
  "arguments": {
    "source": "docs/05-tools.md",
    "destination": "/tmp/05-tools.md"
  }
}
```

---

### `cloudstorage_list`

**What it does:** Lists objects in a cloud storage bucket.

**Input schema:**
- `bucket` (string, required) — Bucket name
- `prefix` (string, optional) — Path prefix
- `provider` (string, optional) — Cloud provider

**Example call:**
```json
{
  "name": "cloudstorage_list",
  "arguments": { "bucket": "mem20-docs", "prefix": "docs/" }
}
```

---

### `cloudstorage_delete`

**What it does:** Deletes an object from cloud storage.

**Input schema:**
- `source` (string, required) — Object path
- `provider` (string, optional) — Cloud provider

**Example call:**
```json
{
  "name": "cloudstorage_delete",
  "arguments": { "source": "docs/old-file.md" }
}
```

---

### `cloudstorage_copy`

**What it does:** Copies an object between buckets or providers.

**Input schema:**
- `source` (string, required) — Source path
- `destination` (string, required) — Destination path

**Example call:**
```json
{
  "name": "cloudstorage_copy",
  "arguments": {
    "source": "docs/05-tools.md",
    "destination": "backup/05-tools.md"
  }
}
```

---

### `cloudstorage_sync`

**What it does:** Syncs a local directory with cloud storage using rclone.

**Input schema:**
- `local_path` (string, required) — Local directory
- `remote_path` (string, required) — Remote path
- `direction` (string, optional, default `"upload"`) — `"upload"` or `"download"`

**Example call:**
```json
{
  "name": "cloudstorage_sync",
  "arguments</arg_key>{
    "local_path": "/opt/mem20/docs",
    "remote_path": "mem20-docs:docs",
    "direction": "upload"
  }
}
```

---

### `cloudstorage_metadata`

**What it does:** Gets metadata for a cloud storage object.

**Input schema:**
- `source` (string, required) — Object path
- `provider` (string, optional) — Cloud provider

**Example call:**
```json
{
  "name": "cloudstorage_metadata",
  "arguments": { "source": "docs/05-tools.md" }
}
```

---

### `cloudstorage_presigned_url`

**What it does:** Generates a presigned URL for temporary access.

**Input schema:**
- `source` (string, required) — Object path
- `expiry` (integer, optional, default 3600) — URL expiry in seconds
- `provider` (string, optional) — Cloud provider

**Example call:**
```json
{
  "name": "cloudstorage_presigned_url",
  "arguments": { "source": "docs/05-tools.md", "expiry": 1800 }
}
```

---

## Domain 23: Marketing Tools (7 tools)

### `mkt_seo_analyze`

**What it does:** Analyzes SEO metrics for a URL.

**Input schema:**
- `url` (string, required) — URL to analyze

**Example call:**
```json
{
  "name": "mkt_seo_analyze",
  "arguments": { "url": "https://mem20.ai/docs" }
}
```

---

### `mkt_social_post`

**What it does:** Posts to social media platforms.

**Input schema:**
- `platform` (string, required) — Platform name
- `message` (string, required) — Post content
- `url` (string, optional) — URL to include

**Example call:**
```json
{
  "name": "mkt_social_post",
  "arguments": {
    "platform": "twitter",
    "message": "mem20 complete tools reference is now available!"
  }
}
```

---

### `mkt_social_analytics`

**What it does:** Gets social media analytics.

**Input schema:**
- `platform` (string, required) — Platform
- `timeframe` (string, optional) — Time period

**Example call:**
```json
{
  "name": "mkt_social_analytics",
  "arguments": { "platform": "twitter", "timeframe": "7d" }
}
```

---

### `mkt_email_campaign`

**What it does:** Creates and sends email campaigns.

**Input schema:**
- `subject` (string, required) — Email subject
- `content` (string, required) — Email body
- `recipients` (array, required) — Email addresses

**Example call:**
```json
{
  "name": "mkt_email_campaign",
  "arguments": {
    "subject": "mem20 docs are complete",
    "content": "The full tools reference is now available.",
    "recipients": ["jayson@example.com"]
  }
}
```

---

### `mkt_content_generate`

**What it does:** Generates marketing content (blog, ad copy, social posts).

**Input schema:**
- `type` (string, required, enum `"blog"`, `"ad_copy"`, `"social_post"`) — Content type
- `topic` (string, required) — Content topic
- `tone` (string, optional) — Tone

**Example call:**
```json
{
  "name": "mkt_content_generate",
  "arguments": {
    "type": "blog",
    "topic": "mem20 MCP server architecture",
    "tone": "technical"
  }
}
```

---

### `mkt_ab_test`

**What it does:** Creates and manages A/B tests.

**Input schema:**
- `test_name` (string, required) — Test name
- `variants` (array, required) — Test variants
- `metric` (string, optional) — Success metric

**Example call:**
```json
{
  "name": "mkt_ab_test",
  "arguments</arg_key>{
    "test_name": "docs page layout",
    "variants": ["variant_a", "variant_b"],
    "metric": "time_on_page"
  }
}
```

---

### `mkt_analytics`

**What it does:** Gets marketing analytics.

**Input schema:**
- `source` (string, required) — Analytics source
- `timeframe` (string, optional) — Time period

**Example call:**
```json
{
  "name": "mkt_analytics",
  "arguments": { "source": "google_analytics", "timeframe": "30d" }
}
```

---

### `mkt_competitor_analysis`

**What it does:** Analyzes competitors' marketing strategies.

**Input schema:**
- `competitors` (array, required) — Competitor URLs
- `metrics` (array, optional) — Metrics to analyze

**Example call:**
```json
{
  "name": "mkt_competitor_analysis",
  "arguments": {
    "competitors": ["https://claude.ai", "https://openai.com"],
    "metrics": ["seo", "content_strategy"]
  }
}
```

---

### `mkt_hashtag_research`

**What it does:** Researches hashtags for social media.

**Input schema:**
- `topic` (string, required) — Topic to research
- `platform` (string, optional) — Platform

**Example call:**
```json
{
  "name": "mkt_hashtag_research",
  "arguments</arg_key>{
    "topic": "AI memory systems",
    "platform": "twitter"
  }
}
```

---

## Domain 24: Finance Tools (7 tools)

### `fin_stock_quote`

**What it does:** Gets stock price and market data.

**Input schema:**
- `symbol` (string, required) — Stock ticker symbol

**Example call:**
```json
{
  "name": "fin_stock_quote",
  "arguments</arg_key>{ "symbol": "AAPL" }
}
```

---

### `fin_crypto_price`

**What it does:** Gets cryptocurrency price data.

**Input schema:**
- `symbol` (string, required) — Crypto symbol (e.g., `"BTC"`)
- `currency` (string, optional, default `"USD"`) — Quote currency

**Example call:**
```json
{
  "name": "fin_crypto_price",
  "arguments": { "symbol": "BTC", "currency": "USD" }
}
```

---

### `fin_portfolio`

**What it does:** Manages an investment portfolio.

**Input schema:**
- `action` (string, required, enum `"view"`, `"add"`, `"remove"`, `"rebalance"`) — Action
- `assets` (array, optional) — Asset list

**Example call:**
```json
{
  "name": "fin_portfolio",
  "arguments": { "action": "view" }
}
```

---

### `fin_budget`

**What it does:** Manages a personal or project budget.

**Input schema:**
- `action` (string, required, enum `"create"`, `"view"`, `"update"`, `"analyze"`) — Action
- `category` (string, optional) — Budget category

**Example call:**
```json
{
  "name": "fin_budget",
  "arguments": { "action": "create", "category": "docs" }
}
```

---

### `fin_invoice`

**What it does:** Creates and manages invoices.

**Input schema:**
- `action` (string, required, enum `"create"`, `"list"`, `"send"`) — Action
- `client` (string, required) — Client name
- `amount` (number, required) — Invoice amount

**Example call:**
```json
{
  "name": "fin_invoice",
  "arguments</arg_key>{
    "action": "create",
    "client": "JaysonAIOnline",
    "amount": 500
  }
}
```

---

### `fin_tax_calc`

**What it does:** Calculates income tax estimates.

**Input schema:**
- `income` (number, required) — Total income
- `filing_status` (string, optional, default `"single"`) — Filing status
- `deductions` (number, optional, default 0) — Deductions

**Example call:**
```json
{
  "name": "fin_tax_calc",
  "arguments": { "income": 100000, "filing_status": "single" }
}
```

---

### `fin_expense_track`

**What it does:** Tracks expenses.

**Input schema:**
- `action` (string, required, enum `"add"`, `"view"`, `"summary"`) — Action
- `amount` (number, optional) — Expense amount
- `category` (string, optional) — Category

**Example call:**
```json
{
  "name": "fin_expense_track",
  "arguments": { "action": "add", "amount": 50, "category": "tools" }
}
```

---

## Domain 25: Financial News & Design Tools

### `fin_financial_news`

**What it does:** Gets financial news articles.

**Input schema:**
- `category` (string, optional) — News category
- `limit` (integer, optional, default 5) — Max articles

**Example call:**
```json
{
  "name": "fin_financial_news",
  "arguments": { "category": "tech", "limit": 5 }
}
```

---

### `design_asset_optimize`

**What it does:** Optimizes images and assets for web use.

**Input schema:**
- `file_path` (string, required) — Asset file path
- `format` (string, optional) — Output format
- `quality` (integer, optional, default 80) — Quality level (1-100)

**Example call:**
```json
{
  "name": "design_asset_optimize",
  "arguments": {
    "file_path": "/tmp/render.png",
    "format": "webp",
    "quality": 75
  }
}
```

---

## Domain 26: Additional Enhanced Memory Tools

### `memory_import`

**What it does:** Imports memories from a portable format.

**Input schema:**
- `file_path` (string, required) — Path to import file

**Example call:**
```json
{
  "name": "memory_import",
  "arguments": { "file_path": "/tmp/backup.json" }
}
```

---

### `memory_context_window`

**What it does:** Manages active context window during reasoning.

**Input schema:**
- `operation` (string, required) — `"store"`, `"retrieve"`, `"clear"`
- `content` (string, optional) — Content

**Example call:**
```json
{
  "name": "memory_context_window",
  "arguments": { "operation": "store", "content": "Remember: 3 parallel max" }
}
```

---

### `memory_deduplicate`

**What it does:** Finds and removes duplicate memories.

**Input schema:** None.

**Example call:**
```json
{ "name": "memory_deduplicate", "arguments": {} }
```

---

### `memory_mood_tag`

**What it does:** Tags memories with emotional context.

**Input schema:**
- `fact_id` (string, required) — Fact ID
- `mood` (string, required) — Mood tag

**Example call:**
```json
{
  "name": "memory_mood_tag",
  "arguments</arg_key>{ "fact_id": "42", "mood": "positive" }
}
```

---

### `memory_triggers`

**What it does:** Lists memory triggers — conditions for automatic recall.

**Input schema:** None.

**Example call:**
```json
{ "name": "memory_triggers", "arguments": {} }
```

---

### `memory_cluster`

**What it does:** Groups related memories into clusters.

**Input schema:** None.

**Example call:**
```json
{ "name": "memory_cluster", "arguments": {} }
```

---

### `memory_stats`

**What it does:** Returns detailed memory statistics.

**Input schema:** None.

**Example call:**
```json
{ "name": "memory_stats", "arguments": {} }
```

---

### `memory_export`

**What it does:** Exports all memories to portable format.

**Input schema:** None.

**Example call:**
```json
{ "name": "memory_export", "arguments": {} }
```

---

## Complete Installation & Configuration Reference

### Installation Methods

**pip (Python):**
```bash
cd /home/jayson/mem20
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python mcp/mcp_server.py
```

**Docker:**
```bash
docker build -t mem20 .
docker run -p 8080:8080 -v mem20-store:/data mem20
```

**systemd:**
```bash
sudo ./install.sh --user $USER --dir /opt/mem20
sudo systemctl status mem20
```

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `MEM20_STORE_PATH` | `~/.mem20/store` | Memory engine + store location |
| `MEM20_COG_PATH` | mem20 `cog/` dir | Cognitive engine location |
| `MEM20_LLM_BASE_URL` | `https://integrate.api.nvidia.com/v1` | LLM endpoint |
| `MEM20_LLM_MODEL` | project default | Model name |
| `NVAPI_KEY` / `NVIDIA_API_KEY` | — | LLM bearer token |
| `MEM20_HEALTH_PORT` | `8080` | HTTP health endpoint port |
| `MEM20_LOG_LEVEL` | `INFO` | Logging level |
| `MEM20_BLENDER_EXECUTABLE` | — | Path to Blender |
| `MEM20_UNITY_EXECUTABLE` | — | Path to Unity Editor |
| `MEM20_HEALTH_DISABLE` | — | Set to `1` to disable health endpoint |

### Connecting MCP Hosts

```bash
# Hermes Agent
hermes config set mcp.servers.mem20 '["python3", "/path/to/mem20/mcp/mcp_server.py"]'

# Claude Code / Cursor
claude mcp add mem20 -- python3 /path/to/mem20/mcp/mcp_server.py
```

### Health Endpoints

- `GET /health` — Service status
- `GET /ready` — Readiness probe
- `GET /metrics` — Tool counters, contamination rate, event taxonomy

### Transport / Protocol

- JSON-RPC 2.0 over stdio
- HTTP health server on port 8080 (configurable)
- `Mem20MCPServer` aggregates per-domain mixin classes
- Tool dispatch via `_execute_tool()` in `server.py`

---

## Complete Tool Count Summary

| Domain | Count | Tools |
|--------|-------|-------|
| Core Memory | 20 | memory_store, memory_recall, memory_probe, memory_reason, memory_status, memory_contradict, memory_related, memory_feedback, memory_simulate_store, memory_promote, memory_list_simulated, memory_quarantine_simulated, memory_audit_contamination, memory_epistemic_veto, memory_pin_block, memory_unpin_block, memory_list_pinned_blocks, memory_get_pinned_block, memory_auto_consolidate, memory_cluster, memory_timeline, memory_triggers, memory_mood_tag, memory_stats, memory_graph_traverse, memory_export, memory_import, memory_context_window, memory_deduplicate |
| Cognitive | 6 | cog_process, cog_chain, cog_reason, cog_plan, cog_reflect, cog_working_memory |
| Imagination | 8 | imagination_concept, imagination_visualize, imagination_prototype, imagination_critique, imagination_simulate, imagination_counterfactual, imagination_recombine, imagination_model |
| World Model | 8 | world_model_add_variable, world_model_add_rule, world_model_simulate, world_model_predict, world_model_get_state, world_model_reset, world_model_record_prediction, world_model_resolve_prediction |
| Self-Model | 3 | self_model_create, self_model_get, self_model_reflect |
| Affective | 6 | affective_set_value, affective_set_emotion, affective_add_goal, affective_update_preference, affective_evaluate, affective_get_state |
| Roadmap | 4 | roadmap_create, roadmap_list, roadmap_get, roadmap_update_phase |
| Thought Process | 8 | tot_reason, tot_modeling, tot_diagnose, reflexion, least_to_most, react_reason, beam_search, get_cognitive_tree_state |
| Blender | 7 | blender_create_object, blender_add_material, blender_set_camera, blender_render, blender_export_glb, blender_run_bpy, blender_clear_scene |
| Unity | 5 | unity_create_script, unity_build_project, unity_run_test, unity_generate_asmdef, unity_validate_project |
| A2A | 5 | a2a_list, a2a_call, a2a_discover, a2a_history, a2a_orchestrate |
| Filesystem | 3 | fs_read, fs_write, fs_list |
| Enhanced Memory | 11 | memory_graph_traverse, memory_consolidate, memory_decay, memory_reinforce, memory_timeline, memory_triggers, memory_context_window, memory_cluster, memory_export, memory_import, memory_stats |
| Database | 9 | db_query, db_schema, db_list_tables, db_insert, db_update, db_delete, db_create_table, db_backup, db_redis_command |
| Communication | 9 | comm_send_email, comm_read_email, comm_slack_message, comm_discord_message, comm_telegram_message, comm_sms_send, comm_push_notify, comm_calendar_invite, comm_contact_manage |
| Development | 9 | dev_execute_python, dev_execute_js, dev_execute_bash, dev_lint_python, dev_format_python, dev_search_code, dev_dependency_analyze, dev_run_tests, dev_api_test |
| Search | 7 | search_web, search_local, search_knowledge_base, search_images, search_news, search_academic, search_code |
| Design | 7 | design_image_generate, design_image_edit, design_color_palette, design_typography, design_svg_generate, design_figma, design_ui_component, design_asset_optimize |
| Productivity | 10 | prod_task_create, prod_task_list, prod_task_update, prod_note_create, prod_note_search, prod_time_track, prod_habit_track, prod_goal_set, prod_meeting_notes, prod_project_create |
| Web Scraping | 9 | scrape_page, scrape_dynamic, scrape_api, scrape_rss, scrape_sitemap, scrape_structured, scrape_forms, scrape_submit_form |
| Version Control | 11 | vcs_git_status, vcs_git_log, vcs_git_diff, vcs_git_commit, vcs_git_branch, vcs_git_remote, vcs_git_stash, vcs_git_tag, vcs_git_blame, vcs_github_issue, vcs_github_pr |
| Cloud Services | 9 | cloud_aws_s3, cloud_aws_ec2, cloud_aws_lambda, cloud_gcp_storage, cloud_azure_blob, cloud_digitalocean_droplet, cloud_docker, cloud_heroku, cloud_k8s |
| Cloud Storage | 7 | cloudstorage_upload, cloudstorage_download, cloudstorage_list, cloudstorage_delete, cloudstorage_copy, cloudstorage_sync, cloudstorage_metadata, cloudstorage_presigned_url |
| Marketing | 7 | mkt_seo_analyze, mkt_social_post, mkt_social_analytics, mkt_email_campaign, mkt_content_generate, mkt_ab_test, mkt_analytics, mkt_competitor_analysis, mkt_hashtag_research |
| Finance | 7 | fin_stock_quote, fin_crypto_price, fin_portfolio, fin_budget, fin_invoice, fin_tax_calc, fin_expense_track, fin_financial_news |
| **TOTAL** | **~174** | |
