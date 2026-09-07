#!/usr/bin/env python3
"""
COMPREHENSIVE MEM20 TEST SUITE
Runs through mem20's native cognitive engine.
Tests ALL systems: legacy + new.
"""

import sys
import os
from pathlib import Path

# Setup paths
ROOT = Path("/home/jayson/mem20")
sys.path.insert(0, str(ROOT / "cog"))
sys.path.insert(0, str(ROOT / "mcp"))
sys.path.insert(0, str(ROOT / "mcp" / "tools"))

import asyncio
import json
import time

# ── Imports ────────────────────────────────────────────────────────────

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

def run_test(name, coro):
    """Run an async test and record results."""
    global PASSED, FAILED
    start = time.time()
    try:
        result = asyncio.run(coro)
        elapsed = time.time() - start
        ok = result is not None and (not isinstance(result, str) or len(result.strip()) > 0)
        status = "PASS" if ok else "FAIL"
        if ok:
            PASSED += 1
        else:
            FAILED += 1
        RESULTS.append({"name": name, "status": status, "time": round(elapsed, 2), "preview": str(result)[:150]})
        print(f"  [{status}] {name} ({elapsed:.2f}s)")
    except Exception as e:
        elapsed = time.time() - start
        FAILED += 1
        RESULTS.append({"name": name, "status": "ERROR", "time": round(elapsed, 2), "error": str(e)[:100]})
        print(f"  [ERROR] {name}: {str(e)[:80]}")

# ── Tests ──────────────────────────────────────────────────────────────

def main():
    global PASSED, FAILED
    print("=" * 60)
    print("MEM20 COMPREHENSIVE TEST SUITE")
    print("=" * 60)

    print("\n--- Core Cognition ---")
    run_test("aprocess_thought", aprocess_thought("Test thought", "analyze", ""))
    run_test("arun_chain", arun_chain(["step1", "step2"], ""))
    run_test("areason (deductive)", areason("What is 2+2?", "deductive", 3))
    run_test("areason (inductive)", areason("Patterns in prime numbers", "inductive", 3))
    run_test("aplan (medium)", aplan("Build a web scraper", "medium", [], [], True))
    run_test("areflect", areflect("I tried X", "It failed", "learning_extraction"))
    run_test("aworking_memory", aworking_memory("store", ["a", "b"], "", 7))

    print("\n--- Imagination ---")
    run_test("aimagination_concept", aimagination_concept("flying car", "expand", 3, []))
    run_test("aimagination_counterfactual", aimagination_counterfactual("No internet", "Internet never existed", 3, ["social"]))
    run_test("aimagination_recombine", aimagination_recombine(["fire", "water"], "blend", 3, ""))
    run_test("aimagination_model", aimagination_model("game economy", "causal", "Will inflation occur?", []))
    run_test("aimagination_critique", aimagination_critique("Crypto as daily currency", ["feasibility"], True))
    run_test("aimagination_simulate", aimagination_simulate("AI takes coding jobs", [], 3, 2, ""))
    run_test("aimagination_dream", aimagination_dream("City of the future", 2, "concepts", []))

    print("\n--- Theory of Mind ---")
    run_test("theory_of_mind_simulate", atheory_of_mind_simulate(
        {"knows": "Python", "believes": "Python is best", "goals": "Code"},
        "Code review", 2))
    run_test("theory_of_mind_perspective", atheory_of_mind_perspective(
        "developer", "remote work", "Startup"))

    print("\n--- Reasoning Paradigms ---")
    run_test("acot_reason", acot_reason("Why is the sky blue?", 3, "deductive"))
    run_test("apot_reason", apot_reason("Calculate fibonacci(10)", "python", "simple"))
    run_test("atot_reason", atot_reason("Choose a database", 3, 3, "cost,performance"))

    print("\n--- JSON Parser ---")
    # Test parser directly
    parser_tests = [
        ('{"key": "value"}', {"key": "value"}),
        ('```json\n{"a": 1}\n```', {"a": 1}),
        ('text ```json\n{"nested": {"x": 1}}\n``` more', {"nested": {"x": 1}}),
        ('no json', {}),
    ]
    for i, (inp, exp) in enumerate(parser_tests):
        try:
            cleaned, parsed = robust_slice(inp)
            ok = parsed == exp or (not exp and "parsing_error" in parsed)
            status = "PASS" if ok else "FAIL"
            if ok:
                PASSED += 1
            else:
                FAILED += 1
            print(f"  [{status}] parser_case_{i}")
        except Exception as e:
            FAILED += 1
            print(f"  [ERROR] parser_case_{i}: {e}")

    print("\n--- Substrate Evaluation ---")
    sub_tests = [
        ({"defensive": {"blast_radius": "predictable", "is_idempotent": True}, "resource": {"big_o": "O(n)"}}, 0, 0),
        ({"defensive": {"blast_radius": "unpredictable"}}, -100, 1),
        ({"resource": {"big_o": "O(2^n)"}}, -100, 1),
        ({}, 0, 0),
    ]
    for i, (sub, exp_delta, exp_pruned) in enumerate(sub_tests):
        try:
            delta, pruned = _evaluate_substrate(sub)
            ok = delta == exp_delta and pruned == exp_pruned
            status = "PASS" if ok else "FAIL"
            if ok:
                PASSED += 1
            else:
                FAILED += 1
            print(f"  [{status}] substrate_case_{i} (delta={delta}, pruned={pruned})")
        except Exception as e:
            FAILED += 1
            print(f"  [ERROR] substrate_case_{i}: {e}")

    print("\n--- Cross-Session Learning ---")
    run_test("first_run", atot_reason("Design a caching strategy", 2, 2, "speed,cost"))
    lessons = get_tot_historical_lessons("Design a caching strategy", 3)
    print(f"  [INFO] Historical lessons found: {len(lessons)}")
    run_test("second_run", atot_reason("Design a caching strategy", 2, 2, "speed,cost"))

    print("\n" + "=" * 60)
    TOTAL = PASSED + FAILED
    print(f"RESULTS: {PASSED}/{TOTAL} passed, {FAILED} failed")
    print("=" * 60)

    return 0 if FAILED == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
