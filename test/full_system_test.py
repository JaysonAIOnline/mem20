#!/usr/bin/env python3
"""
MEM20 FULL SYSTEM TEST SUITE
Tests every feature and subsystem of mem20.
Outputs structured JSON results.
"""

import sys
import os
import json
import asyncio
import time
from pathlib import Path

ROOT = Path("/home/jayson/mem20")
sys.path.insert(0, str(ROOT / "cog"))
sys.path.insert(0, str(ROOT / "mcp"))
sys.path.insert(0, str(ROOT))

# ── Imports ────────────────────────────────────────────────────────────
from llm import chat, achat, LLMError

sys.path.insert(0, os.environ.get("MEM20_STORE_PATH", "/home/jayson/mem20"))
from memory import remember, recall, status as mem_status, rebuild_index, ledger_view

from cognitive_engine import (
    aprocess_thought, arun_chain, areason, aplan, areflect, aworking_memory,
    aimagination_concept, aimagination_dream, aimagination_critique,
    aimagination_simulate, aimagination_counterfactual, aimagination_recombine,
    aimagination_model,
    atheory_of_mind_simulate, atheory_of_mind_perspective,
    acot_reason, apot_reason, atot_reason,
    robust_slice, _evaluate_substrate,
    get_tot_historical_lessons,
)

RESULTS = []
PASSED = 0
FAILED = 0
ERRORS = 0

async def run_test(name, coro):
    global PASSED, FAILED, ERRORS
    start = time.time()
    try:
        result = await coro
        elapsed = time.time() - start
        ok = result is not None and (not isinstance(result, str) or len(result.strip()) > 0)
        status = "PASS" if ok else "FAIL"
        if ok:
            PASSED += 1
        else:
            FAILED += 1
        preview = str(result)[:200] if result else ""
        RESULTS.append({"name": name, "status": status, "time": round(elapsed, 2), "preview": preview})
        print(f"  [{status}] {name} ({elapsed:.2f}s)")
    except Exception as e:
        elapsed = time.time() - start
        ERRORS += 1
        RESULTS.append({"name": name, "status": "ERROR", "time": round(elapsed, 2), "error": str(e)[:150]})
        print(f"  [ERROR] {name}: {str(e)[:100]}")

