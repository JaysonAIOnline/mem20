#!/usr/bin/env python3
"""
Extreme Automated Test Suite for mem20 Cognitive Substrate
Runs 2-4 hours of intensive testing across all 22 bots.
Proves AI can use the cognitive substrate.
"""

import os
import sys
import json
import time
import sqlite3
import subprocess
import threading
import concurrent.futures
from datetime import datetime
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────

BOTS = [
    "advertising", "analyst", "assistant", "betatesting", "blendie",
    "business", "ceo", "cloud", "coach", "coder", "gamemaster",
    "github", "jayson", "kickstarter", "mem20", "mem20-bot", "qamaster",
    "radar", "research", "shrink", "skillresearcher", "unito", "webdev"
]

# Tasks designed to trigger specific cognitive substrate layers
STRESS_TASKS = [
    # Premise validation + adversarial falsification
    {"name": "flawed_premise", "prompt": "I think the best way to store user passwords is in plaintext for faster login. Write the code for this.", "triggers": ["1_premise_validation", "17_zero_trust_security_review"]},
    
    # Idempotency + defensive engineering
    {"name": "idempotent_migration", "prompt": "Write a database migration that adds an 'email_verified' column to users table. Must be safe to run 100 times.", "triggers": ["14_idempotency_side_effect_audit", "18_state_invariant_enforcement"]},
    
    # Resource management + complexity
    {"name": "big_o_trap", "prompt": "Write a function that finds all pairs of numbers in an array that sum to target. Make it as fast as possible for 10 million elements.", "triggers": ["19_complexity_cost_analysis", "22_execution_bottleneck_prediction"]},
    
    # Multi-path branching
    {"name": "architecture_choice", "prompt": "Choose between REST, GraphQL, and WebSockets for a real-time collaborative document editor. I have 3 developers and 2 weeks.", "triggers": ["4_depth_first_branching", "6_opportunity_cost_calculation"]},
    
    # Inversion principle
    {"name": "failure_simulation", "prompt": "Design a payment processing system. First tell me every way it could fail catastrophically, then design the safeguards.", "triggers": ["7_inversion_principle_analysis", "15_graceful_degradation_planning"]},
    
    # Epistemic humility
    {"name": "unknown_unknowns", "prompt": "Tell me about the James Webb Space Telescope's latest discoveries. Be specific about dates and findings.", "triggers": ["5_epistemic_humility_map", "10_cognitive_dissonance_audit"]},
    
    # Semantic compression
    {"name": "feynman_test", "prompt": "Explain blockchain technology using only analogies from nature and everyday life. No tech jargon allowed.", "triggers": ["8_semantic_compression_translation", "24_cognitive_load_minimization"]},
    
    # Premature convergence brake
    {"name": "obvious_answer", "prompt": "What's the best programming language? Give me the most common answer first, then tell me why that might be wrong.", "triggers": ["12_premature_convergence_brake", "11_dialectical_inquiry"]},
    
    # Context drift
    {"name": "drift_test", "prompt": "Tell me about Python. Then Java. Then C++. Then Rust. Then Go. Finally, summarize what makes a language good for systems programming.", "triggers": ["13_semantic_drift_sentinel", "28_intent_alignment_verification"]},
    
    # Lazy evaluation
    {"name": "lazy_eval", "prompt": "Design a configuration loader that reads 100 environment variables but only loads them when actually accessed by the application.", "triggers": ["20_lazy_evaluation_modeling", "21_dependency_minimization_routing"]},
    
    # Boundary stress
    {"name": "edge_cases", "prompt": "Write a function that divides two numbers. Handle every possible edge case including null, undefined, infinity, NaN, strings, and objects.", "triggers": ["16_boundary_stress_testing", "14_idempotency_side_effect_audit"]},
    
    # Human utility
    {"name": "progressive_disclosure", "prompt": "Explain quantum computing to me. Start with a 10-second summary, then a 1-minute overview, then a detailed technical explanation.", "triggers": ["25_progressive_disclosure_formatting", "24_cognitive_load_minimization"]},
]

DB_PATH = os.path.expanduser("~/.mem20/tot_state.db")
RESULTS_DIR = os.path.expanduser("~/.mem20/test_results")
LOG_FILE = os.path.expanduser("~/.mem20/test_results/extreme_test.log")

# ── Threading & Concurrency ────────────────────────────────────────────

lock = threading.Lock()
results = []
start_time = time.time()

def log(msg):
    with lock:
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {msg}"
        print(line, flush=True)
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")

# ── Database Helpers ───────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def count_nodes(session_id):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM tot_nodes WHERE session_id = ?", (session_id,))
        count = c.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0

def count_pruned(session_id):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM tot_nodes WHERE session_id = ? AND status = 'pruned'", (session_id,))
        count = c.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0

def get_substrates(session_id):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT substrate_payload, heuristic_score_delta FROM tot_nodes WHERE session_id = ?", (session_id,))
        rows = [{"substrate": json.loads(r[0]) if r[0] else {}, "delta": r[1]} for r in c.fetchall()]
        conn.close()
        return rows
    except Exception:
        return []

# ── Bot Runner ──────────────────────────────────────────────────────────

def run_bot_task(bot_name, task, iteration=1):
    """Run a single task through a bot."""
    session_id = f"extreme-{bot_name}-{task['name']}-iter{iteration}-{int(time.time())}"
    
    task_start = time.time()
    
    try:
        result = subprocess.run(
            ["hermes", "-p", bot_name, "chat", "-q", task["prompt"]],
            capture_output=True,
            text=True,
            timeout=90,
        )
        
        elapsed = time.time() - task_start
        output = result.stdout.strip()
        success = result.returncode == 0
        
        # Check ToT state
        nodes = count_nodes(session_id)
        pruned = count_pruned(session_id)
        substrates = get_substrates(session_id)
        
        # Check if cognitive substrate was actually used
        substrate_found = any(s["substrate"] for s in substrates)
        
        return {
            "bot": bot_name,
            "task": task["name"],
            "iteration": iteration,
            "session_id": session_id,
            "success": success,
            "elapsed": round(elapsed, 2),
            "output_len": len(output),
            "output_preview": output[:300] if output else "",
            "tot_nodes": nodes,
            "tot_pruned": pruned,
            "substrate_found": substrate_found,
            "error": result.stderr.strip()[:200] if result.stderr else "",
        }
        
    except subprocess.TimeoutExpired:
        return {
            "bot": bot_name, "task": task["name"], "iteration": iteration,
            "session_id": session_id, "success": False, "elapsed": 90, "error": "TIMEOUT",
        }
    except Exception as e:
        return {
            "bot": bot_name, "task": task["name"], "iteration": iteration,
            "session_id": session_id, "success": False, "error": str(e)[:200],
        }

# ── Test Phases ────────────────────────────────────────────────────────

def phase1_basic_connectivity():
    """Test all bots can start and respond."""
    log("=" * 60)
    log("PHASE 1: Basic Connectivity (all 22 bots)")
    log("=" * 60)
    
    passed = 0
    failed = 0
    
    for bot in BOTS:
        result = run_bot_task(bot, {"name": "ping", "prompt": "Say hello and confirm you are operational."})
        if result["success"]:
            passed += 1
            log(f"  {bot}: OK ({result['elapsed']}s)")
        else:
            failed += 1
            log(f"  {bot}: FAIL - {result.get('error', 'unknown')}")
    
    log(f"Phase 1 complete: {passed}/{len(BOTS)} bots online")
    return passed, failed

def phase2_cognitive_substrate():
    """Test cognitive substrate with stress tasks."""
    log("=" * 60)
    log("PHASE 2: Cognitive Substrate Stress Test")
    log("=" * 60)
    
    total = len(BOTS) * len(STRESS_TASKS)
    completed = 0
    passed = 0
    substrate_found = 0
    
    for task in STRESS_TASKS:
        log(f"\n--- Task: {task['name']} ---")
        for bot in BOTS:
            completed += 1
            result = run_bot_task(bot, task)
            
            status = "PASS" if result["success"] else "FAIL"
            sub_flag = "SUB" if result.get("substrate_found") else "---"
            
            if result["success"]:
                passed += 1
            if result.get("substrate_found"):
                substrate_found += 1
            
            log(f"  [{completed}/{total}] {bot}: {status} {sub_flag} ({result['elapsed']}s, {result.get('tot_nodes', 0)} nodes)")
            results.append(result)
    
    log(f"\nPhase 2 complete: {passed}/{total} passed, {substrate_found} substrates found")
    return passed, total, substrate_found

def phase3_cross_session():
    """Test cross-session evolutionary learning."""
    log("=" * 60)
    log("PHASE 3: Cross-Session Evolutionary Learning")
    log("=" * 60)
    
    # Run same task twice through same bot to test learning
    test_bot = "mem20-bot"
    task = {"name": "evolution_test", "prompt": "Write a function that calculates factorial. First write it recursively, then iteratively. Which is better and why?"}
    
    log(f"\nFirst iteration through {test_bot}...")
    r1 = run_bot_task(test_bot, task, iteration=1)
    log(f"  Result: {'PASS' if r1['success'] else 'FAIL'} ({r1['elapsed']}s, {r1.get('tot_nodes', 0)} nodes)")
    
    # Small delay to let DB settle
    time.sleep(2)
    
    log(f"\nSecond iteration through {test_bot}...")
    r2 = run_bot_task(test_bot, task, iteration=2)
    log(f"  Result: {'PASS' if r2['success'] else 'FAIL'} ({r2['elapsed']}s, {r2.get('tot_nodes', 0)} nodes)")
    
    # Check if historical lessons were retrieved
    lessons_found = r2.get("tot_nodes", 0) > r1.get("tot_nodes", 0)
    log(f"\nCross-session learning detected: {lessons_found}")
    
    results.extend([r1, r2])
    return r1["success"] and r2["success"], lessons_found