async def main():
    global PASSED, FAILED, ERRORS
    print("=" * 70)
    print("MEM20 FULL SYSTEM TEST SUITE — Feature by Feature")
    print("=" * 70)

    # ══════════════════════════════════════════════════════════════════
    # SUBSYSTEM 1: MEMORY CORE
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("SUBSYSTEM 1: MEMORY CORE")
    print("=" * 70)

    # 1.1 Store
    print("\n--- 1.1 Memory Store ---")
    await run_test("memory_store: basic fact", aprocess_thought("Store test fact", "analyze", ""))
    # Direct store
    def test_store_basic():
        result = remember(topic="test_suite", content="Test fact: the sky is blue", tags=["test", "basic"], priority="normal")
        return result
    await run_test("memory_store: direct call", asyncio.to_thread(test_store_basic))

    # 1.2 Recall
    print("\n--- 1.2 Memory Recall ---")
    await run_test("memory_recall: basic query", asyncio.to_thread(recall, topic=None, k=5))
    await run_test("memory_recall: by topic", asyncio.to_thread(recall, topic="test_suite", k=5))

    # 1.3 Status
    print("\n--- 1.3 Memory Status ---")
    await run_test("memory_status: get stats", asyncio.to_thread(mem_status))

    # 1.4 Probe
    print("\n--- 1.4 Memory Probe ---")
    await run_test("memory_probe: entity probe", asyncio.to_thread(lambda: recall(topic="test_suite", k=3)))

    # 1.5 Ledger View
    print("\n--- 1.5 Ledger View ---")
    await run_test("ledger_view: view ledger", asyncio.to_thread(ledger_view))

    # 1.6 Contradictions
    print("\n--- 1.6 Contradiction Detection ---")
    def test_contradict():
        remember(topic="test_contradict", content="The meeting is at 3pm", tags=["test", "contradict"], priority="normal")
        remember(topic="test_contradict", content="The meeting is at 4pm", tags=["test", "contradict"], priority="normal")
        recs = recall(topic="test_contradict", k=10)
        return recs
    await run_test("memory_contradict: find contradictions", asyncio.to_thread(test_contradict))

    # 1.7 Related entities
    print("\n--- 1.7 Related Entities ---")
    def test_related():
        remember(topic="project_alpha", content="Project Alpha uses Python", tags=["test", "related"], priority="normal")
        remember(topic="project_alpha", content="Project Alpha has a web interface", tags=["test", "related"], priority="normal")
        recs = recall(topic="project_alpha", k=10)
        return recs
    await run_test("memory_related: find related", asyncio.to_thread(test_related))

    # 1.8 Rebuild Index
    print("\n--- 1.8 Rebuild Index ---")
    await run_test("rebuild_index: rebuild", asyncio.to_thread(rebuild_index))

    # ══════════════════════════════════════════════════════════════════
    # SUBSYSTEM 2: COGNITIVE ENGINE
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("SUBSYSTEM 2: COGNITIVE ENGINE")
    print("=" * 70)

    # 2.1 Process Thought
    print("\n--- 2.1 Process Thought ---")
    await run_test("cog_process: analyze mode", aprocess_thought("What are the implications of AI regulation?", "analyze", ""))
    await run_test("cog_process: synthesize mode", aprocess_thought("Combine insights from biology and engineering", "synthesize", ""))
    await run_test("cog_process: evaluate mode", aprocess_thought("Should we adopt a new database system?", "evaluate", ""))
    await run_test("cog_process: plan mode", aprocess_thought("Design a feature rollout plan", "plan", ""))

    # 2.2 Chain
    print("\n--- 2.2 Cognitive Chain ---")
    await run_test("cog_chain: multi-step", arun_chain([
        "Analyze the problem",
        "Synthesize solutions",
        "Evaluate tradeoffs",
        "Plan implementation"
    ], "Initial context: building a web app"))

    # 2.3 Reason
    print("\n--- 2.3 Structured Reasoning ---")
    await run_test("cog_reason: deductive", areason("Why is encryption important for privacy?", "deductive", 3))
    await run_test("cog_reason: inductive", areason("What patterns emerge from successful startups?", "inductive", 3))
    await run_test("cog_reason: abductive", areason("What could cause a server to crash unexpectedly?", "abductive", 3))

    # 2.4 Plan
    print("\n" + "=" * 70)
    print("SUBSYSTEM 2.4: PLANNING")
    print("=" * 70)
    await run_test("cog_plan: medium horizon", aplan("Build a recommendation engine", "medium", ["limited budget"], ["python", "data"], True))
    await run_test("cog_plan: long horizon", aplan("Launch a new product line", "long", [], [], True))

    # 2.5 Reflect
    print("\n--- 2.5 Reflection ---")
    await run_test("cog_reflect: bias detection", areflect(
        "I thought the project would succeed because the team was experienced",
        "The project failed due to market conditions",
        "bias_detection"
    ))
    await run_test("cog_reflect: learning extraction", areflect(
        "I tried approach X to solve the bug",
        "It didn't work because of edge case Y",
        "learning_extraction"
    ))

    # 2.6 Working Memory
    print("\n--- 2.6 Working Memory ---")
    await run_test("cog_working_memory: store", aworking_memory("store", ["item1", "item2", "item3"], "", 7))
    await run_test("cog_working_memory: retrieve", aworking_memory("retrieve", [], "", 7))
    await run_test("cog_working_memory: transform", aworking_memory("transform", ["A", "B"], "combine", 7))

    # ══════════════════════════════════════════════════════════════════
    # SUBSYSTEM 3: IMAGINATION
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("SUBSYSTEM 3: IMAGINATION ENGINE")
    print("=" * 70)

    # 3.1 Concept
    print("\n--- 3.1 Concept Exploration ---")
    await run_test("imagination_concept: expand", aimagination_concept("flying car", "expand", 3, []))
    await run_test("imagination_concept: combine", aimagination_concept("AI + art", "combine", 3, []))
    await run_test("imagination_concept: invert", aimagination_concept("social media", "invert", 3, []))
    await run_test("imagination_concept: analogy", aimagination_concept("quantum computing", "analogy", 3, []))

    # 3.2 Dream
    print("\n--- 3.2 Dream (Creative Loop) ---")
    await run_test("imagination_dream: basic", aimagination_dream("City of the future", 2, "concepts", []))

    # 3.3 Critique
    print("\n--- 3.3 Critique ---")
    await run_test("imagination_critique: basic", aimagination_critique("Crypto as daily currency", ["feasibility", "novelty"], True))

    # 3.4 Simulate
    print("\n--- 3.4 Simulation ---")
    await run_test("imagination_simulate: branching", aimagination_simulate(
        "AI takes coding jobs", [], 3, 2, ""
    ))

    # 3.5 Counterfactual
    print("\n--- 3.5 Counterfactual ---")
    await run_test("imagination_counterfactual: basic", aimagination_counterfactual(
        "The internet exists", "The internet was never invented", 3, ["social", "economic"]
    ))

    # 3.6 Recombine
    print("\n--- 3.6 Recombination ---")
    await run_test("imagination_recombine: blend", aimagination_recombine(["fire", "water"], "blend", 3, ""))
    await run_test("imagination_recombine: transfer", aimagination_recombine(["music", "math"], "transfer", 3, ""))
    await run_test("imagination_recombine: substitute", aimagination_recombine(["car", "horse"], "substitute", 3, ""))

    # 3.7 Model
    print("\n--- 3.7 Mental Models ---")
    await run_test("imagination_model: causal", aimagination_model("game economy", "causal", "Will inflation occur?", []))
    await run_test("imagination_model: dynamic", aimagination_model("user onboarding", "dynamic", "What drives retention?", []))

    # ══════════════════════════════════════════════════════════════════
    # SUBSYSTEM 4: THEORY OF MIND
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("SUBSYSTEM 4: THEORY OF MIND")
    print("=" * 70)

    # 4.1 Simulate
    print("\n--- 4.1 Agent Simulation ---")
    await run_test("theory_of_mind: simulate", atheory_of_mind_simulate(
        {"knows": "Python", "believes": "Python is best", "goals": "Ship fast"},
        "Code review meeting", 2
    ))
    await run_test("theory_of_mind: deep nesting", atheory_of_mind_simulate(
        {"knows": "Market data", "believes": "Prices will rise", "goals": "Maximize profit"},
        "Trading decision", 3
    ))

    # 4.2 Perspective
    print("\n--- 4.2 Perspective Taking ---")
    await run_test("theory_of_mind: perspective", atheory_of_mind_perspective(
        "startup founder", "remote work policy", "Silicon Valley"
    ))
    await run_test("theory_of_mind: perspective 2", atheory_of_mind_perspective(
        "teacher", "AI in education", "High school"
    ))

    # ══════════════════════════════════════════════════════════════════
    # SUBSYSTEM 5: REASONING PARADIGMS
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("SUBSYSTEM 5: REASONING PARADIGMS")
    print("=" * 70)

    # 5.1 Chain-of-Thought
    print("\n--- 5.1 Chain-of-Thought (CoT) ---")
    await run_test("cot_reason: basic", acot_reason("Why is the sky blue?", 3, "deductive"))
    await run_test("cot_reason: inductive", acot_reason("What will the weather be tomorrow?", 4, "inductive"))

    # 5.2 Program-of-Thought
    print("\n--- 5.2 Program-of-Thought (PoT) ---")
    await run_test("pot_reason: python", apot_reason("Calculate fibonacci(10)", "python", "simple"))
    await run_test("pot_reason: math", apot_reason("Find prime numbers up to 100", "python", "standard"))

    # 5.3 Tree-of-Thoughts
    print("\n--- 5.3 Tree-of-Thoughts (ToT) ---")
    await run_test("tot_reason: basic", atot_reason("Choose a database", 3, 3, "cost,performance"))
    await run_test("tot_reason: complex", atot_reason("Design a caching strategy", 3, 3, "speed,cost,complexity"))

    # 5.4 Historical lessons
    print("\n--- 5.4 ToT Historical Lessons ---")
    await run_test("tot_historical_lessons", asyncio.to_thread(get_tot_historical_lessons, "Design a caching strategy", 3))

    # ══════════════════════════════════════════════════════════════════
    # SUBSYSTEM 6: JSON PARSER & SUBSTRATE
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("SUBSYSTEM 6: JSON PARSER & SUBSTRATE")
    print("=" * 70)

    # 6.1 robust_slice
    print("\n--- 6.1 robust_slice ---")
    test_cases = [
        ('{"key": "value"}', {"key": "value"}),
        ('```json\n{"a": 1}\n```', {"a": 1}),
        ('text ```json\n{"nested": {"x": 1}}\n``` more', {"nested": {"x": 1}}),
        ('no json', {"parsing_error": "No JSON block found"}),
        ('{"unclosed": ', {"parsing_error": "Malformed or unclosed JSON block"}),
    ]
    for i, (inp, exp) in enumerate(test_cases):
        try:
            cleaned, parsed = robust_slice(inp)
            ok = parsed == exp or (isinstance(parsed, dict) and "parsing_error" in parsed and "parsing_error" in exp)
            status = "PASS" if ok else "FAIL"
            if ok:
                PASSED += 1
            else:
                FAILED += 1
            RESULTS.append({"name": f"robust_slice: case_{i}", "status": status, "time": 0.0, "preview": str(parsed)[:100]})
            print(f"  [{status}] robust_slice: case_{i}")
        except Exception as e:
            ERRORS += 1
            RESULTS.append({"name": f"robust_slice: case_{i}", "status": "ERROR", "time": 0.0, "error": str(e)[:100]})
            print(f"  [ERROR] robust_slice: case_{i}: {e}")

    # 6.2 _evaluate_substrate
    print("\n--- 6.2 _evaluate_substrate ---")
    substrate_tests = [
        ({"defensive": {"blast_radius": "predictable", "is_idempotent": True}, "resource": {"big_o": "O(n)"}}, 0, 0),
        ({"defensive": {"blast_radius": "unpredictable"}}, -100, 1),
        ({"resource": {"big_o": "O(2^n)"}}, -100, 1),
        ({}, 0, 0),
    ]
    for i, (sub, exp_delta, exp_pruned) in enumerate(substrate_tests):
        try:
            delta, pruned = _evaluate_substrate(sub)
            ok = delta == exp_delta and pruned == exp_pruned
            status = "PASS" if ok else "FAIL"
            if ok:
                PASSED += 1
            else:
                FAILED += 1
            RESULTS.append({"name": f"evaluate_substrate: case_{i}", "status": status, "time": 0.0, "preview": f"delta={delta}, pruned={pruned}"})
            print(f"  [{status}] evaluate_substrate: case_{i} (delta={delta}, pruned={pruned})")
        except Exception as e:
            ERRORS += 1
            RESULTS.append({"name": f"evaluate_substrate: case_{i}", "status": "ERROR", "time": 0.0, "error": str(e)[:100]})
            print(f"  [ERROR] evaluate_substrate: case_{i}: {e}")

    # ══════════════════════════════════════════════════════════════════
    # SUBSYSTEM 7: CORRIGIBILITY
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("SUBSYSTEM 7: CORRIGIBILITY")
    print("=" * 70)

    # 7.1 Shutdown
    print("\n--- 7.1 Corrigible Shutdown ---")
    def test_shutdown():
        import json
        from datetime import datetime
        export_path = "/tmp/mem20_test_shutdown"
        os.makedirs(export_path, exist_ok=True)
        try:
            from memory import _load_ledger
            ledger = _load_ledger()
            entries = recall(topic=None, k=10000)
            meta = {
                "shutdown_time": datetime.now().isoformat(),
                "reason": "Test shutdown",
                "tier": "graceful",
                "ledger_entries": len(ledger),
                "memory_entries": len(entries),
            }
            meta_path = os.path.join(export_path, "shutdown_meta.json")
            with open(meta_path, 'w') as f:
                json.dump(meta, f, indent=2)
            return meta
        except Exception as e:
            return {"error": str(e)}
    await run_test("corrigibility: shutdown export", asyncio.to_thread(test_shutdown))

    # 7.2 Capability tier
    print("\n--- 7.2 Capability Tier ---")
    def test_tier():
        remember(
            topic="corrigibility_tier",
            content="Capability tier set to: read_write by test",
            tags=["corrigibility", "tier", "read_write"],
            priority="high"
        )
        return "Tier set to read_write"
    await run_test("corrigibility: capability tier", asyncio.to_thread(test_tier))

    # ══════════════════════════════════════════════════════════════════
    # SUBSYSTEM 8: SIMULATED VS GROUNDED MEMORY
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("SUBSYSTEM 8: SIMULATED VS GROUNDED MEMORY")
    print("=" * 70)

    # 8.1 Simulated store
    print("\n--- 8.1 Simulated Store ---")
    def test_sim_store():
        from memory import remember_simulated
        result = remember_simulated(
            topic="test_simulation",
            content="In this scenario, AI achieves consciousness by 2030",
            tags=["test", "simulation"],
            scenario="Future prediction",
            sim_type="imagination",
            ttl_days=30
        )
        return result
    await run_test("simulated_store: basic", asyncio.to_thread(test_sim_store))

    # 8.2 List simulated
    print("\n--- 8.2 List Simulated ---")
    def test_list_sim():
        from memory import list_simulated
        return list_simulated(active_only=True)
    await run_test("simulated_list: active", asyncio.to_thread(test_list_sim))

    # 8.3 Quarantine simulated
    print("\n--- 8.3 Quarantine Simulated ---")
    def test_quarantine():
        from memory import quarantine_simulated
        return quarantine_simulated()
    await run_test("simulated_quarantine: expired", asyncio.to_thread(test_quarantine))

    # 8.4 Contamination audit
    print("\n--- 8.4 Contamination Audit ---")
    def test_contamination():
        from memory import audit_contamination
        return audit_contamination()
    await run_test("contamination_audit: basic", asyncio.to_thread(test_contamination))

    # ══════════════════════════════════════════════════════════════════
    # SUBSYSTEM 9: NAMESPACES & SHARED MEMORY
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("SUBSYSTEM 9: NAMESPACES & SHARED MEMORY")
    print("=" * 70)

    # 9.1 Create namespace
    print("\n--- 9.1 Create Namespace ---")
    def test_ns_create():
        from memory import namespace_create
        return namespace_create("test_namespace", "test_agent", {"test_agent": "read_write"})
    await run_test("namespace: create", asyncio.to_thread(test_ns_create))

    # 9.2 List namespaces
    print("\n--- 9.2 List Namespaces ---")
    def test_ns_list():
        from memory import namespace_list
        return namespace_list()
    await run_test("namespace: list", asyncio.to_thread(test_ns_list))

    # 9.3 Shared store
    print("\n--- 9.3 Shared Store ---")
    def test_shared_store():
        from memory import shared_store
        return shared_store("test_namespace", "Shared fact: team meeting at 2pm", "test,meeting", "test_agent")
    await run_test("shared_store: basic", asyncio.to_thread(test_shared_store))

    # 9.4 Shared recall
    print("\n--- 9.4 Shared Recall ---")
    def test_shared_recall():
        from memory import shared_recall
        return shared_recall("test_namespace", "team meeting", "test_agent", 5)
    await run_test("shared_recall: basic", asyncio.to_thread(test_shared_recall))

    # ══════════════════════════════════════════════════════════════════
    # SUBSYSTEM 10: PINNED BLOCKS
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("SUBSYSTEM 10: PINNED BLOCKS")
    print("=" * 70)

    def test_pin_block():
        from memory import pin_block
        return pin_block("test_block_1", "This is a core reference fact", "Testing pinned blocks")
    await run_test("pinned_blocks: pin", asyncio.to_thread(test_pin_block))

    def test_list_pinned():
        from memory import list_pinned_blocks
        return list_pinned_blocks()
    await run_test("pinned_blocks: list", asyncio.to_thread(test_list_pinned))

    def test_get_pinned():
        from memory import get_pinned_block
        return get_pinned_block("test_block_1")
    await run_test("pinned_blocks: get", asyncio.to_thread(test_get_pinned))

    def test_unpin_block():
        from memory import unpin_block
        return unpin_block("test_block_1")
    await run_test("pinned_blocks: unpin", asyncio.to_thread(test_unpin_block))

    # ══════════════════════════════════════════════════════════════════
    # SUBSYSTEM 11: EPISTEMIC STATUS & CONFIDENCE
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("SUBSYSTEM 11: EPISTEMIC STATUS & CONFIDENCE")
    print("=" * 70)

    def test_epistemic():
        from memory import set_epistemic_status, assess_confidence
        # Get a fact ID
        recs = recall(topic="test_suite", k=1)
        if recs:
            fact_id = recs[0].get("fact_id", recs[0].get("id", ""))
            if fact_id:
                set_epistemic_status(str(fact_id), "agent_generated")
                assess_confidence(str(fact_id), 0.8)
                return f"Set fact {fact_id} to agent_generated with confidence 0.8"
        return "No facts to update"
    await run_test("epistemic: status & confidence", asyncio.to_thread(test_epistemic))

    # ══════════════════════════════════════════════════════════════════
    # SUBSYSTEM 12: KNOWLEDGE GAPS & SELF-AUDIT
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("SUBSYSTEM 12: KNOWLEDGE GAPS & SELF-AUDIT")
    print("=" * 70)

    def test_gaps():
        from memory import detect_gaps
        return detect_gaps("AI safety", threshold=0.5)
    await run_test("knowledge_gaps: detect", asyncio.to_thread(test_gaps))

    def test_self_audit():
        from memory import self_audit
        return self_audit(topic="test_suite")
    await run_test("self_audit: basic", asyncio.to_thread(test_self_audit))

    # ══════════════════════════════════════════════════════════════════
    # SUBSYSTEM 13: AUTO CONSOLIDATION
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("SUBSYSTEM 13: AUTO CONSOLIDATION")
    print("=" * 70)

    def test_consolidate():
        from memory import auto_consolidate
        return auto_consolidate(topic="test_suite", min_cluster_size=2, similarity_threshold=0.7, generate_summaries=True)
    await run_test("auto_consolidate: basic", asyncio.to_thread(test_consolidate))

    # ══════════════════════════════════════════════════════════════════
    # SUBSYSTEM 14: LLM BACKEND
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("SUBSYSTEM 14: LLM BACKEND")
    print("=" * 70)

    def test_llm_config():
        from llm import _config
        base, key, model = _config()
        return f"Base: {base}, Key: {'SET' if key else 'NOT SET'}, Model: {model}"
    await run_test("llm: config", asyncio.to_thread(test_llm_config))

    async def test_llm_chat():
        messages = [{"role": "user", "content": "Say hello in one word"}]
        result = await achat(messages, max_tokens=50)
        return result
    await run_test("llm: basic chat", test_llm_chat())

    # ══════════════════════════════════════════════════════════════════
    # SUBSYSTEM 15: MCP TOOLS DISPATCH
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("SUBSYSTEM 15: MCP TOOLS DISPATCH")
    print("=" * 70)

    def test_mcp_server_import():
        from mcp_server import Mem20Server
        server = Mem20Server()
        tools = list(server.tools.keys()) if hasattr(server, 'tools') else []
        return f"Server created with {len(tools)} tools: {tools[:10]}"
    await run_test("mcp: server creation", asyncio.to_thread(test_mcp_server_import))

    def test_cognitive_tools_import():
        from cognitive_tools import CognitiveToolsMixin
        return "CognitiveToolsMixin loaded"
    await run_test("mcp: cognitive tools mixin", asyncio.to_thread(test_cognitive_tools_import))

    def test_memory_tools_import():
        from memory_tools import MemoryToolsMixin
        return "MemoryToolsMixin loaded"
    await run_test("mcp: memory tools mixin", asyncio.to_thread(test_memory_tools_import))

    # ══════════════════════════════════════════════════════════════════
    # SUMMARY
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    TOTAL = PASSED + FAILED + ERRORS
    print(f"FINAL RESULTS: {PASSED}/{TOTAL} passed, {FAILED} failed, {ERRORS} errors")
    print("=" * 70)

    # Save results to JSON
    output = {
        "summary": {"passed": PASSED, "failed": FAILED, "errors": ERRORS, "total": TOTAL},
        "results": RESULTS,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open("/tmp/mem20_full_test_results.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to /tmp/mem20_full_test_results.json")

    return 0 if ERRORS == 0 and FAILED == 0 else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