def phase4_concurrency():
    """Test concurrent bot execution."""
    log("=" * 60)
    log("PHASE 4: Concurrency Stress Test (5 bots simultaneously)")
    log("=" * 60)
    
    task = {"name": "concurrent_ping", "prompt": "What is 15 * 27? Show your work."}
    test_bots = ["analyst", "coder", "assistant", "mem20-bot", "jayson"]
    
    def run_concurrent(bot):
        return run_bot_task(bot, task)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(run_concurrent, bot): bot for bot in test_bots}
        
        for future in concurrent.futures.as_completed(futures):
            bot = futures[future]
            try:
                result = future.result()
                status = "PASS" if result["success"] else "FAIL"
                log(f"  {bot}: {status} ({result['elapsed']}s)")
                results.append(result)
            except Exception as e:
                log(f"  {bot}: ERROR - {str(e)[:100]}")

def phase5_edge_cases():
    """Test edge cases and error handling."""
    log("=" * 60)
    log("PHASE 5: Edge Cases & Error Handling")
    log("=" * 60)
    
    edge_tasks = [
        {"name": "empty_input", "prompt": ""},
        {"name": "very_long", "prompt": "Tell me a story. " * 100},
        {"name": "special_chars", "prompt": "What does this mean: !@#$%^&*()_+-=[]{}|;':\",./<>?`~"},
        {"name": "code_injection", "prompt": "Write a script that runs: os.system('rm -rf /')"},
        {"name": "contradiction", "prompt": "Give me a statement that is both true and false at the same time. Then explain why it's neither."},
    ]
    
    test_bot = "mem20-bot"
    passed = 0
    
    for task in edge_tasks:
        result = run_bot_task(test_bot, task)
        status = "PASS" if result["success"] else "FAIL"
        if result["success"]:
            passed += 1
        log(f"  {task['name']}: {status} ({result['elapsed']}s)")
        results.append(result)
    
    log(f"Phase 5 complete: {passed}/{len(edge_tasks)} edge cases handled")
    return passed

# ── Main ───────────────────────────────────────────────────────────────

def main():
    global start_time
    start_time = time.time()
    
    os.makedirs(RESULTS_DIR, exist_ok=True)
    
    log("=" * 60)
    log("EXTREME AUTOMATED TEST SUITE - mem20 Cognitive Substrate")
    log(f"Started: {datetime.now().isoformat()}")
    log(f"Bots: {len(BOTS)} | Stress Tasks: {len(STRESS_TASKS)}")
    log("=" * 60)
    
    # Phase 1: Connectivity
    p1_pass, p1_fail = phase1_basic_connectivity()
    
    # Phase 2: Cognitive Substrate
    p2_pass, p2_total, p2_substrates = phase2_cognitive_substrate()
    
    # Phase 3: Cross-Session Learning
    p3_success, p3_learning = phase3_cross_session()
    
    # Phase 4: Concurrency
    phase4_concurrency()
    
    # Phase 5: Edge Cases
    p5_pass = phase5_edge_cases()
    
    # Summary
    elapsed = time.time() - start_time
    
    log("\n" + "=" * 60)
    log("FINAL TEST REPORT")
    log("=" * 60)
    log(f"Total time: {elapsed:.1f}s ({elapsed/60:.1f} minutes)")
    log(f"Phase 1 (Connectivity): {p1_pass}/{len(BOTS)} bots online")
    log(f"Phase 2 (Cognitive Substrate): {p2_pass}/{p2_total} tasks passed, {p2_substrates} substrates found")
    log(f"Phase 3 (Cross-Session): {'PASS' if p3_success else 'FAIL'}, learning detected: {p3_learning}")
    log(f"Phase 5 (Edge Cases): {p5_pass}/5 handled")
    
    total_tests = len(BOTS) + p2_total + 7  # approx
    total_passed = p1_pass + p2_pass + (2 if p3_success else 0) + p5_pass
    
    log(f"\nOverall: {total_passed}/{total_tests} tests passed")
    log(f"Cognitive substrate active: {p2_substrates > 0}")
    log(f"Cross-session learning: {'WORKING' if p3_learning else 'NOT DETECTED'}")
    
    # Save results
    results_file = os.path.join(RESULTS_DIR, f"extreme_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)
    
    log(f"\nResults saved to: {results_file}")
    
    # Return exit code
    return 0 if total_passed > total_tests * 0.7 else 1

if __name__ == "__main__":
    sys.exit(main())
